# Servico de processamento: detector, canario de qualidade e ETL.
#
# NO-OP por ora (decisao 7 do plano: processamento e deteccao seguem
# embrionarios). O container sobe, escreve heartbeat, dorme em laco e respeita
# SIGTERM. Nao ha logica de deteccao nenhuma dentro dele.
#
# Ele existe agora, vazio, para que a infraestrutura esteja provisionada e
# observavel quando a logica chegar: a task definition, o log group, o alarme de
# RunningTaskCount e o DATABASE_URL ja ficam corretos, e a primeira versao do
# detector entra sem tocar em Terraform. Retrofitar isso depois -- justamente na
# sprint em que se quer atencao no modelo -- custaria um ciclo de apply e de
# revisao de infra que nao tem nada a ver com o problema.

resource "aws_ecs_task_definition" "processing" {
  family                   = "${local.name}-processing"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.processing_cpu
  memory                   = var.processing_memory
  execution_role_arn       = local.task_execution_role_arn
  task_role_arn            = local.task_role_arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = var.worker_cpu_architecture
  }

  container_definitions = jsonencode([
    {
      name      = "processing"
      image     = local.image_uris["processing"]
      essential = true

      environment = concat(local.env_comum, [
        { name = "SERVICE_NAME", value = "${local.name}-processing" },
        { name = "TICK_SECONDS", value = tostring(var.processing_tick_seconds) },
        { name = "HEARTBEAT_PATH", value = "/tmp/argus-heartbeat" },
      ])

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.servicos["processing"].name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "proc"
        }
      }

      healthCheck            = local.healthcheck
      ulimits                = local.ulimits
      readonlyRootFilesystem = false
    }
  ])

  tags = {
    Name = "${local.name}-processing"
  }
}

resource "aws_ecs_service" "processing" {
  name            = "${local.name}-processing"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.processing.arn
  desired_count   = var.processing_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = local.subnet_ids
    security_groups  = [aws_security_group.worker.id]
    assign_public_ip = var.assign_public_ip
  }

  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  enable_execute_command = true

  tags = {
    Name = "${local.name}-processing"
  }
}
