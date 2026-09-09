# Observabilidade da rede: VPC Flow Logs e access logs do ALB.
#
# O log de aplicacao responde "o que a API fez com a requisicao". Ele nao
# responde "a conexao chegou?", e essa e exatamente a pergunta que aparece
# quando alguem erra um security group: a requisicao some sem deixar rastro em
# lugar nenhum, porque nunca chegou ao processo que sabe logar.
#
# Sao tres fontes, em tres niveis, e a utilidade esta em cruzar as tres:
#
#   VPC Flow Logs     -> pacote aceito ou rejeitado, por par origem/destino
#   Access log do ALB -> codigo de resposta e tempo do backend, por requisicao
#   Log da aplicacao  -> o que a rota fez, com X-Request-Id
#
# Uma requisicao que aparece no flow log e nao no access log morreu no security
# group do ALB. Uma que aparece no access log com 502 e nao no log da aplicacao
# morreu antes do gunicorn. O fio que costura as duas ultimas e o X-Request-Id,
# que o ALB propaga e que common/observabilidade ja emite em toda resposta.

locals {
  # Bucket dos flow logs: o informado em `flow_logs_bucket_name`, ou o que este
  # arquivo cria. A indirecao existe por causa da SCP do AWS Academy -- ver o
  # comentario da variavel.
  flow_logs_bucket = (
    !var.create_network || var.flow_logs_destination != "s3" ? "" :
    var.flow_logs_bucket_name != "" ? var.flow_logs_bucket_name :
    aws_s3_bucket.flow_logs[0].bucket
  )
  flow_logs_bucket_arn = (
    local.flow_logs_bucket != "" ? "arn:aws:s3:::${local.flow_logs_bucket}" : ""
  )

  alb_logs_bucket = (
    !var.create_network || !var.alb_access_logs_enabled ? "" :
    var.alb_logs_bucket_name != "" ? var.alb_logs_bucket_name :
    aws_s3_bucket.alb_logs[0].bucket
  )
  alb_logs_bucket_arn = (
    local.alb_logs_bucket != "" ? "arn:aws:s3:::${local.alb_logs_bucket}" : ""
  )
}

# --------------------------------------------------------------------------- #
# Flow Logs -- destino S3, o padrao
# --------------------------------------------------------------------------- #

# Os alarmes de observability.tf medem a APLICACAO: profundidade de fila, DLQ,
# CPU do banco, lag do simulador. Nenhum deles enxerga a rede. Flow Logs
# preenchem esse buraco: todo fluxo ACCEPT e REJECT nas interfaces da VPC, com
# origem, destino, porta e bytes. Na pratica e o que responde "a task esta mesmo
# saindo pelo NAT?" e "quem esta batendo na 5432 e sendo recusado?" sem
# instrumentar nada.
#
# O destino padrao e S3, e a razao e de ambiente e nao de gosto: o caminho do
# CloudWatch exige um papel que confie em `vpc-flow-logs.amazonaws.com`, e a
# LabRole nao confia (verificado na conta: 53 servicos na politica de confianca,
# esse nao esta entre eles). S3 usa politica de bucket, dispensa papel e custa
# menos por GB.
resource "aws_s3_bucket" "flow_logs" {
  count = var.create_network && var.flow_logs_destination == "s3" && var.flow_logs_bucket_name == "" ? 1 : 0

  bucket        = "${local.name}-flow-logs-${data.aws_caller_identity.current.account_id}"
  force_destroy = true

  tags = {
    Name = "${local.name}-flow-logs"
  }
}

resource "aws_s3_bucket_public_access_block" "flow_logs" {
  count = var.create_network && var.flow_logs_destination == "s3" ? 1 : 0

  bucket = local.flow_logs_bucket

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# AES256 e nao KMS: o servico de flow logs recusa entregar em bucket com SSE-KMS
# de chave gerenciada pelo cliente. Descobrir isso pelo silencio de um bucket
# que nunca recebe objeto custa uma sessao inteira de laboratorio.
resource "aws_s3_bucket_server_side_encryption_configuration" "flow_logs" {
  count = var.create_network && var.flow_logs_destination == "s3" ? 1 : 0

  bucket = local.flow_logs_bucket

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Log de rede cresce sem teto e ninguem consulta o de dois meses atras.
#
# A regra so existe se houver retencao definida: `log_retention_days = 0`
# significa "para sempre", e o S3 recusa uma expiracao de zero dias -- o apply
# falharia com um erro sobre o corpo da regra, longe da variavel que o causou.
resource "aws_s3_bucket_lifecycle_configuration" "flow_logs" {
  count = var.create_network && var.flow_logs_destination == "s3" && var.log_retention_days > 0 ? 1 : 0

  bucket = local.flow_logs_bucket

  rule {
    id     = "expirar-flow-logs"
    status = "Enabled"

    filter {}

    expiration {
      days = var.log_retention_days
    }
  }
}

# Sem esta politica o bucket existe e nunca recebe nada -- e a falha e
# silenciosa, sem erro no apply. As condicoes de `aws:SourceAccount` e
# `aws:SourceArn` sao o que impede o problema do "confused deputy": um terceiro
# nao consegue induzir o servico de log a escrever neste bucket.
data "aws_iam_policy_document" "flow_logs_bucket" {
  count = var.create_network && var.flow_logs_destination == "s3" ? 1 : 0

  statement {
    sid    = "AWSLogDeliveryWrite"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["delivery.logs.amazonaws.com"]
    }

    actions   = ["s3:PutObject"]
    resources = ["${local.flow_logs_bucket_arn}/AWSLogs/${data.aws_caller_identity.current.account_id}/*"]

    condition {
      test     = "StringEquals"
      variable = "s3:x-amz-acl"
      values   = ["bucket-owner-full-control"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:logs:${var.region}:${data.aws_caller_identity.current.account_id}:*"]
    }
  }

  statement {
    sid    = "AWSLogDeliveryAclCheck"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["delivery.logs.amazonaws.com"]
    }

    actions   = ["s3:GetBucketAcl"]
    resources = [local.flow_logs_bucket_arn]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:logs:${var.region}:${data.aws_caller_identity.current.account_id}:*"]
    }
  }
}

resource "aws_s3_bucket_policy" "flow_logs" {
  count = var.create_network && var.flow_logs_destination == "s3" ? 1 : 0

  bucket = local.flow_logs_bucket
  policy = data.aws_iam_policy_document.flow_logs_bucket[0].json

  # A politica nega escrita publica; o bloqueio precisa estar valendo antes.
  depends_on = [aws_s3_bucket_public_access_block.flow_logs]
}

# --------------------------------------------------------------------------- #
# Flow Logs -- destino CloudWatch Logs, o caminho alternativo
# --------------------------------------------------------------------------- #

# Vale numa conta normal: o Logs Insights consulta os registros com linguagem de
# consulta, sem baixar arquivo nenhum. No Learner Lab esbarra na LabRole.
resource "aws_cloudwatch_log_group" "vpc_flow" {
  count = var.create_network && var.flow_logs_destination == "cloudwatch" ? 1 : 0

  name              = "/aws/vpc/${local.name}/flow-logs"
  retention_in_days = var.log_retention_days

  tags = {
    Name = "${local.name}-flow-logs"
  }
}

# Mesmo padrao dos demais papeis do stack (ver locals.tf): quando
# `create_iam_roles = false`, tudo colapsa na role unica que o Learner Lab
# permite criar, porque o `voclabs` recusa `iam:CreateRole`. A diferenca, aqui,
# e que esse colapso NAO funciona -- e por isso que o destino padrao e S3.
data "aws_iam_policy_document" "flow_log_assume" {
  count = var.create_network && var.flow_logs_destination == "cloudwatch" && var.create_iam_roles ? 1 : 0

  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["vpc-flow-logs.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "flow_log" {
  count = var.create_network && var.flow_logs_destination == "cloudwatch" && var.create_iam_roles ? 1 : 0

  name               = "${local.name}-flow-log"
  assume_role_policy = data.aws_iam_policy_document.flow_log_assume[0].json
}

data "aws_iam_policy_document" "flow_log" {
  count = var.create_network && var.flow_logs_destination == "cloudwatch" && var.create_iam_roles ? 1 : 0

  statement {
    sid    = "EscreverFlowLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogGroups",
      "logs:DescribeLogStreams",
    ]
    resources = ["${aws_cloudwatch_log_group.vpc_flow[0].arn}:*"]
  }
}

resource "aws_iam_role_policy" "flow_log" {
  count = var.create_network && var.flow_logs_destination == "cloudwatch" && var.create_iam_roles ? 1 : 0

  name   = "escrever-flow-logs"
  role   = aws_iam_role.flow_log[0].id
  policy = data.aws_iam_policy_document.flow_log[0].json
}

# --------------------------------------------------------------------------- #
# O flow log
# --------------------------------------------------------------------------- #

# `traffic_type = "ALL"` e nao "REJECT". O rejeitado sozinho conta metade da
# historia: e o ACCEPT que prova que a task privada SAIU para a internet -- a
# evidencia de que o NAT esta em uso.
resource "aws_flow_log" "vpc" {
  count = var.create_network ? 1 : 0

  vpc_id       = aws_vpc.main[0].id
  traffic_type = "ALL"

  log_destination_type = var.flow_logs_destination == "s3" ? "s3" : "cloud-watch-logs"
  log_destination = (
    var.flow_logs_destination == "s3"
    ? local.flow_logs_bucket_arn
    : aws_cloudwatch_log_group.vpc_flow[0].arn
  )

  # Papel so no caminho do CloudWatch. No S3 quem autoriza e a politica do
  # bucket, e passar um papel aqui seria erro de validacao.
  iam_role_arn = var.flow_logs_destination == "cloudwatch" ? local.flow_log_role_arn : null

  # Formato explicito em vez do default.
  #
  # O default nao traz `pkt-srcaddr`/`pkt-dstaddr`, que sao o endereco REAL
  # antes da traducao do NAT -- sem eles todo trafego de saida das sub-redes
  # privadas aparece vindo do NAT, e fica impossivel dizer QUAL instancia falou
  # com quem. `action` e `log-status` sao o que responde "foi REJECT?" numa
  # consulta do Logs Insights.
  log_format = join(" ", [
    "$${version}", "$${account-id}", "$${interface-id}",
    "$${srcaddr}", "$${dstaddr}", "$${srcport}", "$${dstport}",
    "$${protocol}", "$${packets}", "$${bytes}",
    "$${start}", "$${end}", "$${action}", "$${log-status}",
    "$${vpc-id}", "$${subnet-id}", "$${pkt-srcaddr}", "$${pkt-dstaddr}",
  ])

  # 60 s e nao os 600 s do default: numa demonstracao ao vivo, esperar dez
  # minutos para o primeiro registro aparecer no console e a diferenca entre
  # evidenciar o recurso e falar sobre ele.
  #
  # No destino S3 ainda ha a latencia propria da entrega, de cerca de cinco
  # minutos, que este parametro nao encurta -- planeje a gravacao com isso.
  max_aggregation_interval = 60

  tags = {
    Name = "${local.name}-flow-log"
  }

  depends_on = [aws_s3_bucket_policy.flow_logs]
}

# --------------------------------------------------------------------------- #
# Access logs do ALB
# --------------------------------------------------------------------------- #

# O ALB nao entrega access log no CloudWatch Logs -- so em S3. Nao ha escolha
# de destino aqui; o bucket existe porque o servico exige bucket.
data "aws_elb_service_account" "main" {
  count = var.create_network && var.alb_access_logs_enabled ? 1 : 0
}

resource "aws_s3_bucket" "alb_logs" {
  count = var.create_network && var.alb_access_logs_enabled && var.alb_logs_bucket_name == "" ? 1 : 0

  bucket        = "${local.name}-alb-logs-${data.aws_caller_identity.current.account_id}"
  force_destroy = true

  tags = {
    Name = "${local.name}-alb-logs"
  }
}

resource "aws_s3_bucket_public_access_block" "alb_logs" {
  count = var.create_network && var.alb_access_logs_enabled ? 1 : 0

  bucket = local.alb_logs_bucket

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Access log cresce por requisicao e ninguem volta nele depois de um mes. Sem a
# expiracao o bucket vira custo permanente por um dado que ja nao se consulta.
resource "aws_s3_bucket_lifecycle_configuration" "alb_logs" {
  count = var.create_network && var.alb_access_logs_enabled ? 1 : 0

  bucket = local.alb_logs_bucket

  rule {
    id     = "expirar-access-logs"
    status = "Enabled"

    filter {}

    expiration {
      days = var.alb_access_logs_retention_days
    }
  }
}

# Quem escreve no bucket e o proprio servico de balanceamento, com a identidade
# da conta de servico do ELB da regiao -- nao a nossa. Sem esta policy o ALB
# sobe, mas com `access_logs.enabled = true` o apply falha na validacao que a
# AWS faz gravando um arquivo de teste.
data "aws_iam_policy_document" "alb_logs" {
  count = var.create_network && var.alb_access_logs_enabled ? 1 : 0

  statement {
    sid       = "PermitirEscritaDoELB"
    effect    = "Allow"
    actions   = ["s3:PutObject"]
    resources = ["${local.alb_logs_bucket_arn}/*"]

    principals {
      type        = "AWS"
      identifiers = [data.aws_elb_service_account.main[0].arn]
    }
  }
}

resource "aws_s3_bucket_policy" "alb_logs" {
  count = var.create_network && var.alb_access_logs_enabled ? 1 : 0

  bucket = local.alb_logs_bucket
  policy = data.aws_iam_policy_document.alb_logs[0].json

  depends_on = [aws_s3_bucket_public_access_block.alb_logs]
}
