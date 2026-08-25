"""Entrypoint da API de leitura na AWS Lambda.

O `apig-wsgi` traduz o evento do API Gateway (payload format 2.0) para o
protocolo WSGI que o Flask entende, nos dois sentidos. E so isso: a aplicacao
e a mesma que roda com `flask run` ou gunicorn, sem nenhum `if lambda:` no
codigo.

O `create_app()` roda fora do handler de proposito. Esse trecho executa uma vez
por container e fica em memoria entre invocacoes: e ali que o pool de conexao
com o PostgreSQL e criado. Abrir conexao dentro do handler pagaria o handshake
completo a cada requisicao -- e no PostgreSQL isso e caro de verdade, porque
cada conexao vira um processo novo no servidor, e nao uma thread.
"""

import os
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from apig_wsgi import make_lambda_handler  # noqa: E402

from telemetry.app import create_app  # noqa: E402

app = create_app()

# binary_support=False: a API so devolve JSON. Ligar isso faria o apig-wsgi
# codificar respostas em base64 sem necessidade.
handler = make_lambda_handler(app, binary_support=False)


def lambda_handler(event, context):
    """Entrypoint invocado pela AWS Lambda a cada requisição do API Gateway.

    Args:
        event (dict): Evento do API Gateway no payload format 2.0.
        context: Objeto de contexto de execução da Lambda (`LambdaContext`),
            repassado ao `apig-wsgi` sem uso direto aqui.

    Returns:
        dict: Resposta no formato de proxy do API Gateway, já traduzida a
            partir da resposta WSGI produzida pelo Flask.
    """
    return handler(event, context)


# Permite `python lambda_handler.py` para subir localmente sem gunicorn.
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
