# Duas roles distintas, como manda o ECS:
#
#   execution role -> usada pelo AGENTE do ECS antes do container subir (puxar a
#                     imagem do ECR, criar log stream). Nao e o que o seu codigo
#                     usa.
#   task role      -> usada pelo CODIGO dentro do container. E aqui que mora a
#                     permissao de SQS e de metrica no CloudWatch. O acesso ao
#                     banco NAO passa por aqui: e usuario e GRANT no PostgreSQL,
#                     nao IAM.
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
    sid    = "ConsumirFilas"
    effect = "Allow"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:ChangeMessageVisibility",
    ]
    resources = [aws_sqs_queue.events.arn, aws_sqs_queue.changes.arn]
  }

  statement {
    sid    = "QuarentenarNasDLQ"
    effect = "Allow"
    # So SendMessage: os workers escrevem na DLQ mas nunca leem nem apagam de
    # la. Investigacao e redrive sao operacao manual, feita por gente.
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.dlq.arn, aws_sqs_queue.changes_dlq.arn]
  }

  statement {
    sid    = "LerOrigem"
    effect = "Allow"
    # Somente leitura, e somente deste bucket. O loader le os Parquet; nenhum
    # servico do fluxo tem permissao de escrever ali. O dump cedido pelo
    # parceiro nao pode ser sobrescrito por um bug nosso.
    actions   = ["s3:GetObject", "s3:ListBucket"]
    resources = [aws_s3_bucket.origem.arn, "${aws_s3_bucket.origem.arn}/*"]
  }

  # Nao ha permissao de RDS nenhuma aqui, e isso esta certo: a autenticacao no
  # PostgreSQL e por usuario e senha na DATABASE_URL, nao por IAM. As acoes
  # `rds:*` governam a INSTANCIA (criar, apagar, redimensionar), que e
  # exatamente o que uma task de aplicacao nao deve poder fazer.
}

resource "aws_iam_role_policy" "task" {
  count = var.create_iam_roles ? 1 : 0

  name   = "worker"
  role   = aws_iam_role.task[0].id
  policy = data.aws_iam_policy_document.task.json
}

# A senha do banco. Statement separado e condicional porque so existe no caminho
# do Secrets Manager -- com `db_password_from_secrets_manager = false` nao ha
# segredo a ler, e uma policy apontando para um ARN inexistente falharia o plan.
data "aws_iam_policy_document" "task_secret" {
  count = var.create_iam_roles && var.db_password_from_secrets_manager ? 1 : 0

  statement {
    sid       = "LerSenhaDoBanco"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.db[0].arn]
  }
}

resource "aws_iam_role_policy" "task_secret" {
  count = var.create_iam_roles && var.db_password_from_secrets_manager ? 1 : 0

  name   = "db-secret"
  role   = aws_iam_role.task[0].id
  policy = data.aws_iam_policy_document.task_secret[0].json
}

# O token de ingestao entra na task pelo bloco `secrets` da container
# definition, e quem o resolve e a EXECUTION role, nao a task role: o ECS busca
# o valor antes de o container existir. Conceder a task role aqui nao faria a
# task subir -- ela falharia em `ResourceInitializationError`, sem nenhum log da
# aplicacao para indicar o motivo.
data "aws_iam_policy_document" "execution_ingest_token" {
  count = var.create_iam_roles ? 1 : 0

  statement {
    sid       = "LerTokenDeIngestao"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.ingest_token.arn]
  }
}

resource "aws_iam_role_policy" "execution_ingest_token" {
  count = var.create_iam_roles ? 1 : 0

  name   = "ingest-token"
  role   = aws_iam_role.task_execution[0].id
  policy = data.aws_iam_policy_document.execution_ingest_token[0].json
}
