# Testes do UC03 e análise de valor-limite

Este documento registra o planejamento, a implementação, a execução e os resultados dos testes do UC03. Foi escolhido o **UC03 - Produzir hipóteses de causa provável**, pois suas regras de decisão deixam claro onde um valor no limite muda o resultado. A análise acompanha o caso de uso de ponta a ponta, desde a entrada das anomalias até a classificação e a persistência das hipóteses, passando pelo fluxo principal, pelos fluxos alternativos, pelas exceções e pelas pós-condições.

## 1. Escolha e funcionamento do UC03

O UC03 recebe as anomalias encontradas pelo UC02 (*Processar telemetria e detectar*) e passa cada candidata pelas regras das famílias de hipótese. Durante esse caminho, o motor calcula força, coincidência temporal, corroboração, especificidade, impacto e qualidade, aplica as penalidades necessárias e chega ao `score`, à cobertura e à confiança.

O fluxo usado como referência pode ser resumido assim:

```text
anomalias do UC02 -> regras das famílias -> score e cobertura
                   -> classificação da candidata -> persistência do resultado
```

No final, cada candidata fica como `generated`, `discarded` ou `insufficient_evidence`. Como essa decisão depende de valores numéricos, foi possível testar não só exemplos comuns, mas também o valor imediatamente abaixo, o valor exato e o valor imediatamente acima de cada fronteira.

### 1.1 Regras principais

| Decisão | Regra usada pelo motor |
|---|---:|
| Gerar hipótese | `score >= 40,00` e `coverage >= 0,50` |
| Atribuir confiança alta | `score >= 80,00`, `coverage >= 0,80`, `quality >= 0,70` e `contradiction < 0,50` |

Além desses limiares, o motor aceita no máximo 10.000 candidatos no total, 2.000 por família e 500 hipóteses geradas. Esses valores também foram incluídos porque fazem parte do fluxo E2 e mudam o comportamento quando a quantidade permitida é ultrapassada.

### 1.2 Valores usados nos testes

Para a geração da hipótese, foram usados os seguintes valores:

| Variável | Imediatamente abaixo | No limite | Imediatamente acima |
|---|---:|---:|---:|
| Score | 39,99 | 40,00 | 40,01 |
| Cobertura | 0,49 | 0,50 | 0,51 |

Para a confiança alta, foram usados:

| Variável | Imediatamente abaixo | No limite | Imediatamente acima |
|---|---:|---:|---:|
| Score | 79,99 | 80,00 | 80,01 |
| Cobertura | 0,79 | 0,80 | 0,81 |
| Qualidade | 0,69 | 0,70 | 0,71 |

As fronteiras são inclusivas, então atingir exatamente o valor mínimo já deve produzir o resultado da classe superior quando as outras condições também forem atendidas.

## 2. Organização dos testes

### 2.1 Preparação dos cenários

Nos testes que avaliam as regras, foram usados candidatos e anomalias sintéticas, um catálogo válido e uma fonte com qualidade conhecida. Dessa forma, somente o valor analisado varia e as outras condições não interferem no resultado.

Nos cenários de persistência, a preparação também inclui um PostgreSQL de teste com as migrations aplicadas, um checkpoint Gold e um manifesto registrado. O teste segue além da resposta da função, grava o resultado e consulta o banco novamente para conferir o que realmente ficou salvo.

### 2.2 Fluxo de execução

Cada caso parte de um cenário controlado em que apenas a condição observada é alterada. Em seguida, o teste automatizado compara o resultado esperado com o resultado obtido. Nos casos parametrizados, cada valor abaixo, no limite e acima é coletado separadamente pelo pytest, o que deixa claro qual fronteira apresentou problema caso alguma verificação falhe.

### 2.3 Onde os testes estão

Os testes ficam em [`apps/basica/processing/tests`](../apps/basica/processing/tests). A divisão entre os arquivos acompanha o fluxo do UC03:

- [`test_uc03_valores_limite.py`](../apps/basica/processing/tests/test_uc03_valores_limite.py) concentra os valores-limite, as exceções E1 e E2 e a pós-condição de persistência
- [`test_familias.py`](../apps/basica/processing/tests/test_familias.py) traz os cenários positivos das famílias e os fluxos A4 e A5
- [`test_rules.py`](../apps/basica/processing/tests/test_rules.py) verifica evidências obrigatórias, contradições e relações semânticas
- [`test_budgets_e_detector.py`](../apps/basica/processing/tests/test_budgets_e_detector.py) cobre os limites por família, o limite total e a estabilidade do corte
- [`test_fencing.py`](../apps/basica/processing/tests/test_fencing.py) confere a reversão quando ocorre uma falha na persistência
- [`test_analysis_pipeline.py`](../apps/basica/processing/tests/test_analysis_pipeline.py) verifica que o resultado só aparece depois da publicação do manifesto

## 3. Testes nos valores-limite

A análise começa pelos pontos em que uma diferença pequena muda a classificação. Nos casos CT02 a CT07, uma candidata válida é mantida enquanto somente `score` ou `coverage` varia. Nos casos CT16 a CT24, o mesmo princípio é aplicado às três condições da confiança alta, sempre com as outras variáveis em valores válidos.

| ID | Limite avaliado | Entrada usada | Esperado | Obtido | Situação |
|---|---|---|---|---|---|
| CT02 | Score abaixo da geração | score 39,99 e coverage 0,50 | `discarded` | `discarded` | **Aprovado** |
| CT03 | Score no limite da geração | score 40,00 e coverage 0,50 | `generated` | `generated` | **Aprovado** |
| CT04 | Score acima da geração | score 40,01 e coverage 0,50 | `generated` | `generated` | **Aprovado** |
| CT05 | Cobertura abaixo da geração | score 40,00 e coverage 0,49 | `discarded` | `discarded` | **Aprovado** |
| CT06 | Cobertura no limite da geração | score 40,00 e coverage 0,50 | `generated` | `generated` | **Aprovado** |
| CT07 | Cobertura acima da geração | score 40,00 e coverage 0,51 | `generated` | `generated` | **Aprovado** |
| CT16 | Score abaixo da confiança alta | score 79,99, coverage 0,80 e quality 0,70 | `medium` | `medium` | **Aprovado** |
| CT17 | Score no limite da confiança alta | score 80,00, coverage 0,80, quality 0,70 e contradiction 0,00 | `high` | `high` | **Aprovado** |
| CT18 | Score acima da confiança alta | score 80,01, coverage 0,80 e quality 0,70 | `high` | `high` | **Aprovado** |
| CT19 | Cobertura abaixo da confiança alta | score 80,00, coverage 0,79 e quality 0,70 | `medium` | `medium` | **Aprovado** |
| CT20 | Cobertura no limite da confiança alta | score 80,00, coverage 0,80, quality 0,70 e contradiction 0,00 | `high` | `high` | **Aprovado** |
| CT21 | Cobertura acima da confiança alta | score 80,00, coverage 0,81 e quality 0,70 | `high` | `high` | **Aprovado** |
| CT22 | Qualidade abaixo da confiança alta | score 80,00, coverage 0,80 e quality 0,69 | `medium` | `medium` | **Aprovado** |
| CT23 | Qualidade no limite da confiança alta | score 80,00, coverage 0,80, quality 0,70 e contradiction 0,00 | `high` | `high` | **Aprovado** |
| CT24 | Qualidade acima da confiança alta | score 80,00, coverage 0,80 e quality 0,71 | `high` | `high` | **Aprovado** |

Os testes acima estão parametrizados em [`test_uc03_valores_limite.py`](../apps/basica/processing/tests/test_uc03_valores_limite.py), por isso cada linha aparece como um caso independente durante a execução.

## 4. Fluxo principal, alternativas e exceções

Depois dos limites numéricos, a verificação percorre os outros caminhos do caso de uso. Nessa etapa entram o fluxo principal, as cinco alternativas, as quatro exceções e as pós-condições, sempre com o teste automatizado fazendo a ligação entre o cenário descrito e o comportamento real do código.

| ID | Fluxo | Como foi testado | Esperado | Obtido | Situação |
|---|---|---|---|---|---|
| CT01 | Principal | Execução de `test_familias.py::test_backend_internal` com uma falha interna válida | Hipótese operacional `generated` com corroboração | Hipótese gerada com corroboração | **Aprovado** |
| CT08 | A2 | Avaliação com score máximo e evidência obrigatória ausente nos testes de limite e de regras | `insufficient_evidence` sem criar contradição | `insufficient_evidence` e contradição zero | **Aprovado** |
| CT09 | A3 | Avaliação com score máximo e contradiction 0,80 em `test_a3_contradicao_determinante_prevalece_sobre_score` | `discarded` | `discarded` | **Aprovado** |
| CT10 | A4 | Execução de `test_familias.py::test_expected_live_peak` com pico esperado e com degradação real | Gerar contexto no primeiro cenário e descartar no segundo | Os dois cenários seguiram a regra esperada | **Aprovado** |
| CT11 | A5 | Execução de `test_familias.py::test_source_data_delay` com uma fonte atrasada | Hipótese `generated` do tipo `data_quality` | Hipótese `generated` do tipo `data_quality` | **Aprovado** |
| CT12 | E1 | Criação de um `sources.json` inválido em `test_e1_catalogo_invalido_interrompe_o_motor` | `JSONDecodeError` e catálogo não construído | `JSONDecodeError` e catálogo não construído | **Aprovado** |
| CT13 | E2 | Execução dos testes de quantidade e de um cenário com 501 candidatas válidas | Respeitar os limites de 10.000, 2.000 e 500, registrando o descarte | 500 geradas, a 501ª descartada e truncamento igual a 1 | **Aprovado** |
| CT14 | E3 | Avaliação de entidades sem relação explícita nos testes de regras e famílias | Evidência não relacionada não pode corroborar | A candidata não foi formada ou o fator ficou indisponível | **Aprovado** |
| CT15 | E4 | Falha forçada durante a persistência em `test_falha_na_persistencia_reverte_resultado_e_estado` | Nenhum resultado parcial e execução não concluída | Zero anomalias parciais e execução ainda `running` | **Aprovado** |
| CT25 | Pós-condições | Persistência dos três estados seguida da consulta de hipóteses, metadados, fatores, evidências e avaliações humanas | Dados completos no banco, sem confirmação automática | Três estados persistidos com os metadados esperados e sem avaliação humana | **Aprovado** |

### 4.1 Limites de quantidade

No E2, a verificação não fica limitada aos valores configurados. Uma entrada com 501 candidatas válidas permite observar a mudança de comportamento, confirmando que as primeiras 500 ficam como `generated`, a última é descartada e o contador `truncated` fica em 1.

| Teste automatizado | O que ele confere |
|---|---|
| `test_budgets_e_detector.py::test_budget_por_familia_trunca_e_conta_o_descarte` | Limite por família e contagem do truncamento |
| `test_budgets_e_detector.py::test_budget_total_e_de_geracao_sao_independentes` | Limite total e limite de geração em momentos diferentes |
| `test_budgets_e_detector.py::test_corte_e_estavel_por_forca_impacto_e_chave_canonica` | Mesmo corte independentemente da ordem de entrada |
| `test_uc03_valores_limite.py::test_e2_limite_de_500_hipoteses_geradas` | 500 hipóteses geradas e a 501ª descartada |
| `test_uc03_valores_limite.py::test_e2_tetos_documentados_sao_os_defaults_do_motor` | Valores padrão de 10.000, 2.000 e 500 na assinatura do motor |

## 5. Verificação depois do resultado

A verificação não termina no retorno imediato da função. No CT25, o fluxo segue até o banco e depois consulta as informações persistidas, cobrindo os estados `generated`, `discarded` e `insufficient_evidence`, além de score, cobertura, confiança, `run_id`, `manifest_hash`, fatores e evidências.

Na mesma consulta, `gold.hypothesis_feedback` deve continuar vazio, pois uma hipótese gerada ainda é somente uma candidata para análise humana e não pode aparecer automaticamente como causa confirmada.

O caminho de falha também faz parte da verificação. No CT15, uma exceção durante a transação desfaz o resultado parcial e não conclui a execução, enquanto `test_analysis_pipeline.py::test_pipeline_captura_checkpoint_commita_e_so_publica_depois_do_gate` mostra que um resultado concluído continua invisível até a publicação do manifesto.

## 6. Execução e evidências

Os testes foram executados em WSL com Python 3.12.3 e pytest 9.1.1. Antes da execução, o PostgreSQL 16 local foi recriado e recebeu as migrations de `001` a `029`, deixando o banco `argus_test` pronto para os cenários de persistência.

Os comandos usados foram:

```bash
make -C apps/basica db-local

cd apps/basica/processing
.venv/bin/ruff check --no-cache src tests
.venv/bin/ruff format --check --no-cache src tests

TEST_DATABASE_URL=postgresql://argus:argus@localhost:55432/argus_test \
  .venv/bin/pytest -q -p no:cacheprovider

TEST_DATABASE_URL=postgresql://argus:argus@localhost:55432/argus_test \
  .venv/bin/pytest -vv -p no:cacheprovider tests/test_uc03_valores_limite.py
```

| Verificação | Resultado |
|---|---:|
| Conjunto completo de testes do processamento | 88 pontos de progresso e `[100%]` |
| Testes específicos do UC03 | `22 passed in 20.65s` |
| Falhas exibidas | Nenhuma |
| Erros exibidos | Nenhum |
| Testes ignorados exibidos | Nenhum |
| `ruff check --no-cache src tests` | Aprovado |
| `ruff format --check --no-cache src tests` | Aprovado |

Abaixo estão as capturas de tela do terminal, mostrando a preparação do PostgreSQL, a execução do Ruff e a execução nominal dos testes do UC03.

![Preparação do PostgreSQL e aplicação das migrations](assets/uc03-terminal-banco.png)

*Figura 1 - Saída completa da preparação do PostgreSQL, com a rota de execução e as migrations de 001 a 029.*

![Ruff e conjunto completo de testes do processamento](assets/uc03-terminal-suite-completa.png)

*Figura 2 - Saída completa do Ruff e do conjunto de testes do processamento executado com `-q`.*

![Execução nominal dos testes do UC03](assets/uc03-terminal-suite-uc03.png)

*Figura 3 - Saída nominal completa dos 22 testes do UC03.*

O conjunto completo de testes foi executado com `-q`, por isso o terminal mostrou 88 pontos de progresso e `[100%]`, mas não imprimiu uma frase com o total de testes aprovados. Na sequência, os testes específicos do UC03 apareceram individualmente e a execução terminou com `22 passed in 20.65s`.

O total do conjunto completo vem da contagem dos 88 pontos exibidos na linha de progresso, enquanto o total do UC03 vem do resumo textual emitido pelo próprio pytest. Assim, a documentação preserva a forma como cada resultado apareceu no terminal e mantém visíveis todos os testes executados, sem acrescentar linhas que não estavam na saída original.

## 7. Conclusão

O conjunto de testes não se limita ao cenário em que tudo funciona como esperado. A cobertura passa pelas fronteiras que mudam a decisão, pelos fluxos alternativos, pelos limites de quantidade, pelos erros de catálogo e persistência e pelo estado final salvo no banco.

O resultado reúne uma execução completa com 88 indicadores de aprovação e uma execução específica do UC03 com 22 testes aprovados, sem sinais de falha, erro ou caso ignorado. Dessa forma, cada resultado das tabelas permanece ligado ao teste que o produziu, ao comando usado na execução e à evidência apresentada no próprio documento.
