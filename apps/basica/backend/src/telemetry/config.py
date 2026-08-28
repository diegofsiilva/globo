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

    # Origens do dashboard. A lista real vem de `dashboard_origins` no
    # Terraform e inclui o website S3 no fallback do Learner Lab; "*" e o
    # padrao apenas do desenvolvimento local, onde a porta do `next dev` muda
    # com frequencia.
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")

    # Nivel do log estruturado. O `observability.py` reconfigura o logger raiz
    # com este valor -- em DEBUG a Lambda passa a registrar tambem o SQL do
    # psycopg, o que e util numa investigacao e caro como padrao.
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # O unico POST desta API e feedback textual curto.
    MAX_CONTENT_LENGTH = 4096

    JSON_SORT_KEYS = False


class TestConfig(Config):
    """Configuracoes usadas nos testes."""

    TESTING = True
    USER_ID_HASH_SALT = "test-salt"
    DATABASE_URL = os.getenv("TEST_DATABASE_URL", "")
