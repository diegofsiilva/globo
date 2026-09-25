# Copia privada do export estatico. A Lambda de entrada le estes objetos quando
# o Ingress do EKS falha. O navegador usa somente o dominio HTTPS do API Gateway.
# O bucket e criado fora do Terraform por restricao da SCP do Learner Lab.

resource "aws_s3_bucket_server_side_encryption_configuration" "frontend" {
  bucket = local.frontend_bucket_name

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket = local.frontend_bucket_name

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
