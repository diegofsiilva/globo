locals {
  name = "${var.name_prefix}-${var.environment}"

  # Rede: usa a VPC/subnets default quando nada e passado, para que um
  # `terraform apply` numa conta nova funcione sem configuracao previa.
  vpc_id     = var.vpc_id != "" ? var.vpc_id : data.aws_vpc.default[0].id
  subnet_ids = length(var.subnet_ids) > 0 ? var.subnet_ids : data.aws_subnets.default[0].ids

  # As quatro imagens do fluxo v3. A chave e o nome do repositorio ECR, da pasta
  # em apps/basica/ e do sufixo do recurso -- manter os tres iguais e o que
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

  # Origens aceitas no CORS da API de leitura. O dominio do dashboard entra
  # sozinho -- deixar isso a cargo de uma variavel preenchida a mao era o que
  # mantinha `["*"]` no ambiente publicado.
  #
  # Nao ha ciclo entre os dois recursos: a distribuicao nao referencia a API de
  # leitura (ver a nota do `connect-src` em frontend_s3.tf).
  dashboard_origins = concat(
    ["https://${aws_cloudfront_distribution.frontend.domain_name}"],
    var.dashboard_origins_extra,
  )
}

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

data "aws_vpc" "default" {
  count   = var.vpc_id == "" ? 1 : 0
  default = true
}

data "aws_subnets" "default" {
  count = length(var.subnet_ids) == 0 ? 1 : 0

  filter {
    name   = "vpc-id"
    values = [local.vpc_id]
  }
}
