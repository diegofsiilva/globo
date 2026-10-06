# Recorte real local para comparação

Estado em 05/10/2026: **comparação executada, revisão humana pendente**. O banco local foi carregado com
a amostra Parquet (32 tabelas; 68.717.811 linhas) e a série
`br1|playback.video.globo.com` foi reconstruída em
`silver.analysis_fact_version` a partir de `bronze.signal_bucket`. A origem do
checkpoint consta em `etl.gold_checkpoint.row_counts`; não é um replay de CDC.

| Campo | Valor |
|---|---|
| Checkpoint | `1` |
| Presente simulado | `2026-07-26T20:00:00Z` |
| Run determinístico | `1`, concluído |
| Versões capturadas pelo run | 4.623 |
| `input_lsn` | `11581216` |
| `input_digest` do motor | `498305a8bffcec7f2b33eecde1cc5d791a61d134641d37f64f463d55b00a26ca` |
| Hipóteses do motor | 24 `generated`; 13 `discarded` |
| Agente com Ollama | `evidencia_insuficiente`; nenhuma hipótese |

O arquivo local ignorado pelo Git
`apps/fullstack/agente/saidas/comparacao-real/entrada-run-1.json` contém **as
mesmas versões e os mesmos papéis** registrados em `detect.run_input_fact`.
O `CaseReader` preservou as 4.623 linhas. Seu digest é
`3133d7c14d64e449ef8fac6771b46b6032d58de86c11fbbcadbeaa6767ed3e48`;
o algoritmo de digest difere do SQL do motor, portanto a identidade do conjunto
foi conferida pela exportação e pela contagem, não pela igualdade dos hashes.

O resultado completo do motor está em
`apps/fullstack/agente/saidas/comparacao-real/resultado-motor-run-1.json`, também
ignorado pelo Git. O resultado completo do agente está em
`apps/fullstack/agente/saidas/comparacao-real/agente-ollama/casos/run-1-checkpoint-1.json`.
O [resumo estruturado](real-run-1.json) reúne os dois lados sem versionar os
fatos brutos da amostra.

## Resultado lado a lado

| Aspecto | Motor determinístico | Agente com Ollama |
|---|---|---|
| Entrada | 4.623 versões capturadas no run `1` | As mesmas 4.623 versões e papéis exportados do run |
| Saída | 24 hipóteses geradas; 13 descartadas | `evidencia_insuficiente`; 0 hipóteses |
| Explicações operacionais | 4 `backend_internal` geradas | Nenhuma |
| Qualidade das fontes | 20 `source_data_delay` geradas | Não concluiu sobre qualidade |

O agente consultou uma página de 200 pontos de `error_4xx_rate_pct`. Depois
enviou três chamadas inválidas a `inventariar_fatos`, com filtros que essa
ferramenta não aceita, e desistiu declarando ausência de dados de 4xx. Essa
lacuna **contradiz o recorte**: há 1.541 fatos de 4xx nele, e 200 foram
devolvidos ao agente. A revisão da hipótese deve mostrar esse erro de
investigação, em vez de exibir a desistência como ausência comprovada de dados.

O motor gerou quatro hipóteses operacionais `backend_internal` e vinte de
qualidade de fonte. Isso é a saída observada do run reconstruído, não uma
medida de acerto. Não foi feita validação da causa com rótulos de incidente;
as 24 hipóteses geradas também não equivalem a 24 incidentes distintos.

## Implicações para o frontend

- Mostrar as duas abordagens com status e método de execução separados.
- Diferenciar hipótese operacional, alerta de qualidade e evidência insuficiente.
- Mostrar consultas, erros de ferramenta e lacunas do agente junto com a saída.
- Marcar `sem_dado` como **lacuna contestada** quando o recorte comprova que o
  dado existia e foi devolvido ao agente.
- Exibir checkpoint, presente simulado e quantidade de fatos compartilhados no
  cabeçalho; manter o aviso de que o checkpoint foi reconstruído da Bronze.
