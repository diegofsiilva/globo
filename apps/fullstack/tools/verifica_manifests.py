r"""Verifica invariantes dos manifests do Kubernetes que o `kustomize` nao checa.

O `kubectl kustomize` garante que o YAML e valido e que os patches casam. Ele nao
tem como saber que a ordem das regras do Ingress importa, que a imagem do `Job` de
migration precisa existir na arquitetura dos nos, ou que o Secret criado pelo
Makefile precisa conter exatamente as chaves que os pods pedem. Sao tres acoplamentos
entre arquivos diferentes, e cada um ja custou uma sessao de depuracao:

1. **Ordem do Ingress.** O controlador emite as regras na ordem declarada. Com `/`
   antes de `/api`, ele casa tudo e o backend nunca recebe requisicao. O sintoma e o
   dashboard funcionando e a API respondendo HTML.

2. **Arquitetura da imagem.** As node pools padrao do EKS Auto Mode sao `amd64`; as
   maquinas do time e o Fargate sao `arm64`. Uma imagem publicada so em `arm64` poe o
   pod em `CrashLoopBackOff` com `exec format error`. Em 21/09/2026 isso valia para a
   imagem `processing`, que e a do `Job` de migration: ela rodava no `kind` (amd64 na
   maquina do dev) e nao poderia rodar no EKS.

3. **Chaves do Secret.** O Deployment le `DATABASE_URL` (usuario de leitura) e os dois
   `Job`s (migration e login de leitura) leem `DATABASE_URL_MASTER` (usuario mestre).
   Trocar as duas falha no meio da migration com `permission denied for schema`,
   deixando o banco parcialmente migrado. Uma chave que o pod pede e o Makefile nao
   cria vira `CreateContainerConfigError`.

Roda offline: nao contacta cluster nenhum, nao precisa de credencial da AWS. E
chamado por `make k8s-validate`, que por sua vez e portao do `make check`.

Uso:
    python3 apps/fullstack/tools/verifica_manifests.py \\
        [--k8s apps/fullstack/k8s] [--makefile apps/fullstack/Makefile]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# Os alvos do kustomize que descrevem o que vai para um cluster. `base` e `migrate`
# sozinhos nao sao aplicaveis (as imagens ainda sao placeholders), mas e neles que
# vivem as referencias ao Secret.
ALVOS_INGRESS = ("overlays/aws", "overlays/kind")
ALVOS_SECRET = ("base", "migrate")


def renderiza(k8s: Path, alvo: str, kubectl: str) -> str:
    """Roda `kubectl kustomize` num alvo e devolve o YAML resultante.

    Args:
        k8s: Raiz da pasta de manifests.
        alvo: Caminho do kustomization, relativo a `k8s`.
        kubectl: Executavel do kubectl.

    Returns:
        O YAML renderizado.

    Raises:
        SystemExit: Se o kustomize falhar, com a mensagem dele.
    """
    r = subprocess.run(
        [kubectl, "kustomize", str(k8s / alvo)],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        sys.exit(f"erro: `kubectl kustomize {k8s / alvo}` falhou:\n{r.stderr}")
    return r.stdout


def caminhos_do_ingress(yaml: str) -> list[str]:
    """Extrai, em ordem, os `path:` das regras do Ingress.

    A leitura e por linha de proposito: a alternativa seria arrastar PyYAML para
    `tools/`, que hoje so depende de pyarrow e psycopg, por causa de tres campos.

    Args:
        yaml: YAML renderizado, possivelmente com varios documentos.

    Returns:
        Os caminhos na ordem em que aparecem.
    """
    caminhos: list[str] = []
    dentro_do_ingress = False
    for linha in yaml.splitlines():
        if linha.startswith("kind: "):
            dentro_do_ingress = linha.strip() == "kind: Ingress"
        if dentro_do_ingress:
            m = re.match(r"\s*-?\s*path:\s*(\S+)", linha)
            if m:
                caminhos.append(m.group(1))
    return caminhos


def imagens_referenciadas(k8s: Path) -> set[str]:
    """Descobre quais imagens do projeto o cluster executa.

    Os manifests nunca escrevem o endereco do repositorio: usam os placeholders
    `IMAGE_BACKEND`, `IMAGE_FRONTEND` e `IMAGE_PROCESSING`, substituidos no
    `make k8s-apply`. Sao eles que dizem quais imagens precisam rodar nos nos.

    Args:
        k8s: Raiz da pasta de manifests.

    Returns:
        Nomes de imagem em minuscula, como o Makefile os chama.
    """
    achadas: set[str] = set()
    for arquivo in k8s.rglob("*.yaml"):
        texto = arquivo.read_text(encoding="utf-8")
        # Ancorado no campo `image:` de proposito: `IMAGE_TAG` aparece em
        # comentario e nao e uma imagem.
        for m in re.finditer(r"^\s*image:\s*IMAGE_([A-Z]+)\b", texto, re.MULTILINE):
            achadas.add(m.group(1).lower())
    return achadas


def variavel_do_makefile(makefile: Path, nome: str) -> list[str]:
    """Le uma variavel de lista do Makefile, sem executar make.

    Args:
        makefile: Caminho do Makefile.
        nome: Nome da variavel, por exemplo `IMAGES_MULTIARCH`.

    Returns:
        Os valores declarados, ou lista vazia se a variavel nao existir.
    """
    texto = makefile.read_text(encoding="utf-8")
    m = re.search(rf"^{nome}\s*:?\??=\s*(.*)$", texto, re.MULTILINE)
    return m.group(1).split() if m else []


def chaves_criadas_pelo_makefile(makefile: Path) -> set[str]:
    """Extrai as chaves que `make k8s-secret` grava no Secret.

    Le o proprio Makefile em vez de manter uma copia da lista aqui: uma copia
    divergiria em silencio no dia em que alguem acrescentasse uma chave la.

    Args:
        makefile: Caminho do Makefile.

    Returns:
        Os nomes das chaves.
    """
    texto = makefile.read_text(encoding="utf-8")
    return set(re.findall(r"--from-literal=([A-Z0-9_]+)=", texto))


def chaves_pedidas_pelos_pods(yaml: str) -> dict[str, set[str]]:
    """Mapeia cada carga de trabalho as chaves de Secret que ela consome.

    Args:
        yaml: YAML renderizado.

    Returns:
        Dicionario de `kind/nome` para o conjunto de chaves pedidas.
    """
    pedidas: dict[str, set[str]] = {}
    atual = "?"
    kind = "?"
    linhas = yaml.splitlines()
    for i, linha in enumerate(linhas):
        if linha.startswith("kind: "):
            kind = linha.split(":", 1)[1].strip()
        elif re.match(r"^\s{2}name:\s", linha) and atual == "?":
            atual = f"{kind}/{linha.split(':', 1)[1].strip()}"
        elif linha.startswith("---"):
            atual, kind = "?", "?"
        elif "secretKeyRef:" in linha:
            # A chave e o nome do Secret vem nas linhas seguintes, mais indentados.
            for proxima in linhas[i + 1 : i + 4]:
                m = re.match(r"\s*key:\s*(\S+)", proxima)
                if m:
                    pedidas.setdefault(atual, set()).add(m.group(1))
    return pedidas


def main() -> int:
    """Roda as tres verificacoes e devolve o codigo de saida do processo."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--k8s", default="k8s", type=Path)
    p.add_argument("--makefile", default="Makefile", type=Path)
    p.add_argument("--kubectl", default="kubectl")
    args = p.parse_args()

    falhas: list[str] = []
    vistas = 0

    def relata(nome: str, todas: list[str], detalhe: str) -> None:
        """Imprime o estado de uma verificacao, contando so as falhas novas."""
        nonlocal vistas
        novas = todas[vistas:]
        vistas = len(todas)
        estado = f"FALHOU ({len(novas)})" if novas else f"ok ({detalhe})"
        print(f"  {nome:<24}{estado}")

    # 1. Ordem das regras do Ingress.
    for alvo in ALVOS_INGRESS:
        caminhos = caminhos_do_ingress(renderiza(args.k8s, alvo, args.kubectl))
        if "/" in caminhos:
            raiz = caminhos.index("/")
            tardias = [c for c in caminhos[raiz + 1 :] if c != "/"]
            if tardias:
                falhas.append(
                    f"{alvo}: a regra '/' vem antes de {tardias} no Ingress. "
                    "O controlador emite as regras na ordem declarada, entao '/' "
                    "casaria tudo e esses caminhos nunca receberiam requisicao."
                )
    relata("ordem do Ingress", falhas, f"{len(ALVOS_INGRESS)} overlays")

    # 2. Toda imagem que o cluster executa precisa ser multi-arquitetura.
    no_cluster = imagens_referenciadas(args.k8s)
    multiarch = set(variavel_do_makefile(args.makefile, "IMAGES_MULTIARCH"))
    so_uma_arch = sorted(no_cluster - multiarch)
    if so_uma_arch:
        falhas.append(
            f"imagens executadas no cluster e ausentes de IMAGES_MULTIARCH: "
            f"{so_uma_arch}. Os nos do Auto Mode sao amd64 e o build padrao e "
            "arm64, entao o pod falharia com `exec format error`."
        )
    relata("imagens multi-arch", falhas, f"{len(no_cluster)} no cluster")

    # 3. Chaves de Secret pedidas x criadas, e o par DATABASE_URL / _MASTER.
    criadas = chaves_criadas_pelo_makefile(args.makefile)
    pedidas_total: dict[str, set[str]] = {}
    for alvo in ALVOS_SECRET:
        for carga, chaves in chaves_pedidas_pelos_pods(
            renderiza(args.k8s, alvo, args.kubectl)
        ).items():
            pedidas_total.setdefault(carga, set()).update(chaves)

    for carga, chaves in sorted(pedidas_total.items()):
        faltando = sorted(chaves - criadas)
        if faltando:
            falhas.append(
                f"{carga} pede as chaves {faltando}, que `make k8s-secret` nao cria. "
                "O pod subiria em CreateContainerConfigError."
            )
    migracoes = [c for c in pedidas_total if c.startswith("Job/")]
    for carga in migracoes:
        if "DATABASE_URL_MASTER" not in pedidas_total[carga]:
            falhas.append(
                f"{carga} nao usa DATABASE_URL_MASTER. O Job aplica DDL e faz GRANT: "
                "com o usuario de leitura ele falha no meio, deixando o banco "
                "parcialmente migrado."
            )
    relata("chaves do Secret", falhas, f"{len(pedidas_total)} cargas")

    for f in falhas:
        print(f"\nerro: {f}", file=sys.stderr)
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
