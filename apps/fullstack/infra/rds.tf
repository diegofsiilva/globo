# A instancia PostgreSQL: toda a persistencia do Argus v3.
#
# O Terraform provisiona a instancia e PARA. Ele nao cria schema, nao cria
# tabela, nao cria view. O DDL e das migrations (db/migrations/, aplicadas por
# tools/migrate.py), e a separacao e proposital: iterar o schema passa a custar
# `make migrate` em vez de `terraform apply`, o que numa sessao de laboratorio e
# a diferenca entre trinta segundos e cinco minutos por tentativa.

resource "aws_db_subnet_group" "main" {
  name       = local.name
  subnet_ids = local.subnet_ids

  tags = {
    Name = local.name
  }
}

# --------------------------------------------------------------------------- #
# Rede
# --------------------------------------------------------------------------- #

# Sem regra de entrada por padrao. Quem abre a porta sao as duas regras abaixo,
# e as duas sao explicitas sobre para quem estao abrindo.
resource "aws_security_group" "rds" {
  name        = "${local.name}-rds"
  description = "PostgreSQL do Argus"
  vpc_id      = local.vpc_id

  tags = {
    Name = "${local.name}-rds"
  }
}

# Os servicos deste stack (worker de merge, worker de eventos, simulador,
# processamento, loader) falam com o banco por aqui. Referencia o security group
# das tasks, e nao um CIDR: subnet muda, IP muda, mas a identidade do grupo nao.
resource "aws_security_group_rule" "rds_from_tasks" {
  type                     = "ingress"
  description              = "PostgreSQL vindo das tasks Fargate deste stack"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.rds.id
  source_security_group_id = aws_security_group.worker.id
}

# O acesso do desenvolvedor, para inspecionar o banco e rodar as migrations.
# Existe apenas se `db_allowed_cidr` for preenchido, e a validacao da variavel
# recusa 0.0.0.0/0 -- nunca a internet inteira.
resource "aws_security_group_rule" "rds_from_dev" {
  count = var.db_allowed_cidr != "" ? 1 : 0

  type              = "ingress"
  description       = "PostgreSQL vindo do CIDR informado em db_allowed_cidr"
  from_port         = 5432
  to_port           = 5432
  protocol          = "tcp"
  security_group_id = aws_security_group.rds.id
  cidr_blocks       = [var.db_allowed_cidr]
}

# --------------------------------------------------------------------------- #
# Senha
# --------------------------------------------------------------------------- #

resource "random_password" "db" {
  count = var.db_password_from_secrets_manager ? 1 : 0

  length  = 32
  special = true
  # O RDS recusa estes na senha do usuario mestre. Descobrir isso pelo erro do
  # apply custa um ciclo inteiro de laboratorio.
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

resource "aws_secretsmanager_secret" "db" {
  count = var.db_password_from_secrets_manager ? 1 : 0

  name = "${local.name}-db"
  # Sem janela de recuperacao: num ambiente que e recriado a cada sessao, o
  # padrao de 30 dias faz o proximo apply falhar com "already scheduled for
  # deletion" e obriga a renomear o segredo.
  recovery_window_in_days = 0

  tags = {
    Name = "${local.name}-db"
  }
}

resource "aws_secretsmanager_secret_version" "db" {
  count = var.db_password_from_secrets_manager ? 1 : 0

  secret_id = aws_secretsmanager_secret.db[0].id
  secret_string = jsonencode({
    username = var.db_username
    password = random_password.db[0].result
    engine   = "postgres"
    host     = aws_db_instance.main.address
    port     = 5432
    dbname   = var.db_name
  })
}

# --------------------------------------------------------------------------- #
# Parametros
# --------------------------------------------------------------------------- #

resource "aws_db_parameter_group" "main" {
  name   = local.name
  family = "postgres${split(".", var.db_engine_version)[0]}"

  # Nao ha `autovacuum_*_scale_factor` aqui de proposito.
  #
  # A intencao era manter o autovacuum fora do caminho durante a carga inicial
  # (68,7 M linhas por COPY, com ele disputando I/O). Acontece que os valores que
  # queriamos -- 0.1 para vacuum e 0.05 para analyze -- JA SAO o default da
  # familia `postgres16` no RDS (o do PostgreSQL de baunilha e 0.2 e 0.1; a AWS
  # ja aperta os dois). E a AWS descarta parametro cujo valor e igual ao default:
  # ele some do `describe-db-parameters --source user`, o Terraform ve a
  # diferenca e reescreve, a AWS descarta de novo. `terraform plan` nunca
  # converge -- ficava eterno em "1 to change" sem efeito nenhum.
  #
  # Para apertar mais que o default, basta declarar um valor MENOR aqui.

  # As tabelas particionadas tem centenas de particoes. Sem isso o planner nao
  # poda particao em plano preparado, e toda consulta de uma janela de tempo
  # varre o conjunto inteiro.
  parameter {
    name  = "plan_cache_mode"
    value = "force_custom_plan"
  }

  # Consulta que passa de 1s vira linha de log. E o que permite achar a view
  # cujo plano degradou depois da carga cheia, sem instrumentar a aplicacao.
  parameter {
    name  = "log_min_duration_statement"
    value = "1000"
  }

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Name = local.name
  }
}

# --------------------------------------------------------------------------- #
# A instancia
# --------------------------------------------------------------------------- #

resource "aws_db_instance" "main" {
  identifier     = local.name
  engine         = "postgres"
  engine_version = var.db_engine_version
  instance_class = var.db_instance_class

  db_name  = var.db_name
  username = var.db_username
  password = local.db_password

  allocated_storage = var.db_allocated_storage
  # gp3 e nao gp2: no gp2 o IOPS e amarrado ao tamanho do disco (3 por GB), o
  # que obrigaria a superdimensionar o storage so para conseguir throughput
  # durante a carga inicial. gp3 da 3000 IOPS de base independente do tamanho.
  storage_type      = "gp3"
  storage_encrypted = true

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  # Fixado em false por exigencia da rubrica (3): o banco nunca eh exposto
  # publicamente. O acesso administrativo usa a task `migration` dentro da VPC
  # (make migrate-aws). A variavel var.db_publicly_accessible permanece apenas
  # para compatibilidade com workspaces legados e eh ignorada; qualquer valor
  # diferente de false gera erro em `terraform validate` via variavel validada.
  publicly_accessible = false
  multi_az            = var.db_multi_az

  parameter_group_name       = aws_db_parameter_group.main.name
  backup_retention_period    = var.db_backup_retention_days
  auto_minor_version_upgrade = true

  # Protecao ligada apenas em producao.
  # Em laboratorio, snapshot final de uma conta que vai deixar de existir e lixo
  # com custo -- e `deletion_protection` ligado transformaria `make tf-destroy`
  # num erro que ninguem entende na hora de encerrar a sessao.
  deletion_protection = var.environment == "prod"
  skip_final_snapshot = var.environment != "prod"
  final_snapshot_identifier = (
    var.environment == "prod" ? "${local.name}-final" : null
  )

  # A senha pode ter sido rotacionada fora do Terraform (no console, ou pela
  # rotacao do Secrets Manager). Sem isto, todo plan seguinte proporia
  # devolve-la para o valor do state.
  lifecycle {
    ignore_changes = [password]
  }

  tags = {
    Name = local.name
  }
}

# --------------------------------------------------------------------------- #
# Acesso a partir da rede dedicada: bastion e cluster EKS
# --------------------------------------------------------------------------- #

# O bastion e o unico caminho humano ate o banco depois que ele deixa de ser
# publico. Substitui, para inspecao interativa, o que hoje se faz disparando a
# task ECS `migration` -- que continua existindo para as migrations.
resource "aws_security_group_rule" "rds_from_bastion" {
  count = local.criar_bastion ? 1 : 0

  type                     = "ingress"
  description              = "PostgreSQL vindo do bastion, para tunel e inspecao"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.rds.id
  source_security_group_id = aws_security_group.bastion[0].id
}

# Os pods do cluster Kubernetes entram pelo security group do CLUSTER, que o
# Auto Mode anexa a toda ENI de no. A liberacao e por grupo e nao por CIDR: o
# CIDR das sub-redes privadas ja e conhecido, mas a identidade do grupo
# sobrevive a uma troca de faixa.
#
# Sem esta regra o sintoma e indireto: os pods sobem, /health/live passa, mas
# /health/ready fica em 503 para sempre, o Deployment nunca fica Available e o
# ALB responde 503 sem alvo saudavel. Nada no log diz "security group".
resource "aws_security_group_rule" "rds_from_eks" {
  count = local.criar_eks ? 1 : 0

  type                     = "ingress"
  description              = "PostgreSQL vindo dos pods do cluster EKS"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.rds.id
  source_security_group_id = aws_eks_cluster.main[0].vpc_config[0].cluster_security_group_id
}
