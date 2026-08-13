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

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/ecs/${local.name}"
  retention_in_days = var.log_retention_days
}

# Sem regra de entrada: o worker faz polling, ninguem conecta nele. Com IP
# publico (assign_public_ip) ele ainda fica inalcancavel de fora, porque o
# security group nao abre nenhuma porta.
resource "aws_security_group" "worker" {
  name        = "${local.name}-worker"
  description = "Worker de ingestao: saida apenas"
  vpc_id      = local.vpc_id

  egress {
    description = "HTTPS para as APIs da AWS (SQS, DynamoDB, ECR, Logs)"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${local.name}-worker"
  }
}

resource "aws_ecs_task_definition" "worker" {
  family                   = local.name
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
      name      = "worker"
      image     = local.worker_image
      essential = true

      environment = [
        { name = "EVENTS_QUEUE_URL", value = aws_sqs_queue.events.url },
        { name = "EVENTS_DLQ_URL", value = aws_sqs_queue.dlq.url },
        { name = "EVENTS_TABLE_NAME", value = aws_dynamodb_table.events.name },
        { name = "AWS_REGION", value = var.region },
        { name = "LOG_LEVEL", value = var.worker_log_level },
        { name = "SERVICE_NAME", value = local.name },
        { name = "METRICS_NAMESPACE", value = "Argus/Ingestion" },
        { name = "RETENTION_DAYS", value = tostring(var.retention_days) },
        # Precisa casar com var.gsi1_shards: e o mesmo numero que monta a chave
        # da GSI1 na escrita e na leitura.
        { name = "GSI1_SHARDS", value = tostring(var.gsi1_shards) },
        { name = "SQS_VISIBILITY_TIMEOUT", value = tostring(var.visibility_timeout_seconds) },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.worker.name
          "awslogs-region"        = var.region
          "awslogs-stream-prefix" = "worker"
        }
      }

      healthCheck = {
        # O worker toca o heartbeat a cada ciclo, inclusive quando a fila esta
        # vazia -- fila vazia nao pode ser confundida com processo travado.
        command = [
          "CMD-SHELL",
          "python -c \"import os,sys,time; p=os.environ['HEARTBEAT_PATH']; sys.exit(0 if os.path.exists(p) and time.time()-os.path.getmtime(p) < 120 else 1)\"",
        ]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 20
      }

      # Sobe o limite de descritores: o pool de conexoes do botocore consome
      # varios e o default do Fargate e apertado.
      ulimits = [
        { name = "nofile", softLimit = 8192, hardLimit = 8192 },
      ]

      readonlyRootFilesystem = false # o heartbeat escreve em /tmp
    }
  ])

  tags = {
    Name = local.name
  }
}

resource "aws_ecs_service" "worker" {
  name            = local.name
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = var.worker_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = local.subnet_ids
    security_groups  = [aws_security_group.worker.id]
    assign_public_ip = var.assign_public_ip
  }

  # Deploy sem janela sem consumidor: sobe a nova task antes de derrubar a
  # velha. Como a escrita e idempotente, as duas rodando junto por alguns
  # segundos nao duplica nada.
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  deployment_circuit_breaker {
    enable   = true
    rollback = true # imagem quebrada volta sozinha para a versao anterior
  }

  enable_execute_command = true # `aws ecs execute-command` para debug

  # Nao ha `ignore_changes = [task_definition]` aqui de proposito: hoje o deploy
  # e feito pelo proprio Terraform, entao ignorar faria mudanca de variavel
  # (retention_days, gsi1_shards, log_level) aplicar sem efeito nenhum no
  # servico -- o pior tipo de bug, o silencioso. Quando existir um pipeline de
  # CD chamando `aws ecs update-service --task-definition`, ai sim adicione o
  # ignore_changes, senao os dois vao brigar pelo controle do servico.

  tags = {
    Name = local.name
  }
}
