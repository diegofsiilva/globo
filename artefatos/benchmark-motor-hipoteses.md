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
