# Carga inicial: task definition one-shot, SEM service.
#
# Sem `aws_ecs_service` de proposito. O loader roda uma vez, le os Parquet do
# bucket de origem, faz COPY nas 33 tabelas da bronze e termina. Um service o
# reiniciaria em laco para sempre -- que e exatamente o comportamento errado
# para um trabalho que termina.
#
# Dispara com:
#   make load
# ou, na mao, `aws ecs run-task` com o comando que `terraform output
# loader_run_command` imprime.

resource "aws_ecs_task_definition" "loader" {
  family                   = "${local.name}-loader"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  # Bem mais folgado que os workers: o gargalo aqui e descompactar Parquet e
  # alimentar o COPY, e sao 68,7 M linhas para caber numa sessao de laboratorio.
  cpu                = var.loader_cpu
  memory             = var.loader_memory
  execution_role_arn = local.task_execution_role_arn
  task_role_arn      = local.task_role_arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = var.worker_cpu_architecture
  }

  # Disco efemero maior que o padrao de 20 GB: o loader baixa os Parquet do S3
  # antes de ler. Sao 199 MB compactados, mas o pyarrow precisa de espaco de
  # trabalho e 20 GB e o piso, nao uma folga.
  ephemeral_storage {
    size_in_gib = 40
  }

  container_definitions = jsonencode([
    {
      name      = "loader"
      image     = local.image_uris["loader"]
      essential = true

      environment = concat(local.env_comum, [
        { name = "SERVICE_NAME", value = "${local.name}-loader" },
        { name = "ORIGEM_BUCKET", value = local.origem_bucket_name },
        { name = "ORIGEM_PREFIX", value = "parquet/" },
        { name = "HEARTBEAT_PATH", value = "/tmp/argus-heartbeat" },
      ])

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.servicos["loader"].name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "load"
        }
      }

      ulimits = local.ulimits
      # Sem healthCheck: o container termina de proposito, e um healthcheck
      # marcaria o encerramento normal como falha.
      readonlyRootFilesystem = false
    }
  ])

  tags = {
    Name = "${local.name}-loader"
  }
}
