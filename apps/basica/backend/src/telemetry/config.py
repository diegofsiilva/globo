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

    # Origens do dashboard. "*" e aceitavel enquanto a API nao expoe dado
    # sensivel sem autenticacao; restrinja antes de producao (RNF09).
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")

    JSON_SORT_KEYS = False


class TestConfig(Config):
    """Configuracoes usadas nos testes."""

    TESTING = True
    USER_ID_HASH_SALT = "test-salt"
    DATABASE_URL = os.getenv("TEST_DATABASE_URL", "")
