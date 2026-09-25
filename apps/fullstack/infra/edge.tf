# Entrada publica sem dominio proprio: HTTP API fornece TLS no endpoint
# execute-api. O ALB do EKS e interno e a Lambda faz a comutacao de destino.

resource "aws_ssm_parameter" "edge_primary_host" {
  count = var.create_network ? 1 : 0
  name  = "/${local.name}/edge/primary-alb-host"
  type  = "String"
  value = "desativado"

  # `make k8s-edge-register` publica o hostname criado pelo Ingress depois
  # do apply. O Terraform nao pode conhece-lo durante o primeiro plan.
  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_cloudwatch_log_group" "edge" {
  count             = var.create_network ? 1 : 0
  name              = "/aws/lambda/${local.name}-edge"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role" "edge" {
  count              = var.create_network && var.create_iam_roles ? 1 : 0
  name               = "${local.name}-edge"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume[0].json
}

data "aws_iam_policy_document" "edge" {
  count = var.create_network && var.create_iam_roles ? 1 : 0

  statement {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.edge[0].arn}:*"]
  }

  statement {
    actions   = ["ssm:GetParameter"]
    resources = [aws_ssm_parameter.edge_primary_host[0].arn]
  }

  statement {
    actions   = ["s3:GetObject"]
    resources = ["arn:aws:s3:::${local.frontend_bucket_name}/*"]
  }

  statement {
    actions = [
      "ec2:CreateNetworkInterface",
      "ec2:DescribeNetworkInterfaces",
      "ec2:DeleteNetworkInterface",
      "ec2:AssignPrivateIpAddresses",
      "ec2:UnassignPrivateIpAddresses",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "edge" {
  count  = var.create_network && var.create_iam_roles ? 1 : 0
  name   = "entrada-https"
  role   = aws_iam_role.edge[0].id
  policy = data.aws_iam_policy_document.edge[0].json
}

# O roteador nao precisa acessar o RDS. Um grupo proprio limita sua saida ao
# ALB interno, ao SSM/API HTTPS e ao endpoint S3 da VPC.
resource "aws_security_group" "edge" {
  count       = var.create_network ? 1 : 0
  name        = "${local.name}-edge"
  description = "Entrada HTTPS do Argus: somente saida"
  vpc_id      = local.vpc_id

  tags = {
    Name = "${local.name}-edge"
  }
}

resource "aws_security_group_rule" "edge_to_alb" {
  count             = var.create_network ? 1 : 0
  type              = "egress"
  description       = "Lambda de entrada para o ALB interno do EKS"
  from_port         = 80
  to_port           = 80
  protocol          = "tcp"
  security_group_id = aws_security_group.edge[0].id
  cidr_blocks       = [var.vpc_cidr]
}

resource "aws_security_group_rule" "edge_https" {
  count             = var.create_network ? 1 : 0
  type              = "egress"
  description       = "SSM, API de leitura e S3 por HTTPS"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  security_group_id = aws_security_group.edge[0].id
  cidr_blocks       = ["0.0.0.0/0"]
}

resource "aws_lambda_function" "edge" {
  count         = var.create_network ? 1 : 0
  function_name = "${local.name}-edge"
  role          = var.create_iam_roles ? aws_iam_role.edge[0].arn : var.existing_role_arn
  handler       = "handler.lambda_handler"
  runtime       = "python3.12"
  architectures = ["arm64"]

  filename         = "../edge/dist/argus-edge.zip"
  source_code_hash = filebase64sha256("../edge/dist/argus-edge.zip")

  memory_size = 512
  timeout     = 30

  vpc_config {
    subnet_ids         = local.private_subnet_ids
    security_group_ids = [aws_security_group.edge[0].id]
  }

  environment {
    variables = {
      PRIMARY_HOST_PARAMETER = aws_ssm_parameter.edge_primary_host[0].name
      FRONTEND_BUCKET        = local.frontend_bucket_name
      READ_API_URL           = aws_apigatewayv2_api.read.api_endpoint
    }
  }

  depends_on = [aws_cloudwatch_log_group.edge, aws_iam_role_policy.edge]
}

resource "aws_apigatewayv2_api" "edge" {
  count         = var.create_network ? 1 : 0
  name          = "${local.name}-edge"
  protocol_type = "HTTP"
  description   = "Entrada HTTPS do dashboard e API com contingencia automatica"
}

resource "aws_apigatewayv2_integration" "edge" {
  count                  = var.create_network ? 1 : 0
  api_id                 = aws_apigatewayv2_api.edge[0].id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.edge[0].invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 30000
}

resource "aws_apigatewayv2_route" "edge" {
  count     = var.create_network ? 1 : 0
  api_id    = aws_apigatewayv2_api.edge[0].id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.edge[0].id}"
}

resource "aws_apigatewayv2_stage" "edge" {
  count       = var.create_network ? 1 : 0
  api_id      = aws_apigatewayv2_api.edge[0].id
  name        = "$default"
  auto_deploy = true
}

resource "aws_lambda_permission" "edge" {
  count         = var.create_network ? 1 : 0
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.edge[0].function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.edge[0].execution_arn}/*/*"
}

output "edge_primary_host_parameter" {
  description = "Parametro atualizado por make k8s-edge-register apos o Ingress nascer."
  value       = var.create_network ? aws_ssm_parameter.edge_primary_host[0].name : ""
}
