resource "aws_ecs_cluster" "main" {
  name = local.name

  # "enhanced" cobra por metrica e sai bem mais caro que o proprio Fargate deste
  # stack. "enabled" ja da CPU/memoria/rede por task, que e o que interessa aqui.
  setting {
    name  = "containerInsights"
    value = var.container_insights
  }

  tags = {
    Name = local.name
  }
}

# Um log group por servico. Separados porque `aws logs tail` num group unico com
# cinco containers e ilegivel exatamente na hora em que se precisa dele.
resource "aws_cloudwatch_log_group" "servicos" {
  # `backend` esta em `container_images` para ganhar repositorio no ECR, mas nao
  # roda no ECS -- ele executa como Deployment no cluster EKS (k8s/), e a Lambda
  # de contingencia tem log group proprio (api_read.tf). Um log group
  # `/ecs/<name>/backend` aqui ficaria vazio para sempre.
  for_each = setsubtract(local.container_images, ["backend"])

  name              = "/ecs/${local.name}/${each.key}"
  retention_in_days = var.log_retention_days
}

# Security group unico para todas as tasks. Nenhuma regra de entrada: os workers
# fazem polling e o simulador so faz chamada de saida, entao ninguem conecta
# neles. Com IP publico (assign_public_ip) eles continuam inalcancaveis de fora.
resource "aws_security_group" "worker" {
  name        = "${local.name}-tasks"
  description = "Tasks Fargate do Argus: saida apenas"
  vpc_id      = local.vpc_id

  # NENHUMA regra inline aqui, de proposito.
  #
  # Um bloco `egress` dentro do `aws_security_group` assume posse EXCLUSIVA da
  # saida: no apply seguinte o provider apaga toda regra de egress que nao esteja
  # declarada nele -- inclusive as criadas por `aws_security_group_rule`. Foi
  # exatamente o que aconteceu aqui: com o 443 inline, a regra `tasks_to_rds`
  # nascia no primeiro apply e era removida no segundo, e a Lambda passava a
  # levar `PoolTimeout` em toda rota que toca o banco.
  #
  # Com as duas regras do lado de fora, elas convivem.

  tags = {
    Name = "${local.name}-tasks"
  }
}

resource "aws_security_group_rule" "tasks_https" {
  type              = "egress"
  description       = "HTTPS para as APIs da AWS (SQS, S3, ECR, Logs) e para /v1/changes"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  security_group_id = aws_security_group.worker.id
  cidr_blocks       = ["0.0.0.0/0"]
}

# A saida para o banco aponta para OUTRO security group. Referenciar o grupo do
# RDS em vez de um CIDR e o que mantem a regra correta quando a instancia troca
# de IP.
resource "aws_security_group_rule" "tasks_to_rds" {
  type                     = "egress"
  description              = "PostgreSQL no RDS deste stack"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.worker.id
  source_security_group_id = aws_security_group.rds.id
}

# --------------------------------------------------------------------------- #
# Healthcheck comum
# --------------------------------------------------------------------------- #

locals {
  # Todo container do fluxo toca o mesmo arquivo de heartbeat a cada ciclo,
  # INCLUSIVE quando nao ha trabalho -- fila vazia nao pode ser confundida com
  # processo travado.
  healthcheck = {
    command = [
      "CMD-SHELL",
      "python -c \"import os,sys,time; p=os.environ['HEARTBEAT_PATH']; sys.exit(0 if os.path.exists(p) and time.time()-os.path.getmtime(p) < 120 else 1)\"",
    ]
    interval    = 30
    timeout     = 5
    retries     = 3
    startPeriod = 30
  }

  ulimits = [{ name = "nofile", softLimit = 8192, hardLimit = 8192 }]
}

# --------------------------------------------------------------------------- #
# Merge worker: /v1/changes -> change_log -> MERGE na bronze corrente
# --------------------------------------------------------------------------- #

resource "aws_ecs_task_definition" "merge_worker" {
  family                   = "${local.name}-merge-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.worker_cpu
  memory                   = var.worker_memory
  execution_role_arn       = local.task_execution_role_arn
  task_role_arn            = local.task_role_arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = var.worker_cpu_architecture
  }

  container_definitions = jsonencode([
    {
      name      = "merge-worker"
      image     = local.image_uris["worker"]
      command   = ["merge"]
      essential = true

      environment = concat(local.env_comum, [
        { name = "CHANGES_QUEUE_URL", value = aws_sqs_queue.changes.url },
        { name = "CHANGES_DLQ_URL", value = aws_sqs_queue.changes_dlq.url },
        { name = "SERVICE_NAME", value = "${local.name}-merge-worker" },
        { name = "SQS_VISIBILITY_TIMEOUT", value = tostring(var.changes_visibility_timeout_seconds) },
        { name = "HEARTBEAT_PATH", value = "/tmp/argus-heartbeat" },
      ])

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.servicos["worker"].name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "merge"
        }
      }

      healthCheck            = local.healthcheck
      ulimits                = local.ulimits
      readonlyRootFilesystem = false # o heartbeat escreve em /tmp
    }
  ])

  tags = {
    Name = "${local.name}-merge-worker"
  }
}

resource "aws_ecs_service" "merge_worker" {
  name            = "${local.name}-merge-worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.merge_worker.arn
  desired_count   = var.worker_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = local.subnet_ids
    security_groups  = [aws_security_group.worker.id]
    assign_public_ip = var.assign_public_ip
  }

  # Aqui, ao contrario do worker de eventos, o deploy DERRUBA antes de subir.
  #
  # Dois merge workers rodando ao mesmo tempo aplicam faixas sobrepostas do log
  # e disputam lock nas mesmas linhas da bronze corrente. O resultado final
  # continua correto -- a regra do `_lsn` maior garante isso --, mas o custo sao
  # deadlocks e retry durante toda a janela de deploy. Uma pausa de segundos no
  # consumo e mais barata: o SQS segura as mensagens.
  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  enable_execute_command = true

  tags = {
    Name = "${local.name}-merge-worker"
  }
}

# --------------------------------------------------------------------------- #
# Event worker: /v1/events -> bronze.event
# --------------------------------------------------------------------------- #

resource "aws_ecs_task_definition" "event_worker" {
  family                   = "${local.name}-event-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.worker_cpu
  memory                   = var.worker_memory
  execution_role_arn       = local.task_execution_role_arn
  task_role_arn            = local.task_role_arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = var.worker_cpu_architecture
  }

  container_definitions = jsonencode([
    {
      name      = "event-worker"
      image     = local.image_uris["worker"]
      command   = ["event"]
      essential = true

      environment = concat(local.env_comum, [
        { name = "EVENTS_QUEUE_URL", value = aws_sqs_queue.events.url },
        { name = "EVENTS_DLQ_URL", value = aws_sqs_queue.dlq.url },
        { name = "SERVICE_NAME", value = "${local.name}-event-worker" },
        { name = "SQS_VISIBILITY_TIMEOUT", value = tostring(var.visibility_timeout_seconds) },
        { name = "MAX_CLOCK_SKEW_DAYS", value = tostring(var.max_clock_skew_days) },
        { name = "HEARTBEAT_PATH", value = "/tmp/argus-heartbeat" },
      ])

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.servicos["worker"].name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "event"
        }
      }

      healthCheck            = local.healthcheck
      ulimits                = local.ulimits
      readonlyRootFilesystem = false
    }
  ])

  tags = {
    Name = "${local.name}-event-worker"
  }
}

resource "aws_ecs_service" "event_worker" {
  name            = "${local.name}-event-worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.event_worker.arn
  desired_count   = var.worker_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = local.subnet_ids
    security_groups  = [aws_security_group.worker.id]
    assign_public_ip = var.assign_public_ip
  }

  # Aqui sobe antes de derrubar: a escrita em bronze.event e um INSERT
  # idempotente por (ts, event_id), entao dois consumidores em paralelo por
  # alguns segundos nao duplicam nada -- e evento de TV nao espera na fila de
  # bom grado.
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  enable_execute_command = true

  tags = {
    Name = "${local.name}-event-worker"
  }
}
