output "api_endpoint" {
  description = "URL base da API de ingestao."
  value       = aws_apigatewayv2_api.events.api_endpoint
}

output "ingest_url" {
  description = "URL de ingestao do grain de sessao."
  value       = "${aws_apigatewayv2_api.events.api_endpoint}/v1/events"
}

output "changes_url" {
  description = "URL de ingestao dos change events. E para ca que o simulador emite."
  value       = "${aws_apigatewayv2_api.events.api_endpoint}/v1/changes"
}

output "queue_url" {
  description = "Fila do grain de sessao."
  value       = aws_sqs_queue.events.url
}

output "changes_queue_url" {
  description = "Fila dos change events."
  value       = aws_sqs_queue.changes.url
}

output "dlq_url" {
  description = "DLQ do grain de sessao. E aqui que o evento invalido vai parar."
  value       = aws_sqs_queue.dlq.url
}

output "changes_dlq_url" {
  description = "DLQ dos change events."
  value       = aws_sqs_queue.changes_dlq.url
}

# --------------------------------------------------------------------------- #
# Banco
# --------------------------------------------------------------------------- #

output "db_endpoint" {
  description = "Endereco do PostgreSQL, no formato host:porta."
  value       = aws_db_instance.main.endpoint
}

output "db_name" {
  description = "Nome do banco dentro da instancia."
  value       = var.db_name
}

output "db_secret_name" {
  description = <<-EOT
    Nome do segredo com a credencial do banco no Secrets Manager. Vazio quando
    `db_password_from_secrets_manager = false` (nesse caso a senha esta no seu
    terraform.tfvars, que nao e versionado).
  EOT
  value       = var.db_password_from_secrets_manager ? aws_secretsmanager_secret.db[0].name : ""
}

# A senha NAO entra aqui, nem com `sensitive = true`: output sensivel continua
# gravado em claro no terraform.tfstate, e este comando e o que permite montar a
# URL na hora sem que ela passe por nenhum arquivo.
output "database_url_hint" {
  description = "Como montar a DATABASE_URL para rodar as migrations da sua maquina."
  value = var.db_password_from_secrets_manager ? join("", [
    "export DATABASE_URL=\"postgresql://", var.db_username, ":$(aws secretsmanager ",
    "get-secret-value --secret-id ", aws_secretsmanager_secret.db[0].name,
    " --query SecretString --output text --profile g4 | python3 -c ",
    "'import json,sys,urllib.parse; print(urllib.parse.quote(json.load(sys.stdin)[\"password\"], safe=\"\"))')",
    "@", aws_db_instance.main.endpoint, "/", var.db_name, "?sslmode=require\"",
    ]) : join("", [
    "export DATABASE_URL=\"postgresql://", var.db_username, ":<a senha do seu ",
    "terraform.tfvars>@", aws_db_instance.main.endpoint, "/", var.db_name,
    "?sslmode=require\"",
  ])
}

# --------------------------------------------------------------------------- #
# Containers
# --------------------------------------------------------------------------- #

output "ecr_repository_urls" {
  description = "Repositorio ECR de cada imagem. Destino do docker push."
  value       = { for nome, repo in aws_ecr_repository.images : nome => repo.repository_url }
}

output "ecs_cluster_name" {
  description = "Nome do cluster ECS."
  value       = aws_ecs_cluster.main.name
}

output "ecs_service_names" {
  description = "Services em execucao continua. O loader nao esta aqui: ele roda uma vez e termina."
  value = {
    merge-worker = aws_ecs_service.merge_worker.name
    event-worker = aws_ecs_service.event_worker.name
    simulator    = aws_ecs_service.simulator.name
    processing   = aws_ecs_service.processing.name
  }
}

output "log_groups" {
  description = "Log group de cada servico no CloudWatch."
  value       = { for nome, lg in aws_cloudwatch_log_group.servicos : nome => lg.name }
}

output "origem_bucket" {
  description = "Bucket com o dump e o Parquet. Destino do `aws s3 sync` da carga inicial."
  value       = local.origem_bucket_name
}

output "docker_push_commands" {
  description = <<-EOT
    Sequencia para publicar TODAS as imagens no ECR.

    Cada imagem recebe duas tags: o SHA do commit, que e o que a task definition
    referencia, e `latest`, apelido para quem quiser puxar "a mais recente" a
    mao. Nenhum recurso do Terraform aponta para `latest` -- ver a nota em
    `variable "worker_image_tag"`.
  EOT
  value = join("\n", concat(
    [
      join("", [
        "aws ecr get-login-password --region ", var.region, " --profile g4 \\\n",
        "  | docker login --username AWS --password-stdin ",
        data.aws_caller_identity.current.account_id, ".dkr.ecr.", var.region,
        ".amazonaws.com\n",
      ])
    ],
    [
      for nome in local.container_images : join("", [
        "\ndocker build --platform linux/",
        lower(var.worker_cpu_architecture) == "arm64" ? "arm64" : "amd64",
        " \\\n  -f ../", nome, "/Dockerfile \\\n  -t ",
        aws_ecr_repository.images[nome].repository_url, ":",
        var.worker_image_tag, " \\\n  -t ",
        aws_ecr_repository.images[nome].repository_url, ":latest ..\n",
        "docker push ", aws_ecr_repository.images[nome].repository_url, ":",
        var.worker_image_tag, "\n",
        "docker push ", aws_ecr_repository.images[nome].repository_url, ":latest",
      ])
    ]
  ))
}

# A carga inicial e task one-shot, nao service: nao ha `desired_count` para
# mexer, ela e disparada explicitamente.
output "loader_run_command" {
  description = "Dispara a carga inicial das 33 tabelas."
  value = join("", [
    "aws ecs run-task --profile g4 --region ", var.region,
    " \\\n  --cluster ", aws_ecs_cluster.main.name,
    " \\\n  --task-definition ", aws_ecs_task_definition.loader.family,
    " \\\n  --launch-type FARGATE",
    " \\\n  --network-configuration 'awsvpcConfiguration={subnets=[",
    join(",", local.subnet_ids), "],securityGroups=[",
    aws_security_group.worker.id, "],assignPublicIp=",
    var.assign_public_ip ? "ENABLED" : "DISABLED", "}'",
  ])
}

output "migration_run_command" {
  description = "Aplica migrations pendentes pela VPC, sem expor o RDS."
  value = join("", [
    "aws ecs run-task --profile g4 --region ", var.region,
    " \\\n  --cluster ", aws_ecs_cluster.main.name,
    " \\\n  --task-definition ", aws_ecs_task_definition.migration.family,
    " \\\n  --launch-type FARGATE",
    " \\\n  --network-configuration 'awsvpcConfiguration={subnets=[",
    join(",", local.subnet_ids), "],securityGroups=[",
    aws_security_group.worker.id, "],assignPublicIp=",
    var.assign_public_ip ? "ENABLED" : "DISABLED", "}'",
  ])
}

# A MESMA task definition, com `status` no lugar de `aplicar`. Sobrescrever o
# comando na chamada evita uma segunda task definition que so difere numa
# palavra -- e que divergiria da primeira no primeiro ajuste de imagem ou de
# variavel de ambiente.
#
# E o caminho canonico para inventariar o que ja rodou no RDS: `make
# migrate-status` da maquina exigiria o banco publico, que e justamente o que a
# adequacao do RNF09 removeu.
output "migration_status_command" {
  description = "Lista as migrations ja aplicadas no RDS, pela VPC."
  value = join("", [
    "aws ecs run-task --profile g4 --region ", var.region,
    " \\\n  --cluster ", aws_ecs_cluster.main.name,
    " \\\n  --task-definition ", aws_ecs_task_definition.migration.family,
    " \\\n  --launch-type FARGATE",
    " \\\n  --network-configuration 'awsvpcConfiguration={subnets=[",
    join(",", local.subnet_ids), "],securityGroups=[",
    aws_security_group.worker.id, "],assignPublicIp=",
    var.assign_public_ip ? "ENABLED" : "DISABLED", "}'",
    " \\\n  --overrides '{\"containerOverrides\":[{\"name\":\"migration\",",
    "\"command\":[\"status\"]}]}'",
  ])
}

output "db_reader_run_command" {
  description = "Cria ou atualiza o usuario somente-leitura usado pela Lambda, pela VPC."
  value = join("", [
    "aws ecs run-task --profile g4 --region ", var.region,
    " \\\n  --cluster ", aws_ecs_cluster.main.name,
    " \\\n  --task-definition ", aws_ecs_task_definition.migration.family,
    " \\\n  --launch-type FARGATE",
    " \\\n  --network-configuration 'awsvpcConfiguration={subnets=[",
    join(",", local.subnet_ids), "],securityGroups=[",
    aws_security_group.worker.id, "],assignPublicIp=",
    var.assign_public_ip ? "ENABLED" : "DISABLED", "}'",
    " \\\n  --overrides '{\"containerOverrides\":[{\"name\":\"migration\",",
    "\"command\":[\"criar-leitor\",\"--usuario\",\"", var.read_api_db_user, "\"]}]}'",
  ])
}

# --------------------------------------------------------------------------- #
# Leitura
# --------------------------------------------------------------------------- #

output "read_api_url" {
  description = "URL base da API de leitura. E esta que o dashboard consome."
  value       = aws_apigatewayv2_api.read.api_endpoint
}

output "read_api_id" {
  description = "ID da API de leitura. Usado para limpar o cache do authorizer na rotacao."
  value       = aws_apigatewayv2_api.read.id
}

output "ingest_api_id" {
  description = "ID da API de ingestao. Usado para limpar o cache do authorizer na rotacao."
  value       = aws_apigatewayv2_api.events.id
}

output "frontend_url" {
  description = "Entrada HTTPS unica do dashboard e da API, com fallback automatico."
  value       = var.create_network ? aws_apigatewayv2_api.edge[0].api_endpoint : ""
}

output "frontend_bucket" {
  description = "Bucket do site. Destino do `aws s3 sync` em make frontend-deploy."
  value       = local.frontend_bucket_name
}

output "auth_tokens_secret" {
  description = "Segredo com os SHA-256 dos tokens Bearer. Preenchido por `make auth-rotate`."
  value       = aws_secretsmanager_secret.auth_tokens.name
}

output "ingest_token_secret" {
  description = "Segredo com o token de ingestao em claro, lido pela task do simulador."
  value       = aws_secretsmanager_secret.ingest_token.name
}

output "alarms_topic_arn" {
  description = "Topico SNS dos alarmes."
  value       = aws_sns_topic.alarms.arn
}

output "read_api_examples" {
  description = "Chamadas de exemplo da API de leitura."
  value = {
    relogio  = "${aws_apigatewayv2_api.read.api_endpoint}/api/v1/clock"
    serie    = "${aws_apigatewayv2_api.read.api_endpoint}/api/v1/series?source=prometheus&metric=p95_ms"
    fontes   = "${aws_apigatewayv2_api.read.api_endpoint}/api/v1/facets?field=source"
    eventos  = "${aws_apigatewayv2_api.read.api_endpoint}/api/v1/events?event_name=error&limit=20"
    janelas  = "${aws_apigatewayv2_api.read.api_endpoint}/api/v1/incidents"
    agrupado = "${aws_apigatewayv2_api.read.api_endpoint}/api/v1/metrics/breakdown?dimension=device_manufacturer"
  }
}

# --------------------------------------------------------------------------- #
# Rede dedicada e camada de aplicacao
# --------------------------------------------------------------------------- #

output "vpc_id" {
  description = "VPC efetivamente em uso: a dedicada, a injetada ou a default da conta."
  value       = local.vpc_id
}

output "private_subnet_ids" {
  description = "Sub-redes privadas. Vazio quando create_network = false."
  value       = local.private_subnet_ids
}

output "public_subnet_ids" {
  description = "Sub-redes publicas. Vazio quando create_network = false."
  value       = local.public_subnet_ids
}

output "nat_gateway_ip" {
  description = <<-EOT
    IP de saida das sub-redes privadas. E este endereco que aparece como origem
    para qualquer servico externo chamado pelas instancias -- util quando
    alguem precisa liberar o Argus numa allowlist de terceiro.
  EOT
  value       = var.create_network ? aws_eip.nat[0].public_ip : null
}

output "flow_log_destino" {
  description = <<-EOT
    Onde procurar os VPC Flow Logs -- o bucket S3 ou o log group, conforme
    `flow_logs_destination`. Responde "a conexao chegou?".
  EOT
  value = (
    !var.create_network ? null :
    var.flow_logs_destination == "s3"
    ? "s3://${local.flow_logs_bucket}"
    : aws_cloudwatch_log_group.vpc_flow[0].name
  )
}

output "s3_gateway_endpoint_id" {
  description = <<-EOT
    Gateway endpoint de S3 associado a tabela de rota privada. E o que tira o
    trafego do `loader` de cima do NAT -- e o NAT cobra por GB.
  EOT
  value       = var.create_network ? aws_vpc_endpoint.s3[0].id : null
}

output "bastion_public_ip" {
  description = <<-EOT
    IP publico do bastion. Nulo quando `bastion_key_name` esta vazio.

      ssh -N -L 5432:<endpoint-rds>:5432 ec2-user@<ip>
  EOT
  value       = local.criar_bastion ? aws_instance.bastion[0].public_ip : null
}

output "dashboard_url" {
  description = "Painel do CloudWatch (observability.tf): o banco por tras do caminho sincrono."
  value       = "https://${var.region}.console.aws.amazon.com/cloudwatch/home?region=${var.region}#dashboards:name=${aws_cloudwatch_dashboard.main.dashboard_name}"
}

# --------------------------------------------------------------------------- #
# Kubernetes
# --------------------------------------------------------------------------- #

output "eks_cluster_name" {
  description = "Nome do cluster EKS, ou vazio quando create_eks = false."
  value       = local.criar_eks ? aws_eks_cluster.main[0].name : ""
}

output "eks_cluster_endpoint" {
  description = "Endpoint do control plane."
  value       = local.criar_eks ? aws_eks_cluster.main[0].endpoint : ""
}

output "eks_cluster_security_group_id" {
  description = "Security group do cluster. E por ele que os pods entram no RDS."
  value       = local.criar_eks ? aws_eks_cluster.main[0].vpc_config[0].cluster_security_group_id : ""
}

output "eks_kubeconfig_command" {
  description = "Como apontar o kubectl para este cluster. `make k8s-kubeconfig` faz o mesmo."

  value = local.criar_eks ? join(" ", [
    "aws eks update-kubeconfig",
    "--name", aws_eks_cluster.main[0].name,
    "--region", var.region,
    "--profile g4",
  ]) : "create_eks = false"
}

# Os quatro valores abaixo alimentam `make k8s-secret`, que os le por
# `terraform output -raw` e os canaliza direto para o kubectl. Marcados como
# sensiveis para que nao aparecam no log do apply; `-raw` continua funcionando.
#
# Sem IRSA e sem Pod Identity (o Learner Lab nega iam:CreateRole e
# iam:CreateOpenIDConnectProvider), o pod nao consegue ler o Secrets Manager
# sozinho -- e este e o caminho que mantem o segredo fora do repositorio, fora
# do disco e fora do tfstate.

output "eks_backend_database_url" {
  description = "DATABASE_URL da API no cluster. Usuario argus_api, so leitura das views v_*."
  value       = local.read_api_database_url
  sensitive   = true
}

output "eks_master_database_url" {
  description = <<-EOT
    DATABASE_URL do Job de migration. Usuario MESTRE, e nao argus_api.

    A migration cria schema e faz GRANT, e o usuario de leitura nao tem essa
    permissao por construcao. Reusar a URL da API aqui falharia com "permission
    denied for schema" no meio da aplicacao, deixando o banco parcialmente
    migrado.
  EOT
  value       = local.database_url
  sensitive   = true
}

output "eks_read_api_db_password" {
  description = "Senha do usuario de leitura, que o Job de migration usa para criar/atualizar o login."
  value       = var.read_api_db_password
  sensitive   = true
}

output "eks_user_id_hash_salt" {
  description = "Sal do hash de user_id, consumido pela API."
  value       = var.user_id_hash_salt
  sensitive   = true
}
