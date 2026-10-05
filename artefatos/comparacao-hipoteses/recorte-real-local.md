# Recorte real local para comparação

Estado em 05/10/2026: **comparação incompleta**. O banco local foi carregado com
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
| Agente com Ollama | Pendente de autorização para enviar fatos reais ao endpoint remoto |

O arquivo local ignorado pelo Git
`apps/fullstack/agente/saidas/comparacao-real/entrada-run-1.json` contém **as
mesmas versões e os mesmos papéis** registrados em `detect.run_input_fact`.
O `CaseReader` preservou as 4.623 linhas. Seu digest é
`3133d7c14d64e449ef8fac6771b46b6032d58de86c11fbbcadbeaa6767ed3e48`;
o algoritmo de digest difere do SQL do motor, portanto a identidade do conjunto
foi conferida pela exportação e pela contagem, não pela igualdade dos hashes.

O resultado completo do motor está em
`apps/fullstack/agente/saidas/comparacao-real/resultado-motor-run-1.json`, também
ignorado pelo Git. Esses arquivos locais podem orientar a estrutura da tela,
mas ainda não sustentam uma comparação lado a lado com uma resposta da IA.

O teste de conexão com Ollama passou. A execução que enviaria os 4.623 fatos
reais ao servidor remoto foi rejeitada pela revisão automática de segurança
porque o destino configurado não foi aprovado para esse payload. O agente não
foi executado nesse recorte. Não use as saídas sintéticas com roteiro como se
fossem o resultado dele.
