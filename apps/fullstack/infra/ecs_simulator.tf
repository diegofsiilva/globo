# O simulador: relogio virtual, injecao de falhas e emissor de change events.
#
# E ele que faz o dump de 26 dias virar um fluxo. Avanca `sim.clock`, le a
# janela de bronze/silver a frente do relogio virtual, aplica as falhas de
# `sim.fault` com a seed fixa da `sim.run`, e emite os change events em
# POST /v1/changes -- pela rede, como a origem faria, e nao por INSERT direto no
# banco.
#
# A volta pela API e deliberada: e o que faz o caminho de ingestao ser exercido
# de verdade (API Gateway -> SQS -> merge worker -> MERGE), em vez de testado
# so na apresentacao. Um simulador que escrevesse direto na bronze validaria
# apenas a si mesmo.

resource "aws_ecs_task_definition" "simulator" {
  family                   = "${local.name}-simulator"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.simulator_cpu
  memory                   = var.simulator_memory
  execution_role_arn       = local.task_execution_role_arn
  task_role_arn            = local.task_role_arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = var.worker_cpu_architecture
  }

  container_definitions = jsonencode([
    {
      name      = "simulator"
      image     = local.image_uris["simulator"]
      essential = true

      environment = concat(local.env_comum, [
        { name = "CHANGES_URL", value = "${aws_apigatewayv2_api.events.api_endpoint}/v1/changes" },
        { name = "SERVICE_NAME", value = "${local.name}-simulator" },
        { name = "SIM_SEED", value = tostring(var.simulator_seed) },
        { name = "SIM_SPEED", value = tostring(var.simulator_speed) },
        { name = "SIM_T0", value = var.simulator_t0 },
        { name = "SIM_T1", value = var.simulator_t1 },
        { name = "SIM_TICK_SECONDS", value = tostring(var.simulator_tick_seconds) },
        { name = "HEARTBEAT_PATH", value = "/tmp/argus-heartbeat" },
      ])

      # `secrets` e nao `environment`: o ECS resolve o valor no momento de
      # subir a task, e ele nunca aparece no `describe-task-definition`. Ver o
      # comentario do segredo em auth.tf.
      secrets = [
        {
          name      = "CHANGES_TOKEN"
          valueFrom = aws_secretsmanager_secret.ingest_token.arn
        }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.servicos["simulator"].name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "sim"
        }
      }

      healthCheck            = local.healthcheck
      ulimits                = local.ulimits
      readonlyRootFilesystem = false
    }
  ])

  tags = {
    Name = "${local.name}-simulator"
  }
}

resource "aws_ecs_service" "simulator" {
  name            = "${local.name}-simulator"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.simulator.arn
  desired_count   = var.simulator_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = local.subnet_ids
    security_groups  = [aws_security_group.worker.id]
    assign_public_ip = var.assign_public_ip
  }

  # Nunca dois simuladores ao mesmo tempo: sao dois relogios competindo por
  # `sim.clock`, e o tempo virtual passaria a andar para tras e para a frente.
  deployment_minimum_healthy_percent = 0
  deployment_maximum_percent         = 100

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  enable_execute_command = true

  tags = {
    Name = "${local.name}-simulator"
  }
}
