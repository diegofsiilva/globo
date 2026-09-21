# Fila principal + DLQ.
#
# Standard, nao FIFO. FIFO garantiria ordem e deduplicacao, mas limita a 3.000
# msg/s com batching e custa mais caro. Para telemetria nao precisamos de
# nenhuma das duas coisas: a ordem e reconstruida pela sort key (timestamp) na
# leitura, e a deduplicacao ja vem de graca da chave derivada do hash do
# conteudo -- inclusive para duplicata separada por mais de 5 minutos, que a
# janela de deduplicacao do FIFO nao pegaria.

resource "aws_sqs_queue" "dlq" {
  name                      = "${local.name}-dlq"
  message_retention_seconds = var.dlq_retention_seconds
  sqs_managed_sse_enabled   = true

  tags = {
    Name = "${local.name}-dlq"
  }
}

resource "aws_sqs_queue" "events" {
  name                       = local.name
  visibility_timeout_seconds = var.visibility_timeout_seconds
  message_retention_seconds  = var.message_retention_seconds
  sqs_managed_sse_enabled    = true

  # Long polling no lado da fila tambem, para o caso de algum consumidor pedir
  # receive sem WaitTimeSeconds.
  receive_wait_time_seconds = 20

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = var.max_receive_count
  })

  tags = {
    Name = local.name
  }
}

# Permite reprocessar da DLQ de volta para a fila principal pelo console
# ("Start DLQ redrive") depois de corrigir a causa.
resource "aws_sqs_queue_redrive_allow_policy" "dlq" {
  queue_url = aws_sqs_queue.dlq.id

  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.events.arn]
  })
}

# Só o API Gateway deste stack pode publicar na fila. Sem isso, a policy padrao
# permitiria qualquer principal da propria conta.
data "aws_iam_policy_document" "events_queue" {
  statement {
    sid    = "AllowApiGatewaySendMessage"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["apigateway.amazonaws.com"]
    }

    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.events.arn]

    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = ["${aws_apigatewayv2_api.events.execution_arn}/*"]
    }
  }
}

resource "aws_sqs_queue_policy" "events" {
  queue_url = aws_sqs_queue.events.id
  policy    = data.aws_iam_policy_document.events_queue.json
}
