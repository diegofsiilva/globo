"""Runner de migrations do Argus: aplica os .sql de db/migrations em ordem.

Deliberadamente minimo. Nao ha Alembic nem sqitch aqui porque o que o projeto
precisa cabe em duzentas linhas: aplicar arquivo numerado em ordem, uma vez so,
dentro de uma transacao, e registrar o que ja rodou.

O Terraform NAO cria schema -- ele provisiona a instancia e para. Separar as
duas coisas e o que permite iterar o DDL sem `terraform apply`, que numa sessao
de laboratorio e a diferenca entre trinta segundos e cinco minutos por tentativa.

Uso:
    python tools/migrate.py aplicar          # aplica o que falta
    python tools/migrate.py status           # mostra o que ja rodou
    python tools/migrate.py criar-leitor     # cria o usuario da Lambda

A conexao vem de DATABASE_URL. Nunca de argumento de linha de comando: senha em
argv aparece no `ps` de qualquer processo da maquina.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time
from pathlib import Path

import psycopg

MIGRATIONS = Path(__file__).resolve().parents[1] / "db" / "migrations"

CONTROL = """
CREATE TABLE IF NOT EXISTS public.schema_migrations (
  version    text        PRIMARY KEY,
  checksum   text        NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT now(),
  elapsed_ms integer     NOT NULL
);
"""


def discover() -> list[Path]:
    """Lista as migrations em ordem lexicografica.

    O prefixo numerado de tres digitos e o que faz a ordem lexicografica
    coincidir com a ordem de dependencia. `010` depois de `009` continua
    funcionando; `10` sem o zero nao funcionaria, e a falha seria silenciosa.

    Returns:
        list[Path]: Caminhos dos arquivos .sql, na ordem de aplicacao.
    """
    return sorted(MIGRATIONS.glob("*.sql"))


def checksum(path: Path) -> str:
    """Calcula o hash do conteudo do arquivo.

    Args:
        path (Path): Arquivo da migration.

    Returns:
        str: SHA-256 em hexadecimal.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def connect() -> psycopg.Connection:
    """Abre a conexao a partir de DATABASE_URL.

    Returns:
        psycopg.Connection: Conexao aberta, com autocommit ligado.

    Raises:
        SystemExit: Se DATABASE_URL nao estiver definida.
    """
    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit(
            "erro: DATABASE_URL nao definida.\n"
            "      Local:  postgresql://argus:argus@localhost:5432/argus\n"
            "      No lab: veja `terraform output database_url_hint`"
        )
    # autocommit no nivel da conexao; cada migration abre a sua propria
    # transacao explicita logo abaixo.
    return psycopg.connect(url, autocommit=True)


def applied(conn: psycopg.Connection) -> dict[str, str]:
    """Le as migrations ja registradas.

    Args:
        conn (psycopg.Connection): Conexao aberta.

    Returns:
        dict[str, str]: Mapa `{versao: checksum}`.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT version, checksum FROM public.schema_migrations")
        return dict(cur.fetchall())


def aplicar(conn: psycopg.Connection, forcar: bool = False) -> int:
    """Aplica as migrations pendentes, cada uma numa transacao propria.

    Uma transacao por migration, e nao uma para tudo: o PostgreSQL faz DDL
    transacional, entao uma migration que falha no meio nao deixa metade das
    tabelas criadas. Mas as ja aplicadas ficam -- reexecutar depois de corrigir
    nao refaz o que deu certo.

    Args:
        conn (psycopg.Connection): Conexao aberta.
        forcar (bool): Ignora divergencia de checksum em vez de abortar.

    Returns:
        int: Quantas migrations foram aplicadas.

    Raises:
        SystemExit: Se uma migration ja aplicada teve o conteudo alterado.
    """
    conn.execute(CONTROL)
    ja = applied(conn)
    aplicadas = 0

    for path in discover():
        versao = path.stem
        soma = checksum(path)

        if versao in ja:
            if ja[versao] != soma and not forcar:
                raise SystemExit(
                    f"erro: {versao} ja foi aplicada, mas o arquivo mudou.\n"
                    "      Migration aplicada e imutavel: escreva uma nova em vez\n"
                    "      de editar esta, senao os bancos divergem sem aviso.\n"
                    "      (--forcar apenas reescreve o checksum, nao reaplica.)"
                )
            if ja[versao] != soma:
                conn.execute(
                    "UPDATE public.schema_migrations SET checksum = %s WHERE version = %s",
                    (soma, versao),
                )
                print(f"  ~ {versao}  checksum atualizado (--forcar)")
            continue

        sql = path.read_text(encoding="utf-8")
        print(f"  + {versao} ...", end="", flush=True)
        inicio = time.monotonic()
        with conn.transaction():
            conn.execute(sql)
            elapsed = int((time.monotonic() - inicio) * 1000)
            conn.execute(
                "INSERT INTO public.schema_migrations (version, checksum, elapsed_ms)"
                " VALUES (%s, %s, %s)",
                (versao, soma, elapsed),
            )
        print(f" {elapsed} ms")
        aplicadas += 1

    if not aplicadas:
        print("  nada a fazer: o banco ja esta na ultima versao")
    return aplicadas


def status(conn: psycopg.Connection) -> None:
    """Imprime o que ja rodou e o que falta.

    Args:
        conn (psycopg.Connection): Conexao aberta.
    """
    conn.execute(CONTROL)
    ja = applied(conn)
    for path in discover():
        versao = path.stem
        if versao not in ja:
            marca = "pendente"
        elif ja[versao] != checksum(path):
            marca = "ALTERADA APOS APLICADA"
        else:
            marca = "ok"
        print(f"  {marca:>22s}  {versao}")


def criar_leitor(conn: psycopg.Connection, usuario: str) -> None:
    """Cria (ou atualiza) o usuario de login que a Lambda de leitura usa.

    A senha vem de `DB_READER_PASSWORD`, nunca de argumento: argumento de linha
    de comando aparece no `ps` de qualquer processo da maquina. O usuario nao
    recebe permissao nenhuma diretamente -- so herda `argus_reader`, que so tem
    SELECT nas views `v_*`.

    Args:
        conn (psycopg.Connection): Conexao aberta.
        usuario (str): Nome do usuario a criar.

    Raises:
        SystemExit: Se DB_READER_PASSWORD nao estiver definida.
    """
    senha = os.getenv("DB_READER_PASSWORD")
    if not senha:
        raise SystemExit("erro: DB_READER_PASSWORD nao definida.")

    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (usuario,))
        existe = cur.fetchone() is not None

    verbo = "ALTER" if existe else "CREATE"
    # O nome do papel nao pode ser parametro de bind (identificador, nao valor),
    # entao vai por psycopg.sql.Identifier, que escapa de verdade.
    from psycopg import sql

    conn.execute(
        sql.SQL("{} ROLE {} LOGIN PASSWORD {}").format(
            sql.SQL(verbo), sql.Identifier(usuario), sql.Literal(senha)
        )
    )
    conn.execute(sql.SQL("GRANT argus_reader TO {}").format(sql.Identifier(usuario)))
    print(f"  {usuario}: {'atualizado' if existe else 'criado'}, herda argus_reader")


def main() -> int:
    """Ponto de entrada da linha de comando.

    Returns:
        int: 0 em sucesso.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_aplicar = sub.add_parser("aplicar", help="aplica as migrations pendentes")
    p_aplicar.add_argument(
        "--forcar",
        action="store_true",
        help="aceita checksum divergente numa migration ja aplicada",
    )
    sub.add_parser("status", help="mostra o que ja rodou")
    p_leitor = sub.add_parser("criar-leitor", help="cria o usuario da Lambda")
    p_leitor.add_argument("--usuario", default="argus_api")

    args = parser.parse_args()

    with connect() as conn:
        if args.cmd == "aplicar":
            aplicar(conn, forcar=args.forcar)
        elif args.cmd == "status":
            status(conn)
        elif args.cmd == "criar-leitor":
            criar_leitor(conn, args.usuario)
    return 0


if __name__ == "__main__":
    sys.exit(main())
