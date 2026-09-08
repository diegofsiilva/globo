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

resource "aws_cloudwatch_log_group" "vpc_flow" {
  count = var.create_network ? 1 : 0

  name              = "/aws/vpc/${local.name}/flow-logs"
  retention_in_days = var.log_retention_days

  tags = {
    Name = "${local.name}-flow-logs"
  }
}

resource "aws_flow_log" "vpc" {
  count = var.create_network ? 1 : 0

  vpc_id       = aws_vpc.main[0].id
  traffic_type = "ALL"

  log_destination_type = "cloud-watch-logs"
  log_destination      = aws_cloudwatch_log_group.vpc_flow[0].arn
  iam_role_arn         = local.flow_log_role_arn

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
  max_aggregation_interval = 60

  tags = {
    Name = "${local.name}-flow-log"
  }
}

# --------------------------------------------------------------------------- #
# Papel do flow log
# --------------------------------------------------------------------------- #

# Mesmo padrao dos demais papeis do stack (ver locals.tf): quando
# `create_iam_roles = false`, tudo colapsa na role unica que o Learner Lab
# permite criar, porque o `voclabs` recusa `iam:CreateRole`.
data "aws_iam_policy_document" "flow_log_assume" {
  count = var.create_network && var.create_iam_roles ? 1 : 0

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
  count = var.create_network && var.create_iam_roles ? 1 : 0

  name               = "${local.name}-flow-log"
  assume_role_policy = data.aws_iam_policy_document.flow_log_assume[0].json
}

data "aws_iam_policy_document" "flow_log" {
  count = var.create_network && var.create_iam_roles ? 1 : 0

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
  count = var.create_network && var.create_iam_roles ? 1 : 0

  name   = "escrever-flow-logs"
  role   = aws_iam_role.flow_log[0].id
  policy = data.aws_iam_policy_document.flow_log[0].json
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
  count = var.create_network && var.alb_access_logs_enabled ? 1 : 0

  bucket        = "${local.name}-alb-logs-${data.aws_caller_identity.current.account_id}"
  force_destroy = true

  tags = {
    Name = "${local.name}-alb-logs"
  }
}

resource "aws_s3_bucket_public_access_block" "alb_logs" {
  count = var.create_network && var.alb_access_logs_enabled ? 1 : 0

  bucket = aws_s3_bucket.alb_logs[0].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Access log cresce por requisicao e ninguem volta nele depois de um mes. Sem a
# expiracao o bucket vira custo permanente por um dado que ja nao se consulta.
resource "aws_s3_bucket_lifecycle_configuration" "alb_logs" {
  count = var.create_network && var.alb_access_logs_enabled ? 1 : 0

  bucket = aws_s3_bucket.alb_logs[0].id

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
    resources = ["${aws_s3_bucket.alb_logs[0].arn}/*"]

    principals {
      type        = "AWS"
      identifiers = [data.aws_elb_service_account.main[0].arn]
    }
  }
}

resource "aws_s3_bucket_policy" "alb_logs" {
  count = var.create_network && var.alb_access_logs_enabled ? 1 : 0

  bucket = aws_s3_bucket.alb_logs[0].id
  policy = data.aws_iam_policy_document.alb_logs[0].json
}
