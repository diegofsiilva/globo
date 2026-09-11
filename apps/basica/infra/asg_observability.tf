# Alarmes e painel do caminho sincrono (ALB + Auto Scaling Group).
#
# Os 17 alarmes que ja existiam em observability.tf cobrem a ingestao, o ETL e o
# banco. Nenhum deles enxerga o caminho de leitura depois da migracao: o
# `read_api_errors` observa `AWS/Lambda`, e a Lambda deixa de estar no caminho.
# Sem os alarmes abaixo, a API poderia ficar inteira fora do ar sem que nada
# apitasse.
#
# Todos publicam em `aws_sns_topic.alarms`, o mesmo topico dos demais -- um
# destino unico e o que evita que metade dos alarmes va para um lugar que
# ninguem acompanha. Vale a ressalva registrada no artefato: a assinatura de
# e-mail depende de `var.alarm_email`, e um alarme sem destinatario nao e
# observabilidade.

# Erro que o proprio balanceador gerou, sem chegar a instancia nenhuma: nao ha
# alvo saudavel, ou todos recusaram a conexao. Distinguir do 5xx do alvo importa
# porque a causa e outra -- aqui o problema esta na camada de infraestrutura,
# nao no codigo da aplicacao.
resource "aws_cloudwatch_metric_alarm" "alb_5xx" {
  count = local.criar_app ? 1 : 0

  alarm_name        = "${local.name}-alb-5xx"
  alarm_description = "O balanceador esta respondendo erro sem alcancar as instancias."

  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_ELB_5XX_Count"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 5
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = aws_lb.app[0].arn_suffix
  }

  alarm_actions = [aws_sns_topic.alarms.arn]
}

# Erro que a aplicacao devolveu. Sucessor direto do `read_api_errors`, que
# observava a Lambda.
resource "aws_cloudwatch_metric_alarm" "alb_target_5xx" {
  count = local.criar_app ? 1 : 0

  alarm_name        = "${local.name}-app-5xx"
  alarm_description = "A API de leitura esta falhando: o dashboard nao carrega."

  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_Target_5XX_Count"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 5
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = aws_lb.app[0].arn_suffix
    TargetGroup  = aws_lb_target_group.app[0].arn_suffix
  }

  alarm_actions = [aws_sns_topic.alarms.arn]
}

# p95 e nao media: a media esconde a cauda, e e a cauda que o usuario percebe.
# O limiar de 5 s e o mesmo alvo do RNF02 (p99 < 5 s), medido em p95 para dar
# margem antes de o requisito ser efetivamente violado.
resource "aws_cloudwatch_metric_alarm" "alb_latencia" {
  count = local.criar_app ? 1 : 0

  alarm_name        = "${local.name}-app-latencia"
  alarm_description = "p95 do tempo de resposta acima do alvo do RNF02."

  namespace           = "AWS/ApplicationELB"
  metric_name         = "TargetResponseTime"
  extended_statistic  = "p95"
  period              = 300
  evaluation_periods  = 2
  threshold           = var.alarm_latencia_p95_segundos
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = aws_lb.app[0].arn_suffix
    TargetGroup  = aws_lb_target_group.app[0].arn_suffix
  }

  alarm_actions = [aws_sns_topic.alarms.arn]
}

# O ALARME MAIS IMPORTANTE DESTE ARQUIVO, e o gatilho declarado de rollback.
#
# Zero alvo saudavel significa que nenhuma instancia esta passando no health
# check. Depois de um deploy, a causa quase sempre e a versao nova: imagem que
# nao sobe, migration faltando, variavel de ambiente errada. E o sinal que manda
# apontar o launch template para a versao anterior (ver secao 5.3 do artefato).
#
# `treat_missing_data = "breaching"` aqui, ao contrario dos demais: ausencia de
# dado nesta metrica nao e silencio benigno, e o balanceador sem nada para
# medir.
resource "aws_cloudwatch_metric_alarm" "alb_sem_alvo_saudavel" {
  count = local.criar_app ? 1 : 0

  alarm_name        = "${local.name}-app-sem-alvo-saudavel"
  alarm_description = "Nenhuma instancia passa no health check. Gatilho de rollback do launch template."

  namespace           = "AWS/ApplicationELB"
  metric_name         = "HealthyHostCount"
  statistic           = "Minimum"
  period              = 60
  evaluation_periods  = 2
  threshold           = 1
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching"

  dimensions = {
    LoadBalancer = aws_lb.app[0].arn_suffix
    TargetGroup  = aws_lb_target_group.app[0].arn_suffix
  }

  alarm_actions = [aws_sns_topic.alarms.arn]
}

# A politica escalona por requisicao por alvo, nao por CPU (ver asg.tf). Mas CPU
# alta continua sendo sintoma que merece aviso: se ela subir sem que a contagem
# de requisicoes tenha subido, o problema nao e carga -- e consulta cara ou laco
# preso, e nenhuma quantidade de instancia nova resolve.
resource "aws_cloudwatch_metric_alarm" "asg_cpu" {
  count = local.criar_app ? 1 : 0

  alarm_name        = "${local.name}-app-cpu"
  alarm_description = "CPU alta nas instancias. Se a carga nao subiu junto, investigar consulta cara."

  namespace           = "AWS/EC2"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 3
  threshold           = 80
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    AutoScalingGroupName = aws_autoscaling_group.app[0].name
  }

  alarm_actions = [aws_sns_topic.alarms.arn]
}

# O grupo bateu no teto e nao tem mais para onde crescer. Nao e falha ainda, mas
# e o aviso de que a proxima rajada vira degradacao -- e o momento de rever
# `asg_max_size`.
resource "aws_cloudwatch_metric_alarm" "asg_no_maximo" {
  count = local.criar_app ? 1 : 0

  alarm_name        = "${local.name}-app-no-maximo"
  alarm_description = "O Auto Scaling Group esta no tamanho maximo. Sem margem para a proxima rajada."

  namespace           = "AWS/AutoScaling"
  metric_name         = "GroupInServiceInstances"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 2
  threshold           = var.asg_max_size
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    AutoScalingGroupName = aws_autoscaling_group.app[0].name
  }

  alarm_actions = [aws_sns_topic.alarms.arn]
}

# --------------------------------------------------------------------------- #
# Painel
# --------------------------------------------------------------------------- #

# Ate aqui o repositorio tinha 17 alarmes e nenhum painel: dava para saber que
# algo quebrou, nao para ver o sistema funcionando. As quatro linhas abaixo sao
# a leitura do caminho sincrono de cima para baixo -- carga que chega, tempo de
# resposta, quantas instancias respondem, e o banco por tras. E tambem o que se
# mostra no video enquanto o teste de carga roda.
resource "aws_cloudwatch_dashboard" "main" {
  count = local.criar_app ? 1 : 0

  dashboard_name = local.name

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Requisicoes e erros no ALB"
          region = var.region
          view   = "timeSeries"
          metrics = [
            ["AWS/ApplicationELB", "RequestCount", "LoadBalancer", aws_lb.app[0].arn_suffix, { stat = "Sum" }],
            [".", "HTTPCode_Target_5XX_Count", ".", ".", { stat = "Sum" }],
            [".", "HTTPCode_Target_4XX_Count", ".", ".", { stat = "Sum" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Tempo de resposta do alvo"
          region = var.region
          view   = "timeSeries"
          metrics = [
            ["AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", aws_lb.app[0].arn_suffix, { stat = "p50" }],
            ["...", { stat = "p95" }],
            ["...", { stat = "p99" }],
          ]
          annotations = {
            horizontal = [{ label = "alvo do RNF02", value = var.alarm_latencia_p95_segundos }]
          }
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "Escalonamento: instancias e requisicoes por alvo"
          region = var.region
          view   = "timeSeries"
          metrics = [
            ["AWS/AutoScaling", "GroupInServiceInstances", "AutoScalingGroupName", aws_autoscaling_group.app[0].name, { stat = "Average" }],
            ["AWS/ApplicationELB", "HealthyHostCount", "LoadBalancer", aws_lb.app[0].arn_suffix, "TargetGroup", aws_lb_target_group.app[0].arn_suffix, { stat = "Minimum" }],
            [".", "RequestCountPerTarget", ".", ".", ".", ".", { stat = "Sum" }],
          ]
          annotations = {
            horizontal = [{ label = "alvo da politica", value = var.asg_target_requests_per_target }]
          }
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "Banco"
          region = var.region
          view   = "timeSeries"
          metrics = [
            ["AWS/RDS", "CPUUtilization", "DBInstanceIdentifier", aws_db_instance.main.identifier, { stat = "Average" }],
            [".", "DatabaseConnections", ".", ".", { stat = "Average" }],
          ]
        }
      },
    ]
  })
}
