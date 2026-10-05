# Comparação local dos três casos sintéticos

Executei `apps/fullstack/agente/scripts/comparar_casos.py` com o mesmo recorte
causal em cada abordagem. O arquivo [resultados.json](resultados.json) contém os
campos por caso para exploração no frontend; os registros completos do agente
ficam em `agente-roteiro/casos/`.

| Caso | Agente com roteiro fixo | Motor determinístico, sem baseline histórico |
|---|---|---|
| `caso-01-deploy` | Hipótese de possível regressão após deploy | 0 anomalias; 20 hipóteses `source_data_delay` |
| `caso-02-borda` | Hipótese de possível bloqueio na borda | 0 anomalias; 21 hipóteses `source_data_delay` |
| `caso-03-fonte-atrasada` | Evidência insuficiente, com lacunas | 0 anomalias; 21 hipóteses `source_data_delay` |

## Como ler o resultado

Os fatos, `sim_now` e `input_lsn` são os mesmos em cada par. O agente foi
executado com **roteiros fixos**, sem Ollama. O motor executou suas funções reais
de qualidade, detector, regras e score, em memória e com baseline inicial vazio.
O motor exige 12 observações por slot horário BRT para aquecer o detector; as
fixtures de três horas não oferecem esse histórico. Também não representam a
cobertura completa de fontes que o canário espera, por isso os resultados do
motor são apenas alertas de qualidade de fonte. Eles não demonstram que o motor
deixaria de detectar os mesmos incidentes em um run real.

Essa comparação **não mede qual abordagem é melhor**. Para a comparação real,
precisamos de um checkpoint do banco com histórico suficiente, o resultado do
run determinístico associado e uma execução do agente com Ollama. Deve-se
conferir `sim_now`, `input_lsn` e as versões de fatos de ambos antes de colocar
as saídas lado a lado. O digest do leitor do agente não deve ser presumido igual
ao `input_digest` do motor sem conferir a canonização de cada um.

## Consequência para o frontend

O protótipo de comparação precisa distinguir `hipotese`,
`evidencia_insuficiente`, ausência de anomalia operacional e alerta de qualidade
da fonte. Cada lado deve mostrar seu modo de execução e o recorte de origem.
Números deste ensaio devem aparecer como **dados sintéticos de demonstração**;
não como métrica de acerto ou comparação validada com dados reais.

## Repetir

```bash
uv run --project apps/fullstack/processing python apps/fullstack/agente/scripts/comparar_casos.py
```
