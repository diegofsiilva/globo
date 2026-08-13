output "api_endpoint" {
  description = "URL base da API. O POST vai para <endpoint>/v1/events."
  value       = aws_apigatewayv2_api.events.api_endpoint
}

output "ingest_url" {
  description = "URL completa de ingestao de eventos."
  value       = "${aws_apigatewayv2_api.events.api_endpoint}/v1/events"
}

output "queue_url" {
  description = "URL da fila principal."
  value       = aws_sqs_queue.events.url
}

output "dlq_url" {
  description = "URL da DLQ. E aqui que o evento invalido vai parar."
  value       = aws_sqs_queue.dlq.url
}

output "table_name" {
  description = "Nome da tabela DynamoDB."
  value       = aws_dynamodb_table.events.name
}

output "ecr_repository_url" {
  description = "Repositorio ECR do worker. Destino do docker push."
  value       = aws_ecr_repository.worker.repository_url
}

output "ecs_cluster_name" {
  description = "Nome do cluster ECS."
  value       = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  description = "Nome do service ECS."
  value       = aws_ecs_service.worker.name
}

output "log_group_worker" {
  description = "Log group do worker no CloudWatch."
  value       = aws_cloudwatch_log_group.worker.name
}

output "alarms_topic_arn" {
  description = "Topico SNS dos alarmes."
  value       = aws_sns_topic.alarms.arn
}

output "docker_push_commands" {
  description = "Sequencia para publicar a imagem do worker no ECR."
  value       = <<-EOT
    aws ecr get-login-password --region ${var.region} \
      | docker login --username AWS --password-stdin ${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.region}.amazonaws.com

    docker build --platform linux/${lower(var.worker_cpu_architecture) == "arm64" ? "arm64" : "amd64"} \
      -t ${aws_ecr_repository.worker.repository_url}:${var.worker_image_tag} ../worker/

    docker push ${aws_ecr_repository.worker.repository_url}:${var.worker_image_tag}

    aws ecs update-service --cluster ${aws_ecs_cluster.main.name} \
      --service ${aws_ecs_service.worker.name} --force-new-deployment --region ${var.region}
  EOT
}

output "read_api_url" {
  description = "URL base da API de leitura. E esta que o dashboard consome."
  value       = aws_apigatewayv2_api.read.api_endpoint
}

output "read_api_examples" {
  description = "Chamadas de exemplo da API de leitura."
  value = {
    busca    = "${aws_apigatewayv2_api.read.api_endpoint}/api/v1/events?event_name=error&limit=20"
    sessao   = "${aws_apigatewayv2_api.read.api_endpoint}/api/v1/sessions/{session_id}"
    aparelho = "${aws_apigatewayv2_api.read.api_endpoint}/api/v1/devices/{device_id}"
    agrupado = "${aws_apigatewayv2_api.read.api_endpoint}/api/v1/metrics/breakdown?dimension=device_manufacturer"
    serie    = "${aws_apigatewayv2_api.read.api_endpoint}/api/v1/metrics/timeseries?interval=60&compare=true"
    filtros  = "${aws_apigatewayv2_api.read.api_endpoint}/api/v1/facets?field=event_name&field=app_target"
  }
}
