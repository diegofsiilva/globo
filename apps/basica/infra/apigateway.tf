# API Gateway HTTP API (v2) com integracao direta para o SQS.
#
# Sem Lambda no meio de proposito: o subtype `SQS-SendMessage` deixa o proprio
# API Gateway publicar na fila. Isso remove cold start, remove um ponto de
# falha, e o HTTP API custa US$ 1,00/milhao contra US$ 3,50 do REST API.
#
# O preco disso e que HTTP API nao tem request validator (so o REST API tem).
# Ou seja: nao ha validacao de schema na borda, o payload entra cru na fila e
# quem valida e o worker, mandando o que nao presta para a DLQ com o motivo.
# Para um firehose de telemetria essa e a troca certa -- aceitar rapido e
# validar assincrono e melhor que bloquear a TV do usuario esperando validacao.

resource "aws_apigatewayv2_api" "events" {
  name          = local.name
  protocol_type = "HTTP"
  description   = "Ingestao de eventos de telemetria do Argus"

  cors_configuration {
    allow_origins = var.api_cors_allow_origins
    allow_methods = ["POST", "OPTIONS"]
    allow_headers = ["content-type", "x-client-version", "x-device-id", "x-tenant-id"]
    max_age       = 300
  }

  tags = {
    Name = local.name
  }
}

# Role que o API Gateway assume para escrever na fila.
data "aws_iam_policy_document" "apigw_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["apigateway.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "apigw_sqs" {
  count = var.create_iam_roles ? 1 : 0

  name               = "${local.name}-apigw-sqs"
  assume_role_policy = data.aws_iam_policy_document.apigw_assume.json
}

data "aws_iam_policy_document" "apigw_sqs" {
  statement {
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.events.arn]
  }
}

resource "aws_iam_role_policy" "apigw_sqs" {
  count = var.create_iam_roles ? 1 : 0

  name   = "send-message"
  role   = aws_iam_role.apigw_sqs[0].id
  policy = data.aws_iam_policy_document.apigw_sqs.json
}

resource "aws_apigatewayv2_integration" "sqs" {
  api_id           = aws_apigatewayv2_api.events.id
  integration_type = "AWS_PROXY"

  integration_subtype    = "SQS-SendMessage"
  credentials_arn        = local.apigw_role_arn
  payload_format_version = "1.0"

  request_parameters = {
    QueueUrl = aws_sqs_queue.events.url
    # Corpo do POST vai cru para a fila. O worker aceita um evento, uma lista
    # de eventos, ou {"events": [...]}.
    MessageBody = "$request.body"
  }
}

resource "aws_apigatewayv2_route" "post_events" {
  api_id    = aws_apigatewayv2_api.events.id
  route_key = "POST /v1/events"
  target    = "integrations/${aws_apigatewayv2_integration.sqs.id}"
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/apigateway/${local.name}"
  retention_in_days = var.log_retention_days
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.events.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_rate_limit    = var.api_throttle_rate_limit
    throttling_burst_limit   = var.api_throttle_burst_limit
    detailed_metrics_enabled = true
  }

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api.arn
    format = jsonencode({
      requestId        = "$context.requestId"
      ip               = "$context.identity.sourceIp"
      requestTime      = "$context.requestTime"
      httpMethod       = "$context.httpMethod"
      routeKey         = "$context.routeKey"
      status           = "$context.status"
      responseLength   = "$context.responseLength"
      integrationError = "$context.integrationErrorMessage"
      latency          = "$context.responseLatency"
    })
  }

  tags = {
    Name = local.name
  }
}
