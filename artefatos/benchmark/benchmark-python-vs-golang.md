# Benchmark Python × Golang do motor de hipóteses

Este documento reúne escopo, dados, critérios, comandos, resultados locais e
o registro do futuro teste na AWS. Novas rodadas serão documentadas aqui;
os arquivos JSON por rodada conservam as evidências brutas.

## Pergunta e escopo

O experimento pergunta se uma implementação equivalente em Go reduz o custo do
cálculo de hipóteses. A comparação inicial é executada fora do banco e sem
alterar o serviço de produção. Ela mede, separadamente e em conjunto:

1. `evaluate_quality` (canário por fonte);
2. `detect` (EWMA e atualização dos baselines);
3. `build_candidates` (11 famílias);
4. `evaluate_candidates` e `score_features` (score, cortes e evidências).

Leitura/captura, claim, lease, fencing, persistência, ETL, API e dashboard não
entram no tempo desta primeira comparação. Um ensaio posterior com PostgreSQL
deverá medir o ciclo completo antes de qualquer decisão sobre produção.

## Dados congelados

Os arquivos estão em `apps/fullstack/processing/benchmarks/fixtures/`, usam
`schema_version = 1`, são sintéticos e não incluem o dump do parceiro.

| Arquivo | Conteúdo | Finalidade |
| --- | --- | --- |
| `regras_casos_v1.json` | 49 casos derivados de `test_familias.py`, cobrindo as 11 famílias e situações favoráveis, contrárias, indisponíveis e não relacionadas | Paridade das regras e do score; cada caso traz entrada e saída Python congelada |
| `ciclo_caso_v1.json` | 16 fatos, baselines fixos, janela fixa; produz 21 vereditos de qualidade, 9 anomalias e 15 hipóteses | Paridade de qualidade → detector → regras → score, incluindo baselines atualizados |
| `cargas_v1.json` | Entradas completas para quatro cargas, com contagens de referência | Medir crescimento do custo sem depender de geração aleatória durante a medição |

As cargas `disperso_256` e `disperso_1024` mantêm 9 anomalias e 15 candidatos,
acrescentando fatos sem desvio. `denso_128` e `denso_512` produzem,
respectivamente, 121 e 505 anomalias e 127 e 511 candidatos. A carga densa maior
também exercita o teto de 500 hipóteses geradas. São perfis sintéticos iniciais;
não representam, por si, a distribuição de um replay real.

Cada arquivo registra o hash do manifesto do catálogo. Os casos de regras e do
ciclo registram também o teste e o commit de origem. Se qualquer catálogo ou
regra mudar, atualize as referências de maneira explícita e registre o motivo;
não aceite um resultado divergente apenas por ser mais rápido.

`source_revision = 534a9ca` conserva a origem histórica dos cenários iniciais.
Os hashes das origens identificam o conteúdo efetivamente usado na geração.
O hash do manifesto dos cinco catálogos desta rodada é
`88caf2b297af401908aab82c2eaefa044f63e95ff73c0685adcf0ee6b9309ad0`.

### Contrato portátil dos arquivos

- Horários são textos ISO 8601 com fuso explícito. O detector usa a hora de
  `America/Sao_Paulo` para a chave do baseline.
- `facts` preserva a ordem da entrada. `anomalies[*].fact_key` referencia um
  fato do mesmo caso; a ordem das anomalias define `anomaly_indexes`.
- Cada baseline tem `key = [source, entity, metric, hour_brt]` e `value` com
  média, variância, `n` e último horário processado.
- `null` significa ausência. Não pode virar zero, string vazia ou evidência
  contrária.
- Os cinco catálogos JSON versionados em `processing/src/argus_processing/catalogs`
  são parte da entrada. Python e Go devem carregar o mesmo conteúdo.
- Os casos de regras incluem entradas artificiais que testam causalidade e
  não são uma captura do banco. Em ensaio com banco, a captura temporal deve
  continuar respeitando `available_at <= sim_now`.

## Critérios de equivalência antes de medir

1. Comparar exatamente número e ordem das anomalias, candidatos selecionados e
   hipóteses; contadores de pré-filtro, avaliação e truncamento; famílias,
   `kind`, estados, confiança, escopos e índices de anomalia.
2. Comparar exatamente textos, evidências, polaridades, aplicabilidade das
   features, chaves `dedup_key` e `lineage_key` e baselines identificados por
   sua chave. Ordenação de mapas internos não tem significado; ordenação de
   listas de saída tem.
3. Para números de ponto flutuante fora das chaves, aceitar apenas diferença
   dentro de `abs_tol = 1e-12` **ou** `rel_tol = 1e-9`, como em `math.isclose`.
   Estados e decisões nos limiares continuam exigindo igualdade exata.
4. Reproduzir o hash canônico usado pelo Python: JSON UTF-8, chaves ordenadas,
   sem espaços opcionais, caracteres Unicode não escapados e SHA-256. Diferenças
   de serialização de data ou número que mudem uma chave são falhas de paridade.
5. Executar os 49 casos e o ciclo fixo antes de cronometrar. Cada carga maior
   deve reproduzir ao menos as contagens congeladas; as duas implementações
   devem ainda comparar suas saídas completas na rodada de benchmark.

O teste `test_benchmark_fixtures.py` verifica que as referências congeladas ainda
correspondem ao Python do repositório. Os testes `test_familias.py`,
`test_budgets_e_detector.py` e `test_uc03_valores_limite.py` continuam sendo a
referência para cenários e limites que não caibam nos arquivos portáveis.

## Critérios de medição

- Carregar JSON e catálogos antes do cronômetro. Medir inicialização e
  desserialização separadamente apenas se a análise de implantação exigir.
- Cronometrar cada etapa e o fluxo completo, sem comparação de saída, logs ou
  gravação de arquivos dentro do intervalo medido. Usar relógio monotônico.
- Usar uma execução por vez, no mesmo computador, com a mesma entrada e um
  único worker. Registrar sistema, arquitetura, CPU, memória, versões de
  Python e Go e limites de recursos aplicados.
- Fazer pelo menos 3 rodadas de aquecimento e 20 rodadas medidas por carga.
  Publicar mediana, p95 pelo método *nearest rank* e razão
  `tempo_Python / tempo_Go`. Informar também pico de memória residente (RSS).
  Alocações específicas de cada runtime podem ser exibidas como diagnóstico,
  mas não substituem a comparação de RSS.
- Se a paridade falhar, não usar aquele caso para concluir sobre desempenho.
  Se o ganho aparecer no cálculo, repetir depois o ciclo com banco em ambiente
  isolado e recursos próximos aos do serviço antes de propor migração.

O relatório de resultados deve declarar previamente qual ganho mínimo
justificaria uma implementação de produção. O valor fica em aberto até a equipe
defini-lo, antes de consultar as medições.

## Geração automática e implementação Golang

O gerador versionado está em
`apps/fullstack/processing/benchmarks/gerar_fixtures.py`. Ele recria os três JSONs
a partir dos testes originais e do motor Python, sem ler os JSONs existentes como
entrada. A geração preserva os 49 casos, o ciclo base e os quatro perfis definidos
acima. Cada documento registra também hashes SHA-256 dos arquivos de origem;
`source_revision` conserva a referência histórica inicial, e esses hashes
identificam o conteúdo usado na geração atual.

A tradução independente em Go está em
`apps/fullstack/processing/benchmarks/golang/`. Ela inclui os contratos de domínio,
catálogos, qualidade, detector, onze famílias e score. Usa os mesmos cinco catálogos
do Python e não participa da execução do serviço de produção.

```sh
make -C apps/fullstack benchmark-fixtures        # Reescreve: revisar o diff
make -C apps/fullstack benchmark-fixtures-check  # Confere sem escrever
make -C apps/fullstack benchmark-paridade        # Testes Go + comparação completa
```

O último comando compara as saídas completas dos 54 casos/cargas, incluindo as
quatro cargas maiores, antes de qualquer medição. Ele não substitui o protocolo
de desempenho descrito acima.

### Origem dos dados e verificações do gerador

`gerar_fixtures.py` importa cópias novas dos módulos de teste, captura as
entradas e executa suas asserções originais. A saída congelada dos 49 cenários
inclui todas as famílias produzidas, não apenas a família foco de cada teste.
O ciclo misto vem de `test_rules.py`; o gerador acrescenta baselines artificiais
com `n = 12`, variância `0.01` e observação anterior em um dia. Esse estado
é sintético e não corresponde a uma série histórica real.

As cargas dispersas acrescentam fatos de CPU em entidades novas, sem baseline
aquecido. As densas acrescentam erros em entidades novas com baseline aquecido.
IDs, janelas, ordem e tamanhos são fixos; não há aleatoriedade nem uso do horário
atual. Os resultados esperados vêm do motor Python atual: validam equivalência
de comportamento, sem comprovar de forma independente a correção do diagnóstico.

Os hashes das origens normalizam as quebras de linha para LF. O modo `--check`
detecta divergências de conteúdo e metadados sem sobrescrever os JSONs. Os
testes do gerador verificam reprodução, reinicialização dos IDs e esse
comportamento em caso de divergência.

### Arquivos traduzidos para Golang

Os arquivos Python de referência ficam em
`apps/fullstack/processing/src/argus_processing/`; os arquivos Golang,
em `apps/fullstack/processing/benchmarks/golang/`.

| Python de referência | Golang | Responsabilidade |
| --- | --- | --- |
| `domain.py` | `domain.go` | Fatos, baselines, anomalias, evidências e hipóteses |
| `catalog.py` | `catalog.go` | Catálogos, relações de entidades e hash canônico |
| `quality.py` | `quality.go` | Qualidade por fonte |
| `detector.py` | `detector.go` | EWMA causal, materialidade e hora de São Paulo |
| `rules.py` | `rules.go` | Onze famílias, cortes, evidências e deduplicação |
| `scoring.py` | `scoring.go` | Score, cobertura e confiança |
| Composição isolada do cálculo | `fixtures.go` | Execução dos casos e do ciclo |

A implementação Golang não chama Python nem consulta `expected` para produzir
resultados. A CLI `golang/cmd/paridade` lê um documento portátil e imprime
saídas JSON. `verificar_paridade.py` compila essa CLI em uma pasta temporária
e compara suas saídas com execuções novas do Python.

Os testes Golang adicionais cobrem repetição causal, preservação do estado
de entrada, horário de verão de São Paulo, precisão temporal, qualidade de
dados ausentes, cortes estáveis e limites do detector.

## Execução da medição local

Pré-requisitos: Python e `uv` conforme o projeto, Go 1.22 ou superior e o
ambiente de `make` do repositório. Não há dependências Go externas nem
necessidade de contêiner. No Windows, os alvos gerais precisam de Bash
(por exemplo, Git Bash). Se Go estiver fora do PATH, passe
`GO=/caminho/para/go` ao `make`; o ambiente Python pode ser direcionado
por `UV_PROJECT_ENVIRONMENT`.

| Alvo na raiz do repositório | Resultado |
| --- | --- |
| `make -C apps/fullstack benchmark-fixtures` | Recria os três JSONs; revisar o diff |
| `make -C apps/fullstack benchmark-fixtures-check` | Confere a reprodução sem escrever |
| `make -C apps/fullstack benchmark-go-test` | Executa os testes Golang |
| `make -C apps/fullstack benchmark-paridade` | Verifica as 54 saídas completas |
| `make -C apps/fullstack benchmark-medir` | Verifica paridade e grava medições brutas em JSON |

O alvo `make -C apps/fullstack benchmark-medir` executa a validação de paridade e
mede as quatro etapas e o cálculo completo. A configuração padrão usa cinco
aquecimentos, cinquenta amostras por etapa e um processo novo por carga/linguagem,
com ambos os motores restritos à mesma CPU lógica. A ordem Python/Go alterna
entre cargas. No Windows, ambos usam contadores de alta resolução baseados em
`QueryPerformanceCounter`.

Os dados brutos, versões, hardware e hashes de código/entrada são salvos em
`resultados.json`, na pasta `artefatos/benchmark/resultados-local/` ou na
pasta indicada por `BENCHMARK_ARGS="--output-dir ..."`. As tabelas e a análise
de cada rodada ficam neste documento. O pico de RSS inclui o processo inteiro,
desde a inicialização até terminar todas as etapas; não é memória marginal do
cálculo. A mediana e o p95 do total vêm de sua própria medição.

`BENCHMARK_ARGS` também aceita `--warmups` e `--repetitions`, com mínimos
de 3 e 20. A pasta de saída é relativa a `apps/fullstack/processing`.
A coleta de RSS e a afinidade suportam Windows e Linux. No Windows, o
pico residente usa `PeakWorkingSetSize`; no Linux, o contador `VmHWM`.

Até a definição prévia do critério mínimo de ganho, essas rodadas são
exploratórias. Resultados locais com dados sintéticos não aprovam por si uma
migração nem permitem estimar o custo da AWS.

## Resultado da rodada local de 05/10/2026

**Paridade aprovada em 54 saídas completas:** 49 cenários de regras, um ciclo
base e quatro cargas ampliadas. Os resultados abaixo foram conferidos a partir
das 2.500 amostras brutas; os hashes do código e das entradas correspondem aos
arquivos usados na rodada.

Ambiente: Windows 11 (10.0.26200), AMD64, Intel Core i5-13500H, 16 CPUs lógicas
e 15,74 GiB de memória física. Runtimes: CPython 3.14.4 e Go 1.27.1. Ambos
os processos de cálculo foram restritos à CPU lógica 0, com uma implementação
por vez e `GOMAXPROCS=1`. Foram cinco aquecimentos e cinquenta amostras por
etapa, carga e linguagem, com ordem Python/Go alternada entre cargas. O GC
padrão ficou habilitado; em Go, `GOGC=100` e `GOMEMLIMIT=off`.

### Cálculo completo

Tempos em ms; memória em MiB. A razão é mediana Python / mediana Go.
O total foi medido separadamente e não equivale à soma das medianas por etapa.

| Carga | Fatos | Python mediana | Python p95 | Go mediana | Go p95 | Razão | RSS Python | RSS Go |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ciclo_misto_v1 | 16 | 1,1875 | 1,3461 | 0,1978 | 0,3623 | 6,00× | 23,92 | 14,08 |
| disperso_256 | 256 | 8,1002 | 10,4934 | 2,2885 | 3,1594 | 3,54× | 24,43 | 14,38 |
| disperso_1024 | 1024 | 30,1981 | 32,7981 | 9,3047 | 10,8855 | 3,25× | 26,00 | 14,42 |
| denso_128 | 128 | 58,0029 | 59,6376 | 24,7604 | 26,8585 | 2,34× | 24,64 | 16,62 |
| denso_512 | 512 | 963,9268 | 993,0105 | 430,6092 | 436,4850 | 2,24× | 26,39 | 57,32 |

### Resultados por etapa

CPython 3.14.4 e Go 1.27.1 usam QueryPerformanceCounter nesta rodada,
com resolução declarada de 100 ns em ambos. O overhead do cronômetro
não foi subtraído. Todos os tempos abaixo estão em milissegundos.

#### ciclo_misto_v1

| Etapa | Python mediana | Python p95 | Golang mediana | Golang p95 | Razão |
| --- | ---: | ---: | ---: | ---: | ---: |
| Qualidade | 0,0897 | 0,1118 | 0,0155 | 0,0212 | 5,77× |
| Detector | 0,0564 | 0,0643 | 0,0073 | 0,0124 | 7,78× |
| Candidatos | 0,4386 | 0,4801 | 0,0958 | 0,1221 | 4,58× |
| Score | 0,5107 | 0,5805 | 0,0888 | 0,2798 | 5,75× |
| Total | 1,1875 | 1,3461 | 0,1978 | 0,3623 | 6,00× |

#### disperso_256

| Etapa | Python mediana | Python p95 | Golang mediana | Golang p95 | Razão |
| --- | ---: | ---: | ---: | ---: | ---: |
| Qualidade | 0,1757 | 0,1877 | 0,0330 | 0,0636 | 5,33× |
| Detector | 0,6419 | 0,6903 | 0,1042 | 0,4207 | 6,16× |
| Candidatos | 6,5485 | 7,1161 | 1,9459 | 3,0968 | 3,37× |
| Score | 0,4969 | 0,5723 | 0,0895 | 0,2792 | 5,55× |
| Total | 8,1002 | 10,4934 | 2,2885 | 3,1594 | 3,54× |

#### disperso_1024

| Etapa | Python mediana | Python p95 | Golang mediana | Golang p95 | Razão |
| --- | ---: | ---: | ---: | ---: | ---: |
| Qualidade | 0,3866 | 0,3966 | 0,0609 | 0,2454 | 6,34× |
| Detector | 2,5996 | 2,8081 | 0,3556 | 0,8555 | 7,31× |
| Candidatos | 26,4228 | 28,4065 | 8,3523 | 9,9013 | 3,16× |
| Score | 0,5004 | 0,6691 | 0,1044 | 0,2921 | 4,79× |
| Total | 30,1981 | 32,7981 | 9,3047 | 10,8855 | 3,25× |

#### denso_128

| Etapa | Python mediana | Python p95 | Golang mediana | Golang p95 | Razão |
| --- | ---: | ---: | ---: | ---: | ---: |
| Qualidade | 0,1368 | 0,1462 | 0,0374 | 0,0855 | 3,66× |
| Detector | 0,5270 | 0,5655 | 0,0632 | 0,1797 | 8,34× |
| Candidatos | 51,8218 | 53,1514 | 20,3974 | 24,5646 | 2,54× |
| Score | 5,5426 | 6,2018 | 3,6145 | 4,9405 | 1,53× |
| Total | 58,0029 | 59,6376 | 24,7604 | 26,8585 | 2,34× |

#### denso_512

| Etapa | Python mediana | Python p95 | Golang mediana | Golang p95 | Razão |
| --- | ---: | ---: | ---: | ---: | ---: |
| Qualidade | 0,2508 | 0,2670 | 0,0450 | 0,1356 | 5,57× |
| Detector | 2,1557 | 2,3482 | 0,3547 | 0,8742 | 6,08× |
| Candidatos | 853,8802 | 917,6821 | 381,1245 | 515,4574 | 2,24× |
| Score | 50,2000 | 53,8700 | 68,9062 | 75,3906 | 0,73× |
| Total | 963,9268 | 993,0105 | 430,6092 | 436,4850 | 2,24× |

### Interpretação

- Go teve mediana e p95 menores no cálculo completo das cinco cargas desta
  rodada. O ganho na mediana variou de 2,24× a 6,00×.
- Nas quatro cargas ampliadas, a construção de candidatos foi a etapa mais
  lenta em Python e em Go. Em `denso_512`, suas medianas foram 853,8802 ms
  em Python e 381,1245 ms em Go. No ciclo base, o score foi a etapa mais
  lenta em Python.
- O score isolado de `denso_512` foi **37,26% mais lento em Go**:
  medianas de 50,2000 ms em Python e 68,9062 ms em Go; p95 de 53,8700 ms
  e 75,3906 ms, respectivamente. O ganho no total não se aplica a todas
  as etapas.
- O pico de RSS de Go foi menor em quatro cargas, mas em `denso_512`
  chegou a **57,32 MiB**, contra **26,39 MiB** em Python (aproximadamente
  2,17×). O contador cobre inicialização, entradas, runtime, aquecimentos e
  todas as etapas do processo; não mede memória incremental por chamada.

**Estado da decisão:** evidência exploratória favorável ao tempo do cálculo
completo em Go. O ganho mínimo, o limite de memória e o limite de p95 não
foram definidos antes desta rodada; ela não aprova uma migração. Recomenda-se
investigar o score e a memória da carga densa, definir os critérios e executar
rodadas independentes antes de avaliar o ciclo com PostgreSQL.

Os dados são sintéticos e o tempo exclui JSON, catálogos, compilação,
serialização, comparação e I/O. Banco, ETL, captura, claim/lease, persistência
e rede ficam fora do escopo. Frequência da CPU, plano de energia e processos
externos não foram controlados. Os números comparam estas implementações
e estes runtimes; não isolam o efeito da linguagem nem estimam desempenho
ou custo da arquitetura na AWS.

### Evidências e reprodução

- [Amostras brutas, estatísticas, ambiente e hashes](rodada-local-2026-10-05/resultados.json).
- Revisão base do repositório: `47e3dc7005d4d60117d6e9f04e5c646517ee34c7`.
  A implementação Go e o executor de medição continham alterações locais;
  a identificação exata está nos hashes SHA-256 registrados no JSON.
- Após a rodada, a saída do executor foi ajustada para gravar somente JSON
  e a documentação foi consolidada neste arquivo. Os hashes da evidência
  conservam a versão executada em 05/10/2026; os tempos brutos não foram alterados.
- O perfil `ciclo_misto_v1` corresponde ao ciclo armazenado em
  `ciclo_caso_v1.json`.

```sh
make -C apps/fullstack benchmark-medir GO=/caminho/para/go \
  BENCHMARK_ARGS="--label 2026-10-05 --output-dir ../../../artefatos/benchmark/rodada-local-2026-10-05"
```

Para preservar esta evidência, use outra pasta de saída em rodadas futuras.

## Teste na AWS — próxima etapa

**Status: planejado; ainda não executado.** Os resultados da AWS serão
adicionados nesta seção do mesmo documento, com seus JSONs de evidência
em uma pasta própria dentro de `artefatos/benchmark/`.

### Escopo a registrar antes de executar

Primeiro, repetir o cálculo Python × Golang na AWS com os mesmos dados e
critérios de paridade, para comparar as implementações em um ambiente
representativo do serviço. Registrar recursos, sistema, versões, parâmetros
de GC e protocolo de repetição antes de medir.

Para avaliar o ciclo com PostgreSQL, preparar também a integração de captura,
orquestração e persistência. A tradução Golang atual cobre o cálculo isolado;
a integração com banco ainda precisa ser implementada e validada. Nesse
ensaio, medir separadamente leitura/captura, cálculo, persistência e duração
total, preservando causalidade, claim, lease e fencing.

### Critérios prévios e ambiente

| Campo | Registro da rodada AWS |
| --- | --- |
| Data e responsável | A registrar |
| Escopo executado: cálculo ou ciclo com banco | A definir antes da rodada |
| Revisões e hashes de código, entradas e catálogos | A registrar |
| CPU, memória, arquitetura, sistema e limites aplicados | A registrar |
| Versões Python/Golang e parâmetros de runtime | A registrar |
| Configuração do PostgreSQL, se incluído | A registrar sem credenciais ou endpoints |
| Aquecimentos, amostras e rodadas independentes | A definir antes da rodada |
| Ganho mínimo para decisão | A definir antes da rodada |
| Limites aceitáveis de p95 e memória | A definir antes da rodada |
| Verificação de equivalência | A executar antes da medição |

### Resultados a acrescentar

| Medição | Python na AWS | Golang na AWS | Comparação |
| --- | --- | --- | --- |
| Qualidade, detector, candidatos e score por carga: mediana e p95 | A medir | A medir | Razão Python / Golang |
| Cálculo completo por carga: mediana e p95 | A medir | A medir | Razão Python / Golang |
| Pico de RSS por carga | A medir | A medir | Diferença e razão |
| Leitura/captura, se o banco estiver no escopo | A medir | A medir | Mediana e p95 |
| Persistência, se o banco estiver no escopo | A medir | A medir | Mediana e p95 |
| Ciclo completo com banco, se incluído | A medir | A medir | Mediana, p95 e vazão |

Registrar a análise do score e da memória da carga `denso_512`, as diferenças
de ambiente em relação à rodada local e a estabilidade entre rodadas. A
conclusão deverá usar os critérios definidos previamente e apontar o escopo
efetivamente medido. Os valores locais não serão reutilizados como resultados
da AWS.
