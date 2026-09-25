# Teste da camada de rede com provider mockado.
#
# Roda o plano REAL da configuracao sem tocar a AWS: e o que permite checar a
# coerencia entre variaveis sem depender de uma sessao valida do Learner Lab,
# que vence em horas. Nao substitui o apply -- nao diz se o papel `voclabs`
# autoriza criar cada recurso --, mas pega toda combinacao de variavel que
# produz uma rede invalida.
#
#   terraform test -filter=rede.tftest.hcl

mock_provider "aws" {}

variables {
  create_network   = true
  assign_public_ip = false
  worker_image_tag = "teste"
}

# Valem para todos os `run` deste arquivo.
#
# As AZs viram uma lista fixa porque a conta mockada nao devolve nenhuma. As
# duas policies existem porque o provider valida JSON no plan, e o valor mockado
# nao e JSON -- sao ruido do mock, nao objeto do teste.
override_data {
  target          = data.aws_availability_zones.available[0]
  values          = { names = ["us-east-1a", "us-east-1b", "us-east-1c"] }
  override_during = plan
}

override_data {
  target          = data.aws_iam_policy_document.flow_logs_bucket[0]
  values          = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  override_during = plan
}

override_data {
  target          = data.aws_iam_policy_document.alb_logs[0]
  values          = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  override_during = plan
}

# Mesma razao para os documentos de assume role: o provider 5.100 passou a
# validar `assume_role_policy` no plan, e o `json` mockado nao e JSON. Sem estes
# tres, o `topologia` morre em cinco aws_iam_role antes de olhar a rede.
override_data {
  target          = data.aws_iam_policy_document.ecs_assume
  values          = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  override_during = plan
}

override_data {
  target          = data.aws_iam_policy_document.apigw_assume
  values          = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  override_during = plan
}

override_data {
  target          = data.aws_iam_policy_document.lambda_assume[0]
  values          = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  override_during = plan
}

# Os papeis do EKS sao descobertos por regex na conta do Learner Lab (eks.tf).
# A conta mockada nao devolve papel nenhum, e a precondicao do cluster -- que
# existe para falhar cedo quando a descoberta nao acha nada -- dispararia aqui
# por motivo errado. Estes ARNs sao de mentira e so precisam nao ser vazios.
override_data {
  target          = data.aws_iam_roles.eks_cluster[0]
  values          = { arns = ["arn:aws:iam::000000000000:role/LabEksClusterRole-teste"] }
  override_during = plan
}

override_data {
  target          = data.aws_iam_roles.eks_node[0]
  values          = { arns = ["arn:aws:iam::000000000000:role/LabEksNodeRole-teste"] }
  override_during = plan
}

run "topologia" {
  command = plan

  override_resource {
    target          = aws_subnet.public[0]
    values          = { id = "subnet-pub-a" }
    override_during = plan
  }
  override_resource {
    target          = aws_subnet.public[1]
    values          = { id = "subnet-pub-b" }
    override_during = plan
  }

  assert {
    condition     = length(aws_subnet.public) == 2 && length(aws_subnet.private) == 2
    error_message = "esperado 2 sub-redes publicas e 2 privadas"
  }
  assert {
    condition     = aws_subnet.public[0].availability_zone != aws_subnet.public[1].availability_zone
    error_message = "publicas em AZs distintas (exigencia do ALB do Ingress)"
  }
  assert {
    condition     = aws_subnet.private[0].availability_zone != aws_subnet.private[1].availability_zone
    error_message = "privadas em AZs distintas (subnet group do RDS)"
  }
  assert {
    condition     = alltrue([for s in aws_subnet.private : s.map_public_ip_on_launch != true])
    error_message = "sub-rede privada nao pode auto-atribuir IP publico"
  }
  assert {
    condition     = alltrue([for s in aws_subnet.public : s.map_public_ip_on_launch == true])
    error_message = "sub-rede publica precisa auto-atribuir IP publico"
  }
  assert {
    condition     = contains(["subnet-pub-a", "subnet-pub-b"], aws_nat_gateway.main[0].subnet_id)
    error_message = "o NAT precisa estar numa sub-rede PUBLICA para ter saida"
  }
  assert {
    condition     = length(aws_route_table_association.private) == length(aws_subnet.private)
    error_message = "toda sub-rede privada precisa estar associada a tabela do NAT"
  }
  assert {
    condition     = length(aws_route_table_association.public) == length(aws_subnet.public)
    error_message = "toda sub-rede publica precisa estar associada a tabela do IGW"
  }
}

# As faixas sao derivadas de `vpc_cidr`; trocar o CIDR nao pode deixar sub-rede
# pendurada fora da VPC.
run "cidr_da_vpc_alterado" {
  command = plan

  variables {
    vpc_cidr = "10.42.0.0/16"
  }


  assert {
    condition = alltrue([
      for s in concat(aws_subnet.public, aws_subnet.private) :
      cidrsubnet(aws_vpc.main[0].cidr_block, 8, tonumber(split(".", s.cidr_block)[2])) == s.cidr_block
    ])
    error_message = "ha sub-rede fora do CIDR da VPC"
  }
}

# O gateway endpoint de S3 e gratuito e tira do NAT o trafego do `loader`, que
# le ~200 MB de Parquet por carga. Sumir com ele nao quebra nada visivel -- so
# aparece na fatura.
run "endpoint_s3_na_rota_privada" {
  command = plan

  override_resource {
    target          = aws_route_table.private[0]
    values          = { id = "rtb-privada" }
    override_during = plan
  }

  assert {
    condition     = length(aws_vpc_endpoint.s3) == 1
    error_message = "gateway endpoint de S3 ausente: o trafego do loader volta a passar pelo NAT"
  }
  assert {
    condition     = aws_vpc_endpoint.s3[0].route_table_ids == toset(["rtb-privada"])
    error_message = "o endpoint precisa estar na tabela de rota PRIVADA"
  }
}

# O destino padrao dos flow logs e S3, porque a LabRole nao confia em
# vpc-flow-logs.amazonaws.com. Passar papel nesse destino e erro de validacao.
run "flow_log_em_s3_dispensa_papel" {
  command = plan


  assert {
    condition     = aws_flow_log.vpc[0].traffic_type == "ALL"
    error_message = "flow log precisa registrar ACCEPT e REJECT"
  }
  assert {
    condition     = aws_flow_log.vpc[0].log_destination_type == "s3"
    error_message = "destino padrao precisa ser s3: no CloudWatch a LabRole nao consegue assumir o papel"
  }
  assert {
    condition     = aws_flow_log.vpc[0].iam_role_arn == null
    error_message = "no destino S3 quem autoriza e a politica do bucket, nao um papel"
  }
  assert {
    condition     = length(aws_cloudwatch_log_group.vpc_flow) == 0
    error_message = "o log group so deve existir no destino cloudwatch"
  }
}

# Com a rede dedicada, a task vai para a sub-rede privada.
run "task_privada_nao_pede_ip_publico" {
  command = plan


  assert {
    condition     = aws_ecs_service.merge_worker.network_configuration[0].assign_public_ip == false
    error_message = "task em sub-rede privada com IP publico: sem rota para o IGW, o pull do ECR falha"
  }
}

# E a combinacao invalida precisa morrer no plan, nao em crash loop no ECS.
run "ip_publico_com_rede_dedicada_e_recusado" {
  command = plan

  variables {
    assign_public_ip = true
  }

  expect_failures = [var.assign_public_ip]
}

# O metrics-server nao vem com o Auto Mode: um cluster novo nasce sem ele e o
# HPA fica em `<unknown>` (lab limpo de 18/09/2026). O add-on precisa nascer e
# morrer junto com o cluster.
run "eks_traz_metrics_server" {
  command = plan

  variables {
    create_eks = true
  }

  override_resource {
    target          = aws_subnet.private[0]
    values          = { id = "subnet-priv-a" }
    override_during = plan
  }

  override_resource {
    target          = aws_subnet.private[1]
    values          = { id = "subnet-priv-b" }
    override_during = plan
  }

  assert {
    condition     = length(aws_eks_addon.metrics_server) == 1
    error_message = "create_eks = true precisa declarar o add-on metrics-server; sem ele o HPA fica em <unknown>."
  }

  assert {
    condition     = aws_eks_cluster.main[0].vpc_config[0].subnet_ids == toset(aws_subnet.private[*].id)
    error_message = "Os node pools do EKS so devem receber sub-redes privadas."
  }

  assert {
    condition     = length(aws_apigatewayv2_api.edge) == 1 && length(aws_lambda_function.edge) == 1
    error_message = "A entrada HTTPS com fallback precisa existir na rede dedicada."
  }

  assert {
    condition     = aws_s3_bucket_public_access_block.frontend.block_public_policy
    error_message = "O bucket de contingencia nao pode aceitar policy publica."
  }

  assert {
    condition     = length(aws_security_group_rule.edge_to_alb) == 1 && aws_security_group_rule.edge_to_alb[0].from_port == 80
    error_message = "A Lambda precisa de saida HTTP para o ALB interno."
  }

  assert {
    condition     = aws_eks_addon.metrics_server[0].addon_name == "metrics-server"
    error_message = "O add-on declarado em eks.tf nao e o metrics-server."
  }

  # `addon_version` e computado (o provider escolhe no apply), entao nao da
  # para afirmar nada sobre ele no plan. O que da para segurar e o OVERWRITE:
  # sem ele, um metrics-server instalado a mao faria o create falhar.
  assert {
    condition     = aws_eks_addon.metrics_server[0].resolve_conflicts_on_create == "OVERWRITE"
    error_message = "resolve_conflicts_on_create precisa ser OVERWRITE para assumir um metrics-server instalado a mao."
  }

  assert {
    condition     = aws_eks_addon.metrics_server[0].resolve_conflicts_on_update == "OVERWRITE"
    error_message = "resolve_conflicts_on_update precisa ser OVERWRITE."
  }
}

run "sem_eks_nao_ha_metrics_server" {
  command = plan

  variables {
    create_eks = false
  }

  assert {
    condition     = length(aws_eks_addon.metrics_server) == 0
    error_message = "O add-on metrics-server so existe quando o cluster existe."
  }
}
