# Tabela unica (single-table design) dos eventos de telemetria.
#
#   tabela  pk=SESSION#<session_id>                sk=<ts>#<event_id>
#   GSI1    gsi1pk=EVT#<event_name>#<data>#<shard> gsi1sk=<ts>#<event_id>
#   GSI2    gsi2pk=DEV#<device_id>                 gsi2sk=<ts>#<event_id>
#
# So os atributos de chave sao declarados: o DynamoDB e schemaless no resto, e e
# isso que permite os seis tipos de evento (com colunas diferentes) conviverem
# na mesma tabela sem migracao a cada campo novo.

resource "aws_dynamodb_table" "events" {
  name         = local.name
  billing_mode = var.dynamodb_billing_mode
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }
  attribute {
    name = "sk"
    type = "S"
  }
  attribute {
    name = "gsi1pk"
    type = "S"
  }
  attribute {
    name = "gsi1sk"
    type = "S"
  }
  attribute {
    name = "gsi2pk"
    type = "S"
  }
  attribute {
    name = "gsi2sk"
    type = "S"
  }

  # Eventos de um tipo, num dia. Sharded para nao concentrar a escrita numa
  # particao so (ver var.gsi1_shards).
  global_secondary_index {
    name            = "gsi1"
    hash_key        = "gsi1pk"
    range_key       = "gsi1sk"
    projection_type = "ALL"
  }

  # Historico de um aparelho. device_id ja distribui bem, nao precisa shard.
  global_secondary_index {
    name            = "gsi2"
    hash_key        = "gsi2pk"
    range_key       = "gsi2sk"
    projection_type = "ALL"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = var.dynamodb_point_in_time_recovery
  }

  # Cuidado com a leitura deste bloco: o DynamoDB criptografa em repouso SEMPRE,
  # nao da para desligar. O que muda aqui e so QUAL chave:
  #
  #   false -> chave AWS-owned. Padrao, gratis, invisivel no KMS.
  #   true  -> chave AWS-managed (aws/dynamodb). Aparece no seu KMS, permite
  #            auditar uso via CloudTrail, custa ~US$ 1/mes.
  #
  # Ambiente de laboratorio nao consegue criar a chave gerenciada, por isso a
  # variavel existe.
  server_side_encryption {
    enabled = var.dynamodb_kms_managed_key
  }

  # Protecao contra `terraform destroy` distraido levando a base de eventos.
  # Para derrubar de proposito: mude para false, aplique, e so entao destrua.
  deletion_protection_enabled = var.environment == "prod"

  lifecycle {
    # PROVISIONED ajustado por autoscaling nao pode ser revertido pelo TF a cada
    # plan; em PAY_PER_REQUEST estes campos sao ignorados pela AWS mesmo.
    ignore_changes = [read_capacity, write_capacity]
  }

  tags = {
    Name = local.name
  }
}
