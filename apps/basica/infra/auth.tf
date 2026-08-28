# Autenticacao das APIs: Lambda authorizer com token compartilhado.
#
# Ate aqui as APIs eram publicas e a URL era a unica barreira. Isso reprovava o
# RNF09 e deixava o dado do parceiro a um `curl` de distancia de quem visse a
# URL num print, num video ou no bundle do dashboard.
#
# ## Por que authorizer, e nao API key
#
# A chave de API do API Gateway existe para medir e limitar consumo por cliente.
# A propria documentacao da AWS registra que ela nao e um mecanismo de
# autorizacao e recomenda authorizer, IAM ou Cognito:
# https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-api-usage-plans.html
#
# Cognito daria identidade por pessoa, que e melhor, e custaria um pool de
# usuarios, um fluxo de login e um cadastro para manter -- fora do que este MVP
# entrega. O authorizer com token compartilhado e a opcao intermediaria: barra o
# acesso anonimo de verdade e cabe no escopo. A limitacao esta registrada no
# README: **o token identifica um SERVICO, nao uma pessoa**; nao ha como saber
# qual integrante fez uma consulta, e a resposta a um vazamento e rotacionar,
# nao revogar um usuario.
#
# ## Onde ficam os tokens
#
# Sao dois valores aleatorios de 256 bits. O Secrets Manager guarda APENAS o
# SHA-256 de cada um; o valor em claro so existe no terminal de quem rodou
# `make auth-rotate` e nos clientes que o receberam. Nem o Terraform state nem
# o repositorio chegam a ve-lo -- por isso o segredo e criado aqui vazio e
# preenchido pelo Makefile, e nao por um `aws_secretsmanager_secret_version`
# com `random_password`, que gravaria o token no state em claro.

resource "aws_secretsmanager_secret" "auth_tokens" {
  name        = "${local.name}/auth-tokens"
  description = "SHA-256 dos tokens Bearer das APIs do Argus (dashboard e ingest)"

  # Zero e nao os 30 dias padrao: no Learner Lab um `destroy` seguido de
  # `apply` acontece com frequencia, e um segredo em quarentena bloquearia a
  # recriacao com o mesmo nome por um mes.
  recovery_window_in_days = 0

  tags = {
    Name = "${local.name}-auth-tokens"
  }
}

# O token de ingestao EM CLARO, para os clientes que precisam apresenta-lo.
#
# Segredo separado do de hashes, de proposito. O authorizer le apenas os hashes
# e nunca precisa do valor original; o simulador precisa do valor e nao tem o
# que fazer com os hashes. Duas entradas permitem que cada um leia so o que usa.
#
# O simulador o recebe por `secrets` na task definition, e nao por
# `environment`: o segundo apareceria em claro em qualquer
# `aws ecs describe-task-definition`, que e uma chamada de LEITURA -- o token
# vazaria para quem tem permissao de olhar a infraestrutura, sem nenhuma
# permissao sobre os dados.
resource "aws_secretsmanager_secret" "ingest_token" {
  name        = "${local.name}/ingest-token"
  description = "Token Bearer de ingestao, em claro, para simulador e replay"

  recovery_window_in_days = 0

  tags = {
    Name = "${local.name}-ingest-token"
  }
}

# ---------------------------------------------------------------------------- #
# A funcao
# ---------------------------------------------------------------------------- #

resource "aws_cloudwatch_log_group" "authorizer" {
  name              = "/aws/lambda/${local.name}-authorizer"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "authorizer" {
  function_name = "${local.name}-authorizer"
  role          = local.authorizer_role_arn
  handler       = "handler.lambda_handler"
  runtime       = "python3.12"
  architectures = ["arm64"]

  filename         = var.authorizer_package_path
  source_code_hash = filebase64sha256(var.authorizer_package_path)

  # A funcao le uma variavel de ambiente, calcula um SHA-256 e compara duas
  # strings. O piso de 128 MB ja e folgado; o que importa e o cold start, que
  # entra no caminho de toda requisicao das duas APIs.
  memory_size = 128
  timeout     = 5

  # NAO entra na VPC, ao contrario da API de leitura. O unico destino e o
  # Secrets Manager, que e um endpoint publico da AWS; colocar a funcao numa
  # subnet sem NAT faria toda chamada expirar nos 5 s do timeout, e o resultado
  # seria 403 em tudo.

  environment {
    variables = {
      SECRET_ID = aws_secretsmanager_secret.auth_tokens.name
      # Qual audiencia vale em qual API. E o que impede o token do dashboard --
      # o que fica no navegador do operador, e portanto o mais exposto -- de
      # servir tambem para injetar evento na ingestao.
      AUDIENCIAS_POR_API = jsonencode({
        (aws_apigatewayv2_api.read.id)   = ["dashboard"]
        (aws_apigatewayv2_api.events.id) = ["ingest"]
      })
      LOG_LEVEL = var.worker_log_level
    }
  }

  depends_on = [aws_cloudwatch_log_group.authorizer]

  tags = {
    Name = "${local.name}-authorizer"
  }
}

resource "aws_iam_role" "authorizer" {
  count = var.create_iam_roles ? 1 : 0

  name               = "${local.name}-authorizer"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume[0].json
}

data "aws_iam_policy_document" "authorizer" {
  count = var.create_iam_roles ? 1 : 0

  statement {
    sid       = "LerHashesDosTokens"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.auth_tokens.arn]
  }

  statement {
    sid       = "EscreverLogs"
    effect    = "Allow"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.authorizer.arn}:*"]
  }
}

resource "aws_iam_role_policy" "authorizer" {
  count = var.create_iam_roles ? 1 : 0

  name   = "authorize-requests"
  role   = aws_iam_role.authorizer[0].id
  policy = data.aws_iam_policy_document.authorizer[0].json
}

resource "aws_lambda_permission" "authorizer_read" {
  statement_id  = "AllowReadApiInvokeAuthorizer"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.authorizer.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.read.execution_arn}/*"
}

resource "aws_lambda_permission" "authorizer_events" {
  statement_id  = "AllowEventsApiInvokeAuthorizer"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.authorizer.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.events.execution_arn}/*"
}

# ---------------------------------------------------------------------------- #
# Os authorizers
# ---------------------------------------------------------------------------- #

# `identity_sources` e o que faz o gateway responder 401 SEM invocar a funcao
# quando o cabecalho falta. Com token presente e invalido, a funcao roda e
# devolve `isAuthorized: false`, que vira 403. Separar os dois codigos e o que
# permite distinguir cliente desconfigurado de tentativa de acesso no
# CloudWatch (RNF09).
#
# O cache de 5 min e por valor do identity source, ou seja, por token. Sem ele,
# cada consulta do dashboard pagaria uma invocacao a mais de Lambda; com ele, o
# custo do authorizer some e a rotacao leva no maximo 5 min para propagar.

resource "aws_apigatewayv2_authorizer" "read" {
  api_id                            = aws_apigatewayv2_api.read.id
  name                              = "${local.name}-read-bearer"
  authorizer_type                   = "REQUEST"
  authorizer_uri                    = aws_lambda_function.authorizer.invoke_arn
  authorizer_payload_format_version = "2.0"
  enable_simple_responses           = true
  identity_sources                  = ["$request.header.Authorization"]
  authorizer_result_ttl_in_seconds  = 300
}

resource "aws_apigatewayv2_authorizer" "events" {
  api_id                            = aws_apigatewayv2_api.events.id
  name                              = "${local.name}-ingest-bearer"
  authorizer_type                   = "REQUEST"
  authorizer_uri                    = aws_lambda_function.authorizer.invoke_arn
  authorizer_payload_format_version = "2.0"
  enable_simple_responses           = true
  identity_sources                  = ["$request.header.Authorization"]
  authorizer_result_ttl_in_seconds  = 300
}

# ---------------------------------------------------------------------------- #
# A unica rota publica
# ---------------------------------------------------------------------------- #

# `GET /health/live` fica sem authorizer porque e a sonda de vida: ela precisa
# responder mesmo quando o Secrets Manager esta fora, e nao revela nada -- o
# corpo e `{"status": "ok"}` fixo, sem tocar no banco.
#
# Rota explicita vence `ANY /{proxy+}` no roteamento do API Gateway, entao esta
# declaracao e o que abre a excecao. `/health/ready` NAO entra aqui: ela
# consulta o banco e o resultado ja diz se ha dado do parceiro carregado.
resource "aws_apigatewayv2_route" "health_live" {
  api_id             = aws_apigatewayv2_api.read.id
  route_key          = "GET /health/live"
  target             = "integrations/${aws_apigatewayv2_integration.read.id}"
  authorization_type = "NONE"
}

# ---------------------------------------------------------------------------- #
# Alarme
# ---------------------------------------------------------------------------- #

# Negacao e um evento normal (cliente sem token, token expirado). O que nao e
# normal e um volume subito delas: e o formato de uma tentativa de adivinhar o
# token. O limiar e alto o bastante para nao disparar com alguem errando a
# colagem duas ou tres vezes.
resource "aws_cloudwatch_metric_alarm" "authorizer_negacoes" {
  alarm_name          = "${local.name}-authorizer-negacoes"
  alarm_description   = "Muitas requisicoes recusadas: possivel tentativa de adivinhar o token."
  namespace           = "AWS/ApiGateway"
  metric_name         = "4xx"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = var.alarm_4xx_threshold
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    ApiId = aws_apigatewayv2_api.read.id
  }

  alarm_actions = [aws_sns_topic.alarms.arn]
}
