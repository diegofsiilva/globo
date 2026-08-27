# Um repositorio por imagem. Sao cinco servicos em container agora, e nao um.
#
# Repositorios separados e nao tags diferentes no mesmo repositorio: a politica
# de ciclo de vida conta imagens POR repositorio, entao um repositorio comum
# faria o `worker` expirar por causa de builds do `simulator`. E o scan de
# vulnerabilidade fica atribuido ao servico certo.

resource "aws_ecr_repository" "images" {
  for_each = local.container_images

  name                 = "${local.name}-${each.key}"
  image_tag_mutability = "MUTABLE"

  # Scan a cada push. Nao bloqueia o deploy, so reporta.
  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = {
    Name      = "${local.name}-${each.key}"
    Component = each.key
  }
}

# Sem isso o repositorio cresce para sempre: cada build empurra uma layer nova e
# ninguem lembra de limpar.
resource "aws_ecr_lifecycle_policy" "images" {
  for_each = aws_ecr_repository.images

  repository = each.value.name

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
