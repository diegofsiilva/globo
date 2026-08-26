# Fila dos change events (CDC das 33 tabelas), espelhando sqs.tf.
#
# Fila separada da de eventos de sessao de proposito. Sao dois fluxos com perfis
# diferentes: o CDC chega em rajada durante o replay do simulador e cada
# mensagem custa um MERGE; o grain de sessao chega difuso e so faz INSERT.
# Compartilhar a fila faria uma rajada de replay atrasar o evento de TV, e
# tornaria impossivel dimensionar os dois workers separadamente.

resource "aws_sqs_queue" "changes_dlq" {
  name                      = "${local.name}-changes-dlq"
  message_retention_seconds = var.dlq_retention_seconds
  sqs_managed_sse_enabled   = true

  tags = {
    Name = "${local.name}-changes-dlq"
  }
}

resource "aws_sqs_queue" "changes" {
  name                       = "${local.name}-changes"
  visibility_timeout_seconds = var.changes_visibility_timeout_seconds
  message_retention_seconds  = var.message_retention_seconds
  sqs_managed_sse_enabled    = true
  receive_wait_time_seconds  = 20

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.changes_dlq.arn
    maxReceiveCount     = var.max_receive_count
  })

  tags = {
    Name = "${local.name}-changes"
  }
}

resource "aws_sqs_queue_redrive_allow_policy" "changes_dlq" {
  queue_url = aws_sqs_queue.changes_dlq.id

  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.changes.arn]
  })
}

data "aws_iam_policy_document" "changes_queue" {
  statement {
    sid    = "AllowApiGatewaySendMessage"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["apigateway.amazonaws.com"]
    }

    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.changes.arn]

    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = ["${aws_apigatewayv2_api.events.execution_arn}/*"]
    }
  }
}

resource "aws_sqs_queue_policy" "changes" {
  queue_url = aws_sqs_queue.changes.id
  policy    = data.aws_iam_policy_document.changes_queue.json
}
