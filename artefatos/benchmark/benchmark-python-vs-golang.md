# Benchmark Python × Golang do motor de hipóteses

Este documento reúne escopo, dados, critérios, comandos e resultados locais
e na AWS. Novas rodadas serão documentadas aqui;
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
| `make -C apps/fullstack benchmark-aws` | Cria o ambiente temporário AWS, mede e recolhe os JSONs |

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

Os dados são sintéticos. O tempo exclui carregamento das entradas e catálogos,
compilação, comparação e serialização/gravação dos resultados para evidências.
A geração dos hashes canônicos internos faz parte do cálculo medido.
Banco, ETL, captura, claim/lease, persistência
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

## Teste na AWS — rodada de 06/10/2026

**Status: concluído; recursos temporários removidos.** Esta rodada repetiu o
cálculo isolado em uma EC2 temporária `c6g.medium` (ARM64, 1 vCPU, 2 GiB),
na região `us-east-1`.
O código e os dados sintéticos passam por um bucket S3 privado; um security
group sem regras de entrada permite a execução sem SSH. A instância encerra
após executar, e o controlador recolhe as evidências e remove os recursos
temporários criados por esta rodada.

O ambiente do benchmark é criado pelo alvo `benchmark-aws`, sem usar o estado
Terraform da conta anterior. O cálculo não inclui PostgreSQL, filas, APIs ou
serviços contínuos. Os testes Python dependentes de banco são pulados neste
ambiente, como na rodada local.

Foram três rodadas em processos novos, com cinco aquecimentos e cinquenta
amostras por etapa, carga e linguagem em cada rodada. As versões confirmadas
foram CPython 3.14.4 e Go 1.27.1, mantendo a comparação entre runtimes da rodada
local. O ganho mínimo e os limites de p95 e memória continuam sem definição;
esta execução mantém a finalidade exploratória.

```sh
AWS_PROFILE=g4 AWS_REGION=us-east-1 make -C apps/fullstack benchmark-aws \
  BENCHMARK_AWS_ARGS="--label 2026-10-06-aws --rounds 3 --output-dir ../../../artefatos/benchmark/rodada-aws-2026-10-06"
```

`BENCHMARK_AWS_ARGS` também aceita quantidade de aquecimentos/amostras, região,
tipo de instância ARM64 e versões de Python, Go e uv. A pasta de saída não pode
existir antes da execução, para preservar evidências anteriores. Cada rodada
gera somente JSON; os resultados e a interpretação estão registrados abaixo.

### Escopo definido antes de executar

Primeiro, repetir o cálculo Python × Golang na AWS com os mesmos dados e
critérios de paridade, para comparar as implementações em Linux ARM64 com
recursos fixos. Este ambiente tem configuração própria de benchmark e não
representa automaticamente os recursos ou a carga do serviço de produção.

Para avaliar o ciclo com PostgreSQL, preparar também a integração de captura,
orquestração e persistência. A tradução Golang atual cobre o cálculo isolado;
a integração com banco ainda precisa ser implementada e validada. Nesse
ensaio, medir separadamente leitura/captura, cálculo, persistência e duração
total, preservando causalidade, claim, lease e fencing.

### Critérios prévios e ambiente

| Campo | Registro da rodada AWS |
| --- | --- |
| Data e responsável | 06/10/2026; execução automatizada nesta sessão |
| Escopo executado: cálculo ou ciclo com banco | Cálculo isolado; sem PostgreSQL |
| Revisões e hashes de código, entradas e catálogos | Snapshot enviado com hashes SHA-256; revisão de origem em `ambiente.json` |
| CPU, memória, arquitetura, sistema e limites aplicados | EC2 `c6g.medium`, ARM64, 1 vCPU, 2 GiB; Amazon Linux 2023; mesma CPU para os dois motores |
| Versões Python/Golang e parâmetros de runtime | CPython 3.14.4 e Go 1.27.1; `PYTHONHASHSEED=0`, GC padrão; `GOMAXPROCS=1`, `GOGC=100`, `GOMEMLIMIT=off` |
| Configuração do PostgreSQL, se incluído | Fora do escopo desta rodada |
| Aquecimentos, amostras e rodadas independentes | Três rodadas sequenciais na mesma EC2; processos novos por carga/linguagem; cinco aquecimentos e cinquenta amostras por etapa |
| Ganho mínimo para decisão | Não definido antes da medição; rodada exploratória |
| Limites aceitáveis de p95 e memória | Não definidos antes da medição; rodada exploratória |
| Verificação de equivalência | Exigida antes das medições: 54 saídas completas e reprodução dos três JSONs |

### Validação e ambiente observado

Os testes Python terminaram com **155 aprovados e 46 pulados**. Os testes Go passaram, os três JSONs foram reproduzidos e a paridade foi aprovada nas 54 saídas completas antes de medir. A reprodução e a paridade foram repetidas em cada rodada; todas as **7.500 amostras** positivas, medianas, p95 e hashes foram conferidos após baixar os resultados.

Ambiente observado: Linux `6.18.51-120.163.amzn2023.aarch64`, arquitetura `aarch64`,
1 CPU lógica e 1,79 GiB de memória visível ao sistema; a configuração da EC2
oferece 2 GiB. Ambos os workers usaram a CPU lógica 0. Python usou
`clock_gettime(CLOCK_MONOTONIC)` e Go, `Go monotonic time.Since`. Compilação,
instalação, carregamento/desserialização das entradas e catálogos, gravação dos
JSONs de evidências e transferência pela rede ficaram fora dos intervalos
cronometrados. A serialização para os hashes canônicos internos permaneceu no
cálculo medido.

### Cálculo completo na AWS

Cada mediana e p95 abaixo foi recalculado sobre **150 amostras concatenadas**, provenientes de três rodadas de cinquenta amostras. O p95 usa *nearest rank*; os percentis das rodadas não foram promediados. RSS é o **maior pico dos três processos** de cada carga/linguagem, inclui inicialização, entradas, runtime e todas as etapas, e não é memória marginal por chamada. Tempos em ms; memória em MiB. A razão é mediana Python / mediana Go; o total foi cronometrado separadamente.

| Carga | Fatos | Python mediana | Python p95 | Go mediana | Go p95 | Razão | RSS Python | RSS Go |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ciclo_misto_v1 | 16 | 1,9721 | 2,0164 | 0,5263 | 1,0324 | 3,75× | 23,94 | 9,20 |
| disperso_256 | 256 | 14,3042 | 14,4641 | 5,2851 | 7,0819 | 2,71× | 24,44 | 9,41 |
| disperso_1024 | 1024 | 55,2077 | 55,7209 | 21,9249 | 24,2179 | 2,52× | 25,73 | 12,47 |
| denso_128 | 128 | 103,6944 | 104,9893 | 55,5728 | 57,6447 | 1,87× | 24,69 | 13,02 |
| denso_512 | 512 | 1680,3932 | 1689,8668 | 975,4477 | 987,3153 | 1,72× | 26,93 | 41,48 |

### Resultados por etapa na AWS

Todos os tempos estão em milissegundos e usam as mesmas 150 amostras por combinação.

#### ciclo_misto_v1

| Etapa | Python mediana | Python p95 | Golang mediana | Golang p95 | Razão |
| --- | ---: | ---: | ---: | ---: | ---: |
| Qualidade | 0,1911 | 0,1987 | 0,0341 | 0,0444 | 5,61× |
| Detector | 0,0979 | 0,0993 | 0,0145 | 0,0219 | 6,76× |
| Candidatos | 0,7605 | 0,7784 | 0,2182 | 0,2475 | 3,49× |
| Score | 0,8181 | 0,8468 | 0,2455 | 0,6458 | 3,33× |
| Total | 1,9721 | 2,0164 | 0,5263 | 1,0324 | 3,75× |

#### disperso_256

| Etapa | Python mediana | Python p95 | Golang mediana | Golang p95 | Razão |
| --- | ---: | ---: | ---: | ---: | ---: |
| Qualidade | 0,3087 | 0,3180 | 0,0599 | 0,0711 | 5,15× |
| Detector | 1,2358 | 1,2705 | 0,2364 | 0,7457 | 5,23× |
| Candidatos | 11,7047 | 11,7773 | 4,5983 | 5,6468 | 2,55× |
| Score | 0,8196 | 0,8420 | 0,2487 | 0,5947 | 3,30× |
| Total | 14,3042 | 14,4641 | 5,2851 | 7,0819 | 2,71× |

#### disperso_1024

| Etapa | Python mediana | Python p95 | Golang mediana | Golang p95 | Razão |
| --- | ---: | ---: | ---: | ---: | ---: |
| Qualidade | 0,6899 | 0,7099 | 0,1482 | 0,4062 | 4,66× |
| Detector | 5,0765 | 5,1477 | 1,2207 | 2,8890 | 4,16× |
| Candidatos | 47,7513 | 48,4110 | 19,1562 | 21,6837 | 2,49× |
| Score | 0,8269 | 0,8636 | 0,2577 | 0,6533 | 3,21× |
| Total | 55,2077 | 55,7209 | 21,9249 | 24,2179 | 2,52× |

#### denso_128

| Etapa | Python mediana | Python p95 | Golang mediana | Golang p95 | Razão |
| --- | ---: | ---: | ---: | ---: | ---: |
| Qualidade | 0,2464 | 0,2538 | 0,0497 | 0,1633 | 4,96× |
| Detector | 0,9949 | 1,0185 | 0,1673 | 0,4025 | 5,95× |
| Candidatos | 92,9525 | 93,4968 | 44,7229 | 45,9024 | 2,08× |
| Score | 9,9500 | 10,0384 | 8,2321 | 10,9387 | 1,21× |
| Total | 103,6944 | 104,9893 | 55,5728 | 57,6447 | 1,87× |

#### denso_512

| Etapa | Python mediana | Python p95 | Golang mediana | Golang p95 | Razão |
| --- | ---: | ---: | ---: | ---: | ---: |
| Qualidade | 0,4333 | 0,4481 | 0,0941 | 0,2430 | 4,61× |
| Detector | 4,1442 | 4,2134 | 0,8950 | 1,9602 | 4,63× |
| Candidatos | 1581,5297 | 1587,9921 | 829,3738 | 833,9874 | 1,91× |
| Score | 92,1110 | 95,1079 | 147,4072 | 157,4642 | 0,62× |
| Total | 1680,3932 | 1689,8668 | 975,4477 | 987,3153 | 1,72× |

### Variação entre as rodadas

As três rodadas usaram a mesma EC2 e o mesmo código, com processos novos. Elas não são três implantações independentes. A tabela conserva as medianas do cálculo completo de cada rodada, em ms, para mostrar a variação que a consolidação pode esconder.

| Carga | Python R1 | Go R1 | Python R2 | Go R2 | Python R3 | Go R3 | Razão mínima–máxima |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ciclo_misto_v1 | 1,9553 | 0,5236 | 1,9646 | 0,5237 | 1,9850 | 0,5288 | 3,73×–3,75× |
| disperso_256 | 14,2047 | 5,2957 | 14,3038 | 5,2531 | 14,3954 | 5,2842 | 2,68×–2,72× |
| disperso_1024 | 55,3960 | 21,8320 | 55,3910 | 22,2010 | 53,4022 | 21,9589 | 2,43×–2,54× |
| denso_128 | 103,6735 | 55,6566 | 104,1012 | 55,3371 | 103,1409 | 55,8803 | 1,85×–1,88× |
| denso_512 | 1682,7069 | 946,0420 | 1682,0949 | 978,5929 | 1672,5431 | 977,1842 | 1,71×–1,78× |

### Interpretação da rodada AWS

- Go apresentou mediana e p95 menores no cálculo completo das cinco cargas. A razão das medianas consolidadas variou de **1,72× a 3,75×**.
- A construção de candidatos foi a etapa mais lenta nas quatro cargas ampliadas, em ambas as implementações.
- Em `denso_512`, o score isolado foi **60,03% mais lento em Go**: mediana Python 92,1110 ms e Go 147,4072 ms; p95 95,1079 ms e 157,4642 ms, respectivamente.
- Em `denso_128`, a mediana do score foi menor em Go, mas seu **p95 foi 8,97% maior**: 10,9387 ms em Go e 10,0384 ms em Python. O ganho no total não significa melhora em todas as etapas ou percentis.
- Na carga `denso_512`, o maior pico de RSS foi **26,93 MiB em Python e 41,48 MiB em Go** (1,54× o valor Python). A memória deve ser avaliada junto com o ganho no tempo.
- O ambiente local era Windows/AMD64 em Intel; a AWS usou Linux/ARM64. Sistema, CPU, arquitetura, distribuição dos runtimes e carga externa podem alterar tempos e memória. A razão Python/Go calculada dentro de cada ambiente é a comparação do experimento; a diferença de tempo entre local e AWS não isola o efeito da linguagem.

**Estado da decisão:** esta rodada acrescenta evidência sobre o cálculo isolado. Ganho mínimo, limites de p95 e memória não foram definidos antes de medir; os resultados continuam exploratórios e não aprovam migração. As três rodadas na mesma máquina não demonstram variação entre instâncias, desempenho com concorrência, latência de API nem vazão do ciclo com banco. Frequência de CPU e processos externos não foram controlados.

### Estrutura, preparação e limpeza

O executor criou uma EC2 temporária, disco gp3 criptografado, bucket S3 privado com bloqueio de acesso público e criptografia, e security group sem portas de entrada. Usou a VPC/sub-rede padrão e o `LabInstanceProfile` existente; não criou roles IAM nem alterou o estado Terraform da conta anterior. A EC2 encerra ao final e tem desligamento de segurança programado; o controlador baixa as evidências e remove os recursos que criou.

As duas primeiras tentativas falharam antes de produzir medições: a imagem não incluía Make, e depois o ambiente de inicialização não fornecia a pasta de cache do Go. O bootstrap passou a instalar Make e configurar `GOCACHE`/`GOMODCACHE` em `/work`. Os recursos dessas tentativas também foram removidos; seus registros de limpeza foram preservados.

**Limpeza confirmada:** instância encerrada, disco removido, security group
excluído e bucket/objetos excluídos; `limpeza.json` registra os três estados como
`true`, sem erros. Uma consulta posterior confirmou zero instâncias ativas,
grupos de segurança e buckets do benchmark, além de zero volumes EBS na região;
os contadores estão em `inventario-apos-limpeza.json`. A execução não alterou o
motor Python de produção, ETL, APIs, filas, banco ou contêineres do fluxo normal.
O Makefile recebeu apenas o alvo adicional `benchmark-aws`.

### Evidências e reprodução na AWS

- [Rodada 1: amostras, estatísticas e ambiente](rodada-aws-2026-10-06/rodada-01/resultados.json); SHA-256 `9399fd8c5eb465964c096ae0594e8ea7c3a71db0bcf8184cb0bdb9f1852eb0ea`.
- [Rodada 2: amostras, estatísticas e ambiente](rodada-aws-2026-10-06/rodada-02/resultados.json); SHA-256 `aa2483a3627c34e573ca89d01dfd2e7110349ec510e28c5519f50ad7de183194`.
- [Rodada 3: amostras, estatísticas e ambiente](rodada-aws-2026-10-06/rodada-03/resultados.json); SHA-256 `3da1f4221557bba0ca9c66502dd42f699bfe2369d2134a2b52bcd0bf70b9086a`.
- [Consolidação calculada a partir das amostras](rodada-aws-2026-10-06/consolidado.json).
- [Configuração e hashes do pacote enviado](rodada-aws-2026-10-06/ambiente.json).
- [Validação extraída do log remoto](rodada-aws-2026-10-06/validacao.json).
- [Limpeza da execução concluída](rodada-aws-2026-10-06/limpeza.json).
- [Inventário consultado após a limpeza](rodada-aws-2026-10-06/inventario-apos-limpeza.json).
- Limpeza das tentativas de preparação: [tentativa 1](preparacao-aws-2026-10-06-01/limpeza.json) e [tentativa 2](preparacao-aws-2026-10-06-02/limpeza.json).
- Revisão de origem: `49985e1a18201110af52c7a520d30293ae790aa0`. Os arquivos enviados incluíam o executor AWS e o alvo Make ainda sem commit; os 73 hashes em `ambiente.json` identificam o conteúdo efetivo.
- Revisão do snapshot Git criado na EC2: `4bf4e5fb65b326185b8f7932c2dfb9a79d5cf45c`. Ela identifica a cópia enviada e não substitui a revisão de origem do repositório.
- SHA-256 do arquivo compactado enviado: `ce185a2c5128cf2aae827f91b9362c9eb78c89949247833ad0d9b372bb487229`. Somente código, testes e dados sintéticos foram empacotados; credenciais, arquivos de ambiente, Terraform state, dump e Parquet ficaram fora do pacote.

Para repetir, configurar credenciais válidas no perfil `g4`, AWS CLI e `uv`, acesso à VPC/sub-rede padrão e ao `LabInstanceProfile`, e executar o comando acima com **outro label e outra pasta de saída**. O executor verifica as credenciais, consulta os checksums oficiais de Go/uv, instala as versões fixadas e recolhe evidências antes de limpar o ambiente. Identificadores de recuperação ficam apenas no diretório temporário local, fora do repositório.

### Próximo ensaio na AWS: integração e carga

A medição com PostgreSQL permanece pendente nesta documentação. Antes de executá-la, definir ganho mínimo, limites de p95/memória, volume de entrada, concorrência, duração e critério de erro; implementar e validar a integração Go de captura, orquestração e persistência. Recriar a estrutura necessária ao ciclo com banco e conservar causalidade, claim, lease e fencing. Medir leitura/captura, cálculo, persistência e duração completa separadamente.

| Medição futura | Python na AWS | Golang na AWS | Comparação |
| --- | --- | --- | --- |
| Leitura/captura | Pendente | Pendente | Mediana e p95 |
| Persistência | Pendente | Pendente | Mediana e p95 |
| Ciclo completo com banco | Pendente | Pendente | Mediana, p95 e ciclos por segundo |
| Carga com concorrência controlada | Pendente | Pendente | Vazão, p95, erros, CPU e memória |
