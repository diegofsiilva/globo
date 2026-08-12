# Alarmes do fluxo. A ideia e cobrir os tres jeitos de o pipeline falhar em
# silencio: evento parando na DLQ, fila crescendo sem consumidor, e worker
# morto sem ninguem notar.

resource "aws_sns_topic" "alarms" {
  name = "${local.name}-alarms"

  tags = {
    Name = "${local.name}-alarms"
  }
}

resource "aws_sns_topic_subscription" "email" {
  count = var.alarm_email != "" ? 1 : 0

  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.alarm_email
  # A inscricao so fica ativa depois que o destinatario clicar no link de
  # confirmacao que a AWS manda por e-mail.
}

# --------------------------------------------------------------------------- #
# Evento perdido
# --------------------------------------------------------------------------- #

# Qualquer mensagem na DLQ e sintoma: ou o payload esta quebrado, ou o worker
# falhou 5 vezes seguidas. Nos dois casos alguem precisa olhar.
resource "aws_cloudwatch_metric_alarm" "dlq_not_empty" {
  alarm_name          = "${local.name}-dlq-com-mensagem"
  alarm_description   = "Ha evento na DLQ: payload invalido ou falha repetida de escrita."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.dlq.name
  }

  alarm_actions = [aws_sns_topic.alarms.arn]
  ok_actions    = [aws_sns_topic.alarms.arn]
}

# --------------------------------------------------------------------------- #
# Fila acumulando
# --------------------------------------------------------------------------- #

# Idade da mensagem mais antiga e melhor sinal que profundidade da fila: pico de
# trafego sobe a profundidade sem ser problema, mas mensagem velha significa que
# o consumo nao esta acompanhando a producao.
resource "aws_cloudwatch_metric_alarm" "queue_backlog" {
  alarm_name          = "${local.name}-fila-atrasada"
  alarm_description   = "Mensagem mais antiga na fila passou de ${var.alarm_queue_age_seconds}s."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateAgeOfOldestMessage"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 3
  datapoints_to_alarm = 2
  threshold           = var.alarm_queue_age_seconds
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.events.name
  }

  alarm_actions = [aws_sns_topic.alarms.arn]
  ok_actions    = [aws_sns_topic.alarms.arn]
}

# --------------------------------------------------------------------------- #
# Worker fora do ar
# --------------------------------------------------------------------------- #

resource "aws_cloudwatch_metric_alarm" "worker_down" {
  alarm_name          = "${local.name}-worker-fora-do-ar"
  alarm_description   = "Tasks rodando abaixo do desejado: crash loop ou falha de deploy."
  namespace           = "ECS/ContainerInsights"
  metric_name         = "RunningTaskCount"
  statistic           = "Average"
  period              = 60
  evaluation_periods  = 5
  datapoints_to_alarm = 3
  threshold           = var.worker_desired_count
  comparison_operator = "LessThanThreshold"
  # `missing` em vez de `notBreaching`: se a metrica sumiu, o cluster
  # provavelmente parou de reportar -- silencio aqui nao e boa noticia.
  treat_missing_data = "breaching"

  dimensions = {
    ClusterName = aws_ecs_cluster.main.name
    ServiceName = aws_ecs_service.worker.name
  }

  alarm_actions = [aws_sns_topic.alarms.arn]
  ok_actions    = [aws_sns_topic.alarms.arn]
}

# --------------------------------------------------------------------------- #
# Erros na borda
# --------------------------------------------------------------------------- #

# 5xx no API Gateway significa evento que nem chegou na fila -- perda na
# entrada, que nenhum retry do nosso lado recupera.
resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name          = "${local.name}-api-5xx"
  alarm_description   = "API Gateway retornando 5xx: evento nao chegou a entrar na fila."
  namespace           = "AWS/ApiGateway"
  metric_name         = "5xx"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 10
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    ApiId = aws_apigatewayv2_api.events.id
  }

  alarm_actions = [aws_sns_topic.alarms.arn]
}

# --------------------------------------------------------------------------- #
# Throttle de escrita no DynamoDB
# --------------------------------------------------------------------------- #

# Sinal de particao quente. Se disparar com frequencia, o caminho e aumentar
# gsi1_shards (e o GSI1_SHARDS do worker junto).
resource "aws_cloudwatch_metric_alarm" "dynamodb_throttle" {
  alarm_name          = "${local.name}-dynamodb-throttle"
  alarm_description   = "Escrita throttled no DynamoDB: possivel particao quente, avalie aumentar gsi1_shards."
  namespace           = "AWS/DynamoDB"
  metric_name         = "WriteThrottleEvents"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    TableName = aws_dynamodb_table.events.name
  }

  alarm_actions = [aws_sns_topic.alarms.arn]
}
