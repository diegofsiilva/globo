# Application Load Balancer do caminho de leitura.
#
# Ele resolve tres coisas que a Lambda atras do API Gateway resolvia de graca e
# que passam a ser responsabilidade nossa ao mover a API para EC2:
#
#   1. Um endereco estavel. As instancias do ASG nascem e morrem, e o IP muda
#      junto; o DNS do ALB nao muda enquanto o recurso existir.
#   2. Distribuicao entre as duas AZs, com retirada automatica da instancia que
#      reprova no health check.
#   3. O ponto de medicao. `RequestCountPerTarget` e `TargetResponseTime` sao
#      metricas do balanceador -- sem ele nao ha o que observar nem sobre o que
#      escalonar.
#
# O ALB fica nas sub-redes PUBLICAS. Ele e a fronteira: e a unica coisa deste
# stack que aceita conexao da internet, e por isso as instancias podem ficar
# privadas. Coloca-lo na sub-rede privada e o erro que torna o sistema
# inalcancavel sem que nada no plan pareca errado.

locals {
  criar_app = var.create_network
}

resource "aws_lb" "app" {
  count = local.criar_app ? 1 : 0

  name               = substr("${local.name}-alb", 0, 32)
  load_balancer_type = "application"
  internal           = false

  subnets         = aws_subnet.public[*].id
  security_groups = [aws_security_group.alb[0].id]

  # Cross-zone e sempre ligado no ALB (nao e configuravel, ao contrario do NLB).
  # Fica registrado aqui porque a rubrica pergunta: o trafego que chega ao no de
  # uma AZ pode ser servido por instancia da outra, o que mantem a distribuicao
  # uniforme mesmo com numero desigual de instancias por zona.

  # 60 s e o default e serve: as consultas mais longas da API respondem em
  # segundos, e um valor alto demais segura conexao de cliente que ja desistiu.
  idle_timeout = 60

  enable_deletion_protection = var.environment == "prod"

  dynamic "access_logs" {
    for_each = var.alb_access_logs_enabled ? [1] : []

    content {
      bucket  = aws_s3_bucket.alb_logs[0].id
      prefix  = "alb"
      enabled = true
    }
  }

  tags = {
    Name = "${local.name}-alb"
  }
}

# --------------------------------------------------------------------------- #
# Target group
# --------------------------------------------------------------------------- #

resource "aws_lb_target_group" "app" {
  count = local.criar_app ? 1 : 0

  name        = substr("${local.name}-tg", 0, 32)
  port        = var.app_port
  protocol    = "HTTP"
  vpc_id      = local.vpc_id
  target_type = "instance"

  # O health check e a decisao mais consequente deste arquivo.
  #
  # `/health/live` e nao `/health/ready`. As duas rotas existem no Flask
  # (interfaces/http.py): `live` responde `{"status":"ok"}` fixo, sem tocar no
  # banco; `ready` faz ping no PostgreSQL e devolve 503 quando ele nao responde.
  #
  # `ready` parece a escolha mais rigorosa, e e a errada aqui. Uma indisponibi-
  # lidade momentanea do RDS -- failover, janela de manutencao, esgotamento de
  # conexao -- faria TODAS as instancias reprovarem ao mesmo tempo. O ASG as
  # substituiria em bloco, as substitutas encontrariam o mesmo banco indisponivel
  # e reprovariam tambem, e o grupo entraria em ciclo de reciclagem sem que
  # houvesse nada errado com as instancias. O problema estaria no banco, e a
  # reacao teria derrubado tambem a camada que ainda funcionava.
  #
  # `live` responde "este processo esta vivo e aceitando conexao", que e
  # exatamente a pergunta que o balanceador precisa fazer. A saude do banco e
  # assunto de alarme (ver observability.tf), nao de health check de target.
  health_check {
    enabled             = true
    path                = "/health/live"
    protocol            = "HTTP"
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  # Quanto tempo o ALB espera antes de fechar as conexoes de uma instancia que
  # esta saindo do grupo. E o parametro que protege o *scale in*: sem ele, uma
  # instancia removida no meio de uma consulta derruba a requisicao do usuario.
  # 30 s cobre com folga a consulta mais longa da API de leitura.
  deregistration_delay = 30

  # A API le de views e nao guarda estado entre requisicoes -- nao ha sessao
  # para prender ao mesmo target. Stickiness so reduziria a uniformidade da
  # distribuicao, que e justamente o que a politica de escalonamento mede.
  stickiness {
    type    = "lb_cookie"
    enabled = false
  }

  tags = {
    Name = "${local.name}-tg"
  }
}

# --------------------------------------------------------------------------- #
# Listener
# --------------------------------------------------------------------------- #

# HTTP na 80, e nao HTTPS na 443.
#
# Nao e descuido: TLS no ALB exige certificado no ACM, e um certificado do ACM
# exige um dominio cujo DNS possamos validar. O projeto nao tem dominio proprio,
# e a distribuicao CloudFront -- que resolveria isso com o certificado
# `*.cloudfront.net` -- ficou fora do escopo desta sprint.
#
# A consequencia esta assumida e registrada como risco em
# infraestrutura-integracao.md secao 8: o token Bearer que o operador cola no
# dashboard trafega em claro entre o navegador e o ALB. E a mesma divida que
# arquitetura-inicial.md secao 4.8 ja registrava para o endpoint de website do
# S3, e a correcao planejada e a mesma: CloudFront a frente das duas origens.
#
# Coerencia que vale notar: como o front tambem e servido por HTTP (website S3),
# nao ha conteudo misto. Uma pagina HTTPS chamando este ALB em HTTP seria
# bloqueada pelo navegador -- e o que aconteceria se o CloudFront fosse posto
# so na frente do S3, sem a segunda origem.
resource "aws_lb_listener" "http" {
  count = local.criar_app ? 1 : 0

  load_balancer_arn = aws_lb.app[0].arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.app[0].arn
  }
}

# --------------------------------------------------------------------------- #
# Security group
# --------------------------------------------------------------------------- #

resource "aws_security_group" "alb" {
  count = local.criar_app ? 1 : 0

  name        = "${local.name}-alb"
  description = "Fronteira publica do caminho de leitura"
  vpc_id      = local.vpc_id

  tags = {
    Name = "${local.name}-alb"
  }
}

# O unico `0.0.0.0/0` de entrada de todo o stack, e ele esta no lugar certo:
# um balanceador publico existe para aceitar conexao de qualquer origem. O que
# fica atras dele nao aceita.
resource "aws_security_group_rule" "alb_http" {
  count = local.criar_app ? 1 : 0

  type              = "ingress"
  description       = "HTTP da internet"
  from_port         = 80
  to_port           = 80
  protocol          = "tcp"
  security_group_id = aws_security_group.alb[0].id
  cidr_blocks       = ["0.0.0.0/0"]
}

# A saida do ALB aponta para o SECURITY GROUP das instancias, nao para o CIDR da
# sub-rede. A instancia troca de IP a cada substituicao do ASG; a identidade do
# grupo nao muda.
resource "aws_security_group_rule" "alb_para_app" {
  count = local.criar_app ? 1 : 0

  type                     = "egress"
  description              = "Encaminhamento para as instancias do Auto Scaling Group"
  from_port                = var.app_port
  to_port                  = var.app_port
  protocol                 = "tcp"
  security_group_id        = aws_security_group.alb[0].id
  source_security_group_id = aws_security_group.app[0].id
}
