# Piloto de hipóteses com IA

Execução experimental, separada do motor determinístico. Um agente investiga os
fatos de um checkpoint e formula a própria explicação candidata, ou declara que
a evidência é insuficiente. Ele **não** recebe as anomalias, o score nem as
hipóteses das 11 famílias — a comparação entre as duas abordagens acontece
depois, com uma pessoa no meio.

O desenho está em
[`artefatos/arquitetura-agente-hipoteses-ia.md`](../../../artefatos/arquitetura-agente-hipoteses-ia.md)
e os contratos em
[`artefatos/contrato-agente-hipoteses.md`](../../../artefatos/contrato-agente-hipoteses.md).

Nada aqui escreve no banco, publica em API ou alimenta o dashboard. A saída é
arquivo local, para leitura humana.

## Como rodar

Os alvos saem do `Makefile` de `apps/fullstack`:

```bash
make -C apps/fullstack agente-ensaio   # lote completo com dublê, sem rede
make -C apps/fullstack test-agente     # testes do ciclo, dos tetos e do validador
make -C apps/fullstack agente-checar   # confirma que o Ollama do .env responde
make -C apps/fullstack agente-lote     # lote real, contra o Ollama
make -C apps/fullstack agente-recorte-real   # reconstroi o recorte real da bronze (PostgreSQL local)
make -C apps/fullstack agente-investigar-banco  # investiga o checkpoint do banco (CHECKPOINT=, ENTIDADE=)
```

`agente-ensaio` roda os três casos de `fixtures/` com um dublê de roteiro: não
precisa de modelo, de rede nem de banco, e serve para verificar o ciclo inteiro
numa máquina qualquer. O resultado vai para `saidas/lote-ensaio/`, que é
gitignored.

Para usar o modelo de verdade, as chaves `OLLAMA_*` precisam estar no
`apps/fullstack/.env` — as mesmas que o backend já usa, listadas em
`.env.example`. Nenhuma credencial entra no repositório.

## Onde fica o quê

| Arquivo | O que é |
|---|---|
| `leitor.py` | Leitor de fatos: `CaseReader`, as três consultas e o executor sintético |
| `banco.py` | Abertura de um checkpoint real do PostgreSQL local, somente leitura |
| `contrato.py` | Esquemas e dataclasses do que o modelo responde e do que é gravado |
| `ferramentas.py` | Despacho das três consultas sobre o leitor |
| `casos.py` | Carga de um caso no formato do leitor |
| `prompt.py` | Prompt de sistema e serialização do que o agente vê |
| `modelo.py` | Cliente Ollama (HTTP ou SSH) e o dublê de roteiro |
| `limites.py` | Tetos de chamadas, linhas, tempo e respostas inválidas |
| `agente.py` | O ciclo de investigação |
| `checagem.py` | Confere direção e magnitude das observações usando apenas os pontos citados; a interpretação causal segue para revisão humana |
| `validador.py` | Leitura e recusa da resposta do modelo |
| `registro.py` | Gravação dos casos e do relatório do lote |
| `lote.py` | Execução de vários casos |
| `agentectl.py` | CLI |

## Estado

A leitura dos fatos vive inteira neste pacote: `leitor.py` para o recorte e
`banco.py` para abrir um checkpoint real. As CLIs em `tools/` são só cascas.
O agente não tem leitura própria: ele só investiga. O documento de contratos
descreve os formatos de entrada e saída.
