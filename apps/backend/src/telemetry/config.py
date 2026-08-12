import os


class Config:
    # Tabela que o worker de ingestao escreve. Ver infra/dynamodb.tf.
    EVENTS_TABLE_NAME = os.getenv("EVENTS_TABLE_NAME", "argus-events-dev")
    AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

    # Usado so em teste e desenvolvimento local, para apontar o boto3 para um
    # DynamoDB falso (moto). Vazio em producao.
    DYNAMODB_ENDPOINT_URL = os.getenv("DYNAMODB_ENDPOINT_URL") or None

    # PRECISA bater com var.gsi1_shards do Terraform e com GSI1_SHARDS do
    # worker. Os tres montam a mesma chave: se divergirem, a leitura procura
    # numa particao onde a escrita nunca colocou nada, e o resultado e uma
    # consulta que devolve vazio sem erro nenhum.
    GSI1_SHARDS = int(os.getenv("GSI1_SHARDS", "10"))

    # O user_id vai para o dashboard como hash. Trocar o salt reembaralha os
    # hashes: eventos do mesmo usuario deixam de agrupar com os antigos.
    USER_ID_HASH_SALT = os.getenv("USER_ID_HASH_SALT", "local-development-only")

    # Janela padrao quando a consulta nao informa periodo. Existe para evitar
    # que uma tela sem filtro varra a tabela inteira sem querer.
    DEFAULT_WINDOW_HOURS = int(os.getenv("DEFAULT_WINDOW_HOURS", "168"))

    # Teto de itens lidos numa agregacao. Protege o RNF02 (resposta em 3s):
    # acima disso a resposta vem truncada em vez de demorar.
    MAX_ITEMS_SCANNED = int(os.getenv("MAX_ITEMS_SCANNED", "20000"))

    # Origens do dashboard. "*" e aceitavel enquanto a API nao expoe dado
    # sensivel sem autenticacao; restrinja antes de producao (RNF09).
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")

    JSON_SORT_KEYS = False


class TestConfig(Config):
    TESTING = True
    EVENTS_TABLE_NAME = "argus-events-test"
    USER_ID_HASH_SALT = "test-salt"
    GSI1_SHARDS = 4
