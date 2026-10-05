# Benchmark Python × Go do motor de hipóteses — dados e critérios

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

## Geração automática e implementação Go

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
de desempenho descrito acima. Instruções e mapeamento de arquivos estão em
`apps/fullstack/processing/benchmarks/README.md`.

## Execução da medição local

O alvo `make -C apps/fullstack benchmark-medir` executa a validação de paridade e
mede as quatro etapas e o cálculo completo. A configuração padrão usa cinco
aquecimentos, cinquenta amostras por etapa e um processo novo por carga/linguagem,
com ambos os motores restritos à mesma CPU lógica. A ordem Python/Go alterna
entre cargas. No Windows, ambos usam contadores de alta resolução baseados em
`QueryPerformanceCounter`.

Os dados brutos, versões, hardware, hashes de código/entrada e relatório são
salvos em `artefatos/benchmark/resultados-local/`, ou na pasta indicada por
`BENCHMARK_ARGS="--output-dir ..."`. O pico de RSS inclui o processo inteiro,
desde a inicialização até terminar todas as etapas; não é memória marginal do
cálculo. A mediana e o p95 do total vêm de sua própria medição.

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

- [Registro da rodada no Google Docs](https://docs.google.com/document/d/1JFNI7PQNreKTGj-Nm2qI3IoY9sP--QneeYoeZpNDcc8/edit).
- [Relatório com todas as etapas](benchmark/rodada-local-2026-10-05/relatorio.md).
- [Amostras brutas, estatísticas, ambiente e hashes](benchmark/rodada-local-2026-10-05/resultados.json).
- Revisão base do repositório: `47e3dc7005d4d60117d6e9f04e5c646517ee34c7`.
  A implementação Go e o executor de medição continham alterações locais;
  a identificação exata está nos hashes SHA-256 registrados no JSON.
- O perfil `ciclo_misto_v1` corresponde ao ciclo armazenado em
  `ciclo_caso_v1.json`.

```sh
make -C apps/fullstack benchmark-medir GO=/caminho/para/go \
  BENCHMARK_ARGS="--label 2026-10-05 --output-dir ../../../artefatos/benchmark/rodada-local-2026-10-05"
```

Para preservar esta evidência, use outra pasta de saída em rodadas futuras.
