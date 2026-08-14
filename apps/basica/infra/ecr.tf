resource "aws_ecr_repository" "worker" {
  name                 = local.name
  image_tag_mutability = "MUTABLE"

  # Scan de vulnerabilidade a cada push. Nao bloqueia o deploy, so reporta.
  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = {
    Name = local.name
  }
}

# Sem isso o repositorio cresce para sempre: cada build empurra uma layer nova e
# ninguem lembra de limpar.
resource "aws_ecr_lifecycle_policy" "worker" {
  repository = aws_ecr_repository.worker.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Mantem as 10 imagens marcadas mais recentes"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["v", "sha", "latest"]
          countType     = "imageCountMoreThan"
          countNumber   = 10
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Descarta imagem sem tag depois de 1 dia"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 1
        }
        action = { type = "expire" }
      },
    ]
  })
}
