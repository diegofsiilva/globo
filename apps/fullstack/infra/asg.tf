# Camada de aplicacao do caminho de leitura: launch template + Auto Scaling
# Group de EC2, atras do ALB de alb.tf.
#
# POR QUE SAIR DA LAMBDA. A Lambda escalava sozinha e custava quase nada -- e
# esses eram argumentos bons, registrados em api_read.tf. O que ela nao dava era
# elasticidade OBSERVAVEL: a concorrencia era implicita, nao havia politica para
# declarar, nem grupo para inspecionar, nem instancia entrando em servico para
# mostrar. A rubrica desta sprint pede escalonamento demonstravel com politica
# declarada, e isso e uma propriedade do ASG, nao da Lambda.
#
# POR QUE SO O CAMINHO SINCRONO. O fluxo de ingestao continua em Fargate atras
# de SQS, e nao foi migrado junto. Fila ja absorve rajada por construcao, o
# backlog e a metrica de saude natural daquele fluxo, e reescreve-lo sobre EC2
# acrescentaria risco de regressao sem ganho arquitetural. A elasticidade so
# importa onde a latencia e percebida pelo usuario -- que e aqui.

# --------------------------------------------------------------------------- #
# Launch template
# --------------------------------------------------------------------------- #

# Versionado, e e o versionamento que torna o rollback possivel: cada mudanca
# gera uma versao nova, e voltar atras e apontar o ASG para a versao anterior e
# disparar um instance refresh. Sem launch template versionado, "rollback" seria
# reconstruir a configuracao a mao e torcer para nao esquecer um campo.
resource "aws_launch_template" "app" {
  count = local.criar_app ? 1 : 0

  name_prefix   = "${local.name}-app-"
  image_id      = data.aws_ssm_parameter.al2023[0].value
  instance_type = var.app_instance_type

  vpc_security_group_ids = [aws_security_group.app[0].id]

  iam_instance_profile {
    name = var.instance_profile_name
  }

  metadata_options {
    http_tokens   = "required"
    http_endpoint = "enabled"
    # 2 e nao 1: o processo dentro do container precisa alcancar o IMDS, e cada
    # salto de rede do Docker consome um hop. Com limite 1 a AWS CLI funciona no
    # host e falha dentro do container, com erro de credencial.
    http_put_response_hop_limit = 2
  }

  block_device_mappings {
    device_name = "/dev/xvda"

    ebs {
      volume_size = 20
      volume_type = "gp3"
      encrypted   = true
    }
  }

  user_data = base64encode(templatefile("${path.module}/templates/user_data.sh.tftpl", {
    region   = var.region
    registry = split("/", local.backend_image_uri)[0]
    image    = local.backend_image_uri

    app_port  = var.app_port
    log_group = aws_cloudwatch_log_group.app[0].name
    secret_id = aws_secretsmanager_secret.auth_tokens.id

    # O MESMO usuario de menor privilegio que a Lambda usava: `argus_api`, que
    # so herda `argus_reader` e so enxerga as views v_*. A migracao de plataforma
    # nao pode ser desculpa para a API voltar a entrar no banco como mestre.
    database_url         = local.read_api_database_url
    cors_origins         = join(",", local.dashboard_origins)
    log_level            = var.worker_log_level
    default_window_hours = tostring(var.read_api_default_window_hours)
    max_items_scanned    = tostring(var.read_api_max_items_scanned)
    user_id_hash_salt    = var.user_id_hash_salt

    cloudwatch_config = jsonencode({
      agent = { metrics_collection_interval = 60 }
      metrics = {
        namespace = "Argus/App"
        append_dimensions = {
          AutoScalingGroupName = "$${aws:AutoScalingGroupName}"
          InstanceId           = "$${aws:InstanceId}"
        }
        metrics_collected = {
          mem  = { measurement = ["mem_used_percent"] }
          disk = { measurement = ["used_percent"], resources = ["/"] }
        }
      }
    })
  }))

  # A instancia nova precisa existir antes de a antiga ser destruida, senao o
  # ASG fica sem template valido no meio da substituicao.
  lifecycle {
    create_before_destroy = true
  }

  tag_specifications {
    resource_type = "instance"

    tags = {
      Name = "${local.name}-app"
      Role = "read-api"
    }
  }

  tags = {
    Name = "${local.name}-app"
  }
}

resource "aws_cloudwatch_log_group" "app" {
  count = local.criar_app ? 1 : 0

  name              = "/argus/${local.name}/app"
  retention_in_days = var.log_retention_days

  tags = {
    Name = "${local.name}-app"
  }
}

# --------------------------------------------------------------------------- #
# Auto Scaling Group
# --------------------------------------------------------------------------- #

resource "aws_autoscaling_group" "app" {
  count = local.criar_app ? 1 : 0

  name = "${local.name}-app"

  # Sub-redes PRIVADAS. As instancias nao tem endereco publico: quem fala com a
  # internet por elas e o ALB, na entrada, e o NAT Gateway, na saida.
  vpc_zone_identifier = aws_subnet.private[*].id

  min_size         = var.asg_min_size
  max_size         = var.asg_max_size
  desired_capacity = var.asg_desired_capacity

  # `ELB` e nao `EC2`, e esta e a linha que separa um ASG que funciona de um que
  # so parece funcionar.
  #
  # Com `EC2`, a unica pergunta que o grupo faz e "a maquina virtual esta
  # ligada?". Uma instancia cujo gunicorn morreu, cujo container saiu, ou que
  # nunca conseguiu puxar a imagem continua respondendo "sim" para sempre --
  # fica `InService`, recebe trafego do balanceador e erra toda requisicao.
  #
  # Com `ELB`, a pergunta passa a ser a do target group: "/health/live responde
  # 200?". A instancia quebrada reprova, sai do grupo e e substituida.
  health_check_type = "ELB"

  # Tempo entre a instancia iniciar e o primeiro health check valer. Precisa
  # cobrir boot + dnf install + docker pull + subida do gunicorn. Curto demais e
  # a instancia e morta antes de terminar de subir, e o grupo entra em ciclo de
  # substituicao que parece falha da aplicacao.
  health_check_grace_period = var.asg_health_check_grace_period

  target_group_arns = [aws_lb_target_group.app[0].arn]

  launch_template {
    id = aws_launch_template.app[0].id
    # `$Latest` e nao um numero fixo: e o que permite `terraform apply` publicar
    # versao nova e o refresh usa-la. O rollback troca isto por um numero,
    # deliberadamente (ver secao 5.3 do artefato).
    version = "$Latest"
  }

  # Substituicao gradual das instancias quando o template muda. E o mecanismo de
  # DEPLOY e o de ROLLBACK -- os dois sao o mesmo comando, mudando so para qual
  # versao o template aponta.
  instance_refresh {
    strategy = "Rolling"

    preferences {
      # 50%: com `min_size = 2`, sempre resta uma instancia servindo. Um valor
      # de 100% exigiria capacidade extra antes de derrubar qualquer coisa, e o
      # laboratorio nao tem quota folgada para isso; abaixo de 50% haveria
      # momento com zero instancia saudavel.
      min_healthy_percentage = 50
      instance_warmup        = var.asg_health_check_grace_period
    }

    triggers = ["tag"]
  }

  # Espera as instancias entrarem em servico antes de dar o apply por concluido.
  # Sem isto o Terraform retorna com o grupo ainda vazio e o smoke test seguinte
  # falha por motivo que nao e o dele.
  wait_for_capacity_timeout = "10m"

  tag {
    key                 = "Name"
    value               = "${local.name}-app"
    propagate_at_launch = true
  }

  tag {
    key                 = "Component"
    value               = "read-api"
    propagate_at_launch = true
  }

  depends_on = [aws_nat_gateway.main]
}

# --------------------------------------------------------------------------- #
# Politica de escalonamento
# --------------------------------------------------------------------------- #

# Target tracking, e a metrica e contagem de requisicao por alvo -- nao CPU.
#
# A escolha da metrica e o que decide se a politica funciona. Esta API passa a
# maior parte do tempo de cada requisicao ESPERANDO o PostgreSQL responder, e
# nao calculando: sob carga real a CPU da instancia fica na casa de 30-40%
# enquanto a latencia percebida ja dobrou. Uma politica com alvo de CPU em 70%
# simplesmente nunca dispararia -- o grupo ficaria em duas instancias
# saturadas de conexao, com a metrica dizendo que esta tudo bem.
#
# `ALBRequestCountPerTarget` mede o que de fato cresce: quantas requisicoes cada
# instancia esta tendo que atender. E, por vir do balanceador, e a mesma metrica
# que o painel do CloudWatch mostra e que o avaliador ve subir no video.
#
# ALTERNATIVA DESCARTADA: step scaling, que daria controle fino sobre o tamanho
# do degrau (quantas instancias por vez, por faixa de metrica). Custa manter os
# alarmes e a tabela de degraus a mao, e o ganho so aparece com padrao de carga
# conhecido e irregular -- que nao e o caso aqui.
resource "aws_autoscaling_policy" "app_target_tracking" {
  count = local.criar_app ? 1 : 0

  name                   = "${local.name}-req-por-alvo"
  autoscaling_group_name = aws_autoscaling_group.app[0].name
  policy_type            = "TargetTrackingScaling"

  # Tempo que uma instancia recem-criada fica FORA do calculo da media. Sem
  # isto, a instancia que ainda esta puxando a imagem entra na conta com zero
  # requisicao, derruba a media, e a politica conclui que ja escalou o bastante
  # -- parando de crescer no meio da rajada.
  estimated_instance_warmup = var.asg_health_check_grace_period

  target_tracking_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ALBRequestCountPerTarget"

      # O sufixo que o ALB espera e "<arn_suffix do lb>/<arn_suffix do tg>".
      resource_label = "${aws_lb.app[0].arn_suffix}/${aws_lb_target_group.app[0].arn_suffix}"
    }

    target_value = var.asg_target_requests_per_target

    # Scale in LIGADO, de proposito. Desliga-lo evitaria o risco de cortar
    # requisicao em voo, mas deixaria o grupo no tamanho do pico para sempre --
    # o que num laboratorio com credito limitado esgota o orcamento sozinho.
    # O risco do scale in esta coberto pelo `deregistration_delay` de 30 s do
    # target group: a instancia sai do balanceador, termina o que ja aceitou, e
    # so entao e encerrada.
    disable_scale_in = false
  }
}

# --------------------------------------------------------------------------- #
# Security group das instancias
# --------------------------------------------------------------------------- #

resource "aws_security_group" "app" {
  count = local.criar_app ? 1 : 0

  name        = "${local.name}-app"
  description = "Instancias EC2 que servem a API de leitura"
  vpc_id      = local.vpc_id

  tags = {
    Name = "${local.name}-app"
  }
}

# A porta da aplicacao NAO aceita a internet. Aceita o security group do ALB, e
# so ele -- e por isso que a instancia pode ficar em sub-rede privada sem deixar
# de ser alcancavel. Referencia de SG e nao CIDR: a sub-rede pode mudar, o IP do
# no do balanceador muda sozinho, mas a identidade do grupo nao.
resource "aws_security_group_rule" "app_do_alb" {
  count = local.criar_app ? 1 : 0

  type                     = "ingress"
  description              = "Trafego da aplicacao vindo apenas do balanceador"
  from_port                = var.app_port
  to_port                  = var.app_port
  protocol                 = "tcp"
  security_group_id        = aws_security_group.app[0].id
  source_security_group_id = aws_security_group.alb[0].id
}

# SSH so do bastion. Nao ha regra de porta 22 com CIDR nenhum aqui: a unica
# forma de chegar a esta instancia por SSH e saltando do bastion, que por sua
# vez so aceita o CIDR declarado do time.
resource "aws_security_group_rule" "app_ssh_do_bastion" {
  count = local.criar_bastion ? 1 : 0

  type                     = "ingress"
  description              = "SSH apenas a partir do bastion"
  from_port                = 22
  to_port                  = 22
  protocol                 = "tcp"
  security_group_id        = aws_security_group.app[0].id
  source_security_group_id = aws_security_group.bastion[0].id
}

# Saida 443: ECR (pull da imagem), Secrets Manager (hash do token no boot),
# CloudWatch (logs e metricas) e o repositorio de pacotes do Amazon Linux.
# Tudo isso passa pelo NAT Gateway.
resource "aws_security_group_rule" "app_https" {
  count = local.criar_app ? 1 : 0

  type              = "egress"
  description       = "HTTPS para ECR, Secrets Manager, CloudWatch e pacotes"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  security_group_id = aws_security_group.app[0].id
  cidr_blocks       = ["0.0.0.0/0"]
}

resource "aws_security_group_rule" "app_para_rds" {
  count = local.criar_app ? 1 : 0

  type                     = "egress"
  description              = "PostgreSQL para o RDS"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.app[0].id
  source_security_group_id = aws_security_group.rds.id
}

# HTTP de saida para o repositorio de pacotes do Amazon Linux, que serve parte
# dos metadados em texto claro. Sem isto o `dnf install` do user_data trava.
resource "aws_security_group_rule" "app_http" {
  count = local.criar_app ? 1 : 0

  type              = "egress"
  description       = "HTTP para o repositorio de pacotes do Amazon Linux"
  from_port         = 80
  to_port           = 80
  protocol          = "tcp"
  security_group_id = aws_security_group.app[0].id
  cidr_blocks       = ["0.0.0.0/0"]
}
