# API de leitura dos eventos, consumida pelo dashboard.
#
# Flask empacotado em Lambda (via apig-wsgi) atras de um HTTP API proprio,
# separado do de ingestao. Os dois sao servicos diferentes: um recebe evento de
# TV em volume alto e nao pode recusar nada, o outro serve consulta para uma
# tela interna e vai precisar de autenticacao. Separar deixa throttling, CORS e
# authorizer independentes -- e HTTP API cobra por requisicao, nao por API,
# entao ter dois nao custa a mais.
#
# Lambda e nao Fargate porque o padrao de uso e intermitente: alguem abre o
# dashboard, faz algumas consultas e fecha. Um container ocioso 24/7 custaria
# ~US$ 7/mes para ficar esperando; aqui o custo tende a zero e a URL sobrevive
# ao restart do laboratorio, ao contrario de um IP de EC2.

resource "aws_cloudwatch_log_group" "api_read" {
  name              = "/aws/lambda/${local.name}-read-api"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "read_api" {
  function_name = "${local.name}-read-api"
  role          = local.read_api_role_arn
  handler       = "lambda_handler.lambda_handler"
  runtime       = "python3.12"
  architectures = ["arm64"] # ~20% mais barato que x86 no Lambda

  filename         = var.read_api_package_path
  source_code_hash = filebase64sha256(var.read_api_package_path)

  # O fan-out da GSI1 e limitado por rede, nao por CPU: sao dezenas de queries
  # em paralelo esperando resposta. Memoria acima disso nao acelera, mas abaixo
  # reduz a fatia de CPU e as threads passam a competir.
  memory_size = var.read_api_memory_mb
  timeout     = var.read_api_timeout_seconds

  environment {
    variables = {
      EVENTS_TABLE_NAME = aws_dynamodb_table.events.name
      # Precisa bater com var.gsi1_shards e com o GSI1_SHARDS do worker: os
      # tres montam a mesma chave da GSI1. Divergir faz a leitura procurar numa
      # particao onde a escrita nunca colocou nada -- devolve vazio, sem erro.
      GSI1_SHARDS          = tostring(var.gsi1_shards)
      USER_ID_HASH_SALT    = var.user_id_hash_salt
      DEFAULT_WINDOW_HOURS = tostring(var.read_api_default_window_hours)
      MAX_ITEMS_SCANNED    = tostring(var.read_api_max_items_scanned)
      CORS_ORIGINS         = join(",", var.dashboard_origins)
      LOG_LEVEL            = var.worker_log_level
    }
  }

  depends_on = [aws_cloudwatch_log_group.api_read]

  tags = {
    Name = "${local.name}-read-api"
  }
}

# ---------------------------------------------------------------------------- #
# Permissao de leitura
# ---------------------------------------------------------------------------- #

data "aws_iam_policy_document" "lambda_assume" {
  count = var.create_iam_roles ? 1 : 0

  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "read_api" {
  count = var.create_iam_roles ? 1 : 0

  name               = "${local.name}-read-api"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume[0].json
}

data "aws_iam_policy_document" "read_api" {
  count = var.create_iam_roles ? 1 : 0

  statement {
    sid    = "LerEventos"
    effect = "Allow"
    # Somente leitura, e sem GetItem: o acesso a um evento e sempre por Query
    # dentro da particao da sessao. Nada de PutItem, UpdateItem ou DeleteItem
    # -- a escrita pertence ao worker e o expurgo ao TTL.
    actions = ["dynamodb:Query", "dynamodb:Scan", "dynamodb:DescribeTable"]
    resources = [
      aws_dynamodb_table.events.arn,
      "${aws_dynamodb_table.events.arn}/index/*",
    ]
  }

  statement {
    sid       = "EscreverLogs"
    effect    = "Allow"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.api_read.arn}:*"]
  }
}

resource "aws_iam_role_policy" "read_api" {
  count = var.create_iam_roles ? 1 : 0

  name   = "read-events"
  role   = aws_iam_role.read_api[0].id
  policy = data.aws_iam_policy_document.read_api[0].json
}

# ---------------------------------------------------------------------------- #
# HTTP API
# ---------------------------------------------------------------------------- #

resource "aws_apigatewayv2_api" "read" {
  name          = "${local.name}-read"
  protocol_type = "HTTP"
  description   = "API de leitura dos eventos de telemetria (dashboard)"

  # O CORS tambem e tratado pelo Flask. Aqui ele existe para responder ao
  # preflight OPTIONS sem acordar a Lambda -- resposta mais rapida e uma
  # invocacao a menos por consulta do navegador.
  cors_configuration {
    allow_origins = var.dashboard_origins
    allow_methods = ["GET", "OPTIONS"]
    allow_headers = ["content-type", "authorization"]
    max_age       = 300
  }

  tags = {
    Name = "${local.name}-read"
  }
}

resource "aws_apigatewayv2_integration" "read" {
  api_id                 = aws_apigatewayv2_api.read.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.read_api.invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = var.read_api_timeout_seconds * 1000
}

# Rota unica em proxy: o roteamento fica no Flask, num lugar so. Declarar cada
# rota aqui duplicaria o mapa de URLs entre Terraform e codigo, e as duas
# copias divergiriam na primeira rota nova.
resource "aws_apigatewayv2_route" "read_proxy" {
  api_id    = aws_apigatewayv2_api.read.id
  route_key = "ANY /{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.read.id}"
}

resource "aws_apigatewayv2_route" "read_root" {
  api_id    = aws_apigatewayv2_api.read.id
  route_key = "ANY /"
  target    = "integrations/${aws_apigatewayv2_integration.read.id}"
}

resource "aws_lambda_permission" "read_api" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.read_api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.read.execution_arn}/*/*"
}

resource "aws_cloudwatch_log_group" "read_api_access" {
  name              = "/aws/apigateway/${local.name}-read"
  retention_in_days = var.log_retention_days
}

resource "aws_apigatewayv2_stage" "read" {
  api_id      = aws_apigatewayv2_api.read.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_rate_limit    = var.read_api_throttle_rate_limit
    throttling_burst_limit   = var.read_api_throttle_burst_limit
    detailed_metrics_enabled = true
  }

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.read_api_access.arn
    format = jsonencode({
      requestId        = "$context.requestId"
      ip               = "$context.identity.sourceIp"
      requestTime      = "$context.requestTime"
      httpMethod       = "$context.httpMethod"
      path             = "$context.path"
      status           = "$context.status"
      integrationError = "$context.integrationErrorMessage"
      latency          = "$context.responseLatency"
    })
  }

  tags = {
    Name = "${local.name}-read"
  }
}

# ---------------------------------------------------------------------------- #
# Alarme
# ---------------------------------------------------------------------------- #

resource "aws_cloudwatch_metric_alarm" "read_api_errors" {
  alarm_name          = "${local.name}-read-api-erros"
  alarm_description   = "A API de leitura esta falhando: o dashboard nao carrega."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 5
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.read_api.function_name
  }

  alarm_actions = [aws_sns_topic.alarms.arn]
}
