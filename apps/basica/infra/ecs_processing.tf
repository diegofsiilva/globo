# Servico de processamento: ETL incremental, detector e canario de qualidade.
#
# O ETL (bronze->silver e silver->gold) RODA -- ver "Watermarks e workers de
# transicao de camada" e db/migrations/015_etl_incremental.sql. Os dois workers
# sao duas threads dentro deste UNICO container (argus_processing/__main__.py),
# cada uma dona do seu watermark e da sua cadencia -- e nao dois servicos ECS
# separados, porque esta task definition, o log group e o alarme de
# RunningTaskCount ja estavam provisionados para hospedar processamento (ver
# comentario historico abaixo), e a atomicidade de cada ciclo mora no banco
# (uma unica chamada SQL por ciclo), nao em memoria compartilhada entre elas.
#
# Detector e canario de qualidade CONTINUAM no-op (decisao 7 do plano, agora
# parcial): dependem de logica que ainda nao existe (EWMA circadiano, cadencia
# esperada por fonte). O container existe provisionado e observavel para eles
# desde ja pelo mesmo motivo de sempre: a primeira versao do detector entra sem
# tocar em Terraform.

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
        {
          name  = "ETL_BRONZE_SILVER_INTERVAL_SECONDS"
          value = tostring(var.etl_bronze_silver_interval_seconds)
        },
        {
          name  = "ETL_BRONZE_SILVER_BATCH_SIZE"
          value = tostring(var.etl_bronze_silver_batch_size)
        },
        {
          name  = "ETL_SILVER_GOLD_INTERVAL_SECONDS"
          value = tostring(var.etl_silver_gold_interval_seconds)
        },
        {
          name  = "ETL_SILVER_GOLD_JANELA_MAX_SECONDS"
          value = tostring(var.etl_silver_gold_janela_max_segundos)
        },
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
