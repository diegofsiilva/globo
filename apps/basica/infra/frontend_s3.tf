# Hospedagem do dashboard: bucket S3 com website hosting.
#
# O dashboard e um export estatico do Next (`output: "export"`), entao sao
# arquivos, nao um processo. Isso e o que permite hospedar em S3 por centavos,
# sem instancia para manter viva, corrigir ou religar.
#
# Por que S3 e nao EC2, ja que a entrega aceita os dois: o Learner Lab desliga
# as instancias ao fim da sessao e o IP publico muda ao religar, o que quebraria
# o link do relatorio e do video entre a gravacao e a correcao. O endereco do
# bucket e estavel e atravessa o ciclo do lab.
#
# Video demonstrativo: https://youtu.be/Vhd8BgToZF4
#
# O nome do bucket precisa ser unico no mundo inteiro, dai o sufixo com o id da
# conta -- sem ele, um `apply` numa conta nova colide com a nossa.

resource "aws_s3_bucket" "frontend" {
  bucket = "${local.name}-site-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_website_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  index_document {
    suffix = "index.html"
  }

  # O export do Next nao gera pagina de erro propria, e um SPA resolve rota no
  # cliente. Devolver o index no 404 faz o roteamento do navegador assumir, em
  # vez de mostrar o XML de erro do S3.
  error_document {
    key = "index.html"
  }
}

# Website hosting do S3 so funciona com leitura publica: o endpoint de site nao
# fala SigV4, entao nao existe "publico mas autenticado" aqui. Os quatro
# bloqueios precisam sair para que a policy abaixo seja aceita.
#
# O que fica exposto e apenas o HTML/CSS/JS do dashboard, que ja seria baixado
# por qualquer visitante. O dado sensivel nao esta aqui -- esta atras da API, e
# a lacuna de autenticacao dela esta registrada no README desta pasta (secao
# "Seguranca e lacunas conhecidas").
resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id

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
        Resource  = "${aws_s3_bucket.frontend.arn}/*"
      }
    ]
  })

  # A policy publica so e aceita depois que os bloqueios caem. Sem esta
  # dependencia explicita o Terraform tenta as duas em paralelo e o apply falha
  # de forma intermitente, dependendo de qual chamada chega primeiro.
  depends_on = [aws_s3_bucket_public_access_block.frontend]
}
