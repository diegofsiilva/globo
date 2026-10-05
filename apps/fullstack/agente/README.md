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
| `contrato.py` | Esquemas e dataclasses dos quatro contratos |
| `ferramentas.py` | Porta das três consultas e o adaptador sobre fixture |
| `casos.py` | Carga de um caso e cálculo do digest do recorte |
| `prompt.py` | Prompt de sistema e serialização do que o agente vê |
| `modelo.py` | Cliente Ollama (HTTP ou SSH) e o dublê de roteiro |
| `limites.py` | Tetos de chamadas, linhas, tempo e respostas inválidas |
| `agente.py` | O ciclo de investigação |
| `validador.py` | Leitura e recusa da resposta do modelo |
| `registro.py` | Gravação dos casos e do relatório do lote |
| `lote.py` | Execução de vários casos |
| `agentectl.py` | CLI |

## Estado

O adaptador de dados é um dublê sobre arquivo JSON. O adaptador real sobre
`silver.analysis_fact_version` é trabalho da pessoa dos dados, e a seção 6 do
documento de contratos lista o que ainda depende dela.
