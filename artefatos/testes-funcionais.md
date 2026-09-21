# Testes do UC03 e análise de valor-limite

Este documento registra o planejamento, a implementação, a execução e os resultados dos testes do **UC03 - Produzir hipóteses de causa provável**. Ele cobre exclusivamente o item 3 da avaliação. Os testes unitários gerais, os testes de integração e os testes de carga são responsabilidades documentadas nos artefatos correspondentes dos demais integrantes.

## 1. Caso de uso e escopo

O UC03 recebe as anomalias detectadas pelo UC02, avalia famílias de hipóteses e persiste candidatas auditáveis para análise humana. No fluxo principal, o motor calcula força, coincidência temporal, corroboração, especificidade, impacto e qualidade. Depois, aplica penalidades, calcula `score`, cobertura e confiança e classifica cada candidata como `generated`, `discarded` ou `insufficient_evidence`.

O caso de uso foi escolhido porque possui entradas numéricas com limites explícitos. Os testes cobrem o fluxo principal, os fluxos alternativos A1 a A5, as exceções E1 a E4, as pós-condições e os valores imediatamente abaixo, no limite e imediatamente acima das fronteiras.

### 1.1 Regras avaliadas

| Decisão | Regra |
|---|---:|
| Gerar hipótese | `score >= 40,00` e `coverage >= 0,50` |
| Atribuir confiança alta | `score >= 80,00`, `coverage >= 0,80`, `quality >= 0,70` e `contradiction < 0,50` |

O motor também possui os limites de 10.000 candidatos no total, 2.000 candidatos por família e 500 hipóteses geradas. Esses limites são verificados no fluxo de exceção E2.

### 1.2 Classes de equivalência e valores-limite

#### Geração da hipótese

| Variável | Classe abaixo do limite | Fronteira inclusiva | Classe acima do limite |
|---|---:|---:|---:|
| Score | 39,99 | 40,00 | 40,01 |
| Cobertura | 0,49 | 0,50 | 0,51 |

#### Confiança alta

| Variável | Imediatamente abaixo | Fronteira inclusiva | Imediatamente acima |
|---|---:|---:|---:|
| Score | 79,99 | 80,00 | 80,01 |
| Cobertura | 0,79 | 0,80 | 0,81 |
| Qualidade | 0,69 | 0,70 | 0,71 |

As fronteiras são inclusivas. Atingir exatamente o valor mínimo é suficiente quando as demais condições da decisão também são satisfeitas.

## 2. Planejamento e condições de execução

### 2.1 Pré-condições comuns

Os testes de avaliação usam candidatos sintéticos, anomalias sintéticas, um catálogo válido e uma fonte com qualidade conhecida. Nos casos de persistência, também são necessários um PostgreSQL de teste, as migrations aplicadas, um checkpoint Gold e um manifesto registrado. Os testes que dependem do banco são identificados na matriz.

### 2.2 Procedimento comum

1. Preparar as entradas sintéticas ou o cenário de banco indicado no caso.
2. Executar a função ou o fluxo correspondente ao teste automatizado.
3. Comparar o estado, o score, a cobertura, a confiança, os contadores ou os registros persistidos com o resultado esperado.
4. Registrar a saída do pytest e, nos testes de banco, consultar as tabelas de resultado e de feedback.

Nos testes parametrizados, cada combinação de valores abaixo, no limite e acima é coletada como um caso independente pelo pytest.

### 2.3 Localização do código e reprodução

Os testes estão em [`apps/basica/processing/tests`](../apps/basica/processing/tests). Os principais arquivos utilizados são:

- [`test_uc03_valores_limite.py`](../apps/basica/processing/tests/test_uc03_valores_limite.py), com os limites, as exceções E1 e E2 e as pós-condições.
- [`test_familias.py`](../apps/basica/processing/tests/test_familias.py), com os cenários positivos das famílias e os fluxos A4 e A5.
- [`test_rules.py`](../apps/basica/processing/tests/test_rules.py), com as regras de evidência e relação semântica.
- [`test_budgets_e_detector.py`](../apps/basica/processing/tests/test_budgets_e_detector.py), com os cortes por família, total e determinismo.
- [`test_fencing.py`](../apps/basica/processing/tests/test_fencing.py), com a reversão da persistência após falha.
- [`test_analysis_pipeline.py`](../apps/basica/processing/tests/test_analysis_pipeline.py), com o gate de publicação do manifesto.

Para reproduzir a suíte específica no WSL:

```bash
cd apps/basica/processing
TEST_DATABASE_URL=postgresql://argus:argus@localhost:55432/argus_test \
  .venv/bin/pytest -q -p no:cacheprovider tests/test_uc03_valores_limite.py
```

Para executar todos os testes do processamento:

```bash
cd apps/basica/processing
TEST_DATABASE_URL=postgresql://argus:argus@localhost:55432/argus_test \
  .venv/bin/pytest -q -p no:cacheprovider
```

## 3. Casos de teste de valor-limite

Nos casos CT02 a CT07, a pré-condição é uma candidata válida e a entrada variável é `score` ou `coverage`. O procedimento consiste em substituir apenas esse valor, executar `test_a1_limites_de_geracao` e verificar `evaluation_status`. A evidência é a saída parametrizada do pytest em [`test_uc03_valores_limite.py`](../apps/basica/processing/tests/test_uc03_valores_limite.py).

Nos casos CT16 a CT24, a pré-condição é uma avaliação sem contradição, com as demais variáveis válidas. O procedimento consiste em variar apenas `score`, `coverage` ou `quality`, executar a função parametrizada correspondente e comparar `confidence`. A evidência é a saída parametrizada do pytest no mesmo arquivo.

| ID | Objetivo e condição | Requisito ou fluxo relacionado | Entrada variável | Resultado esperado | Resultado obtido | Situação |
|---|---|---|---|---|---|---|
| CT02 | Verificar score imediatamente abaixo | A1, evidência suficiente | score 39,99 e coverage 0,50 | `discarded` | `discarded` | **Aprovado** |
| CT03 | Verificar score na fronteira | A1, evidência suficiente | score 40,00 e coverage 0,50 | `generated` | `generated` | **Aprovado** |
| CT04 | Verificar score imediatamente acima | A1, evidência suficiente | score 40,01 e coverage 0,50 | `generated` | `generated` | **Aprovado** |
| CT05 | Verificar cobertura imediatamente abaixo | A1, evidência suficiente | score 40,00 e coverage 0,49 | `discarded` | `discarded` | **Aprovado** |
| CT06 | Verificar cobertura na fronteira | A1, evidência suficiente | score 40,00 e coverage 0,50 | `generated` | `generated` | **Aprovado** |
| CT07 | Verificar cobertura imediatamente acima | A1, evidência suficiente | score 40,00 e coverage 0,51 | `generated` | `generated` | **Aprovado** |
| CT16 | Verificar score de confiança abaixo | Regra de confiança alta | score 79,99, coverage 0,80 e quality 0,70 | `medium` | `medium` | **Aprovado** |
| CT17 | Verificar score de confiança na fronteira | Regra de confiança alta | score 80,00, coverage 0,80, quality 0,70 e contradiction 0,00 | `high` | `high` | **Aprovado** |
| CT18 | Verificar score de confiança acima | Regra de confiança alta | score 80,01, coverage 0,80 e quality 0,70 | `high` | `high` | **Aprovado** |
| CT19 | Verificar cobertura de confiança abaixo | Regra de confiança alta | score 80,00, coverage 0,79 e quality 0,70 | `medium` | `medium` | **Aprovado** |
| CT20 | Verificar cobertura de confiança na fronteira | Regra de confiança alta | score 80,00, coverage 0,80, quality 0,70 e contradiction 0,00 | `high` | `high` | **Aprovado** |
| CT21 | Verificar cobertura de confiança acima | Regra de confiança alta | score 80,00, coverage 0,81 e quality 0,70 | `high` | `high` | **Aprovado** |
| CT22 | Verificar qualidade abaixo | Regra de confiança alta | score 80,00, coverage 0,80 e quality 0,69 | `medium` | `medium` | **Aprovado** |
| CT23 | Verificar qualidade na fronteira | Regra de confiança alta | score 80,00, coverage 0,80, quality 0,70 e contradiction 0,00 | `high` | `high` | **Aprovado** |
| CT24 | Verificar qualidade acima | Regra de confiança alta | score 80,00, coverage 0,80 e quality 0,71 | `high` | `high` | **Aprovado** |

## 4. Fluxo principal, fluxos alternativos e exceções

Para CT01 e CT08 a CT15, aplicam-se as pré-condições e o procedimento comum da seção 2. O procedimento específico é o indicado na coluna de teste. A evidência é a saída do pytest e, quando indicado, a consulta ao banco realizada pelo próprio teste.

| ID | Objetivo e cenário | Requisito ou caso de uso relacionado | Procedimento e teste automatizado | Resultado esperado | Resultado obtido | Evidência e reprodução | Situação |
|---|---|---|---|---|---|---|---|
| CT01 | Avaliar candidata válida com fatores, score e estado | Fluxo principal do UC03 | Construir cenário positivo de falha interna e executar `test_familias.py::test_backend_internal` | Hipótese operacional `generated` com corroboração | Hipótese gerada com corroboração disponível | Executar `pytest -q tests/test_familias.py::test_backend_internal` | **Aprovado** |
| CT08 | Ausência obrigatória não deve virar contradição | A2, evidência indisponível | Avaliar score máximo com `required_missing` e executar `test_a2_evidencia_obrigatoria_ausente_prevalece_sobre_score` e `test_rules.py::test_evidencia_required_indisponivel_fica_insufficient_e_nao_contraria` | `insufficient_evidence` e contradição zero | `insufficient_evidence` e contradição zero | Executar os dois testes indicados | **Aprovado** |
| CT09 | Contradição determinante deve prevalecer sobre score | A3, evidência contrária determinante | Avaliar score máximo com contradiction 0,80 e executar `test_a3_contradicao_determinante_prevalece_sobre_score` | `discarded` | `discarded` | Executar `pytest -q tests/test_uc03_valores_limite.py::test_a3_contradicao_determinante_prevalece_sobre_score` | **Aprovado** |
| CT10 | Distinguir pico ao vivo esperado de degradação | A4, pico ao vivo esperado | Executar `test_familias.py::test_expected_live_peak` com evento compatível e com piora real | Contexto `generated` no primeiro cenário e descarte no segundo | Resultado observado nos dois cenários | Executar o teste indicado | **Aprovado** |
| CT11 | Separar problema da fonte de causa operacional | A5, problema na própria fonte | Executar `test_familias.py::test_source_data_delay` com fonte atrasada | Hipótese `generated` do tipo `data_quality` | Hipótese `generated` do tipo `data_quality` | Executar o teste indicado | **Aprovado** |
| CT12 | Interromper o motor diante de catálogo inválido | E1, catálogo ou manifesto inválido | Criar `sources.json` malformado e instanciar `Catalog` em `test_e1_catalogo_invalido_interrompe_o_motor` | `JSONDecodeError` e catálogo não construído | `JSONDecodeError` e catálogo não construído | Executar o teste indicado | **Aprovado** |
| CT13 | Aplicar cortes determinísticos e auditáveis | E2, limite de candidatos excedido | Executar os testes de orçamento da tabela abaixo | Respeitar 10.000, 2.000 e 500, contabilizando o truncamento | Contadores, determinismo, defaults e 500ª/501ª hipóteses corretos | Reproduzir os cinco testes indicados na tabela de evidências | **Aprovado** |
| CT14 | Impedir corroboração por entidade não relacionada | E3, relação semântica desconhecida | Executar `test_rules.py::test_relacao_semantica_e_corte_sao_estaveis` e os cenários não relacionados de `test_familias.py` | Evidência não relacionada não corrobora | Candidata não formada ou feature indisponível | Executar os testes indicados | **Aprovado** |
| CT15 | Reverter resultado parcial após falha | E4, falha ao persistir | Forçar falha durante persistência em `test_fencing.py::test_falha_na_persistencia_reverte_resultado_e_estado` | Zero resultado parcial e run não concluído | Zero anomalias parciais e run `running` | Executar o teste indicado com PostgreSQL disponível | **Aprovado** |
| CT25 | Verificar as pós-condições completas | Pós-condições do UC03 | Persistir três hipóteses e consultar estados, metadados, fatores, evidências e feedback em `test_pos_condicao_persiste_estados_metadados_e_sem_confirmacao` | Três estados persistidos, vínculo ao run e manifesto, fatores e evidências presentes e ausência de confirmação automática | Três estados e metadados persistidos, sem feedback de confirmação | Executar o teste indicado com PostgreSQL disponível | **Aprovado** |

### 4.1 Evidência específica do limite de candidatos

| Teste automatizado | Verificação |
|---|---|
| `test_budgets_e_detector.py::test_budget_por_familia_trunca_e_conta_o_descarte` | Limite por família e contagem do truncamento |
| `test_budgets_e_detector.py::test_budget_total_e_de_geracao_sao_independentes` | Limite total e limite de geração em etapas diferentes |
| `test_budgets_e_detector.py::test_corte_e_estavel_por_forca_impacto_e_chave_canonica` | Determinismo do corte independentemente da ordem de entrada |
| `test_uc03_valores_limite.py::test_e2_limite_de_500_hipoteses_geradas` | 500 hipóteses geradas e 501ª descartada por limite |
| `test_uc03_valores_limite.py::test_e2_tetos_documentados_sao_os_defaults_do_motor` | Defaults 10.000, 2.000 e 500 na assinatura do motor |

## 5. Pós-condições e rastreabilidade

O CT25 confirma, na mesma execução, a persistência de `generated`, `discarded` e `insufficient_evidence`, a preservação de score, cobertura e confiança, ao menos um fator e uma evidência por candidata, o vínculo ao `run_id` e ao `manifest_hash` e a ausência de registro em `gold.hypothesis_feedback`. Portanto, uma candidata não é promovida automaticamente a causa confirmada.

O CT15 complementa a pós-condição de falha. Uma exceção dentro da transação remove o resultado parcial e não marca a execução como concluída. O teste `test_analysis_pipeline.py::test_pipeline_captura_checkpoint_commita_e_so_publica_depois_do_gate` confirma que um resultado concluído permanece invisível até a promoção explícita do manifesto.

## 6. Execução e resultados

### 6.1 Execução registrada

A execução foi realizada com Python 3.12, PostgreSQL 16 local e ambiente WSL. O comando equivalente ao alvo `test-processing` do `Makefile` foi:

```bash
cd apps/basica/processing
TEST_DATABASE_URL=postgresql://argus:argus@localhost:55432/argus_test \
  .venv/bin/pytest -q -p no:cacheprovider
```

| Verificação | Resultado registrado |
|---|---:|
| Casos coletados | 88 |
| Casos aprovados | 88 |
| Falhas | 0 |
| Erros | 0 |
| Código de saída | 0 |
| `ruff check --no-cache src tests` | Aprovado |
| `ruff format --check --no-cache src tests` | Aprovado |

Essa execução é a evidência histórica usada para os resultados dos testes de banco descritos neste documento.

Em uma verificação posterior, sem PostgreSQL de teste disponível, foram coletados 84 testes. Desses, 51 foram aprovados e 33 foram ignorados por indisponibilidade do banco. Não houve falhas. A suíte específica `test_uc03_valores_limite.py` contém 22 testes coletáveis. Nessa verificação, 21 foram aprovados e o teste de persistência foi ignorado. Portanto, essa execução posterior não revalida as pós-condições no banco real.

## 7. Conclusão

O UC03 foi testado no fluxo principal, em todos os fluxos alternativos e de exceção descritos, nas pós-condições e nas fronteiras abaixo, no limite e acima dos limiares de geração e confiança. Os casos foram implementados com pytest, possuem localização no repositório, procedimento de reprodução, resultado esperado, resultado obtido e situação explícita. A execução histórica registrou 88 casos aprovados. A verificação posterior deixou documentada a indisponibilidade do PostgreSQL, sem transformar testes ignorados em aprovação.
