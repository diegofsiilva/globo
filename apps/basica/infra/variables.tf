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
    VPC endpoints de sqs/ecr/logs/secretsmanager -- caso contrario a task nem
    baixa a imagem do ECR e o service fica em crash loop.
  EOT
  type        = list(string)
  default     = []
}

variable "assign_public_ip" {
  description = <<-EOT
    IP publico na task Fargate. O padrao e `false`, e ele anda junto com
    `create_network = true`: a task fica na sub-rede PRIVADA e alcanca ECR, SQS
    e Secrets Manager pelo NAT Gateway.

    As duas chaves nao sao independentes -- as quatro combinacoes nao valem:

      create_network | assign_public_ip | resultado
      ---------------|------------------|---------------------------------------
      true           | false            | correto: privada + NAT
      true           | true             | QUEBRA: a task ganha IP publico numa
                                          sub-rede sem rota para o Internet
                                          Gateway. O endereco nao serve para
                                          nada, o pull do ECR falha e o service
                                          entra em crash loop
      false          | true             | comportamento anterior a esta sprint:
                                          VPC default, task com IP publico
      false          | false            | QUEBRA: sem NAT e sem IP publico a
                                          task nao tem rota nenhuma de saida

    O unico controle que impedia alguem de alcancar a task no desenho antigo era
    o security group sem regra de entrada. Com sub-rede privada some tambem a
    rota: dois controles independentes em vez de um.
  EOT
  type        = bool
  default     = false

  # A combinacao invalida vira erro de plan, e nao crash loop no ECS.
  #
  # Sem esta regra o sintoma chega horas depois e no lugar errado: o service
  # nao estabiliza, o evento do ECS fala em "unable to pull image", e nada
  # aponta para a variavel de rede que causou. Terraform >= 1.9 permite validar
  # olhando outra variavel; e o que torna a checagem possivel aqui.
  validation {
    condition     = !(var.create_network && var.assign_public_ip)
    error_message = "assign_public_ip = true com create_network = true poe a task numa sub-rede privada, que nao tem rota para o Internet Gateway: o IP publico nao serve para nada e o pull do ECR falha. Use false (a task sai pelo NAT) ou desligue create_network."
  }
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
    Legado — mantido apenas para compatibilidade com tfvars antigos.

    A instancia RDS eh fixada em `publicly_accessible = false` diretamente em
    `rds.tf` por exigencia da rubrica (3). Esta variavel eh IGNORADA pelo
    recurso; mantem-se aqui para nao quebrar `terraform plan` de workspaces
    que ainda a definem. Para acesso administrativo use a task `migration`:

      cd infra && terraform output -raw migration_status_command | bash
      cd infra && terraform output -raw migration_run_command | bash

    Qualquer valor diferente de `false` eh rejeitado para evitar reexposicao
    acidental do banco.
  EOT
  type        = bool
  default     = false

  validation {
    condition     = var.db_publicly_accessible == false
    error_message = "db_publicly_accessible deve ser false — o RDS eh privado por exigencia da rubrica. Use a task migration dentro da VPC para administracao."
  }
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
  description = <<-EOT
    Tag da imagem que as task definitions referenciam. **Precisa ser o SHA do
    commit**, e nao `latest`.

    Com `latest`, a task definition nao muda quando a imagem muda: o Terraform
    ve a mesma string, nao propoe nada, e o servico continua rodando o digest
    antigo ate alguem forcar um deploy a mao. Foi assim que event worker, merge
    worker e processing passaram a executar builds diferentes entre si sem que
    nada no `plan` indicasse isso.

    Com o SHA, a task definition muda junto com o codigo, o `plan` mostra a
    diferenca e o rollback e escolher o SHA anterior.

    `make push` e `make deploy` preenchem sozinhos, via `TF_VAR_worker_image_tag`.
    Para rodar `terraform` direto:

      export TF_VAR_worker_image_tag=$(git rev-parse --short=12 HEAD)
  EOT
  type        = string

  validation {
    condition     = var.worker_image_tag != "latest" && var.worker_image_tag != ""
    error_message = "worker_image_tag precisa ser o SHA do commit. `latest` so existe como apelido no ECR, nunca como referencia da task definition."
  }
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
# Processamento (ETL incremental ligado; detector e canario seguem no-op --
# decisao 7 parcial)
# --------------------------------------------------------------------------- #

variable "processing_desired_count" {
  description = <<-EOT
    Tasks de processamento. 1 mantem os dois workers de ETL (bronze->silver e
    silver->gold, rodando como threads dentro do mesmo container -- ver
    argus_processing/__main__.py) no ar; 0 economiza credito de laboratorio.
  EOT
  type        = number
  default     = 1
}

variable "processing_tick_seconds" {
  description = "Intervalo do laco principal (heartbeat/healthcheck) entre duas batidas."
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

variable "etl_bronze_silver_interval_seconds" {
  description = <<-EOT
    Cadencia do worker bronze->silver: quase linha-a-linha, por isso o padrao
    e curto. Ver publicacao "Watermarks e workers de transicao de camada".
  EOT
  type        = number
  default     = 60
}

variable "etl_bronze_silver_batch_size" {
  description = "Teto de entradas do bronze.change_log processadas por chamada."
  type        = number
  default     = 5000
}

variable "etl_silver_gold_interval_seconds" {
  description = <<-EOT
    Cadencia do worker silver->gold: mais espacada, porque carrega uma janela
    de recomputacao mais cara (EWMA circadiano, casamento com incident_window).
  EOT
  type        = number
  default     = 900
}

variable "etl_silver_gold_janela_max_segundos" {
  description = <<-EOT
    Teto de tempo virtual absorvido por chamada do worker silver->gold.
    PRECISA ser maior que etl.watermark_silver_gold.margem_seguranca (2h por
    default no banco), senao etl.executar_silver_gold recusa rodar -- ver o
    comentario da funcao em db/migrations/015_etl_incremental.sql.
  EOT
  type        = number
  default     = 14400
}

variable "analysis_enabled" {
  description = "Habilita a terceira thread de detector, canario e hipoteses."
  type        = bool
  default     = true
}

variable "analysis_poll_seconds" {
  description = "Intervalo entre polls quando nao existe checkpoint analisavel."
  type        = number
  default     = 30
}

variable "analysis_lease_seconds" {
  description = "Duracao do lease de um run de analise."
  type        = number
  default     = 120
}

variable "analysis_heartbeat_seconds" {
  description = "Intervalo de renovacao do lease da analise."
  type        = number
  default     = 30
}

variable "analysis_max_input_rows" {
  description = "Teto de fatos capturados por run; exceder falha sem mover o cursor."
  type        = number
  default     = 250000
}

variable "analysis_max_candidates" {
  description = "Teto global de candidatos avaliados por run."
  type        = number
  default     = 10000
}

variable "analysis_max_candidates_per_family" {
  description = "Teto de candidatos avaliados por familia e run."
  type        = number
  default     = 2000
}

variable "analysis_max_generated" {
  description = "Teto de hipoteses generated persistidas por run."
  type        = number
  default     = 500
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

variable "alarm_4xx_threshold" {
  description = <<-EOT
    Respostas 4xx em 5 minutos na API de leitura que disparam alarme.

    Recusa e evento normal (cliente sem token, sessao expirada). O que nao e
    normal e um VOLUME subito delas -- o formato de quem tenta adivinhar o
    token. O padrao e alto o bastante para nao alarmar com alguem errando a
    colagem algumas vezes.
  EOT
  type        = number
  default     = 50
}

# --------------------------------------------------------------------------- #
# Autenticacao (Lambda authorizer)
# --------------------------------------------------------------------------- #

variable "authorizer_package_path" {
  description = <<-EOT
    Caminho do zip do Lambda authorizer.

    Precisa existir ANTES do plan, como o da API de leitura. Gere com:
      ../authorizer/scripts/build_lambda.sh

    `make tf-plan`, `tf-apply` e `deploy` ja chamam os dois builds antes.
  EOT
  type        = string
  default     = "../authorizer/dist/argus-authorizer.zip"
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
    proporcional a memoria, e serializar uma agregacao grande em JSON e trabalho
    de CPU. Medido contra o banco real, a busca por tipo de evento caiu de
    ~2,8s (512 MB) para ~1,5s (1024 MB) -- a diferenca entre raspar no teto de
    5s do RNF02 e ter folga. O custo a mais e desprezivel no volume de um
    dashboard.
  EOT
  type        = number
  default     = 1024
}

variable "read_api_timeout_seconds" {
  description = "Timeout da Lambda. Acima do teto de 5s do RNF02, com folga para cold start."
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

variable "hypothesis_feedback_throttle_rate_limit" {
  description = "Requisicoes por segundo da escrita publica de feedback."
  type        = number
  default     = 5
}

variable "hypothesis_feedback_throttle_burst_limit" {
  description = "Burst da escrita publica de feedback."
  type        = number
  default     = 10
}

variable "dashboard_origins_extra" {
  description = <<-EOT
    Origens ADICIONAIS aceitas no CORS da API de leitura, alem do website S3.

    O dominio do dashboard entra sozinho
    (`aws_s3_bucket_website_configuration`); esta lista existe para o
    desenvolvimento local, onde a origem e
    `http://localhost:3000`. Deixe vazia no ambiente de entrega.

    Nao use ["*"]: com autenticacao por token no navegador, uma origem coringa
    permitiria que qualquer pagina aberta pelo operador lesse as respostas da
    API usando o token dele.
  EOT
  type        = list(string)
  default     = []
}

variable "user_id_hash_salt" {
  description = <<-EOT
    Salt do hash de user_id na saida da API (RNF10).

    A bronze guarda o identificador original porque a ingestao nao o
    transforma; o hash acontece na LEITURA (`application/redaction.py`). Trocar
    o salt reembaralha tudo: eventos do mesmo usuario deixam de agrupar com os
    antigos.
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

# --------------------------------------------------------------------------- #
# Rede dedicada (VPC, sub-redes, NAT)
# --------------------------------------------------------------------------- #

variable "create_network" {
  description = <<-EOT
    Cria a VPC dedicada, as sub-redes publica e privada em duas AZs, o Internet
    Gateway, o NAT Gateway e as tabelas de rota -- mais tudo que depende delas:
    bastion, ALB e Auto Scaling Group.

    `false` mantem o comportamento anterior a esta sprint: todo o stack roda na
    VPC default da conta, com IP publico nas tasks. Existe para que a migracao
    possa ser planejada e validada antes de ser aplicada, e para que uma conta
    onde o papel do laboratorio recuse criar VPC ainda consiga subir o resto.

    CUIDADO ao trocar de `true` para `false` num ambiente ja aplicado: o RDS nao
    muda de VPC, e mover o subnet group forca a SUBSTITUICAO da instancia --
    o que apaga o banco. Numa conta nova isso nao e problema, porque o banco ja
    nasce na VPC nova (ver secao 4.1 do artefato).
  EOT
  type        = bool
  default     = true
}

variable "vpc_cidr" {
  description = <<-EOT
    Bloco da VPC dedicada. /16 da folga para crescer sem renumerar: as quatro
    sub-redes de hoje ocupam quatro /24, e sobram 252.
  EOT
  type        = string
  default     = "10.0.0.0/16"

  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0))
    error_message = "vpc_cidr precisa ser um bloco CIDR valido, por exemplo 10.0.0.0/16."
  }
}

variable "public_subnet_cidrs" {
  description = <<-EOT
    Sub-redes publicas, uma por zona de disponibilidade. Executam o ALB, o NAT
    Gateway e o bastion -- os unicos recursos com motivo para ter endereco
    roteavel.

    Vazio (o padrao) DERIVA as faixas de `vpc_cidr` com `cidrsubnet`: um /24 por
    AZ a partir do inicio da VPC. Derivar em vez de fixar e o que impede a falha
    silenciosa de trocar `vpc_cidr` e esquecer esta lista -- as sub-redes
    nasceriam fora da VPC e o apply quebraria com "InvalidSubnet.Range", um erro
    que nao aponta para a variavel que o causou.

    Preencher a mao so faz sentido para casar com uma faixa que ja exista fora
    do Terraform. Nesse caso precisam ser pelo menos duas: o Application Load
    Balancer exige sub-redes em no minimo duas AZs distintas.
  EOT
  type        = list(string)
  default     = []

  validation {
    condition     = length(var.public_subnet_cidrs) == 0 || length(var.public_subnet_cidrs) >= 2
    error_message = "Deixe vazio para derivar de vpc_cidr, ou informe no minimo duas (exigencia do ALB)."
  }
}

variable "private_subnet_cidrs" {
  description = <<-EOT
    Sub-redes privadas, uma por zona de disponibilidade. Executam as instancias
    do Auto Scaling Group, as tasks Fargate e o subnet group do RDS. Sem rota
    para o Internet Gateway: a saida e pelo NAT.

    Vazio (o padrao) deriva de `vpc_cidr`, com um salto de 10 no indice em
    relacao as publicas: `10.0.10.0/24` e `10.0.11.0/24` num `10.0.0.0/16`. O
    salto e legibilidade pura -- olhando um IP num flow log, o terceiro octeto
    ja diz de que lado da rede ele veio.

    Duas no minimo, porque o subnet group do RDS exige duas AZs e porque o ASG
    precisa poder substituir instancia na zona que sobrou.
  EOT
  type        = list(string)
  default     = []

  validation {
    condition     = length(var.private_subnet_cidrs) == 0 || length(var.private_subnet_cidrs) >= 2
    error_message = "Deixe vazio para derivar de vpc_cidr, ou informe no minimo duas (RDS e ASG)."
  }
}

variable "azs" {
  description = <<-EOT
    Zonas de disponibilidade da rede. Vazio (o padrao) usa as duas primeiras que
    a conta oferecer.

    O nome da zona nao e portavel entre contas: o "us-east-1a" de uma conta pode
    ser o hardware que a outra enxerga como "us-east-1c", e nem toda conta do
    Learner Lab recebe a mesma lista. Por isso o padrao consulta em vez de fixar.
    Fixar aqui so importa quando o laboratorio restringe alguma zona -- caso em
    que o sintoma, sem esta variavel, apareceria como "capacidade insuficiente"
    no meio do apply.
  EOT
  type        = list(string)
  default     = []

  validation {
    condition     = length(var.azs) == 0 || length(var.azs) >= 2
    error_message = "azs precisa estar vazio ou conter ao menos duas zonas (ALB e subnet group do RDS)."
  }
}

# --------------------------------------------------------------------------- #
# Bastion
# --------------------------------------------------------------------------- #

variable "bastion_allowed_cidr" {
  description = <<-EOT
    Unico CIDR autorizado na porta 22 do bastion. Preencha com o IP da sua rede
    em /32.

    A validacao recusa 0.0.0.0/0 de proposito: um bastion aberto para a internet
    inteira nao reduz exposicao nenhuma -- apenas acrescenta um salto ao caminho
    do atacante. O custo da restricao e real e esta assumido: quem trocar de rede
    perde o acesso ate atualizar esta variavel e reaplicar.
  EOT
  type        = string
  default     = "0.0.0.0/32"

  validation {
    condition     = var.bastion_allowed_cidr != "0.0.0.0/0"
    error_message = "0.0.0.0/0 expoe a porta 22 para a internet inteira. Use o seu IP em /32."
  }
}

variable "bastion_key_name" {
  description = <<-EOT
    Nome de um key pair EC2 que ja exista na conta. Vazio (padrao) NAO cria o
    bastion -- sem chave a instancia seria inalcancavel, e pagar por ela seria
    desperdicio.

    A chave privada nunca entra no repositorio. Crie o par no console ou com
    `aws ec2 create-key-pair --profile g4` e guarde o .pem fora da arvore.
  EOT
  type        = string
  default     = ""
}

variable "bastion_instance_type" {
  description = <<-EOT
    Tipo do bastion. O menor possivel de proposito: ele so encaminha SSH e abre
    um psql eventual, entao qualquer coisa maior seria custo sem uso -- e uma
    maquina ociosa maior e superficie maior.

    Familia `t4g` (Graviton, arm64) para casar com a AMI arm64 do bastion e do
    ASG. Ver a nota sobre arquitetura em `app_instance_type`.
  EOT
  type        = string
  default     = "t4g.micro"
}

# --------------------------------------------------------------------------- #
# Camada de aplicacao: ALB e Auto Scaling Group
# --------------------------------------------------------------------------- #

variable "app_port" {
  description = <<-EOT
    Porta em que o gunicorn escuta na instancia, e para a qual o target group
    encaminha. 5000 e a porta que backend/Dockerfile expoe -- mudar aqui sem
    mudar la faz o health check reprovar todas as instancias.
  EOT
  type        = number
  default     = 5000
}

variable "app_instance_type" {
  description = <<-EOT
    Tipo das instancias do Auto Scaling Group.

    `small` e nao `micro`: o container roda gunicorn com 2 workers x 4 threads
    mais o agente CloudWatch, e 1 GiB de memoria fica no limite durante o
    `docker pull`. Nao e instancia grande de proposito -- a resposta a carga
    aqui e horizontal, e nao vertical; e para isso que existe o grupo.

    ARQUITETURA: familia `t4g`, que e Graviton (arm64). Isto NAO e escolha de
    custo, e requisito de compatibilidade: `make push` constroi todas as imagens
    com `--platform linux/arm64`, e uma instancia x86_64 nao executaria a imagem
    -- o `docker run` do user_data falharia com "exec format error", e o sintoma
    chegaria como instancia reprovando no health check, longe da causa.

    Trocar por uma familia x86 (`t3`, `t2`) exige trocar junto a AMI em
    bastion.tf e o `--platform` do Makefile.
  EOT
  type        = string
  default     = "t4g.small"
}

variable "asg_min_size" {
  description = <<-EOT
    Minimo de instancias. Dois, e nao um: com uma instancia so, perde-la e
    indisponibilidade total ate a substituta subir -- vaos de varios minutos,
    contando boot e pull da imagem. Com duas em AZs distintas, a perda de uma
    instancia ou de uma zona inteira degrada a capacidade sem derrubar o servico.

    ZERO tambem e valido, e significa outra coisa: o caminho de leitura saiu
    daqui e foi para o cluster Kubernetes (eks.tf). Nesse caso o grupo nao serve
    ninguem, e manter duas instancias ligadas seria pagar duas vezes pela mesma
    API. O grupo continua no estado -- launch template, target group e politicas
    intactos --, entao voltar e trocar este valor, nao refazer o apply.
  EOT
  type        = number
  default     = 2

  validation {
    # Um e o unico valor proibido: e o que parece alta disponibilidade e nao e.
    # Zero e uma decisao explicita (o grupo esta desligado); dois ou mais e o
    # grupo servindo com folga. Um e o meio-termo que so aparece como problema
    # no dia em que a instancia cai.
    condition     = var.asg_min_size == 0 || var.asg_min_size >= 2
    error_message = "Use 0 (grupo desligado, caminho de leitura no cluster) ou >= 2 (a perda de uma instancia nao derruba o servico). O valor 1 nao e aceito: parece redundante e nao e."
  }
}

variable "asg_max_size" {
  description = <<-EOT
    Teto de instancias. Existe para limitar o estrago de uma rajada anomala ou
    de um laco de requisicao: sem teto, a politica escalaria ate esgotar o
    credito do laboratorio. Seis cobre com folga a carga do rnf02.
  EOT
  type        = number
  default     = 6
}

variable "asg_desired_capacity" {
  description = <<-EOT
    Tamanho inicial do grupo. Igual ao minimo: a politica de escalonamento
    assume dali para cima, e comecar acima do minimo so anteciparia custo.
  EOT
  type        = number
  default     = 2
}

variable "asg_target_requests_per_target" {
  description = <<-EOT
    Valor-alvo da politica de target tracking, em requisicoes por instancia por
    minuto. O grupo cresce quando a media passa disso e encolhe quando fica
    abaixo por tempo suficiente.

    60 vem da carga do plano de teste: `tests/carga/rnf02_tempo_resposta.js`
    sustenta ~600 consultas/min com 10 usuarios virtuais. Contra duas
    instancias, sao 300 por alvo -- cinco vezes o alvo, o que faz a politica
    disparar de forma observavel durante a gravacao, e nao no limite.

    Baixo demais oscila o grupo (sobe e desce a cada variacao); alto demais so
    escala quando a latencia ja subiu, e ai o escalonamento chega tarde.
  EOT
  type        = number
  default     = 60
}

variable "asg_health_check_grace_period" {
  description = <<-EOT
    Segundos entre a instancia iniciar e o health check do ELB comecar a valer.
    Serve tambem como `instance_warmup` do refresh e da politica.

    300 s cobre boot do Amazon Linux + `dnf install` de docker e agente +
    `docker pull` da imagem + subida do gunicorn. Curto demais e o pior modo de
    falha desta configuracao: a instancia e morta antes de terminar de subir, a
    substituta faz o mesmo, e o grupo entra em ciclo de reciclagem que parece
    falha da aplicacao.
  EOT
  type        = number
  default     = 300
}

variable "instance_profile_name" {
  description = <<-EOT
    Instance profile das instancias do ASG e do bastion. Precisa permitir pull
    no ECR, leitura do segredo de tokens e escrita no CloudWatch Logs.

    No AWS Academy Learner Lab o valor e `LabInstanceProfile`, que ja existe na
    conta e vem anexado a LabRole -- pelo mesmo motivo de `existing_role_arn`:
    o papel `voclabs` recusa `iam:CreateRole`.
  EOT
  type        = string
  default     = "LabInstanceProfile"
}

variable "backend_image_tag" {
  description = <<-EOT
    Tag da imagem do backend que as instancias puxam do ECR. Vazio usa
    `worker_image_tag`, mantendo backend e workers na mesma tag de commit.

    Fixar uma tag por SHA e o que da sentido ao rollback: apontar o launch
    template para a versao anterior so devolve a versao anterior do codigo se a
    tag daquela versao ainda existir no ECR. `latest` quebraria isso.
  EOT
  type        = string
  default     = ""
}

# A Lambda de leitura e o HTTP API que a expoe (api_read.tf, auth.tf) NAO foram
# tornados condicionais.
#
# A intencao era uma flag `enable_lambda_read_api` para desligar o caminho antigo
# depois da migracao. Na pratica ela exigiria `count` em dez recursos espalhados
# por api_read.tf, auth.tf e outputs.tf, com a reescrita de indice que vem junto
# -- muita cirurgia em codigo que funciona, para uma flag cujo padrao (`true`)
# nao mudaria nada hoje.
#
# Os dois caminhos coexistem de proposito durante a migracao: derrubar a Lambda
# no mesmo apply que sobe o ASG deixaria o dashboard sem API caso o grupo nao
# suba. O desligamento e um passo manual e posterior, descrito na secao 4 do
# artefato de infraestrutura.

# --------------------------------------------------------------------------- #
# Observabilidade da rede e do caminho sincrono
# --------------------------------------------------------------------------- #

variable "flow_logs_destination" {
  description = <<-EOT
    Onde os VPC Flow Logs sao entregues: `s3` ou `cloudwatch`.

    `s3` e o padrao por uma restricao verificada na conta do AWS Academy: o
    destino CloudWatch Logs exige um papel IAM que confie em
    `vpc-flow-logs.amazonaws.com`, e a politica de confianca da `LabRole` lista
    53 servicos sem incluir esse. Com `create_iam_roles = false`, obrigatorio no
    laboratorio, o caminho do CloudWatch nao entrega nada -- e a falha e
    silenciosa: o recurso e criado e simplesmente nunca escreve.

    O destino S3 usa politica de bucket em vez de papel, some com a dependencia
    da LabRole e ainda custa menos por GB. A evidencia de console e a mesma.

    `cloudwatch` e melhor numa conta normal: o Logs Insights consulta os
    registros com linguagem de consulta, sem baixar arquivo.
  EOT
  type        = string
  default     = "s3"

  validation {
    condition     = contains(["s3", "cloudwatch"], var.flow_logs_destination)
    error_message = "flow_logs_destination precisa ser \"s3\" ou \"cloudwatch\"."
  }
}

variable "flow_logs_bucket_name" {
  description = <<-EOT
    Bucket S3 ja existente para receber os flow logs. Vazio (o padrao) faz o
    Terraform criar o bucket.

    Existe por uma restricao verificada do AWS Academy: a SCP da organizacao
    NEGA `s3:GetBucketObjectLockConfiguration`, e o provider AWS chama exatamente
    essa API ao reler qualquer `aws_s3_bucket` recem-criado. O bucket nasce, o
    apply falha na releitura, e o recurso fica no estado envenenando todo plan
    seguinte. Criar o bucket fora do Terraform e informar o nome aqui contorna
    isso sem abrir mao de controle: politica, bloqueio publico, criptografia e
    ciclo de vida continuam gerenciados neste stack, porque essas chamadas a SCP
    permite.

        aws s3api create-bucket --bucket <nome> --region us-east-1

    Numa conta sem essa restricao, deixe vazio.
  EOT
  type        = string
  default     = ""
}

variable "alb_access_logs_enabled" {
  description = <<-EOT
    Grava os access logs do ALB num bucket S3. O ALB nao entrega esse log no
    CloudWatch Logs -- so em S3 -- entao o bucket existe porque o servico exige
    bucket, nao por escolha de destino.

    E o que responde "qual foi o codigo de resposta e quanto tempo o backend
    levou", por requisicao, sem depender de a aplicacao ter conseguido logar.
  EOT
  type        = bool
  default     = true
}

variable "alb_access_logs_retention_days" {
  description = <<-EOT
    Dias ate o access log expirar. Access log cresce por requisicao e ninguem
    volta nele depois de um mes; sem expiracao o bucket vira custo permanente
    por dado que ja nao se consulta.
  EOT
  type        = number
  default     = 30
}

variable "alb_logs_bucket_name" {
  description = <<-EOT
    Bucket S3 ja existente para os access logs do ALB. Vazio (o padrao) faz o
    Terraform criar o bucket.

    Mesma valvula de escape de `flow_logs_bucket_name`, e pela mesma razao: a
    SCP do AWS Academy nega a leitura de configuracao de object lock, entao todo
    `aws_s3_bucket` criado por este stack quebra o plan seguinte naquela conta.
  EOT
  type        = string
  default     = ""
}

variable "alarm_latencia_p95_segundos" {
  description = <<-EOT
    Limiar do alarme de tempo de resposta, medido em p95 no target group.

    5 s e o alvo do RNF02, que especifica p99 < 5 s. Alarmar o p95 no mesmo
    valor da margem: quando o p95 cruza, o p99 ja esta pior, e o aviso chega
    antes de o requisito ser violado.
  EOT
  type        = number
  default     = 5
}

# --------------------------------------------------------------------------- #
# Kubernetes (EKS Auto Mode)
# --------------------------------------------------------------------------- #

variable "create_eks" {
  type    = bool
  default = false

  description = <<-EOT
    Cria o cluster EKS que orquestra o caminho sincrono (eks.tf).

    Desligado por padrao porque o cluster custa por hora existindo, e o
    orcamento do Learner Lab e finito. Ligar e uma linha no terraform.tfvars;
    desligar destroi SO o cluster -- ECS, ALB, ASG e RDS nao referenciam nada
    dele, entao continuam de pe.

    Depende de create_network: o Auto Mode precisa das sub-redes privadas com
    saida por NAT para alcancar o RDS. Ver local.criar_eks em eks.tf.
  EOT
}

variable "eks_version" {
  type    = string
  default = "1.33"

  description = <<-EOT
    Versao do control plane do Kubernetes.

    Apenas major.minor: a AWS escolhe o patch e o aplica sozinha. Fixar o patch
    aqui produziria um diff a cada atualizacao automatica da AWS.
  EOT
}

variable "eks_node_pools" {
  type    = list(string)
  default = ["general-purpose", "system"]

  description = <<-EOT
    Node pools geridos pelo Auto Mode.

    `general-purpose` recebe a carga da aplicacao; `system` recebe os
    componentes do proprio cluster (CoreDNS e afins). Remover `system` faz os
    dois disputarem o mesmo no, e uma rajada de trafego passa a poder
    pressionar o DNS do cluster.
  EOT
}

variable "eks_cluster_role_arn" {
  type    = string
  default = ""

  description = <<-EOT
    Escape para o papel de CLUSTER, quando a descoberta automatica falhar.

    O caminho normal e vazio: eks.tf descobre o papel do lab por regex
    (eks_cluster_role_name_regex), porque o nome carrega um prefixo de sessao
    que muda a cada lab. Preencha isto apenas se `terraform plan` falhar com
    AccessDenied em iam:ListRoles -- `make eks-roles` imprime o valor.
  EOT
}

variable "eks_node_role_arn" {
  type    = string
  default = ""

  description = <<-EOT
    Escape para o papel dos NOS. Mesma logica de eks_cluster_role_arn.
  EOT
}

variable "eks_cluster_role_name_regex" {
  type    = string
  default = ".*LabEksClusterRole.*"

  description = <<-EOT
    Regex que encontra o papel de cluster do Learner Lab.

    O papel ja existe na conta e NAO pode ser criado (iam:CreateRole e negado).
    Ele traz o conjunto que o Auto Mode exige: AmazonEKSClusterPolicy,
    NetworkingPolicy, ComputePolicy, BlockStoragePolicy e LoadBalancingPolicy --
    esta ultima e o que permite ao cluster criar o ALB sem IRSA.
  EOT
}

variable "eks_node_role_name_regex" {
  type    = string
  default = ".*LabEksNodeRole.*"

  description = <<-EOT
    Regex que encontra o papel dos nos do Learner Lab.

    Traz apenas WorkerNodePolicy, CNI e ECR ReadOnly -- nada de SQS ou S3, e e
    o suficiente: nenhum pod deste cluster fala com a AWS.
  EOT
}

variable "eks_public_access_cidrs" {
  type    = list(string)
  default = ["0.0.0.0/0"]

  description = <<-EOT
    De onde o endpoint publico do control plane aceita conexao.

    Aberto por padrao porque o time troca de rede e a sessao do lab dura horas;
    fechar no IP do laboratorio e uma melhoria barata quando o endereco e
    estavel. O acesso ainda exige credencial da AWS E uma access entry no
    cluster -- o CIDR e a primeira camada, nao a unica.
  EOT
}

variable "eks_extra_admin_role_arns" {
  type    = list(string)
  default = []

  description = <<-EOT
    Papeis que tambem recebem acesso de administrador ao cluster.

    O apply ja da acesso a quem o executou. Sem acrescentar os demais aqui, o
    colega que rodar `aws eks update-kubeconfig` recebe "You must be logged in
    to the server (Unauthorized)" -- um erro que parece de credencial da AWS,
    mas e de autorizacao do cluster.

    No Learner Lab todos assumem o mesmo papel `voclabs`, entao normalmente
    esta lista fica vazia.
  EOT
}
