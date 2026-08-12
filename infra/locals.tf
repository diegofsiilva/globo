locals {
  name = "${var.name_prefix}-${var.environment}"

  # Rede: usa a VPC/subnets default quando nada e passado, para que um
  # `terraform apply` numa conta nova funcione sem configuracao previa.
  vpc_id     = var.vpc_id != "" ? var.vpc_id : data.aws_vpc.default[0].id
  subnet_ids = length(var.subnet_ids) > 0 ? var.subnet_ids : data.aws_subnets.default[0].ids

  worker_image = var.worker_image != "" ? var.worker_image : "${aws_ecr_repository.worker.repository_url}:${var.worker_image_tag}"

  # Com create_iam_roles = false, os tres papeis colapsam na mesma role
  # existente (ver var.existing_role_arn).
  apigw_role_arn          = var.create_iam_roles ? aws_iam_role.apigw_sqs[0].arn : var.existing_role_arn
  task_execution_role_arn = var.create_iam_roles ? aws_iam_role.task_execution[0].arn : var.existing_role_arn
  task_role_arn           = var.create_iam_roles ? aws_iam_role.task[0].arn : var.existing_role_arn
  read_api_role_arn       = var.create_iam_roles ? aws_iam_role.read_api[0].arn : var.existing_role_arn
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
