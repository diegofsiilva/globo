# Rota POST /v1/changes, integrada direto no SQS.
#
# Reusa a MESMA API HTTP de /v1/events (aws_apigatewayv2_api.events) em vez de
# criar uma segunda: as duas rotas sao ingestao, tem o mesmo throttling, o mesmo
# CORS e o mesmo perfil de seguranca. O que precisa ser separado -- a fila e o
# worker -- ja esta separado; separar tambem a API so acrescentaria um endpoint
# a mais para configurar no simulador e no runbook.

resource "aws_apigatewayv2_integration" "sqs_changes" {
  api_id           = aws_apigatewayv2_api.events.id
  integration_type = "AWS_PROXY"

  integration_subtype    = "SQS-SendMessage"
  credentials_arn        = local.apigw_role_arn
  payload_format_version = "1.0"

  request_parameters = {
    QueueUrl = aws_sqs_queue.changes.url
    # Corpo cru para a fila. O merge worker aceita um change event, uma lista,
    # ou {"changes": [...]}.
    MessageBody = "$request.body"
  }
}

resource "aws_apigatewayv2_route" "post_changes" {
  api_id    = aws_apigatewayv2_api.events.id
  route_key = "POST /v1/changes"
  target    = "integrations/${aws_apigatewayv2_integration.sqs_changes.id}"
}
