# A rede gerenciada do Argus: VPC propria, quatro subnets, um NAT e flow logs.
#
# Ate aqui o stack CONSUMIA a VPC default da conta (`data "aws_vpc" "default"`
# em locals.tf). Consumir nao e gerenciar: a faixa de enderecos, as rotas e a
# separacao publico/privado eram o que a AWS entregou pronto, iguais em toda
# conta nova, e nenhuma delas estava descrita em codigo.
#
# Este arquivo declara a rede como recurso. O que ele acrescenta, em ordem de
# importancia:
#
#   1. Subnet PRIVADA de verdade -- sem rota para o Internet Gateway. Hoje o
#      unico controle que impede alguem de alcancar as tasks e o security group
#      sem regra de entrada. Com subnet privada some tambem a rota: dois
#      controles independentes em vez de um.
#   2. NAT Gateway, para que essas tasks sem IP publico continuem alcancando
#      ECR, SQS, Secrets Manager e CloudWatch. Sem ele a task nem baixa a imagem
#      e o service entra em crash loop -- ver a nota em var.subnet_ids.
#   3. Flow Logs, a observabilidade da propria rede: todo fluxo aceito ou
#      rejeitado nas interfaces da VPC, com origem, destino e porta.
#
# Tudo aqui e condicionado a `var.create_vpc`. Com `false`, nada e criado e o
# stack volta a rodar na VPC default -- o caminho de antes continua existindo.
#
# ATENCAO ao ligar pela primeira vez: a AWS nao move uma instancia RDS entre
# VPCs. Trocar a rede RECRIA o banco. Tire um snapshot manual antes do apply.
# Ver a secao "Rede: publica vs privada" do README.

data "aws_availability_zones" "available" {
  count = var.create_vpc ? 1 : 0
  state = "available"
}

locals {
  # Duas AZs, nao uma. Uma subnet so nao permite Multi-AZ no RDS nem um ALB, que
  # exige no minimo duas -- e a rede e a fundacao dos dois.
  azs = var.create_vpc ? (
    length(var.azs) > 0
    ? var.azs
    : slice(data.aws_availability_zones.available[0].names, 0, 2)
  ) : []

  # 10.0.0.0/24 e 10.0.1.0/24 para as publicas; 10.0.10.0/24 e 10.0.11.0/24 para
  # as privadas. O salto de 10 no indice e so legibilidade: olhando um IP em log
  # de flow, o terceiro octeto ja diz de que lado da rede ele veio.
  public_cidrs  = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 8, i)]
  private_cidrs = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 8, i + 10)]

  # Bucket dos flow logs: o informado em `flow_logs_bucket_name`, ou o que este
  # arquivo cria. A indirecao existe por causa de uma restricao de ambiente --
  # ver o comentario sobre a SCP na secao de Flow Logs, abaixo.
  flow_logs_bucket = (
    var.flow_logs_destination != "s3" ? "" :
    var.flow_logs_bucket_name != "" ? var.flow_logs_bucket_name :
    var.create_vpc ? aws_s3_bucket.flow_logs[0].bucket : ""
  )
  flow_logs_bucket_arn = (
    local.flow_logs_bucket != "" ? "arn:aws:s3:::${local.flow_logs_bucket}" : ""
  )
}

# --------------------------------------------------------------------------- #
# A VPC
# --------------------------------------------------------------------------- #

resource "aws_vpc" "main" {
  count = var.create_vpc ? 1 : 0

  cidr_block = var.vpc_cidr

  # Os dois sao obrigatorios, nao opcionais de conforto. O endpoint do RDS, o do
  # Secrets Manager e o do ECR sao nomes DNS; sem resolucao dentro da VPC a task
  # falha na conexao com o banco antes de qualquer coisa da aplicacao rodar.
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = local.name
  }
}

resource "aws_internet_gateway" "main" {
  count = var.create_vpc ? 1 : 0

  vpc_id = aws_vpc.main[0].id

  tags = {
    Name = local.name
  }
}

# --------------------------------------------------------------------------- #
# Subnets
# --------------------------------------------------------------------------- #

# Publicas: NAT Gateway, e adiante o bastion e o Application Load Balancer.
#
# `map_public_ip_on_launch` deixa a diferenca visivel no console -- a tela
# VPC > Subnets mostra duas com "auto-assign public IP" ligado e duas sem.
resource "aws_subnet" "public" {
  count = var.create_vpc ? length(local.azs) : 0

  vpc_id                  = aws_vpc.main[0].id
  cidr_block              = local.public_cidrs[count.index]
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name = "${local.name}-publica-${local.azs[count.index]}"
    Tier = "publica"
  }
}

# Privadas: as tasks Fargate, a Lambda de leitura e o RDS. Nenhum recurso daqui
# recebe IP publico, e nenhuma rota daqui aponta para o Internet Gateway.
resource "aws_subnet" "private" {
  count = var.create_vpc ? length(local.azs) : 0

  vpc_id            = aws_vpc.main[0].id
  cidr_block        = local.private_cidrs[count.index]
  availability_zone = local.azs[count.index]

  tags = {
    Name = "${local.name}-privada-${local.azs[count.index]}"
    Tier = "privada"
  }
}

# --------------------------------------------------------------------------- #
# NAT Gateway
# --------------------------------------------------------------------------- #

resource "aws_eip" "nat" {
  count = var.create_vpc ? 1 : 0

  domain = "vpc"

  tags = {
    Name = "${local.name}-nat"
  }
}

# UM NAT, nao um por AZ.
#
# Em producao o correto e um NAT por zona, com uma tabela de rota privada por
# zona: com um so, a queda daquela AZ derruba a saida das duas. A escolha aqui e
# de custo -- US$ 33/mes contra US$ 66 --, consciente e declarada, do mesmo tipo
# das decisoes registradas na tabela 4.9 de artefatos/arquitetura-inicial.md.
resource "aws_nat_gateway" "main" {
  count = var.create_vpc ? 1 : 0

  allocation_id = aws_eip.nat[0].id
  subnet_id     = aws_subnet.public[0].id

  # O NAT precisa do IGW ja anexado para funcionar; sem isto o Terraform pode
  # cria-lo antes e ele nasce sem saida.
  depends_on = [aws_internet_gateway.main]

  tags = {
    Name = local.name
  }
}

# --------------------------------------------------------------------------- #
# Rotas
# --------------------------------------------------------------------------- #

# O que separa subnet publica de privada nao e nada na subnet: e a tabela de
# rota associada a ela. Estas duas tabelas SAO a distincao.

resource "aws_route_table" "public" {
  count = var.create_vpc ? 1 : 0

  vpc_id = aws_vpc.main[0].id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main[0].id
  }

  tags = {
    Name = "${local.name}-publica"
  }
}

resource "aws_route_table" "private" {
  count = var.create_vpc ? 1 : 0

  vpc_id = aws_vpc.main[0].id

  # A clausula inteira do NAT esta nesta rota: a maquina privada inicia conexao
  # para fora e a resposta volta; ninguem de fora consegue iniciar conexao para
  # dentro, porque nao ha caminho de entrada.
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main[0].id
  }

  tags = {
    Name = "${local.name}-privada"
  }
}

resource "aws_route_table_association" "public" {
  count = var.create_vpc ? length(local.azs) : 0

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public[0].id
}

resource "aws_route_table_association" "private" {
  count = var.create_vpc ? length(local.azs) : 0

  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[0].id
}

# --------------------------------------------------------------------------- #
# Gateway endpoint de S3
# --------------------------------------------------------------------------- #

# Gateway endpoint e GRATIS -- diferente do endpoint de interface, que custa
# ~US$ 7/mes por AZ. Ele e uma entrada na tabela de rota, nao uma interface de
# rede.
#
# Vale por dois motivos. O `loader` le os ~200 MB de Parquet do bucket `origem`
# a cada carga inicial, e o NAT cobra por GB trafegado: esse trafego sai de cima
# dele. E o acesso passa a ser interno a AWS, sem sequer chegar a internet.
resource "aws_vpc_endpoint" "s3" {
  count = var.create_vpc ? 1 : 0

  vpc_id            = aws_vpc.main[0].id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private[0].id]

  tags = {
    Name = "${local.name}-s3"
  }
}

# --------------------------------------------------------------------------- #
# Flow Logs -- a observabilidade da rede
# --------------------------------------------------------------------------- #

# Os 16 alarmes de observability.tf medem a APLICACAO: profundidade de fila,
# DLQ, CPU do banco, lag do simulador. Nenhum deles enxerga a rede. Flow Logs
# preenchem exatamente esse buraco: registram todo fluxo ACCEPT e REJECT nas
# interfaces da VPC, com origem, destino, porta e bytes.
#
# Na pratica e o que responde "a task esta mesmo saindo pelo NAT?" e "quem esta
# batendo na porta 5432 e sendo recusado?" sem instrumentar nada.

# Destino S3 -- o padrao, e provavelmente a escolha melhor.
#
# Entregar flow logs ao CloudWatch Logs exige um papel IAM que confie em
# `vpc-flow-logs.amazonaws.com`. A LabRole do AWS Academy confia em
# `apigateway`, `ecs-tasks` e `lambda` -- e nao no servico de flow logs. Com
# `create_iam_roles = false`, obrigatorio no laboratorio, esse caminho falha por
# confianca negada. S3 usa politica de bucket em vez de papel, some com a
# dependencia, e ainda custa menos por GB. A evidencia de console funciona igual.
# `flow_logs_bucket_name` desliga a criacao deste recurso, e existe por causa de
# uma restricao real do AWS Academy: a SCP da organizacao NEGA
# `s3:GetBucketObjectLockConfiguration`, e o provider chama exatamente essa API
# ao reler qualquer `aws_s3_bucket` depois de cria-lo. O bucket nasce, o apply
# falha na releitura, e o recurso fica no state envenenando todo plan seguinte.
#
# Informar um bucket criado fora do Terraform contorna o problema sem abrir mao
# de nada: a politica, o bloqueio publico, a criptografia e o ciclo de vida
# continuam gerenciados aqui, porque essas chamadas a SCP permite.
resource "aws_s3_bucket" "flow_logs" {
  count = var.create_vpc && var.flow_logs_destination == "s3" && var.flow_logs_bucket_name == "" ? 1 : 0

  bucket        = "${local.name}-flow-logs-${data.aws_caller_identity.current.account_id}"
  force_destroy = true

  tags = {
    Name = "${local.name}-flow-logs"
  }
}

resource "aws_s3_bucket_public_access_block" "flow_logs" {
  count = var.create_vpc && var.flow_logs_destination == "s3" ? 1 : 0

  bucket = local.flow_logs_bucket

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# AES256 e nao KMS: o servico de flow logs recusa entregar em bucket com
# SSE-KMS de chave gerenciada pelo cliente. Descobrir isso pelo silencio de um
# bucket que nunca recebe objeto custa uma sessao inteira de laboratorio.
resource "aws_s3_bucket_server_side_encryption_configuration" "flow_logs" {
  count = var.create_vpc && var.flow_logs_destination == "s3" ? 1 : 0

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
  count = var.create_vpc && var.flow_logs_destination == "s3" && var.log_retention_days > 0 ? 1 : 0

  bucket = local.flow_logs_bucket

  rule {
    id     = "expira-flow-logs"
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
  count = var.create_vpc && var.flow_logs_destination == "s3" ? 1 : 0

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
  count = var.create_vpc && var.flow_logs_destination == "s3" ? 1 : 0

  bucket = local.flow_logs_bucket
  policy = data.aws_iam_policy_document.flow_logs_bucket[0].json

  # A politica nega escrita publica; o bloqueio precisa estar valendo antes.
  depends_on = [aws_s3_bucket_public_access_block.flow_logs]
}

# Destino CloudWatch Logs -- o caminho alternativo.
#
# Vale a pena numa conta normal: Logs Insights consulta os registros com uma
# linguagem de consulta, sem baixar arquivo nenhum. Em laboratorio, esbarra na
# LabRole (ver acima).
resource "aws_cloudwatch_log_group" "flow_logs" {
  count = var.create_vpc && var.flow_logs_destination == "cloudwatch" ? 1 : 0

  name              = "/aws/vpc/${local.name}/flow-logs"
  retention_in_days = var.log_retention_days

  tags = {
    Name = "${local.name}-flow-logs"
  }
}

resource "aws_iam_role" "flow_logs" {
  count = var.create_vpc && var.flow_logs_destination == "cloudwatch" && var.create_iam_roles ? 1 : 0

  name = "${local.name}-flow-logs"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "vpc-flow-logs.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = {
    Name = "${local.name}-flow-logs"
  }
}

resource "aws_iam_role_policy" "flow_logs" {
  count = var.create_vpc && var.flow_logs_destination == "cloudwatch" && var.create_iam_roles ? 1 : 0

  name = "escrever-flow-logs"
  role = aws_iam_role.flow_logs[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "logs:DescribeLogStreams",
      ]
      Resource = "${aws_cloudwatch_log_group.flow_logs[0].arn}:*"
    }]
  })
}

# `traffic_type = "ALL"` e nao "REJECT". O rejeitado sozinho conta metade da
# historia: e o ACCEPT que prova que a task privada SAIU para a internet -- a
# evidencia do NAT.
resource "aws_flow_log" "main" {
  count = var.create_vpc ? 1 : 0

  vpc_id       = aws_vpc.main[0].id
  traffic_type = "ALL"

  log_destination_type = var.flow_logs_destination == "s3" ? "s3" : "cloud-watch-logs"
  log_destination = (
    var.flow_logs_destination == "s3"
    ? local.flow_logs_bucket_arn
    : aws_cloudwatch_log_group.flow_logs[0].arn
  )
  iam_role_arn = (
    var.flow_logs_destination == "cloudwatch"
    ? (var.create_iam_roles ? aws_iam_role.flow_logs[0].arn : var.existing_role_arn)
    : null
  )

  # Um minuto em vez dos dez do padrao. Numa apresentacao ao vivo, esperar dez
  # minutos para o primeiro registro aparecer no console e a diferenca entre
  # mostrar a evidencia e falar sobre ela.
  max_aggregation_interval = 60

  tags = {
    Name = local.name
  }

  depends_on = [aws_s3_bucket_policy.flow_logs]
}
