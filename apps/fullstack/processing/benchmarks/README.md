# Gerador e motor Go para o benchmark

Este diretório contém o experimento isolado de cálculo do motor de hipóteses.
O serviço Python continua sendo a implementação de produção. A versão Go não
acessa PostgreSQL, ETL, filas, API, leases ou persistência.

## Executar

Pré-requisitos: Python e `uv` conforme o projeto, Go 1.22 ou superior e o
ambiente de `make` do repositório. Não há dependências Go externas nem necessidade
de contêiner. No Windows, os alvos gerais do repositório precisam de Bash
(por exemplo, Git Bash); o executável Go deve estar no PATH.

Na raiz do repositório:

```sh
make -C apps/fullstack benchmark-fixtures
make -C apps/fullstack benchmark-paridade
```

O primeiro comando **reescreve** os três JSONs: revise o diff antes de aceitar
novas referências. O segundo confere a reprodução dos JSONs, executa os testes
Go e compara as saídas completas Python × Go. Ele não altera referências.

Alvos individuais:

| Alvo | Resultado |
| --- | --- |
| `benchmark-fixtures` | Recria os três JSONs determinísticos |
| `benchmark-fixtures-check` | Falha se houver divergência, sem escrever arquivos |
| `benchmark-go-test` | Executa os testes do motor Go, incluindo paridade e bordas |
| `benchmark-paridade` | Verifica 49 cenários, ciclo base e quatro cargas completas |
| `benchmark-medir` | Verifica paridade, mede cinco perfis e grava tempos brutos e relatório |

Para uma instalação Go fora do PATH, passe `GO=/caminho/para/go` ao `make`.
O ambiente Python também pode ser direcionado com `UV_PROJECT_ENVIRONMENT`,
conforme o comportamento padrão do `uv`.

## De onde vêm os dados

`gerar_fixtures.py` importa cópias novas dos módulos de teste e captura suas
entradas, executando também as asserções originais. Os JSONs existentes nunca
são usados como entrada do gerador.

- `test_familias.py`: 49 chamadas dos cenários das 11 famílias. A saída congelada
  inclui todas as famílias produzidas, não apenas a família foco do teste.
- `test_rules.py`: cenário positivo misto com 16 fatos. O gerador adiciona
  baselines artificiais com `n = 12`, variância `0.01` e observação anterior
  em um dia. `n = 12` descreve um estado sintético, não uma série histórica real.
- Cargas dispersas: acrescentam fatos de CPU em entidades novas, sem baseline
  aquecido; não geram anomalias adicionais.
- Cargas densas: acrescentam erros em entidades novas com baseline aquecido;
  a maior carga exercita o limite de 500 hipóteses geradas.

Não há aleatoriedade, horário atual ou dados do parceiro na geração. IDs, janelas,
ordem e tamanhos são fixos. Os resultados esperados vêm do motor Python atual;
isso mede equivalência de comportamento, não valida a correção do diagnóstico
de forma independente.

`source_revision = 534a9ca` conserva a origem histórica dos cenários iniciais.
`source_files_sha256` identifica o conteúdo efetivamente usado dos testes,
módulos Python e ferramentas de geração/comparação, inclusive alterações ainda
sem commit. Os hashes normalizam quebras de linha para LF. O manifesto identifica
os cinco catálogos e os parâmetros do motor. O modo `--check` também detecta
divergências nesses metadados.

## Tradução para Go

| Python de referência | Go em `golang/` |
| --- | --- |
| `domain.py` | `domain.go`: fatos, baselines, anomalias, evidências e hipóteses |
| `catalog.py` | `catalog.go`: carregamento, relações de entidades e hash canônico |
| `quality.py` | `quality.go`: qualidade por fonte |
| `detector.py` | `detector.go`: EWMA causal, materialidade e hora de São Paulo |
| `rules.py` | `rules.go`: 11 famílias, cortes, evidências e deduplicação |
| `scoring.py` | `scoring.go`: score, cobertura e confiança |
| Composição do cálculo | `fixtures.go`: execução isolada dos casos e do ciclo |

É uma implementação Go independente, escrita a partir do Python; ela não chama
Python nem lê `expected` para produzir resultados. Os catálogos são lidos da pasta
Python original. A CLI `golang/cmd/paridade` lê um documento portátil e imprime
suas saídas como JSON. O script `verificar_paridade.py` compila essa CLI em uma
pasta temporária e compara com execuções novas do Python.

As verificações cobrem campos ausentes, textos, ordenação, evidências, status,
hashes e contadores. Números reais aceitam `abs_tol=1e-12` ou `rel_tol=1e-9`;
classificações e chaves exigem igualdade. As quatro cargas são comparadas por
**saída completa**, além de suas contagens congeladas.

Testes Go adicionais exercitam repetição causal, preservação do estado de entrada,
horário de verão de São Paulo, precisão temporal, qualidade de dados ausentes e
cortes estáveis, além de aquecimento, direção, materialidade e limites do detector.
Os testes Python do gerador verificam reprodução, reinicialização
dos IDs e falha de `--check` sem sobrescrever arquivos.

## Medição local

```sh
make -C apps/fullstack benchmark-medir
```

O alvo confere os dados, roda os testes Go, exige paridade completa e então mede
qualidade, detector, geração de candidatos, score e cálculo completo. Por padrão,
são 5 aquecimentos e 50 repetições por etapa/carga/linguagem. As entradas tipadas e
os catálogos são preparados fora do cronômetro; o ciclo total não inclui projeção
para JSON. Python usa `perf_counter_ns`; no Windows o Go usa
`QueryPerformanceCounter` para evitar a granularidade insuficiente observada no
relógio padrão para estas etapas curtas.

Cada perfil/linguagem usa um processo novo, com afinidade à mesma CPU lógica.
Somente um processo medido roda por vez; a ordem Python/Go alterna entre perfis.
O pico de memória residente do processo é lido pelo sistema operacional e inclui
inicialização, dados, runtime, aquecimentos e todas as etapas. Não equivale a
alocações por chamada. A coleta de RSS e a afinidade suportam Windows e Linux.

As evidências ficam em `artefatos/benchmark/resultados-local/`: `resultados.json`
(amostras e metadados) e `relatorio.md` (mediana, p95, razões e memória). Para
preservar rodadas distintas, passe uma pasta diferente:

```sh
make -C apps/fullstack benchmark-medir BENCHMARK_ARGS="--label rodada-01 --output-dir ../../../artefatos/benchmark/rodada-01"
```

Essa pasta é relativa a `apps/fullstack/processing`. `BENCHMARK_ARGS` também aceita
`--warmups` e `--repetitions`, respeitando os mínimos de 3 e 20. As medições são
exploratórias enquanto a equipe não definir previamente o ganho mínimo que
justificaria uma migração. Não incluem banco, rede, ETL ou infraestrutura AWS.
O protocolo está em `artefatos/benchmark-motor-hipoteses.md` na raiz do repositório.
