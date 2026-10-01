"""Configuracoes da API de leitura."""

import os


class Config:
    """Configuracoes globais do backend de leitura do Argus."""

    # Conexao com o PostgreSQL. A Lambda entra como `argus_api`, NAO como o
    # usuario mestre: esse papel so tem SELECT nas views v_*, e e ele que
    # impede a API de enxergar alem do relogio virtual mesmo que alguem esqueca
    # o filtro numa rota nova. Ver 009_views_v.sql.
    DATABASE_URL = os.getenv("DATABASE_URL", "")

    AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

    # O user_id vai para o dashboard como hash. O banco guarda o identificador
    # original porque a ingestao nao o transforma; o hash acontece na LEITURA.
    # Trocar o salt reembaralha os hashes: eventos do mesmo usuario deixam de
    # agrupar com os antigos.
    USER_ID_HASH_SALT = os.getenv("USER_ID_HASH_SALT", "local-development-only")

    # Janela padrao quando a consulta nao informa periodo. Existe para evitar
    # que uma tela sem filtro varra a particao inteira sem querer. Contada a
    # partir de sim.now(), o presente VIRTUAL.
    DEFAULT_WINDOW_HOURS = int(os.getenv("DEFAULT_WINDOW_HOURS", "168"))

    # Teto de linhas devolvidas numa busca ou numa serie. Protege o RNF02
    # (resposta em 3s) e o navegador: um grafico com 200 mil pontos trava a aba
    # antes de terminar de desenhar.
    MAX_ITEMS_SCANNED = int(os.getenv("MAX_ITEMS_SCANNED", "20000"))

    # Teto de duracao de UMA consulta, em milissegundos. O padrao de 15 s fica
    # abaixo dos 30 s da Lambda: assim o erro chega como 500 legivel em vez do
    # 502 que o API Gateway devolve quando a Lambda morre antes de responder.
    # No Deployment do EKS nao existe esse teto de 30 s, e a tela Agora varre
    # 7 dias de baseline -- num RDS burstable sem credito de CPU isso passa dos
    # 15 s e a tela quebra com 500. La o valor e elevado pelo ambiente.
    STATEMENT_TIMEOUT_MS = int(os.getenv("STATEMENT_TIMEOUT_MS", "15000"))

    # Origens do dashboard. A lista real vem de `dashboard_origins` no
    # Terraform e inclui o website S3 no fallback do Learner Lab; "*" e o
    # padrao apenas do desenvolvimento local, onde a porta do `next dev` muda
    # com frequencia.
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")

    # Nivel do log estruturado. O `observability.py` reconfigura o logger raiz
    # com este valor -- em DEBUG a Lambda passa a registrar tambem o SQL do
    # psycopg, o que e util numa investigacao e caro como padrao.
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # Autenticacao Bearer dentro da aplicacao.
    #
    # Existe desde que a API saiu da Lambda: o API Gateway tinha um authorizer,
    # o Application Load Balancer nao tem, e sem isto tirar o gateway do caminho
    # deixaria a API aberta. Ver interfaces/auth.py.
    #
    # Desligada por padrao porque o desenvolvimento local, os testes e o e2e do
    # frontend sobem a aplicacao sem segredo nenhum. Quem liga na AWS e o
    # ConfigMap do cluster (k8s/base/configmap.yaml).
    AUTH_REQUIRED = os.getenv("AUTH_REQUIRED", "0")

    # SHA-256 do token da audiencia `dashboard`. NAO e o token: o valor em claro
    # nunca entra no container. `make k8s-secret` le o hash dos outputs do
    # Terraform e o poe no Secret do namespace, de onde o pod o recebe como
    # variavel -- e por isso que a aplicacao nao precisa de boto3.
    DASHBOARD_TOKEN_SHA256 = os.getenv("DASHBOARD_TOKEN_SHA256", "")

    # Ollama e opcional e fica fora do motor deterministico. Em desenvolvimento,
    # OLLAMA_URL normalmente aponta para localhost, na ponta de um tunel SSH.
    OLLAMA_URL = os.getenv("OLLAMA_URL", "")
    # Vazio seleciona automaticamente o primeiro modelo devolvido por /api/tags.
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "")
    OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "90"))
    OLLAMA_SSH_HOST = os.getenv("OLLAMA_SSH_HOST", "")
    OLLAMA_SSH_PORT = int(os.getenv("OLLAMA_SSH_PORT", "22"))
    OLLAMA_SSH_USER = os.getenv("OLLAMA_SSH_USER", "")
    OLLAMA_SSH_PASSWORD = os.getenv("OLLAMA_SSH_PASSWORD", "")
    OLLAMA_REMOTE_HOST = os.getenv("OLLAMA_REMOTE_HOST", "127.0.0.1")
    OLLAMA_REMOTE_PORT = int(os.getenv("OLLAMA_REMOTE_PORT", "11434"))

    # O unico POST desta API e feedback textual curto.
    MAX_CONTENT_LENGTH = 4096

    JSON_SORT_KEYS = False


class TestConfig(Config):
    """Configuracoes usadas nos testes."""

    TESTING = True
    USER_ID_HASH_SALT = "test-salt"
    DATABASE_URL = os.getenv("TEST_DATABASE_URL", "")
