# Testes Funcionais e Unitários do Sistema Argus

## 1. Visão Geral da Suíte de Testes Unitários

Esta suíte de testes unitários foi desenvolvida para verificar componentes com **lógica de negócio interna densa** (estruturas condicionais `if/elif/else`, laços de iteração `for`, validações de regras de domínio, transformações matemáticas e tratamento de exceções).

Todos os testes são **puramente unitários e isolados**:
- Não dependem de banco de dados ativo, filas AWS SQS, rede ou serviços externos.
- Execução determinística em alta velocidade (< 1 segundo).

### Informações gerais consolidadas

| Módulo / Serviço | Localização dos Testes | Framework | Quantidade de Testes | Status |
|---|---|---|---|---|
| **Backend** | `apps/basica/backend/tests/unit/` | pytest (Python 3.12) | 63 testes | ✅ 100% aprovados |
| **Worker (Ingestão & CDC)** | `apps/basica/worker/tests/` | pytest (Python 3.12) | 78 testes | ✅ 100% aprovados |
| **Simulador de Telemetria** | `apps/basica/simulator/tests/` | pytest (Python 3.12) | 22 testes | ✅ 100% aprovados |
| **Motor de Processamento** | `apps/basica/processing/tests/` | pytest (Python 3.12) | 51 testes | ✅ 100% aprovados |
| **Lambda Authorizer** | `apps/basica/authorizer/tests/` | pytest (Python 3.12) | 18 testes | ✅ 100% aprovados |

---

## 2. Especificação das Unidades Testadas

Conforme as boas práticas de engenharia de software e testes de unidade, cada teste foca na menor unidade testável do software. A tabela a seguir classifica e referencia cada unidade no código-fonte:

### 2.1. Simulador (`apps/basica/simulator/`)

| Unidade Testada | Tipo no Código | Arquivo Fonte de Origem | Arquivo de Teste | Lógica Interna Testada |
|---|---|---|---|---|
| `Falha.alcanca` | **Método de Classe** (na classe `Falha`) | [`faults.py`](../apps/basica/simulator/src/argus_simulator/faults.py) | `tests/test_faults.py` | Avalia intervalo temporal `ts_start <= ts < ts_end` (limite inferior inclusivo e superior exclusivo) e correspondência de chaves de alvo (`source`, `entity`, `metric`), tratando chaves ausentes no alvo como coringas (*wildcards*). |
| `Falha.aplicar` | **Método de Classe** (na classe `Falha`) | [`faults.py`](../apps/basica/simulator/src/argus_simulator/faults.py) | `tests/test_faults.py` | Lógica de distorção de telemetria: preserva `None` de entrada, converte qualquer valor em `None` para falhas do tipo `source_outage` (apagão de métrica), e aplica multiplicação escalar `valor * multiplicador` para outros tipos. |
| `sortear` | **Função de Módulo** | [`faults.py`](../apps/basica/simulator/src/argus_simulator/faults.py) | `tests/test_faults.py` | Geração pseudo-aleatória determinística baseada em semente (`seed`) via `random.Random`, ordenação prévia e estável de fontes, e ordenação cronológica estrita das falhas geradas por `ts_start`. |
| `_params` | **Função de Módulo** | [`faults.py`](../apps/basica/simulator/src/argus_simulator/faults.py) | `tests/test_faults.py` | Geração de parâmetros numéricos dentro das faixas estatísticas de cada tipo de incidente: `error_spike` [3.0, 12.0], `latency` [1.15, 1.6], `drift` [0.7, 0.9] e `source_outage` `{}`. |
| `_blocos` | **Função de Módulo** | [`emitter.py`](../apps/basica/simulator/src/argus_simulator/emitter.py) | `tests/test_emitter.py` | Algoritmo de empacotamento em lotes com corte duplo: limite de tamanho serializado em bytes (`TETO_DO_CORPO_BYTES = 48 KB`) para respeitar restrições de URI do API Gateway e limite de quantidade (`TETO_DE_ITENS = 500`). Trata itens individualmente gigantes mantendo-os em blocos isolados sem descarte. |

### 2.2. Workers de Ingestão (`apps/basica/worker/`)

| Unidade Testada | Tipo no Código | Arquivo Fonte de Origem | Arquivo de Teste | Lógica Interna Testada |
|---|---|---|---|---|
| `_extract` | **Função de Módulo** | [`consumer.py`](../apps/basica/worker/src/argus_worker/consumer.py) | `tests/test_extract.py` | Extração flexível dos 3 formatos de mensagem entregues pelo API Gateway/SQS (objeto único `{...}`, lista crua `[{...}]` ou envelope `{"events": [...]}`). Valida e rejeita strings vazias, JSONs malformados, tipos primitivos ou listas sem itens. |
| `_registro_recusado` | **Função de Módulo** | [`consumer.py`](../apps/basica/worker/src/argus_worker/consumer.py) | `tests/test_extract.py` | Lógica de decisão de destino de falha: erros de dados/integridade (`IntegrityError`, `DataError`) retornam `True` (desvio para DLQ para não travar a fila), enquanto falhas de infraestrutura (`OperationalError`) e sintaxe (`ProgrammingError`) retornam `False` para reentrega. |
| `_serializavel` | **Função de Módulo** | [`consumer.py`](../apps/basica/worker/src/argus_worker/consumer.py) | `tests/test_extract.py` | Normalização para serialização em quarentena: detecta se o objeto possui método `model_dump` (Pydantic) e converte em dicionário ou preserva objetos nativos. |
| `ChangeEvent` | **Classe** (modelo Pydantic) | [`changes.py`](../apps/basica/worker/src/argus_worker/changes.py) | `tests/test_changes.py` | Validação de esquemas de CDC: `_tabela_conhecida` (método validador de classe que barra tabelas fora da allowlist fechada), `_para_utc` (normalização forçada de datas para UTC), e `_pk_nao_vazia` (rejeição de chaves primárias vazias). |
| `parse_change` | **Função de Módulo** | [`changes.py`](../apps/basica/worker/src/argus_worker/changes.py) | `tests/test_changes.py` | Regra de coerência operacional: se a operação for inserção (`i`), atualização (`u`) ou leitura (`r`), valida a presença obrigatória do campo `after`; se for deleção (`d`), permite ausência de `after`. |
| `check_size` | **Função de Módulo** | [`repository.py`](../apps/basica/worker/src/argus_worker/repository.py) | `tests/test_check_size.py` | Validação de guarda de capacidade: calcula tamanho em bytes do payload serializado e levanta `ChangeTooLarge` se ultrapassar `MAX_CHANGE_BYTES` (4.000.000 bytes / 4 MB). |
| `_env_int` | **Função de Módulo** | [`config.py`](../apps/basica/worker/src/argus_worker/config.py) | `tests/test_config.py` | Conversão e fallback de inteiros a partir de variáveis de ambiente, levantando `ValueError` com mensagem amigável em caso de valor não numérico. |
| `Config.from_env` | **Método de Classe** (na classe `Config`) | [`config.py`](../apps/basica/worker/src/argus_worker/config.py) | `tests/test_config.py` | Carregamento condicional por modo (`merge` vs `event`), validação de variáveis de ambiente obrigatórias, mapeamento de prefixos de fila (`CHANGES_` vs `EVENTS_`) e clamping do `batch_size` ao teto duro do SQS (`SQS_MAX_MESSAGES = 10`). |

### 2.3. Processamento & Detecção (`apps/basica/processing/`)

| Unidade Testada | Tipo no Código | Arquivo Fonte de Origem | Arquivo de Teste | Lógica Interna Testada |
|---|---|---|---|---|
| `_transform` | **Função de Módulo** | [`detector.py`](../apps/basica/processing/src/argus_processing/detector.py) | `tests/test_detector_logic.py` | Transformação de espaço métrico: aplica `math.log1p(max(value, 0.0))` para comprimir cauda longa em métricas com política `log1p` (prevenindo z-scores falsos em latência) e identidade para as demais. |
| `_inverse` | **Função de Módulo** | [`detector.py`](../apps/basica/processing/src/argus_processing/detector.py) | `tests/test_detector_logic.py` | Reversão matemática de `log1p` usando `math.expm1` para retornar valores esperados à unidade nativa exibida ao operador. |
| `_material` | **Função de Módulo** | [`detector.py`](../apps/basica/processing/src/argus_processing/detector.py) | `tests/test_detector_logic.py` | Filtro de relevância operacional que exige **simultaneamente** desvio absoluto (`|obs - exp| >= abs`) e desvio relativo (`|obs - exp| / exp >= rel`), com proteção contra divisão por zero (`1e-12`). |
| `_bad_direction` | **Função de Módulo** | [`detector.py`](../apps/basica/processing/src/argus_processing/detector.py) | `tests/test_detector_logic.py` | Filtragem direcional de desvios prejudiciais: distingue se anomalia é para cima (`up`), para baixo (`down`) ou bidirecional (`two_sided`), descartando melhorias operacionais. |
| `_clamp` | **Função de Módulo** | [`quality.py`](../apps/basica/processing/src/argus_processing/quality.py) | `tests/test_detector_logic.py` | Limitação de valores numéricos de razões estatísticas ao intervalo fechado `[0.0, 1.0]`. |
| `score_features` | **Função de Módulo** | [`scoring.py`](../apps/basica/processing/src/argus_processing/scoring.py) | `tests/test_detector_logic.py` | Cálculo do score ponderado de hipóteses (pesos A:0.25, T:0.20, C:0.20, E:0.15, I:0.15, Q:0.05), penalização por contradição (`-30 * contradiction`), cálculo de cobertura e determinação da confiança (`high`, `medium`, `low`). |

### 2.4. Backend (`apps/basica/backend/`)

| Unidade Testada | Tipo no Código | Arquivo Fonte de Origem | Arquivo de Teste | Lógica Interna Testada |
|---|---|---|---|---|
| `summarize` | **Função de Módulo** | [`use_cases.py`](../apps/basica/backend/src/telemetry/application/use_cases.py) | `tests/unit/test_use_cases_logic.py` | Agregação estatística de eventos de uma sessão: calcula `event_count`, contagem por tipo em `by_event_name`, `error_count`, datas de início e fim, duração em segundos e metadados de aparelho/app. |
| `shift_window_back` | **Função de Módulo** | [`use_cases.py`](../apps/basica/backend/src/telemetry/application/use_cases.py) | `tests/unit/test_use_cases_logic.py` | Cálculo de deslocamento de janela temporal para comparação entre períodos (RF14). Valida se `occurred_from` e `occurred_to` existem e se `span > 0`, deslocando os limites para trás com precisão de microssegundos. |
| `replace_window` | **Função de Módulo** | [`use_cases.py`](../apps/basica/backend/src/telemetry/application/use_cases.py) | `tests/unit/test_use_cases_logic.py` | Clonagem de slots de `EventFilters` atualizando unicamente as datas de início e fim sem alterar os demais filtros de sessão, aparelho ou app. |
| `_encode_cursor` / `_decode_cursor` | **Funções de Módulo** | [`hypotheses.py`](../apps/basica/backend/src/telemetry/infrastructure/hypotheses.py) | `tests/unit/test_use_cases_logic.py` | Serialização e desserialização de cursores opacos de paginação keyset em Base64 URL-safe, com remoção e recomposição de padding (`=`) e tratamento resiliente de erros com `ValueError('cursor invalido')`. |
| `_token_do_cabecalho` | **Função de Módulo** | [`auth.py`](../apps/basica/backend/src/telemetry/interfaces/auth.py) | `tests/unit/test_use_cases_logic.py` | Extração do token Bearer com inspeção case-insensitive de prefixo `bearer `, rejeição de esquemas estranhos (ex: `Basic`), tokens vazios e strings nulas. |
| `rota_publica` | **Função de Módulo** | [`auth.py`](../apps/basica/backend/src/telemetry/interfaces/auth.py) | `tests/unit/test_use_cases_logic.py` | Regra de liberação de rotas públicas (`/health/live`, `/health/ready`, `/docs`, `/openapi.json`, `/favicon.ico`) vs rotas protegidas que exigem token (`/api/v1/events`, etc.). |

---

## 3. Tabela Consolidada de Casos de Teste Unitários

| ID | Unidade testada | Tipo no Código | Tipo de Caso | Entrada | Resultado Esperado | Situação |
|---|---|---|---|---|---|---|
| **TU-01 a TU-30** | `redaction`, `normalization`, `timeline`, `signals` | Módulos do backend | Válidos / Limites | Payloads e query params variados | Sanitização, parsing, amostragem e z-score | ✅ Aprovado |
| **TU-31** | `Falha.alcanca` | Método de Classe | Válido | `ts` dentro da janela com target exato | Retorna `True` | ✅ Aprovado |
| **TU-32** | `Falha.alcanca` | Método de Classe | Limite | `ts == ts_start` (inclusivo) e `ts == ts_end` (exclusivo) | `True` no início e `False` no fim | ✅ Aprovado |
| **TU-33** | `Falha.alcanca` | Método de Classe | Limite | Target sem campos `entity`/`metric` (coringas) | Retorna `True` para qualquer entidade/métrica | ✅ Aprovado |
| **TU-34** | `Falha.alcanca` | Método de Classe | Erro previsto | `ts` anterior ou posterior à janela da falha | Retorna `False` | ✅ Aprovado |
| **TU-35** | `Falha.aplicar` | Método de Classe | Válido | `valor = 10.0`, multiplicador = `4.5` | Retorna `45.0` | ✅ Aprovado |
| **TU-36** | `Falha.aplicar` | Método de Classe | Regra especial | Tipo `source_outage` com `valor = 150.0` | Retorna `None` (simula ausência de dado) | ✅ Aprovado |
| **TU-37** | `Falha.aplicar` | Método de Classe | Limite | `valor = None` | Retorna `None` | ✅ Aprovado |
| **TU-38** | `sortear` | Função | Determinismo | Mesma `seed=42`, `t0`, `t1` e `fontes` executado 2 vezes | Retorna exatamente as mesmas falhas | ✅ Aprovado |
| **TU-39** | `sortear` | Função | Ordenação | 10 falhas sorteadas aleatoriamente | Lista estritamente ordenada por `ts_start` | ✅ Aprovado |
| **TU-40** | `_params` | Função | Limites | Tipo `error_spike`, `latency`, `drift` | Multiplicadores dentro das faixas [3.0, 12.0], [1.15, 1.6], [0.7, 0.9] | ✅ Aprovado |
| **TU-41** | `_blocos` | Função | Limite de Quantidade | 1050 itens | Fatiamento em blocos de 500, 500 e 50 itens | ✅ Aprovado |
| **TU-42** | `_blocos` | Função | Limite de Bytes | 10 itens de 10 KB (> 48 KB total) | Divisão em múltiplos blocos respeitando 48 KB | ✅ Aprovado |
| **TU-43** | `_blocos` | Função | Caso Especial | Item individual com 53 KB (> teto) | Bloco isolado contendo o item, sem descarte | ✅ Aprovado |
| **TU-44** | `_extract` | Função | Válido | Objeto único `{"event_name": "x"}` | Extraído como lista `[{"event_name": "x"}]` | ✅ Aprovado |
| **TU-45** | `_extract` | Função | Válido | Envelope `{"changes": [...]}` | Lista interna extraída diretamente | ✅ Aprovado |
| **TU-46** | `_extract` | Função | Erro previsto | String vazia ou espaços em branco | Levanta `ValueError("corpo da mensagem vazio")` | ✅ Aprovado |
| **TU-47** | `_extract` | Função | Erro previsto | JSON inválido ou tipo primitivo numérico | Levanta `ValueError` | ✅ Aprovado |
| **TU-48** | `_registro_recusado` | Função | Regra de Negócio | `IntegrityError` e `DataError` | Retorna `True` (direciona para DLQ) | ✅ Aprovado |
| **TU-49** | `_registro_recusado` | Função | Regra de Negócio | `OperationalError` e `ProgrammingError` | Retorna `False` (mantém na fila para reentrega) | ✅ Aprovado |
| **TU-50** | `ChangeEvent` | Classe | Validação | Tabela inexistente `tabela_xpto` | Levanta `ValidationError("tabela desconhecida")` | ✅ Aprovado |
| **TU-51** | `ChangeEvent` | Classe | Validação | Timestamp sem fuso horário | Convertido para UTC automaticamente | ✅ Aprovado |
| **TU-52** | `ChangeEvent` | Classe | Validação | Chave primária vazia `pk={}` | Levanta `ValidationError("pk vazia")` | ✅ Aprovado |
| **TU-53** | `parse_change` | Função | Coerência | Operação `u` sem campo `after` | Levanta `ValueError("op='u' exige after")` | ✅ Aprovado |
| **TU-54** | `parse_change` | Função | Coerência | Operação `d` sem campo `after` | Aceita sem erro | ✅ Aprovado |
| **TU-55** | `check_size` | Função | Limite de Guarda | Payload serializado > 4.000.000 bytes | Levanta `ChangeTooLarge` | ✅ Aprovado |
| **TU-56** | `_env_int` | Função | Válido / Erro | String `"123"` vs `"texto"` | Retorna `123` e levanta `ValueError` | ✅ Aprovado |
| **TU-57** | `Config.from_env` | Método de Classe | Validação | Modo desconhecido `"invalido"` | Levanta `ValueError` | ✅ Aprovado |
| **TU-58** | `Config.from_env` | Método de Classe | Limite | Variável `SQS_BATCH_SIZE=50` | `batch_size` limitado ao teto 10 | ✅ Aprovado |
| **TU-59** | `_transform` / `_inverse` | Funções | Transformação | Política `log1p` vs `identity` | Compressão log1p e reversão expm1 simétricas | ✅ Aprovado |
| **TU-60** | `_material` | Função | Materialidade Dupla | Delta absoluto e relativo simultâneos | `True` apenas quando atende ambos | ✅ Aprovado |
| **TU-61** | `_bad_direction` | Função | Direcionalidade | Direção `up`, `down` e `two_sided` | Descarte de desvios que representam melhoria | ✅ Aprovado |
| **TU-62** | `score_features` | Função | Ponderação | Features completas sem contradição | `score=100.0`, `confidence="high"` | ✅ Aprovado |
| **TU-63** | `score_features` | Função | Penalidade | Contradição = 0.5 | Reduz 15 pontos do score base | ✅ Aprovado |
| **TU-64** | `summarize` | Função | Agregação | Sessão com 3 eventos (1 erro) | Resumo com totais, datas e contagem por tipo | ✅ Aprovado |
| **TU-65** | `shift_window_back` | Função | Cálculo Temporal | Janela de 2h (10h às 12h) | Recua para período anterior (08h às 10h) | ✅ Aprovado |
| **TU-66** | `_encode_cursor` / `_decode` | Funções | Keyset Paging | Tupla `[score, start, id]` | Codificação Base64 URL-safe e decodificação exata | ✅ Aprovado |
| **TU-67** | `_token_do_cabecalho` | Função | Segurança | `"Bearer tok1"`, `"bearer tok2"`, `"Basic ..."` | Extração correta nos dois primeiros e `None` no último | ✅ Aprovado |
| **TU-68** | `rota_publica` | Função | Autorização | `/health/live`, `/docs` vs `/api/v1/events` | `True` para públicas e `False` para protegidas | ✅ Aprovado |

---

## 4. Como Executar os Testes Unitários

Todos os testes unitários podem ser disparados tanto localmente quanto nos pipelines de integração contínua (CI):

```bash
# Executar todos os testes unitários do backend
cd apps/basica/backend && uv run pytest tests/unit -v

# Executar testes unitários do simulador
cd apps/basica/simulator && uv run pytest tests/test_faults.py tests/test_emitter.py -v

# Executar testes unitários do worker de ingestão
cd apps/basica/worker && uv run pytest tests/test_extract.py tests/test_changes.py tests/test_check_size.py tests/test_config.py -v

# Executar testes unitários de detecção e scoring do processamento
cd apps/basica/processing && uv run pytest tests/test_detector_logic.py -v

# Executar o portão de testes unitários através do Makefile
make -C apps/basica test-simulator test-worker test-processing
```
