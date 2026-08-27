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

  # A Lambda entra na VPC SEMPRE, mesmo com o RDS publico.
  #
  # A versao anterior disto so entrava quando `db_publicly_accessible = false`,
  # para poupar o cold start de ENI. Nao funciona: uma Lambda fora da VPC sai
  # por um IP publico arbitrario da AWS, que muda a cada invocacao. Nao ha o que
  # colocar no security group do RDS -- e o resultado e a Lambda batendo no
  # endpoint publico e sendo barrada, com `PoolTimeout` depois de 10 s em toda
  # rota que toca o banco.
  #
  # Dentro da VPC ela usa o security group das tasks, que a regra
  # `rds_from_tasks` ja autoriza. Nao precisa de NAT: o unico destino e o RDS, e
  # o log vai pelo servico da Lambda, nao pela ENI.
  vpc_config {
    subnet_ids         = local.subnet_ids
    security_group_ids = [aws_security_group.worker.id]
  }

  environment {
    variables = {
      # A Lambda conecta como `argus_api`, NAO como o usuario mestre. Esse
      # usuario so herda o papel argus_reader, que so tem SELECT nas views v_*
      # -- e o que impede a API de enxergar alem de sim.now() mesmo que alguem
      # esqueca o filtro numa rota nova. Criado por:
      #   python tools/migrate.py criar-leitor
      DATABASE_URL         = local.read_api_database_url
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

  # Nao ha statement de leitura de dado aqui, e isso e o desenho, nao um
  # esquecimento. A autorizacao de leitura mudou de lugar: com o DynamoDB ela
  # era IAM, agora e GRANT no PostgreSQL. A Lambda entra no banco como
  # `argus_api`, que so enxerga as views v_* -- ver 009_views_v.sql.
  #
  # A vantagem pratica: o IAM nao sabe filtrar linha por available_at, e o
  # GRANT do banco, combinado com a definicao da view, sabe.

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
    allow_methods = ["GET", "POST", "OPTIONS"]
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

# A rota explicita vence o proxy e recebe um limite proprio: feedback e a unica
# escrita publica desta API e nao deve compartilhar o burst das consultas.
resource "aws_apigatewayv2_route" "hypothesis_feedback" {
  api_id    = aws_apigatewayv2_api.read.id
  route_key = "POST /api/v1/hypotheses/{hypothesis_id}/feedback"
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


  route_settings {
    route_key                = aws_apigatewayv2_route.hypothesis_feedback.route_key
    throttling_rate_limit    = var.hypothesis_feedback_throttle_rate_limit
    throttling_burst_limit   = var.hypothesis_feedback_throttle_burst_limit
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
