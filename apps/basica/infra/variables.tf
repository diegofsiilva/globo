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
# RDS PostgreSQL
# --------------------------------------------------------------------------- #

variable "db_instance_class" {
  description = <<-EOT
    Classe da instancia RDS.

    db.t3.medium por conta de storage, nao de CPU: bronze ~13 GB, silver ~6 GB
    (signal_point duplicado), mais o change_log crescendo com o replay e o WAL.
    Os 199 MB de Parquet expandem bastante porque o PostgreSQL nao comprime
    heap -- prom_point sao 41,2 M x ~52 B ~ 2,1 GB de dados mais ~1,2 GB de
    indice.

    Se o laboratorio limitar a classe, db.t3.small ou micro seguem viaveis: as
    telas leem gold.v_* e nunca bronze, entao o tamanho de prom_point nao entra
    no caminho de leitura do dashboard.
  EOT
  type        = string
  default     = "db.t3.medium"
}

variable "db_allocated_storage" {
  description = "GB de gp3. Ver a conta de tamanho em db_instance_class."
  type        = number
  default     = 100
}

variable "db_engine_version" {
  description = <<-EOT
    Versao do PostgreSQL. So o major: a AWS escolhe o minor mais recente
    disponivel, e fixar o minor aqui faz o apply quebrar quando a AWS aposentar
    aquele numero especifico.

    As migrations foram validadas contra 16.15 em container local.
  EOT
  type        = string
  default     = "16"
}

variable "db_name" {
  description = "Nome do banco criado na instancia."
  type        = string
  default     = "argus"
}

variable "db_username" {
  description = "Usuario mestre. `postgres` e reservado pela AWS em algumas versoes."
  type        = string
  default     = "argus"
}

variable "db_password_from_secrets_manager" {
  description = <<-EOT
    `true` (padrao, o correto numa conta normal) gera a senha com
    `random_password` e guarda num `aws_secretsmanager_secret`.

    `false` cai para `var.db_password`, porque o ambiente de laboratorio pode
    negar o Secrets Manager. Em nenhum dos dois caminhos a senha entra em
    arquivo versionado: no primeiro ela nunca sai do Secrets Manager, no
    segundo vem do terraform.tfvars, que esta no .gitignore.
  EOT
  type        = bool
  default     = true
}

variable "db_password" {
  description = "Senha usada quando db_password_from_secrets_manager = false."
  type        = string
  default     = ""
  sensitive   = true

  validation {
    condition     = var.db_password == "" || length(var.db_password) >= 16
    error_message = "db_password precisa de ao menos 16 caracteres."
  }
}

variable "db_publicly_accessible" {
  description = <<-EOT
    Endereco publico na instancia.

    `false` e a postura de producao e o padrao aqui. A alternativa (RDS privado
    + Lambda dentro da VPC) custa cold start de ENI na Lambda e impede
    inspecionar o banco sem bastion, entao o laboratorio liga com `true` no
    tfvars -- o mesmo raciocinio que ja justifica o assign_public_ip do worker.

    Ligar isto NAO abre o banco: quem abre e db_allowed_cidr, e sem ele o
    security group nao tem regra de entrada nenhuma.
  EOT
  type        = bool
  default     = false
}

variable "db_allowed_cidr" {
  description = <<-EOT
    CIDR autorizado a conectar na porta 5432, alem dos servicos deste stack.

    Vazio (padrao) nao cria regra de entrada externa nenhuma. Preencha com o
    SEU IP em /32 para inspecionar o banco da sua maquina -- nunca 0.0.0.0/0,
    que expoe a instancia para a internet inteira.
  EOT
  type        = string
  default     = ""

  validation {
    condition     = var.db_allowed_cidr != "0.0.0.0/0"
    error_message = "0.0.0.0/0 expoe o banco para a internet inteira. Use o seu IP em /32."
  }
}

variable "db_backup_retention_days" {
  description = "Dias de backup automatico. 0 desliga (e desliga o PITR junto)."
  type        = number
  default     = 1
}

variable "db_multi_az" {
  description = "Multi-AZ dobra o custo. Falso fora de producao."
  type        = bool
  default     = false
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
# Simulador
# --------------------------------------------------------------------------- #

variable "simulator_desired_count" {
  description = <<-EOT
    Quantos simuladores manter no ar. 0 ou 1 -- nunca mais.

    Dois simuladores sao dois relogios competindo por `sim.clock`, e o tempo
    virtual passaria a andar para tras e para a frente conforme cada um
    reancorasse. Comece em 0: o simulador so faz sentido depois de a carga
    inicial ter rodado.
  EOT
  type        = number
  default     = 0

  validation {
    condition     = var.simulator_desired_count >= 0 && var.simulator_desired_count <= 1
    error_message = "simulator_desired_count so aceita 0 ou 1: dois relogios virtuais brigam pelo mesmo sim.clock."
  }
}

variable "simulator_seed" {
  description = <<-EOT
    Semente da injecao de falhas.

    Fixa de proposito: duas execucoes com a mesma seed produzem exatamente a
    mesma sequencia de falhas, que e o que permite comparar dois detectores
    sobre o mesmo cenario. Mudar a seed muda o cenario.
  EOT
  type        = number
  default     = 20260821
}

variable "simulator_speed" {
  description = "Tempo virtual por segundo de parede. 60 = 1 min/s (26 dias em ~10 h)."
  type        = number
  default     = 60
}

variable "simulator_t0" {
  description = "Inicio da janela replicada, em ISO-8601. Primeiro instante do dump."
  type        = string
  default     = "2026-07-12T00:00:00Z"
}

variable "simulator_t1" {
  description = "Fim da janela replicada, em ISO-8601. Ultimo instante do dump."
  type        = string
  default     = "2026-08-05T23:59:59Z"
}

variable "simulator_tick_seconds" {
  description = "Intervalo de parede entre dois avancos do relogio virtual."
  type        = number
  default     = 5
}

variable "simulator_cpu" {
  description = "Unidades de CPU da task do simulador."
  type        = number
  default     = 512
}

variable "simulator_memory" {
  description = "MiB de memoria do simulador."
  type        = number
  default     = 1024
}

# --------------------------------------------------------------------------- #
# Processamento (no-op por ora -- decisao 7)
# --------------------------------------------------------------------------- #

variable "processing_desired_count" {
  description = <<-EOT
    Tasks de processamento. 1 mantem a infraestrutura observavel mesmo com o
    container no-op, que e o ponto de provisiona-la agora; 0 economiza credito
    de laboratorio enquanto nao ha logica nenhuma la dentro.
  EOT
  type        = number
  default     = 1
}

variable "processing_tick_seconds" {
  description = "Intervalo do laco do container no-op entre dois heartbeats."
  type        = number
  default     = 30
}

variable "processing_cpu" {
  description = "Unidades de CPU do processamento."
  type        = number
  default     = 512
}

variable "processing_memory" {
  description = "MiB de memoria do processamento."
  type        = number
  default     = 1024
}

# --------------------------------------------------------------------------- #
# Loader da carga inicial
# --------------------------------------------------------------------------- #

variable "loader_cpu" {
  description = <<-EOT
    Unidades de CPU do loader (1024 = 1 vCPU).

    Bem acima dos workers porque o gargalo e descompactar Parquet e alimentar o
    COPY, e o alvo sao 20 a 30 minutos para 68,7 M linhas -- precisa caber com
    folga numa sessao do laboratorio.
  EOT
  type        = number
  default     = 2048
}

variable "loader_memory" {
  description = "MiB de memoria do loader."
  type        = number
  default     = 4096
}

# --------------------------------------------------------------------------- #
# Ingestao de eventos
# --------------------------------------------------------------------------- #

variable "changes_visibility_timeout_seconds" {
  description = <<-EOT
    Visibility timeout da fila de change events.

    Maior que o da fila de eventos porque o processamento aqui inclui um MERGE
    contra tabela particionada, e nao um INSERT. Curto demais faz o SQS
    reentregar uma mensagem que ainda esta sendo aplicada -- a regra do `_lsn`
    absorve a repeticao sem corromper nada, mas o trabalho e refeito a toa.
  EOT
  type        = number
  default     = 180
}

variable "max_clock_skew_days" {
  description = <<-EOT
    Desvio de relogio acima do qual o evento e marcado com clock_skew, mas
    NUNCA descartado. Relogio de TV e notoriamente errado, e jogar o evento
    fora perderia justamente o aparelho com problema.
  EOT
  type        = number
  default     = 365
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

# --------------------------------------------------------------------------- #
# API de leitura (dashboard)
# --------------------------------------------------------------------------- #

variable "read_api_package_path" {
  description = <<-EOT
    Caminho do zip da API de leitura.

    Precisa existir ANTES do plan: o Terraform calcula o hash do arquivo para
    saber se a funcao mudou. Gere com:
      ../backend/scripts/build_lambda.sh
  EOT
  type        = string
  default     = "../backend/dist/telemetry-read-api.zip"
}

variable "read_api_memory_mb" {
  description = <<-EOT
    Memoria da Lambda de leitura.

    1024 e nao 512 por medicao, nao por precaucao: na Lambda a fatia de CPU e
    proporcional a memoria, e o fan-out da GSI1 precisa de CPU para serializar
    dezenas de respostas em paralelo. Medido contra a tabela real, a busca por
    tipo caiu de ~2,8s (512 MB) para ~1,5s (1024 MB) -- a diferenca entre
    raspar no teto de 3s do RNF02 e ter folga. O custo a mais e desprezivel no
    volume de um dashboard.
  EOT
  type        = number
  default     = 1024
}

variable "read_api_timeout_seconds" {
  description = "Timeout da Lambda. Acima do teto de 3s do RNF02, com folga para cold start."
  type        = number
  default     = 30
}

variable "read_api_default_window_hours" {
  description = "Janela padrao das consultas sem periodo informado. Evita varrer a tabela sem querer."
  type        = number
  default     = 168
}

variable "read_api_max_items_scanned" {
  description = "Teto de itens lidos numa agregacao. Protege o tempo de resposta."
  type        = number
  default     = 20000
}

variable "read_api_throttle_rate_limit" {
  description = "Requisicoes por segundo da API de leitura."
  type        = number
  default     = 50
}

variable "read_api_throttle_burst_limit" {
  description = "Pico instantaneo da API de leitura."
  type        = number
  default     = 100
}

variable "dashboard_origins" {
  description = <<-EOT
    Origens do dashboard aceitas no CORS.

    ["*"] e aceitavel enquanto a API nao tem autenticacao e os dados sao de
    teste. Restrinja para o dominio do dashboard antes de producao: esta API
    serve dado, diferente da de ingestao, que so recebe.
  EOT
  type        = list(string)
  default     = ["*"]
}

variable "user_id_hash_salt" {
  description = <<-EOT
    Salt do hash de user_id na saida da API (RNF10).

    O DynamoDB guarda o identificador original porque a ingestao nao o
    transforma; o hash acontece na leitura. Trocar o salt reembaralha tudo:
    eventos do mesmo usuario deixam de agrupar com os antigos.
  EOT
  type        = string
  default     = "trocar-em-producao"
  sensitive   = true
}

variable "alarm_lag_sim_wall_seconds" {
  description = <<-EOT
    Quanto tempo de PAREDE o pipeline pode ficar atras antes de alarmar.

    O limiar do alarme e este valor multiplicado por `simulator_speed`, porque a
    metrica `LagSimSeconds` e medida em tempo VIRTUAL.

    A versao anterior fixava o limiar direto em 900 s virtuais, o que parecia
    certo -- medir em tempo de parede nao faz sentido para uma metrica virtual --
    mas era inatingivel na pratica. Com speed = 60, um unico minuto de parede
    processando um lote vira 3600 s virtuais de defasagem: o alarme ficava
    permanentemente disparado sem que nada estivesse errado.

    O que o operador consegue julgar e "o pipeline pode ficar dois minutos para
    tras". A conversao para tempo virtual e mecanica, e por isso e o Terraform
    que faz, e nao a pessoa.
  EOT
  type        = number
  default     = 120
}

variable "read_api_db_user" {
  description = <<-EOT
    Usuario que a Lambda de leitura usa. Criado pelas migrations, NAO pelo
    Terraform:

      python tools/migrate.py criar-leitor --usuario argus_api

    Ele nao recebe permissao nenhuma diretamente: so herda `argus_reader`, que
    so tem SELECT nas views v_*.
  EOT
  type        = string
  default     = "argus_api"
}

variable "read_api_db_password" {
  description = <<-EOT
    Senha do usuario de leitura. Vem do terraform.tfvars (gitignored) ou de
    TF_VAR_read_api_db_password, e precisa ser a mesma que voce passou em
    DB_READER_PASSWORD ao rodar `criar-leitor`.

    Nao e gerada aqui de proposito: o Terraform nao cria este usuario, entao
    gerar a senha do lado dele deixaria os dois lados sem como concordar.
  EOT
  type        = string
  default     = ""
  sensitive   = true
}
