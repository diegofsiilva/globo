variable "region" {
  description = "Regiao AWS onde o fluxo e criado."
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Ambiente logico (dev, staging, prod). Entra no nome de todo recurso."
  type        = string
  default     = "dev"

  validation {
    condition     = can(regex("^[a-z0-9-]{2,12}$", var.environment))
    error_message = "environment deve ser minusculo, alfanumerico ou hifen, 2 a 12 caracteres."
  }
}

variable "name_prefix" {
  description = "Prefixo dos nomes. Isola este projeto dos outros que ja existem na conta."
  type        = string
  default     = "argus-events"
}

# --------------------------------------------------------------------------- #
# IAM
# --------------------------------------------------------------------------- #

variable "create_iam_roles" {
  description = <<-EOT
    `true` cria roles dedicadas com permissao minima (o correto numa conta
    normal). `false` reaproveita uma role ja existente em `existing_role_arn`.

    Ambientes de laboratorio (AWS Academy / Learner Lab) negam `iam:CreateRole`
    e obrigam o uso da `LabRole` que ja vem pronta -- por isso a chave existe.
    Note que a LabRole e MUITO mais permissiva do que este fluxo precisa: e uma
    concessao do ambiente, nao um padrao a copiar para producao.
  EOT
  type        = bool
  default     = true
}

variable "existing_role_arn" {
  description = <<-EOT
    Role usada quando `create_iam_roles = false`, nos tres papeis (credencial do
    API Gateway, execution role e task role do ECS).

    Precisa confiar em `apigateway.amazonaws.com` e `ecs-tasks.amazonaws.com`.
    A LabRole do AWS Academy confia nos dois.
  EOT
  type        = string
  default     = ""

  validation {
    condition     = var.create_iam_roles || var.existing_role_arn != ""
    error_message = "Com create_iam_roles = false, existing_role_arn e obrigatorio (ex.: a LabRole)."
  }
}

# --------------------------------------------------------------------------- #
# Rede
# --------------------------------------------------------------------------- #

variable "vpc_id" {
  description = "VPC onde as tasks Fargate rodam. Vazio usa a VPC default da conta."
  type        = string
  default     = ""
}

variable "subnet_ids" {
  description = <<-EOT
    Subnets das tasks Fargate. Vazio usa as subnets default da VPC.

    Se `assign_public_ip = true`, precisam ser subnets publicas (com rota para
    Internet Gateway). Se `false`, precisam ser privadas com NAT Gateway ou os
    VPC endpoints de sqs/dynamodb/ecr/logs -- caso contrario a task nem baixa a
    imagem do ECR e o service fica em crash loop.
  EOT
  type        = list(string)
  default     = []
}

variable "assign_public_ip" {
  description = <<-EOT
    IP publico na task. `true` evita o NAT Gateway (~US$ 32/mes + trafego), que
    seria o item mais caro do fluxo inteiro. A task nao aceita conexao de fora:
    o security group nao tem regra de entrada, so de saida.

    Em producao com dado sensivel, prefira `false` + subnet privada + VPC
    endpoints (ver infra/README.md).
  EOT
  type        = bool
  default     = true
}

# --------------------------------------------------------------------------- #
# DynamoDB
# --------------------------------------------------------------------------- #

variable "dynamodb_billing_mode" {
  description = "PAY_PER_REQUEST (sem planejar capacidade) ou PROVISIONED."
  type        = string
  default     = "PAY_PER_REQUEST"

  validation {
    condition     = contains(["PAY_PER_REQUEST", "PROVISIONED"], var.dynamodb_billing_mode)
    error_message = "dynamodb_billing_mode deve ser PAY_PER_REQUEST ou PROVISIONED."
  }
}

variable "dynamodb_kms_managed_key" {
  description = <<-EOT
    `true` usa a chave KMS gerenciada (aws/dynamodb): auditavel no CloudTrail,
    ~US$ 1/mes. `false` usa a chave AWS-owned, gratuita.

    Em nenhum dos dois casos a tabela fica sem criptografia -- o DynamoDB
    criptografa em repouso sempre. Ambiente de laboratorio precisa de `false`,
    porque nao consegue provisionar a chave gerenciada.
  EOT
  type        = bool
  default     = true
}

variable "dynamodb_point_in_time_recovery" {
  description = "PITR: restaura para qualquer segundo dos ultimos 35 dias. Custa ~20% do storage."
  type        = bool
  default     = true
}

variable "retention_days" {
  description = "Dias ate o TTL apagar o evento. Contado a partir da ingestao."
  type        = number
  default     = 90
}

variable "gsi1_shards" {
  description = <<-EOT
    Numero de shards da GSI1 (indice por tipo de evento e dia).

    Sem sharding, todo evento de um mesmo tipo num mesmo dia cai na mesma
    particao, e particao do DynamoDB satura em 1000 WCU -- o gargalo classico de
    ingestao de serie temporal. A leitura vira fan-out de N queries.

    Precisa ser igual a GSI1_SHARDS do worker: mudar aqui sem mudar la torna os
    dados antigos invisiveis para a query nova.
  EOT
  type        = number
  default     = 10

  validation {
    condition     = var.gsi1_shards >= 1 && var.gsi1_shards <= 100
    error_message = "gsi1_shards deve estar entre 1 e 100."
  }
}

# --------------------------------------------------------------------------- #
# SQS
# --------------------------------------------------------------------------- #

variable "visibility_timeout_seconds" {
  description = "Tempo que a mensagem fica invisivel apos o receive. Deve cobrir o pior caso de escrita."
  type        = number
  default     = 60
}

variable "max_receive_count" {
  description = "Tentativas antes de a mensagem ir para a DLQ pelo redrive."
  type        = number
  default     = 5
}

variable "message_retention_seconds" {
  description = "Quanto tempo a mensagem sobrevive na fila principal. Padrao 4 dias."
  type        = number
  default     = 345600
}

variable "dlq_retention_seconds" {
  description = "Retencao da DLQ. Maximo do SQS (14 dias) para dar tempo de investigar."
  type        = number
  default     = 1209600
}

# --------------------------------------------------------------------------- #
# API Gateway
# --------------------------------------------------------------------------- #

variable "api_throttle_rate_limit" {
  description = "Requisicoes por segundo em regime permanente."
  type        = number
  default     = 500
}

variable "api_throttle_burst_limit" {
  description = "Pico instantaneo de requisicoes."
  type        = number
  default     = 1000
}

variable "api_cors_allow_origins" {
  description = "Origens aceitas no CORS. ['*'] libera geral -- restrinja em producao."
  type        = list(string)
  default     = ["*"]
}

# --------------------------------------------------------------------------- #
# ECS
# --------------------------------------------------------------------------- #

variable "worker_image" {
  description = <<-EOT
    Imagem do worker. Vazio aponta para o repositorio ECR criado aqui, na tag
    `worker_image_tag`.

    Atencao: no primeiro apply o ECR esta vazio, entao o service sobe em crash
    loop ate o primeiro push. Ver o runbook em infra/README.md.
  EOT
  type        = string
  default     = ""
}

variable "worker_image_tag" {
  description = "Tag da imagem no ECR. Prefira o SHA do commit a `latest`."
  type        = string
  default     = "latest"
}

variable "worker_cpu" {
  description = "Unidades de CPU da task (256 = 0.25 vCPU)."
  type        = number
  default     = 256
}

variable "worker_memory" {
  description = "MiB de memoria da task. Combinacoes validas dependem do cpu."
  type        = number
  default     = 512
}

variable "worker_desired_count" {
  description = "Quantas tasks do worker manter no ar."
  type        = number
  default     = 1
}

variable "worker_cpu_architecture" {
  description = "ARM64 (Graviton) custa ~20% menos que X86_64 no Fargate."
  type        = string
  default     = "ARM64"

  validation {
    condition     = contains(["ARM64", "X86_64"], var.worker_cpu_architecture)
    error_message = "worker_cpu_architecture deve ser ARM64 ou X86_64."
  }
}

variable "container_insights" {
  description = "Container Insights do ECS: disabled, enabled ou enhanced. `enhanced` cobra por metrica."
  type        = string
  default     = "enabled"

  validation {
    condition     = contains(["disabled", "enabled", "enhanced"], var.container_insights)
    error_message = "container_insights deve ser disabled, enabled ou enhanced."
  }
}

variable "worker_log_level" {
  description = "Nivel de log do worker."
  type        = string
  default     = "INFO"
}

variable "log_retention_days" {
  description = "Retencao dos logs no CloudWatch. 0 = para sempre (nao recomendado: cresce sem teto)."
  type        = number
  default     = 30
}

# --------------------------------------------------------------------------- #
# Alarmes
# --------------------------------------------------------------------------- #

variable "alarm_email" {
  description = "E-mail para os alarmes. Vazio cria o topico SNS sem inscricao."
  type        = string
  default     = ""
}

variable "alarm_queue_age_seconds" {
  description = "Idade da mensagem mais antiga na fila que dispara alarme de atraso."
  type        = number
  default     = 300
}
