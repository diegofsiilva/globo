# Task avulsa que aplica migrations dentro da mesma VPC e do mesmo security
# group do processamento. Ela reutiliza a imagem de processing, que embarca o
# runner e os SQLs, e termina normalmente depois de aplicar o que estiver
# pendente.

resource "aws_ecs_task_definition" "migration" {
  family                   = "${local.name}-migration"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = local.task_execution_role_arn
  task_role_arn            = local.task_role_arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = var.worker_cpu_architecture
  }

  container_definitions = jsonencode([
    {
      name       = "migration"
      image      = local.image_uris["processing"]
      essential  = true
      entryPoint = ["python", "/app/tools/migrate.py"]
      command    = ["aplicar"]

      environment = concat(local.env_comum, [
        { name = "SERVICE_NAME", value = "${local.name}-migration" },
      ])

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.servicos["processing"].name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "migration"
        }
      }

      ulimits                = local.ulimits
      readonlyRootFilesystem = true
    }
  ])

  tags = {
    Name = "${local.name}-migration"
  }
}
