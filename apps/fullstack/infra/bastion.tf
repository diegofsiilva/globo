# Bastion host: o unico ponto de entrada administrativo da rede privada.
#
# As instancias do Auto Scaling Group e o RDS nao tem endereco publico -- e esse
# e o ponto. Mas alguem precisa conseguir abrir um psql para investigar um
# incidente, ou entrar numa instancia para ler um log que nao chegou ao
# CloudWatch. As alternativas eram:
#
#   1. Dar IP publico as instancias. Desfaz a rede privada inteira.
#   2. Abrir o RDS para a internet (`db_publicly_accessible = true`). Expoe o
#      banco a varredura continua, e a unica barreira passa a ser a senha.
#   3. Um host intermediario, minimo, com uma unica porta aberta para um CIDR
#      conhecido -- e nada mais.
#
# A (3) e esta. O bastion nao roda aplicacao, nao guarda dado e nao tem papel
# IAM de escrita: se for comprometido, o atacante ganha o que ja teria com a
# chave SSH, e nada alem disso.
#
# AVALIADO E DESCARTADO: AWS Systems Manager Session Manager, que elimina a
# porta 22 e a chave SSH por completo. E a postura mais forte, e seria a escolha
# em producao. Aqui depende de o papel `voclabs` do Learner Lab conceder
# `ssm:StartSession` e de a instancia carregar um instance profile com a policy
# gerenciada `AmazonSSMManagedInstanceCore` -- duas coisas que a conta de
# laboratorio nao garante, e cuja falha so aparece na hora da demonstracao.
# O bastion classico funciona em qualquer conta.

locals {
  # Sem key pair nao ha como entrar na maquina, entao criar o bastion seria
  # pagar por uma instancia inalcancavel. Deixar o nome vazio e tambem o que
  # permite `terraform validate` e `plan` numa conta que ainda nao tem o par.
  criar_bastion = var.create_network && var.bastion_key_name != ""
}

# AMI pelo parametro publico do SSM, e nao por um `ami-` fixo.
#
# O id da AMI muda a cada release da Amazon e e diferente em cada regiao. Fixar
# um id significa subir uma imagem sem os patches dos ultimos meses, e quebrar
# o apply no dia em que aquela AMI for desregistrada.
data "aws_ssm_parameter" "al2023" {
  count = var.create_network ? 1 : 0

  # arm64 (Graviton), e nao x86_64.
  #
  # Nao e detalhe de custo: TODO o pipeline de imagens deste repositorio
  # constroi arm64 (`make push` usa `--platform linux/arm64`, a Lambda e arm64,
  # as tasks Fargate tambem). Uma AMI x86_64 faria o `docker run` do user_data
  # falhar com "exec format error" -- e o sintoma apareceria como instancia
  # reprovando no health check, longe da causa.
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

resource "aws_instance" "bastion" {
  count = local.criar_bastion ? 1 : 0

  ami           = data.aws_ssm_parameter.al2023[0].value
  instance_type = var.bastion_instance_type
  key_name      = var.bastion_key_name

  # Publica porque precisa ser alcancavel de fora -- e a definicao do papel.
  subnet_id                   = aws_subnet.public[0].id
  vpc_security_group_ids      = [aws_security_group.bastion[0].id]
  associate_public_ip_address = true

  # IMDSv2 obrigatorio. Com IMDSv1 uma falha de SSRF na maquina permite ler as
  # credenciais temporarias do instance profile com um simples GET; o token
  # exigido pelo v2 fecha esse caminho.
  metadata_options {
    http_tokens                 = "required"
    http_endpoint               = "enabled"
    http_put_response_hop_limit = 1
  }

  root_block_device {
    volume_size = 8
    volume_type = "gp3"
    encrypted   = true
  }

  # O bastion nao serve dado e nao guarda estado: um `docker` ou um `psql` para
  # inspecao e tudo que se espera dele. Instalar aqui evita depender de rede no
  # meio de uma investigacao.
  user_data = <<-EOT
    #!/bin/bash
    set -euo pipefail
    dnf install -y postgresql16
  EOT

  tags = {
    Name = "${local.name}-bastion"
    Role = "bastion"
  }
}

# --------------------------------------------------------------------------- #
# Security group
# --------------------------------------------------------------------------- #

# Sem regra nenhuma inline. Todas as regras sao recursos separados abaixo, pelo
# mesmo motivo de rds.tf: regra inline e substituida em bloco a cada mudanca, e
# a diferenca fica ilegivel no plan.
resource "aws_security_group" "bastion" {
  count = local.criar_bastion ? 1 : 0

  name        = "${local.name}-bastion"
  description = "Acesso administrativo SSH a rede privada"
  vpc_id      = local.vpc_id

  tags = {
    Name = "${local.name}-bastion"
  }
}

# A UNICA porta de entrada, e ela nao aceita `0.0.0.0/0`: a validacao de
# `bastion_allowed_cidr` recusa esse valor, do mesmo jeito que `db_allowed_cidr`
# ja recusa hoje. Um bastion aberto para a internet inteira nao e um bastion --
# e a mesma exposicao de antes, com um salto a mais.
#
# Custo pratico da restricao: quem troca de rede (sai do campus, muda de
# operadora) perde o acesso ate atualizar a variavel e reaplicar. E o preco de
# a porta 22 nao ficar visivel para a varredura continua da internet.
resource "aws_security_group_rule" "bastion_ssh" {
  count = local.criar_bastion ? 1 : 0

  type              = "ingress"
  description       = "SSH do CIDR declarado pelo time"
  from_port         = 22
  to_port           = 22
  protocol          = "tcp"
  security_group_id = aws_security_group.bastion[0].id
  cidr_blocks       = [var.bastion_allowed_cidr]
}

# Saida restrita a tres destinos, e nao `0.0.0.0/0`. O bastion so precisa
# alcancar a rede privada e os endpoints da AWS; abrir a saida inteira daria a
# quem o comprometesse um trampolim para qualquer lugar.
resource "aws_security_group_rule" "bastion_para_app" {
  count = local.criar_bastion ? 1 : 0

  type                     = "egress"
  description              = "SSH para as instancias do Auto Scaling Group"
  from_port                = 22
  to_port                  = 22
  protocol                 = "tcp"
  security_group_id        = aws_security_group.bastion[0].id
  source_security_group_id = aws_security_group.app[0].id
}

resource "aws_security_group_rule" "bastion_para_rds" {
  count = local.criar_bastion ? 1 : 0

  type                     = "egress"
  description              = "PostgreSQL para o RDS, usado pelo tunel de inspecao"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.bastion[0].id
  source_security_group_id = aws_security_group.rds.id
}

# Necessario para `dnf` e para a AWS CLI. Sai pelo Internet Gateway, porque o
# bastion esta em sub-rede publica.
resource "aws_security_group_rule" "bastion_https" {
  count = local.criar_bastion ? 1 : 0

  type              = "egress"
  description       = "HTTPS para atualizacao de pacote e chamadas a API da AWS"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  security_group_id = aws_security_group.bastion[0].id
  cidr_blocks       = ["0.0.0.0/0"]
}
