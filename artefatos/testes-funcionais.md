# Testes funcionais, unitários e de carga

> **Escopo desta atualização:** testes unitários. As seções de testes de
> integração, caso de uso com análise de valor limite e carga serão incluídas
> após a implementação e a execução efetiva dessas etapas.

## 1. Objetivo e escopo

Este documento registra o planejamento, a implementação, a execução e os
resultados dos testes do Argus. Nesta entrega foram avaliadas unidades de lógica
do backend, do worker de ingestão, do simulador e do motor de processamento.

Os testes desta seção são unitários porque exercitam funções, métodos ou classes
em memória, sem PostgreSQL, filas SQS, rede ou serviços da AWS. A suíte foi
implementada com `pytest` e inclui entradas válidas, entradas inválidas e valores
de fronteira.

### 1.1 Critérios de aceite desta etapa

| Critério | Evidência observada | Situação |
|---|---|---|
| Pelo menos quatro testes unitários implementados | 133 casos automatizados em 12 arquivos | Aprovado |
| Função, método ou classe testada identificada | Unidade indicada na matriz e no arquivo de cada teste | Aprovado |
| Casos válidos e casos de erro | Casos TU-01 e TU-03 válidos; TU-02, TU-04, TU-05 e TU-09 de erro ou rejeição | Aprovado |
| Uso de ferramenta automatizada | `pytest` nos quatro serviços | Aprovado |
| Testes efetivamente executados | 133 aprovados e nenhuma falha na execução de 21/09/2026 | Aprovado |
| Código, comandos e evidências localizáveis | Caminhos e comandos registrados nas seções 2, 5 e 6 | Aprovado |

## 2. Ambiente, ferramenta e localização

### 2.1 Ambiente da execução

| Item | Valor observado |
|---|---|
| Data e hora | 21/09/2026, 16:56:50 (UTC-03:00) |
| Sistema | Linux |
| Linguagem | Python 3.12.3 |
| Ferramenta | pytest |
| Versão no backend | pytest 8.4.2 |
| Versão nos demais serviços | pytest 9.1.1 |
| Dependências externas | Nenhuma para os arquivos unitários selecionados |
| Evidência textual | [`evidencias/testes-unitarios.txt`](evidencias/testes-unitarios.txt) |

### 2.2 Inventário do código executado

| Serviço | Arquivo de teste | Unidades principais | Casos |
|---|---|---|---:|
| Backend | [`test_normalization.py`](../apps/basica/backend/tests/unit/test_normalization.py) | `parse_datetime`, `parse_json_object`, conversões, chaves e UUID | 20 |
| Backend | [`test_redaction.py`](../apps/basica/backend/tests/unit/test_redaction.py) | `hash_user_id`, `sanitize_url`, `redact_headers`, `redact_attributes` | 15 |
| Backend | [`test_signals.py`](../apps/basica/backend/tests/unit/test_signals.py) | `_severidade`, `_signal_id`, `GenerateSignals.execute` | 11 |
| Backend | [`test_timeline.py`](../apps/basica/backend/tests/unit/test_timeline.py) | `amostrar_raia` | 6 |
| Backend | [`test_use_cases_logic.py`](../apps/basica/backend/tests/unit/test_use_cases_logic.py) | resumo, janelas, cursores e autenticação | 11 |
| Worker | [`test_changes.py`](../apps/basica/worker/tests/test_changes.py) | `ChangeEvent`, `parse_change` | 7 |
| Worker | [`test_check_size.py`](../apps/basica/worker/tests/test_check_size.py) | `check_size` | 4 |
| Worker | [`test_config.py`](../apps/basica/worker/tests/test_config.py) | `_env_int`, `Config.from_env` | 8 |
| Worker | [`test_extract.py`](../apps/basica/worker/tests/test_extract.py) | `_extract`, `_registro_recusado`, `_serializavel` | 14 |
| Simulador | [`test_emitter.py`](../apps/basica/simulator/tests/test_emitter.py) | `_blocos` | 5 |
| Simulador | [`test_faults.py`](../apps/basica/simulator/tests/test_faults.py) | `Falha.alcanca`, `Falha.aplicar`, `sortear`, `_params` | 15 |
| Processamento | [`test_detector_logic.py`](../apps/basica/processing/tests/test_detector_logic.py) | transformações, materialidade, direção, qualidade e scoring | 17 |
| **Total** | **12 arquivos** | **funções, métodos e classes isolados** | **133** |

Os arquivos-fonte exercitados ficam nos diretórios `src/telemetry`,
`src/argus_worker`, `src/argus_simulator` e `src/argus_processing` dos
respectivos serviços. As configurações do pytest estão nos arquivos
`pyproject.toml` de cada serviço.

## 3. Planejamento e rastreabilidade

Foram selecionados nove casos representativos para documentação detalhada. A
seleção inclui comportamento nominal, rejeição de dados inválidos, proteção de
informações, autenticação, análise de sinais e os dois lados da fronteira de
4 MB. Os demais testes dos 12 arquivos funcionam como suíte complementar de
regressão.

| ID | Unidade testada | Tipo | Requisito ou caso de uso relacionado | Arquivo automatizado |
|---|---|---|---|---|
| TU-01 | `hash_user_id` | Válido | RNF10 — proteção dos dados coletados | `backend/tests/unit/test_redaction.py` |
| TU-02 | `parse_datetime` | Erro | RF01/RF03 — receber telemetria sem aceitar data inválida | `backend/tests/unit/test_normalization.py` |
| TU-03 | `amostrar_raia` | Fronteira válida | RF12 — apresentar gráficos e indicadores | `backend/tests/unit/test_timeline.py` |
| TU-04 | `GenerateSignals.execute` | Fluxo alternativo | RF13 — destacar falhas de maior impacto | `backend/tests/unit/test_signals.py` |
| TU-05 | `_extract` | Erro | RNF04/RNF11 — isolar entrada inválida e identificar a falha | `worker/tests/test_extract.py` |
| TU-06 | `check_size` | Limite aceito | RNF04 — impedir que payload inválido comprometa o fluxo | `worker/tests/test_check_size.py` |
| TU-07 | `check_size` | Imediatamente acima | RNF04 — rejeitar payload irrecuperável | `worker/tests/test_check_size.py` |
| TU-08 | `_material` | Válido | RF17/RNF08 — hipóteses apoiadas por evidências relevantes | `processing/tests/test_detector_logic.py` |
| TU-09 | `_token_do_cabecalho` | Erro | RNF09 — acesso apenas com credencial autorizada | `backend/tests/unit/test_use_cases_logic.py` |

## 4. Especificação e resultado dos casos

### TU-01 — Gerar identificador desidentificado e determinístico

- **Objetivo:** verificar que `hash_user_id` transforma um identificador em um
  hash estável, sem expor o valor original, apoiando o RNF10.
- **Unidade testada:** função `hash_user_id`, em
  [`redaction.py`](../apps/basica/backend/src/telemetry/application/redaction.py).
- **Pré-condições:** ambiente do backend instalado pelo `uv`; nenhuma conexão
  externa é necessária.
- **Dados de entrada:** `user_id="usuario-123"` e
  `salt="meu-salt-secreto"`.
- **Procedimento:** executar o nó pytest indicado na seção 6; o teste calcula
  independentemente o SHA-256 esperado e compara os 32 caracteres iniciais.
- **Resultado esperado:** hash hexadecimal determinístico com 32 caracteres.
- **Resultado obtido:** valor, tamanho e alfabeto hexadecimal aprovados.
- **Situação:** **Aprovado**.
- **Evidência:** saída `PASSED` para o nó TU-01 no arquivo de evidência.

### TU-02 — Rejeitar data em formato desconhecido

- **Objetivo:** garantir que uma data não interpretável não seja silenciosamente
  aceita durante a normalização de telemetria.
- **Unidade testada:** função `parse_datetime`, em
  [`normalization.py`](../apps/basica/backend/src/telemetry/application/normalization.py).
- **Pré-condições:** ambiente do backend instalado; nenhuma dependência externa.
- **Dados de entrada:** string `"nao-e-uma-data"`.
- **Procedimento:** chamar `parse_datetime` dentro de `pytest.raises` e validar
  a exceção de domínio e a mensagem contendo `invalido`.
- **Resultado esperado:** `ValidationError`; nenhum `datetime` produzido.
- **Resultado obtido:** a exceção esperada foi capturada.
- **Situação:** **Aprovado**.
- **Evidência:** nó TU-02 marcado como `PASSED` no arquivo de evidência.

### TU-03 — Amostrar série um ponto acima do limite

- **Objetivo:** confirmar que `amostrar_raia` reduz uma série que ultrapassa o
  limite sem perder as extremidades temporais usadas pela Timeline.
- **Unidade testada:** função `amostrar_raia`, em
  [`timeline.py`](../apps/basica/backend/src/telemetry/application/timeline.py).
- **Pré-condições:** lista ordenada em memória; nenhuma conexão externa.
- **Dados de entrada:** 101 pontos e `limite=100`.
- **Procedimento:** executar a função e verificar `truncated=True`, quantidade
  menor ou igual a 100 e preservação do primeiro e do último ponto.
- **Resultado esperado:** série truncada, com extremos preservados.
- **Resultado obtido:** todas as pós-condições foram atendidas.
- **Situação:** **Aprovado**.
- **Evidência:** nó TU-03 marcado como `PASSED` no arquivo de evidência.

### TU-04 — Ignorar sinal que deixou de exceder o limiar

- **Objetivo:** verificar que o backend não apresenta como ativo um sinal cujo
  bucket mais recente voltou à faixa estável.
- **Unidade testada:** método `GenerateSignals.execute`, em
  [`signals.py`](../apps/basica/backend/src/telemetry/application/signals.py).
- **Pré-condições:** repositório fake em memória retornando dois buckets.
- **Dados de entrada:** primeiro bucket com `z=3.0` e último com `z=1.5`, abaixo
  do limiar de sinal `2.0`.
- **Procedimento:** executar o caso de uso e inspecionar `count` e `items`.
- **Resultado esperado:** `count=0` e `items=[]`.
- **Resultado obtido:** nenhum sinal ativo foi produzido.
- **Situação:** **Aprovado**.
- **Evidência:** nó TU-04 marcado como `PASSED` no arquivo de evidência.

### TU-05 — Rejeitar JSON inválido recebido pelo worker

- **Objetivo:** confirmar que um corpo corrompido é identificado antes da
  persistência e recebe motivo de falha reproduzível.
- **Unidade testada:** função `_extract`, em
  [`consumer.py`](../apps/basica/worker/src/argus_worker/consumer.py).
- **Pré-condições:** ambiente do worker instalado; não requer SQS nem banco.
- **Dados de entrada:** corpo `"{ chave_sem_fechar: "` e chave `"events"`.
- **Procedimento:** chamar `_extract` dentro de `pytest.raises` e comparar a
  mensagem de erro com `JSON invalido`.
- **Resultado esperado:** `ValueError` identificando JSON inválido.
- **Resultado obtido:** exceção e mensagem esperadas foram observadas.
- **Situação:** **Aprovado**.
- **Evidência:** nó TU-05 marcado como `PASSED` no arquivo de evidência.

### TU-06 — Aceitar payload exatamente no limite de 4 MB

- **Objetivo:** provar que a guarda de tamanho não rejeita um change event ainda
  permitido pelo contrato.
- **Unidade testada:** função `check_size`, em
  [`repository.py`](../apps/basica/worker/src/argus_worker/repository.py).
- **Pré-condições:** `MAX_CHANGE_BYTES=4.000.000`; mesma serialização da
  implementação.
- **Dados de entrada:** dicionário cujo JSON possui exatamente `4.000.000` bytes.
- **Procedimento:** confirmar o tamanho serializado e chamar `check_size`.
- **Resultado esperado:** retorno sem exceção.
- **Resultado obtido:** o payload no limite foi aceito.
- **Situação:** **Aprovado**.
- **Evidência:** nó TU-06 marcado como `PASSED` no arquivo de evidência.

### TU-07 — Rejeitar payload um byte acima do limite

- **Objetivo:** comprovar o primeiro valor inválido após a fronteira de tamanho.
- **Unidade testada:** função `check_size`, no mesmo arquivo do TU-06.
- **Pré-condições:** iguais às do TU-06.
- **Dados de entrada:** JSON de exatamente `4.000.001` bytes.
- **Procedimento:** chamar `check_size` dentro de `pytest.raises`.
- **Resultado esperado:** lançamento de `ChangeTooLarge`.
- **Resultado obtido:** `ChangeTooLarge` foi capturada.
- **Situação:** **Aprovado**.
- **Evidência:** nó TU-07 marcado como `PASSED` no arquivo de evidência.

### TU-08 — Aprovar desvio que atende aos dois critérios de materialidade

- **Objetivo:** verificar que uma evidência só é material quando atende
  simultaneamente aos limites absoluto e relativo.
- **Unidade testada:** função `_material`, em
  [`detector.py`](../apps/basica/processing/src/argus_processing/detector.py).
- **Pré-condições:** política com limite absoluto `10.0` e relativo `0.20`.
- **Dados de entrada:** observado `125.0` e esperado `100.0`, com diferença
  absoluta `25.0` e relativa `25%`.
- **Procedimento:** executar `_material` com a política indicada.
- **Resultado esperado:** `True`, pois ambos os critérios são atendidos.
- **Resultado obtido:** retorno `True`.
- **Situação:** **Aprovado**.
- **Evidência:** nó TU-08 marcado como `PASSED` no arquivo de evidência.

### TU-09 — Rejeitar cabeçalhos de autenticação inválidos

- **Objetivo:** garantir que esquemas diferentes de Bearer, valores vazios e
  entradas ausentes não sejam interpretados como credenciais.
- **Unidade testada:** função `_token_do_cabecalho`, em
  [`auth.py`](../apps/basica/backend/src/telemetry/interfaces/auth.py).
- **Pré-condições:** nenhuma; função pura.
- **Dados de entrada:** `None`, string vazia, `"Basic dXNlcjpwYXNz"`,
  `"Bearer"` e `"Bearer    "`.
- **Procedimento:** executar a função para cada entrada e comparar o retorno.
- **Resultado esperado:** `None` em todos os casos.
- **Resultado obtido:** todas as entradas foram rejeitadas.
- **Situação:** **Aprovado**.
- **Evidência:** nó TU-09 marcado como `PASSED` no arquivo de evidência.

## 5. Resultado consolidado da execução

| Serviço | Coletados | Aprovados | Reprovados | Duração observada | Situação |
|---|---:|---:|---:|---:|---|
| Backend | 63 | 63 | 0 | 0,04 s | Aprovado |
| Worker | 33 | 33 | 0 | 0,23 s | Aprovado |
| Simulador | 20 | 20 | 0 | 0,04 s | Aprovado |
| Processamento | 17 | 17 | 0 | 0,02 s | Aprovado |
| **Total** | **133** | **133** | **0** | **0,33 s somados** | **Aprovado** |

As durações são as informadas pelo pytest em execuções separadas e locais; a
soma serve apenas como registro desta rodada, não como ensaio de desempenho. Os
testes que dependem de PostgreSQL não fazem parte desta contagem unitária.

### 5.1 Conclusão

O item de testes unitários atende ao mínimo da especificação e o ultrapassa em
amplitude: há mais de quatro casos, unidades identificadas, entradas válidas,
erros e fronteiras, execução automatizada e evidência reproduzível. O resultado
comprovado nesta rodada é de 133 testes aprovados e nenhuma reprovação.

Essa aprovação é restrita às unidades e entradas exercitadas. Ela não substitui
os testes de integração, o teste completo de um caso de uso nem os ensaios de
carga exigidos nas próximas etapas do documento.

## 6. Instruções para reprodução

Os comandos partem da raiz do repositório e usam os ambientes declarados em
cada `pyproject.toml`:

```bash
# Backend: 63 testes unitários
cd apps/basica/backend
uv run --quiet pytest tests/unit --tb=no

# Worker: 33 testes unitários selecionados
cd ../worker
uv run --quiet pytest \
  tests/test_changes.py \
  tests/test_check_size.py \
  tests/test_config.py \
  tests/test_extract.py \
  --tb=no

# Simulador: 20 testes unitários selecionados
cd ../simulator
uv run --quiet pytest tests/test_emitter.py tests/test_faults.py --tb=no

# Processamento: 17 testes unitários selecionados
cd ../processing
uv run --quiet pytest tests/test_detector_logic.py --tb=no
```

Para reproduzir apenas os nove casos detalhados, devem ser usados os nós pytest
registrados integralmente em
[`evidencias/testes-unitarios.txt`](evidencias/testes-unitarios.txt). Um processo
terminado com código `0`, todos os nós como `PASSED` e nenhuma linha `FAILED`
reproduz o resultado aprovado.

## 7. Próximas etapas do documento

Sem antecipar resultados ainda não executados, permanecem pendentes:

1. documentar e executar pelo menos dois testes de integração entre camadas;
2. selecionar um caso de uso e cobrir fluxo principal, alternativos, exceções,
   pós-condições e valores nos limites e imediatamente ao redor deles;
3. executar três níveis progressivos de carga, registrando concorrência, volume,
   duração, latência, erros, critérios de sucesso e conclusão.
