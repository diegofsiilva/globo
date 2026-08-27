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

# Quatro servicos agora, e nao um. `for_each` em vez de quatro blocos copiados:
# o limiar e a janela sao os mesmos, e o que muda e so o nome do service.
resource "aws_cloudwatch_metric_alarm" "servico_down" {
  # Servico deliberadamente desligado (desired_count = 0) nao tem como estar
  # "fora do ar" -- por isso o filtro, e nao um alarme com limiar zero. Sem ele
  # o simulador parado alarmaria para sempre e o painel viraria ruido que
  # ninguem olha.
  for_each = {
    for nome, cfg in {
      merge-worker = { service = aws_ecs_service.merge_worker.name, esperado = var.worker_desired_count }
      event-worker = { service = aws_ecs_service.event_worker.name, esperado = var.worker_desired_count }
      simulator    = { service = aws_ecs_service.simulator.name, esperado = var.simulator_desired_count }
      processing   = { service = aws_ecs_service.processing.name, esperado = var.processing_desired_count }
    } : nome => cfg if cfg.esperado > 0
  }

  alarm_name        = "${local.name}-${each.key}-fora-do-ar"
  alarm_description = "Tasks de ${each.key} abaixo do desejado: crash loop ou falha de deploy."

  namespace           = "ECS/ContainerInsights"
  metric_name         = "RunningTaskCount"
  statistic           = "Average"
  period              = 60
  evaluation_periods  = 5
  datapoints_to_alarm = 3
  threshold           = each.value.esperado
  comparison_operator = "LessThanThreshold"
  # `missing` em vez de `notBreaching`: se a metrica sumiu, o cluster
  # provavelmente parou de reportar -- silencio aqui nao e boa noticia.
  treat_missing_data = "breaching"

  dimensions = {
    ClusterName = aws_ecs_cluster.main.name
    ServiceName = each.value.service
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
# A fila de change events
# --------------------------------------------------------------------------- #

# Mesmo raciocinio do alarme da fila de eventos: idade da mensagem mais antiga e
# melhor sinal que profundidade. Fila separada precisa de alarme separado --
# sem ele, uma rajada de replay do simulador acumulando sem consumidor passaria
# despercebida ate alguem abrir o dashboard e ver o dado parado.
resource "aws_cloudwatch_metric_alarm" "changes_backlog" {
  alarm_name          = "${local.name}-changes-atrasada"
  alarm_description   = "Change events parados na fila ha mais de ${var.alarm_queue_age_seconds}s."
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
    QueueName = aws_sqs_queue.changes.name
  }

  alarm_actions = [aws_sns_topic.alarms.arn]
  ok_actions    = [aws_sns_topic.alarms.arn]
}

resource "aws_cloudwatch_metric_alarm" "changes_dlq_not_empty" {
  alarm_name          = "${local.name}-changes-dlq-com-mensagem"
  alarm_description   = "Change event na DLQ: payload invalido ou MERGE falhando de forma repetida."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.changes_dlq.name
  }

  alarm_actions = [aws_sns_topic.alarms.arn]
  ok_actions    = [aws_sns_topic.alarms.arn]
}

# --------------------------------------------------------------------------- #
# O banco
# --------------------------------------------------------------------------- #

# Storage cheio e a falha mais provavel deste stack, e a mais brutal: o
# PostgreSQL para de aceitar escrita e o RDS nao volta sozinho. A conta de
# tamanho em var.db_instance_class deixa folga, mas o change_log cresce com o
# replay e o WAL cresce junto -- e um replay longo demais fura a estimativa.
resource "aws_cloudwatch_metric_alarm" "rds_storage" {
  alarm_name          = "${local.name}-rds-storage"
  alarm_description   = "Espaco livre no RDS abaixo de 10 GB: o banco para de aceitar escrita quando zerar."
  namespace           = "AWS/RDS"
  metric_name         = "FreeStorageSpace"
  statistic           = "Minimum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 10 * 1024 * 1024 * 1024
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.id
  }

  alarm_actions = [aws_sns_topic.alarms.arn]
}

# --------------------------------------------------------------------------- #
# Motor de hipoteses
# --------------------------------------------------------------------------- #

resource "aws_cloudwatch_metric_alarm" "analysis_failures" {
  count = var.analysis_enabled && var.processing_desired_count > 0 ? 1 : 0

  alarm_name          = "${local.name}-analysis-tres-falhas"
  alarm_description   = "Tres ciclos consecutivos da analise terminaram com falha."
  namespace           = "Argus/Ingestion"
  metric_name         = "AnalysisRunsFailed"
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 3
  datapoints_to_alarm = 3
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    Service = "${local.name}-processing-analysis"
  }
  alarm_actions = [aws_sns_topic.alarms.arn]
  ok_actions    = [aws_sns_topic.alarms.arn]
}

resource "aws_cloudwatch_metric_alarm" "analysis_takeover" {
  count = var.analysis_enabled && var.processing_desired_count > 0 ? 1 : 0

  alarm_name          = "${local.name}-analysis-lease-expirado"
  alarm_description   = "Uma tentativa assumiu run cujo lease expirou."
  namespace           = "Argus/Ingestion"
  metric_name         = "AnalysisTakeovers"
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    Service = "${local.name}-processing-analysis"
  }
  alarm_actions = [aws_sns_topic.alarms.arn]
}

resource "aws_cloudwatch_metric_alarm" "analysis_backlog" {
  count = var.analysis_enabled && var.processing_desired_count > 0 ? 1 : 0

  alarm_name          = "${local.name}-analysis-backlog"
  alarm_description   = "Analise acumula pelo menos tres checkpoints."
  namespace           = "Argus/Ingestion"
  metric_name         = "AnalysisBacklogCheckpoints"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 3
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    Service = "${local.name}-processing-analysis"
  }
  alarm_actions = [aws_sns_topic.alarms.arn]
  ok_actions    = [aws_sns_topic.alarms.arn]
}

resource "aws_cloudwatch_metric_alarm" "analysis_truncated" {
  count = var.analysis_enabled && var.processing_desired_count > 0 ? 1 : 0

  alarm_name          = "${local.name}-analysis-truncado"
  alarm_description   = "Um run excedeu o budget deterministico de candidatos."
  namespace           = "Argus/Ingestion"
  metric_name         = "AnalysisCandidatesTruncated"
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    Service = "${local.name}-processing-analysis"
  }
  alarm_actions = [aws_sns_topic.alarms.arn]
}

resource "aws_cloudwatch_metric_alarm" "analysis_input_limit" {
  count = var.analysis_enabled && var.processing_desired_count > 0 ? 1 : 0

  alarm_name          = "${local.name}-analysis-entrada-excedida"
  alarm_description   = "Um checkpoint excedeu o limite de fatos; o cursor permanece parado."
  namespace           = "Argus/Ingestion"
  metric_name         = "AnalysisInputLimitExceeded"
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions = {
    Service = "${local.name}-processing-analysis"
  }
  alarm_actions = [aws_sns_topic.alarms.arn]
}

resource "aws_cloudwatch_metric_alarm" "analysis_no_completed_run" {
  count = var.analysis_enabled && var.processing_desired_count > 0 ? 1 : 0

  alarm_name          = "${local.name}-analysis-sem-run-concluido"
  alarm_description   = "Nenhum run de analise concluiu nos ultimos 30 minutos reais."
  namespace           = "Argus/Ingestion"
  metric_name         = "AnalysisRunsCompleted"
  statistic           = "Sum"
  period              = 1800
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching"
  dimensions = {
    Service = "${local.name}-processing-analysis"
  }
  alarm_actions = [aws_sns_topic.alarms.arn]
  ok_actions    = [aws_sns_topic.alarms.arn]
}

# Numa classe t3, CPU alta e sintoma de credito de burst acabando. Quando o
# credito zera, a instancia e limitada ao baseline e TUDO fica lento de uma vez
# -- inclusive as views que o dashboard consulta.
resource "aws_cloudwatch_metric_alarm" "rds_cpu" {
  alarm_name          = "${local.name}-rds-cpu"
  alarm_description   = "CPU do RDS acima de 80%: numa classe t3, e o credito de burst acabando."
  namespace           = "AWS/RDS"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 3
  datapoints_to_alarm = 2
  threshold           = 80
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.id
  }

  alarm_actions = [aws_sns_topic.alarms.arn]
}

# db.t3.medium fecha em ~340 conexoes. Cinco containers com pool, mais a Lambda
# (que abre uma conexao por execucao concorrente, e a Lambda escala sozinha),
# chegam la mais rapido do que a intuicao sugere.
resource "aws_cloudwatch_metric_alarm" "rds_conexoes" {
  alarm_name          = "${local.name}-rds-conexoes"
  alarm_description   = "Conexoes no RDS acima de 200: pool vazando ou concorrencia da Lambda crescendo."
  namespace           = "AWS/RDS"
  metric_name         = "DatabaseConnections"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 2
  threshold           = 200
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.main.id
  }

  alarm_actions = [aws_sns_topic.alarms.arn]
}

# --------------------------------------------------------------------------- #
# Atraso do pipeline em tempo virtual
# --------------------------------------------------------------------------- #

# lag_sim: quanto tempo VIRTUAL o pipeline esta atras da origem. E a metrica que
# so faz sentido neste sistema -- o merge worker a emite comparando sim.now()
# com o captured_at da ultima mensagem aplicada.
#
# Alarma por ausencia (`breaching`): se o worker parou de emitir, o pipeline
# parou, e um painel silencioso pareceria saudavel.
resource "aws_cloudwatch_metric_alarm" "lag_sim" {
  alarm_name          = "${local.name}-lag-sim"
  alarm_description   = "O pipeline esta mais de ${var.alarm_lag_sim_wall_seconds}s de PAREDE atras da origem (${local.lag_sim_limite}s de tempo virtual a speed ${var.simulator_speed})."
  namespace           = "Argus/Ingestion"
  metric_name         = "LagSimSeconds"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 2
  threshold           = local.lag_sim_limite
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "breaching"

  dimensions = {
    Service = "${local.name}-merge-worker"
  }

  alarm_actions = [aws_sns_topic.alarms.arn]
  ok_actions    = [aws_sns_topic.alarms.arn]
}

# Heartbeat por fonte: cada fonte do dataset tem cadencia propria (prometheus 1
# min, rpaas 15 min, npaw 28 h de latencia). Uma fonte que simplesmente PARA de
# chegar nao derruba nada -- as outras continuam, o dashboard continua
# desenhando, e o buraco so aparece quando alguem for investigar um incidente e
# nao achar o dado. Por isso e alarme proprio.
resource "aws_cloudwatch_metric_alarm" "fonte_silenciosa" {
  alarm_name          = "${local.name}-fonte-silenciosa"
  alarm_description   = "Alguma fonte parou de mandar dado: o buraco so apareceria na investigacao."
  namespace           = "Argus/Ingestion"
  metric_name         = "SourcesSilent"
  statistic           = "Maximum"
  period              = 900
  evaluation_periods  = 2
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    Service = "${local.name}-merge-worker"
  }

  alarm_actions = [aws_sns_topic.alarms.arn]
  ok_actions    = [aws_sns_topic.alarms.arn]
}
