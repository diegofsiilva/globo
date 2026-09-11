# Hospedagem temporaria do dashboard: bucket S3 com website hosting.
#
# O dashboard e um export estatico do Next (`output: "export"`), entao sao
# arquivos, nao um processo. Isso permite hospedar em S3 sem uma instancia para
# manter viva, corrigir ou religar.
#
# Esta e uma compatibilidade para o AWS Academy Learner Lab, cujo papel
# `voclabs` nao permite criar os recursos de CloudFront usados pela arquitetura
# principal. O endpoint de website do S3 serve SOMENTE HTTP. Como o dashboard
# recebe um token Bearer, use este modo apenas temporariamente e em uma rede
# confiavel: um intermediario pode ler ou alterar a pagina e capturar o token.
#
# O nome do bucket precisa ser unico no mundo inteiro, dai o sufixo com o id da
# conta -- sem ele, um `apply` numa conta nova colide com a nossa.
#
# O bucket em si nasce FORA do Terraform (aws s3api create-bucket), pelo
# mesmo motivo de flow_logs/alb_logs (ver locals.tf): a SCP do Academy nega a
# releitura que o recurso `aws_s3_bucket` faz logo depois de criar ou
# importar, e nesta versao do provider isso derruba o Terraform com panic em
# vez de so falhar. `local.frontend_bucket_name` mantem o nome deterministico.

resource "aws_s3_bucket_website_configuration" "frontend" {
  bucket = local.frontend_bucket_name

  index_document {
    suffix = "index.html"
  }

  # O export estatico escreve cada rota em um diretorio com seu index.html. O
  # endpoint de website completa esses caminhos sem uma funcao de borda.
  error_document {
    key = "404.html"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "frontend" {
  bucket = local.frontend_bucket_name

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Website hosting do S3 so funciona com leitura publica: o endpoint de site nao
# fala SigV4, entao nao existe "publico mas autenticado" aqui. Os quatro
# bloqueios precisam sair para que a policy abaixo seja aceita.
resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket = local.frontend_bucket_name

  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_policy" "frontend" {
  bucket = local.frontend_bucket_name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "LeituraPublicaDoSite"
        Effect = "Allow"
        # Somente leitura de objeto, e so deste bucket. Nenhuma permissao de
        # escrita, de listagem do bucket ou de alteracao da propria policy.
        Principal = "*"
        Action    = "s3:GetObject"
        Resource  = "arn:aws:s3:::${local.frontend_bucket_name}/*"
      }
    ]
  })

  # A policy publica so e aceita depois que os bloqueios caem. Sem esta
  # dependencia explicita o Terraform tenta as duas em paralelo e o apply falha
  # de forma intermitente, dependendo de qual chamada chega primeiro.
  depends_on = [aws_s3_bucket_public_access_block.frontend]
}
