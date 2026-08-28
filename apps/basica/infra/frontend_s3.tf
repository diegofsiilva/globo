# Hospedagem do dashboard: bucket S3 PRIVADO atras do CloudFront.
#
# O dashboard e um export estatico do Next (`output: "export"`), entao sao
# arquivos, nao um processo. Isso e o que permite hospedar por centavos, sem
# instancia para manter viva, corrigir ou religar.
#
# Por que S3 e nao EC2, ja que a entrega aceita os dois: o Learner Lab desliga
# as instancias ao fim da sessao e o IP publico muda ao religar, o que quebraria
# o link do relatorio e do video entre a gravacao e a correcao. O endereco do
# CloudFront e estavel e atravessa o ciclo do lab.
#
# ## Por que CloudFront entrou
#
# O website hosting do S3 serve **somente HTTP**. Enquanto a API era publica
# isso era feio; depois que o operador passou a COLAR UM TOKEN na tela, virou
# uma falha: numa pagina carregada por HTTP, qualquer intermediario da rede le
# o token em claro, e ainda pode injetar JavaScript que o exfiltre. Uma
# credencial so faz sentido sobre um transporte que a protege.
#
# O CloudFront resolve os dois lados: TLS obrigatorio na borda e, com Origin
# Access Control, o bucket volta a ser privado -- so a distribuicao consegue ler
# os objetos, e o endpoint de website do S3 deixa de existir. Referencia:
# https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-s3.html
#
# O nome do bucket precisa ser unico no mundo inteiro, dai o sufixo com o id da
# conta -- sem ele, um `apply` numa conta nova colide com a nossa.

resource "aws_s3_bucket" "frontend" {
  bucket = "${local.name}-site-${data.aws_caller_identity.current.account_id}"
}

# Os quatro bloqueios VOLTAM a ficar ligados. Na versao anterior eles precisavam
# cair porque o endpoint de website do S3 nao fala SigV4 e exigia leitura
# publica. Com OAC a leitura e assinada pela distribuicao, entao nada aqui
# precisa ser publico -- e um `aws s3 cp` anonimo no bucket passa a receber 403.
resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# A policy autoriza UMA distribuicao, identificada pelo ARN. `AWS:SourceArn` e o
# que impede que outra conta crie uma distribuicao apontando para este bucket e
# passe a servir o nosso conteudo.
data "aws_iam_policy_document" "frontend" {
  statement {
    sid       = "LeituraPelaDistribuicaoCloudFront"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.frontend.arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.frontend.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  policy = data.aws_iam_policy_document.frontend.json

  depends_on = [aws_s3_bucket_public_access_block.frontend]
}

# ---------------------------------------------------------------------------- #
# CloudFront
# ---------------------------------------------------------------------------- #

resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "${local.name}-site"
  description                       = "OAC do dashboard Argus"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# O export do Next escreve `agora/index.html`, e nao `agora`. O endpoint REST do
# S3 -- ao contrario do de website -- nao completa o caminho sozinho, entao
# `/agora/` devolveria 404. Esta funcao faz a completacao na borda.
#
# Roda em viewer-request, que e onde a URL ainda pode ser reescrita antes de
# virar chave do objeto. CloudFront Functions sao cobradas por invocacao a um
# decimo do preco de uma Lambda@Edge e executam em microssegundos; para uma
# reescrita de string e o instrumento certo.
resource "aws_cloudfront_function" "rewrite_index" {
  name    = "${local.name}-rewrite-index"
  runtime = "cloudfront-js-2.0"
  comment = "Completa /rota/ com index.html para o export estatico do Next"
  publish = true
  code    = <<-JS
    function handler(event) {
      var request = event.request;
      var uri = request.uri;

      if (uri.endsWith('/')) {
        request.uri = uri + 'index.html';
      } else if (!uri.includes('.')) {
        // Sem extensao e sem barra final: /agora -> /agora/index.html. O teste
        // e por ponto, e nao por lista de rotas, para que uma tela nova nao
        // exija editar esta funcao.
        request.uri = uri + '/index.html';
      }
      return request;
    }
  JS
}

# Cabecalhos de seguranca aplicados a toda resposta.
#
# HSTS: uma vez visitado por HTTPS, o navegador se recusa a voltar para HTTP
# neste host, mesmo que alguem cole um link `http://`. E a barreira que fecha a
# janela do primeiro acesso, onde o downgrade ainda seria possivel.
#
# `nosniff`: sem ele, um navegador pode decidir tratar um arquivo servido como
# texto como se fosse JavaScript, a partir do conteudo.
#
# `frame-ancestors 'none'` e `X-Frame-Options DENY`: o dashboard nunca deve ser
# embutido em outro site. Sem isso, uma pagina hostil poderia sobrepor a tela de
# acesso e capturar o token digitado (clickjacking).
resource "aws_cloudfront_response_headers_policy" "frontend" {
  name    = "${local.name}-seguranca"
  comment = "Cabecalhos de seguranca do dashboard Argus"

  security_headers_config {
    strict_transport_security {
      access_control_max_age_sec = 31536000
      include_subdomains         = true
      preload                    = false
      override                   = true
    }

    content_type_options {
      override = true
    }

    frame_options {
      frame_option = "DENY"
      override     = true
    }

    referrer_policy {
      # A URL da API nao e segredo depois da autenticacao, mas tambem nao ha
      # motivo para vazar o caminho da tela em que o operador estava para todo
      # host externo que ele venha a abrir.
      referrer_policy = "strict-origin-when-cross-origin"
      override        = true
    }

    content_security_policy {
      # `connect-src` limita para onde o bundle pode abrir conexao. Sem isso,
      # um script injetado poderia mandar o token do operador para qualquer
      # host -- que e exatamente o risco novo trazido pela tela de acesso.
      #
      # O curinga `*.execute-api.<regiao>` em vez do endpoint exato e
      # deliberado: referenciar `aws_apigatewayv2_api.read` aqui fecharia um
      # ciclo no grafo do Terraform (a API de leitura precisa do dominio desta
      # distribuicao para o CORS). O curinga ainda restringe a API Gateway
      # nesta regiao, que e o que separa "a nossa API" de um coletor arbitrario
      # na internet.
      content_security_policy = join("; ", [
        "default-src 'self'",
        "connect-src 'self' https://*.execute-api.${var.region}.amazonaws.com",
        "img-src 'self' data:",
        # O Next injeta estilos e o bootstrap de hidratacao inline no HTML
        # exportado; sem 'unsafe-inline' a pagina sobe sem CSS.
        "style-src 'self' 'unsafe-inline'",
        "script-src 'self' 'unsafe-inline'",
        "font-src 'self' data:",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'none'",
      ])
      override = true
    }
  }
}

resource "aws_cloudfront_distribution" "frontend" {
  enabled             = true
  default_root_object = "index.html"
  comment             = "${local.name} — dashboard Argus"
  # PriceClass_100 = America do Norte e Europa. A audiencia e um time no
  # Brasil, atendido pelas bordas dos EUA com latencia aceitavel; as classes
  # maiores acrescentam pontos de presenca na Asia e Oceania que ninguem usaria.
  price_class = "PriceClass_100"

  origin {
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_id                = "s3-frontend"
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
  }

  default_cache_behavior {
    target_origin_id = "s3-frontend"
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]

    # A razao de o CloudFront existir aqui. Um acesso por HTTP e redirecionado,
    # e nao servido: a pagina que pede o token nunca chega ao navegador em
    # texto claro.
    viewer_protocol_policy = "redirect-to-https"
    compress               = true

    # CachingOptimized, id gerenciado pela AWS. O bundle do Next tem hash no
    # nome, entao pode ser cacheado por muito tempo sem risco de servir versao
    # velha; o `index.html` e invalidado a cada deploy (ver `make
    # frontend-deploy`).
    cache_policy_id            = "658327ea-f89d-4fab-a63d-7e88639e58f6"
    response_headers_policy_id = aws_cloudfront_response_headers_policy.frontend.id

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.rewrite_index.arn
    }
  }

  # Sem isto, uma rota inexistente devolveria o XML de AccessDenied do S3 -- o
  # bucket e privado, entao o S3 responde 403 e nao 404 para chave ausente.
  # Traduzir para a pagina 404 do proprio Next mantem o erro dentro do produto.
  custom_error_response {
    error_code            = 403
    response_code         = 404
    response_page_path    = "/404.html"
    error_caching_min_ttl = 60
  }

  custom_error_response {
    error_code            = 404
    response_code         = 404
    response_page_path    = "/404.html"
    error_caching_min_ttl = 60
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    # Certificado default do CloudFront, que cobre o dominio *.cloudfront.net.
    # Um dominio proprio exigiria certificado no ACM em us-east-1 e um registro
    # de DNS que o laboratorio nao tem onde hospedar.
    #
    # `minimum_protocol_version` NAO entra aqui: a AWS so o aceita junto com um
    # certificado proprio, e com o certificado default a chamada falha em
    # `InvalidArgument`. A borda ja negocia TLS 1.2+ com qualquer navegador
    # atual.
    cloudfront_default_certificate = true
  }

  tags = {
    Name = "${local.name}-site"
  }
}
