# Duas roles distintas, como manda o ECS:
#
#   execution role -> usada pelo AGENTE do ECS antes do container subir (puxar a
#                     imagem do ECR, criar log stream). Nao e o que o seu codigo
#                     usa.
#   task role      -> usada pelo CODIGO dentro do container. E aqui que mora a
#                     permissao de SQS e DynamoDB.
#
# Separar as duas e o que impede o worker de, por exemplo, sobrescrever imagem no
# ECR: ele simplesmente nao tem essa credencial.

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }

    # Impede o "confused deputy": so tasks desta conta e deste cluster podem
    # assumir a role, mesmo que o ARN vaze.
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

# --------------------------------------------------------------------------- #
# Execution role
# --------------------------------------------------------------------------- #

resource "aws_iam_role" "task_execution" {
  count = var.create_iam_roles ? 1 : 0

  name               = "${local.name}-task-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "task_execution" {
  count = var.create_iam_roles ? 1 : 0

  role       = aws_iam_role.task_execution[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# --------------------------------------------------------------------------- #
# Task role: o que o worker realmente pode fazer
# --------------------------------------------------------------------------- #

resource "aws_iam_role" "task" {
  count = var.create_iam_roles ? 1 : 0

  name               = "${local.name}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

data "aws_iam_policy_document" "task" {
  statement {
    sid    = "ConsumirFilaPrincipal"
    effect = "Allow"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:ChangeMessageVisibility",
    ]
    resources = [aws_sqs_queue.events.arn]
  }

  statement {
    sid    = "QuarentenarNaDLQ"
    effect = "Allow"
    # So SendMessage: o worker escreve na DLQ mas nunca le nem apaga de la.
    # Investigacao e redrive sao operacao manual, feita por gente.
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.dlq.arn]
  }

  statement {
    sid    = "GravarEventos"
    effect = "Allow"
    # Sem DeleteItem e sem UpdateItem: este worker so insere. O expurgo e feito
    # pelo TTL do proprio DynamoDB, que nao precisa de permissao nossa.
    actions   = ["dynamodb:PutItem", "dynamodb:BatchWriteItem"]
    resources = [aws_dynamodb_table.events.arn]
  }
}

resource "aws_iam_role_policy" "task" {
  count = var.create_iam_roles ? 1 : 0

  name   = "worker"
  role   = aws_iam_role.task[0].id
  policy = data.aws_iam_policy_document.task.json
}
