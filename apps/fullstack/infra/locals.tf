locals {
  name = "${var.name_prefix}-${var.environment}"

  # Rede: tres origens possiveis, nesta ordem de precedencia.
  #
  #   1. `create_network = true` -- a VPC dedicada deste stack (vpc.tf). E o
  #      caminho desta sprint: sub-redes publica e privada em duas AZs, NAT.
  #   2. `vpc_id` / `subnet_ids` preenchidos -- rede pre-existente injetada.
  #   3. Nenhum dos dois -- a VPC default da conta, comportamento anterior.
  #
  # As cargas (tasks Fargate, instancias do ASG, RDS) vao para as sub-redes
  # PRIVADAS quando a rede dedicada existe. Antes iam para as default, que sao
  # todas publicas -- e era por isso que `assign_public_ip = true` era
  # necessario para elas terem saida.
  vpc_id = (
    var.create_network
    ? aws_vpc.main[0].id
    : (var.vpc_id != "" ? var.vpc_id : data.aws_vpc.default[0].id)
  )

  private_subnet_ids = var.create_network ? aws_subnet.private[*].id : []
  public_subnet_ids  = var.create_network ? aws_subnet.public[*].id : []

  subnet_ids = (
    var.create_network
    ? local.private_subnet_ids
    : (length(var.subnet_ids) > 0 ? var.subnet_ids : data.aws_subnets.default[0].ids)
  )

  # As quatro imagens do fluxo v3. A chave e o nome do repositorio ECR, da pasta
  # em apps/fullstack/ e do sufixo do recurso -- manter os tres iguais e o que
  # permite `make image-<nome>` funcionar sem tabela de traducao.
  #
  # Repare que merge worker e event worker NAO sao imagens separadas. Sao dois
  # consumidores com a mesma estrutura (mesmo laco de SQS, mesma observabilidade,
  # mesmo pool de conexao) que diferem no destino da escrita, entao sao dois
  # `command` da mesma imagem. Duas imagens identicas em 95% do conteudo
  # significariam dois builds, dois scans e duas chances de esquecer uma delas
  # no deploy.
  container_images = toset([
    "worker",     # SQS -> change_log/MERGE (merge) ou bronze.event (event)
    "simulator",  # relogio virtual, injecao de falhas, emissor de changes
    "processing", # detector / canario / ETL -- no-op por ora (decisao 7)
    "loader",     # carga inicial one-shot: Parquet -> COPY -> bronze
    "backend",    # API de leitura -- passou de zip de Lambda a imagem no EC2
    "frontend",   # dashboard servido por nginx dentro do cluster (k8s/)
  ])

  image_uris = {
    for nome in local.container_images :
    nome => "${aws_ecr_repository.images[nome].repository_url}:${var.worker_image_tag}"
  }

  # Com create_iam_roles = false, os papeis colapsam na mesma role existente
  # (ver var.existing_role_arn).
  apigw_role_arn          = var.create_iam_roles ? aws_iam_role.apigw_sqs[0].arn : var.existing_role_arn
  task_execution_role_arn = var.create_iam_roles ? aws_iam_role.task_execution[0].arn : var.existing_role_arn
  task_role_arn           = var.create_iam_roles ? aws_iam_role.task[0].arn : var.existing_role_arn
  read_api_role_arn       = var.create_iam_roles ? aws_iam_role.read_api[0].arn : var.existing_role_arn
  authorizer_role_arn     = var.create_iam_roles ? aws_iam_role.authorizer[0].arn : var.existing_role_arn

  # O papel que o servico de VPC Flow Logs assume para escrever no CloudWatch.
  # So existe nesse destino: no S3 quem autoriza e a politica do bucket.
  #
  # O colapso na LabRole, que funciona para os demais papeis do stack, NAO
  # funciona para este: a politica de confianca da LabRole nao inclui
  # `vpc-flow-logs.amazonaws.com`. E por isso que `flow_logs_destination` tem
  # `s3` como padrao -- ver a variavel.
  flow_log_role_arn = (
    var.create_network && var.flow_logs_destination == "cloudwatch" && var.create_iam_roles
    ? aws_iam_role.flow_log[0].arn
    : var.existing_role_arn
  )

  # Imagem que as instancias do ASG puxam. `backend_image_tag` vazio segue a
  # mesma tag dos workers, para que um `make rollout` deixe todo o stack no
  # mesmo commit -- e para que so exista uma tag a conferir num diagnostico.
  backend_image_uri = join("", [
    aws_ecr_repository.images["backend"].repository_url,
    ":",
    var.backend_image_tag != "" ? var.backend_image_tag : var.worker_image_tag,
  ])

  db_password = (
    var.db_password_from_secrets_manager
    ? random_password.db[0].result
    : var.db_password
  )

  # A URL de conexao que todo container recebe em DATABASE_URL.
  #
  # sslmode=require e nao `verify-full`: o RDS apresenta certificado assinado
  # por uma CA propria da Amazon, e exigir verificacao completa obrigaria a
  # embarcar o bundle rds-ca em toda imagem. `require` ja cifra o trafego, que e
  # o que separa a senha de trafegar em claro dentro da VPC.
  database_url = join("", [
    "postgresql://", var.db_username, ":", urlencode(local.db_password),
    "@", aws_db_instance.main.address, ":", tostring(aws_db_instance.main.port),
    "/", var.db_name, "?sslmode=require",
  ])

  # A URL da Lambda de leitura, com o usuario de MENOS privilegio.
  #
  # Os containers do fluxo conectam como o usuario mestre porque escrevem em
  # bronze, silver e gold. A Lambda nao escreve nada e nao deve nem conseguir
  # ler tabela base -- ela entra como `argus_api`, que so herda `argus_reader`.
  # Ver 009_views_v.sql e `python tools/migrate.py criar-leitor`.
  read_api_database_url = join("", [
    "postgresql://", var.read_api_db_user, ":", urlencode(var.read_api_db_password),
    "@", aws_db_instance.main.address, ":", tostring(aws_db_instance.main.port),
    "/", var.db_name, "?sslmode=require",
  ])

  # Ambiente comum a todos os containers. Cada task definition acrescenta o que
  # e so dela, em vez de repetir estas seis linhas cinco vezes.
  env_comum = [
    { name = "DATABASE_URL", value = local.database_url },
    { name = "AWS_REGION", value = var.region },
    { name = "LOG_LEVEL", value = var.worker_log_level },
    { name = "METRICS_NAMESPACE", value = "Argus/Ingestion" },
  ]
  # Limiar do alarme de lag, convertido de tempo de parede para tempo virtual.
  #
  # `LagSimSeconds` e medida em tempo VIRTUAL, entao o limiar precisa estar na
  # mesma unidade. Mas quem opera raciocina em tempo de parede ("pode ficar dois
  # minutos para tras"), e a conversao depende da velocidade do simulador -- que
  # e justamente o que muda entre uma demonstracao e outra.
  #
  # Sem isto, o limiar fixo de 900 s virtuais alarmava permanentemente a speed
  # 60: um unico minuto de parede processando um lote ja da 3600 s virtuais.
  lag_sim_limite = var.alarm_lag_sim_wall_seconds * var.simulator_speed

  # Origens aceitas no CORS da API de leitura. O endpoint HTTP do website S3
  # entra sozinho; a lista adicional continua reservada ao desenvolvimento
  # local. Nao use `*`, porque a API recebe um token Bearer do navegador.
  dashboard_origins = concat(
    ["http://${aws_s3_bucket_website_configuration.frontend.website_endpoint}"],
    var.dashboard_origins_extra,
  )

  # Buckets de origem/frontend criados FORA do Terraform (aws s3api
  # create-bucket), pela mesma razao de flow_logs/alb_logs: a SCP do AWS
  # Academy nega s3:GetBucketObjectLockConfiguration, a chamada que o provider
  # faz ao ler qualquer `aws_s3_bucket` recem-criado ou importado. Nesta versao
  # do provider isso nao da so erro -- derruba o Terraform com panic ao tentar
  # serializar o estado do bucket recem-criado. O nome continua deterministico
  # (nome + conta), so o resource `aws_s3_bucket` que deixa de existir; os
  # sub-recursos (versioning, encryption, PAB, policy, website) continuam
  # gerenciados aqui, referenciando o nome direto.
  frontend_bucket_name = "${local.name}-site-${data.aws_caller_identity.current.account_id}"
  origem_bucket_name   = "${local.name}-origem-${data.aws_caller_identity.current.account_id}"
}

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

# O caminho alternativo: a VPC que a AWS entrega pronta em toda conta. So e
# consultada quando nem `var.vpc_id` nem `var.create_network` respondem pela
# rede -- consultar sempre custaria uma chamada inutil e, numa conta sem VPC
# default, faria o plan falhar por uma rede que este stack nem usa.
data "aws_vpc" "default" {
  count   = var.vpc_id == "" && !var.create_network ? 1 : 0
  default = true
}

data "aws_subnets" "default" {
  count = length(var.subnet_ids) == 0 && !var.create_network ? 1 : 0

  filter {
    name   = "vpc-id"
    values = [local.vpc_id]
  }
}
