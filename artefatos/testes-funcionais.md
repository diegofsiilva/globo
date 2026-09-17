# Testes Funcionais

## Testes unitários

### Informações gerais

| Item | Valor |
|---|---|
| **Ferramenta** | pytest 8.4.2 (Python 3.12.3) |
| **Comando de execução** | `cd apps/basica/backend && .venv/bin/python -m pytest tests/unit -v` |
| **Localização dos testes** | `apps/basica/backend/tests/unit/` |
| **Quantidade de testes** | 52 |
| **Resultado final** | ✅ **52 passed** — 0 failed — 0 errors |
| **Tempo de execução** | 0.04 s |
| **Evidência** | [`artefatos/evidencias/testes-unitarios.txt`](evidencias/testes-unitarios.txt) |

### Arquivos de teste

| Arquivo | Módulo testado | Testes |
|---|---|---|
| `tests/unit/test_redaction.py` | `telemetry.application.redaction` | 15 |
| `tests/unit/test_normalization.py` | `telemetry.application.normalization` | 20 |
| `tests/unit/test_timeline.py` | `telemetry.application.timeline` | 6 |
| `tests/unit/test_signals.py` | `telemetry.application.signals` | 11 |

### Isolamento

Todos os testes são **puramente unitários**:

- Nenhuma dependência de banco de dados, AWS, rede ou API externa.
- A classe `GenerateSignals` (que depende de um repositório) foi isolada com um **stub** (`_FakeSignalsRepository`).
- Execução completa em **< 0.1 s**.

### Tabela de casos de teste

| ID | Unidade testada | Tipo | Entrada | Resultado esperado | Resultado obtido | Situação |
|---|---|---|---|---|---|---|
| TU-01 | `redaction.hash_user_id` | Válido | `"usuario-123"`, salt `"meu-salt-secreto"` | Hash SHA-256 truncado em 32 hex chars, determinístico | Hash correto de 32 chars | ✅ Aprovado |
| TU-02 | `redaction.hash_user_id` | Erro | `None`, `""`, `"***"` | `None` para todas as entradas | `None` retornado | ✅ Aprovado |
| TU-03 | `redaction.sanitize_url` | Válido | URL com `token=abc123&page=2&sort=asc` | `token` removido, `page` e `sort` preservados | URL sanitizada corretamente | ✅ Aprovado |
| TU-04 | `redaction.sanitize_url` | Erro | `None`, `""` | `None` | `None` retornado | ✅ Aprovado |
| TU-05 | `redaction.redact_headers` | Válido | Dict com Content-Type, Authorization, Cookie | Apenas Content-Type e X-Client-Version sobrevivem | Filtragem correta | ✅ Aprovado |
| TU-06 | `redaction.redact_headers` | Erro | `"string"`, `None`, `42` | `{}` sem exceção | `{}` retornado | ✅ Aprovado |
| TU-07 | `redaction.redact_attributes` | Válido | Dict com `authorization`, `response_headers`, `request_url` com token | Campos bloqueados removidos, URL sanitizada | Redação aplicada corretamente | ✅ Aprovado |
| TU-08 | `normalization.parse_datetime` | Válido | `"2026-07-13T10:30:00Z"` | datetime UTC com year=2026, month=7, hour=10 | datetime correto em UTC | ✅ Aprovado |
| TU-09 | `normalization.parse_datetime` | Erro | `None` | `ValidationError` com "obrigatorio" | Exceção levantada | ✅ Aprovado |
| TU-10 | `normalization.parse_datetime` | Erro | `"nao-e-uma-data"` | `ValidationError` com "invalido" | Exceção levantada | ✅ Aprovado |
| TU-11 | `normalization.parse_json_object` | Válido | `'{"key": "value"}'` | `{"key": "value"}` | Dict parseado | ✅ Aprovado |
| TU-12 | `normalization.parse_json_object` | Erro | `"{invalido"` | `ValidationError` com "JSON valido" | Exceção levantada | ✅ Aprovado |
| TU-13 | `normalization.parse_json_object` | Erro | `"[1, 2, 3]"` | `ValidationError` com "objeto JSON" | Exceção levantada | ✅ Aprovado |
| TU-14 | `normalization.optional_float` | Válido | `"3.14"` | `3.14` (float) | `3.14` retornado | ✅ Aprovado |
| TU-15 | `normalization.optional_float` | Erro | `"abc"` | `ValidationError` com "numerico" | Exceção levantada | ✅ Aprovado |
| TU-16 | `normalization.optional_int` | Válido | `"2024"` | `2024` (int) | `2024` retornado | ✅ Aprovado |
| TU-17 | `normalization.optional_int` | Erro | `"3.14"` | `ValidationError` com "inteiro" | Exceção levantada | ✅ Aprovado |
| TU-18 | `normalization.canonicalize_keys` | Válido | `{"Event Name": "request"}` | `{"event_name": "request"}` | Chave mapeada | ✅ Aprovado |
| TU-19 | `normalization.parse_event_id` | Válido | `None` | UUID v4 gerado | Instância de UUID | ✅ Aprovado |
| TU-20 | `normalization.parse_event_id` | Erro | `"nao-e-uuid"` | `ValidationError` com "UUID" | Exceção levantada | ✅ Aprovado |
| TU-21 | `timeline.amostrar_raia` | Válido | 50 pontos, limite=100 | Lista intacta, `truncated=False` | Sem redução | ✅ Aprovado |
| TU-22 | `timeline.amostrar_raia` | Válido | 500 pontos, limite=10 | ≤10 pontos com bordas preservadas | Bordas presentes | ✅ Aprovado |
| TU-23 | `timeline.amostrar_raia` | Erro previsto | 200 pontos, limite=50 | Sem duplicatas na amostra | Zero duplicatas | ✅ Aprovado |
| TU-24 | `timeline.amostrar_raia` | Limite | `[]`, limite=100 | `([], False)` | Lista vazia | ✅ Aprovado |
| TU-25 | `signals._severidade` | Válido | `4.0`, `2.5`, `2.0` | `critical`, `warning`, `stable` | Classificação correta | ✅ Aprovado |
| TU-26 | `signals._severidade` | Limite | `2.49`, `2.5`, `3.99`, `4.0` | `stable→warning→warning→critical` | Transições exatas | ✅ Aprovado |
| TU-27 | `signals._signal_id` | Válido | Tripla `("pop-sp", "app-video", "p95_latency")` | ID de 16 hex chars, determinístico | ID estável | ✅ Aprovado |
| TU-28 | `signals.GenerateSignals.execute` | Válido | 2 buckets com z=3.0, value=120, media=50 | 1 sinal, severity=warning, multiplier=2.4 | Sinal montado | ✅ Aprovado |
| TU-29 | `signals.GenerateSignals.execute` | Erro previsto | Último bucket com z=1.5 (< limiar 2.0) | 0 sinais, items=[] | Sinal filtrado | ✅ Aprovado |
| TU-30 | `signals.GenerateSignals.execute` | Válido | 5 sinais, limite=2 | count=2, truncated=True, ordenado por |z| desc | Truncamento com ranking | ✅ Aprovado |

> **Nota:** A tabela acima resume os 30 cenários principais. Os 52 testes completos incluem subcasos adicionais dentro de cada grupo (ex: salts diferentes, formato americano de data, threshold_value calculado, etc.). A evidência completa está em [`testes-unitarios.txt`](evidencias/testes-unitarios.txt).

---

## Testes de integração

### O que este bloco verifica

&emsp; Os testes unitários da seção anterior olham para uma função de cada vez, com
tudo em volta substituído por um **dublê** — um objeto falso que responde o que o
teste mandar. Eles respondem "esta unidade calcula certo?".

&emsp; Os testes desta seção respondem outra pergunta: **"estas duas camadas
conversam?"**. Cada um exercita um caminho real entre componentes que rodam em
processos, linguagens ou tecnologias diferentes, sem dublê no meio do trecho sob
teste. É por isso que eles encontram uma classe de defeito que nenhum teste
unitário alcança: o campo que a origem chama de um jeito e o destino lê de outro,
o filtro que a tela mostra mas nunca envia, o número que o banco agrega e a
interface arredonda errado.

&emsp; Foram planejados, implementados e executados **quatro testes de integração**,
somando **onze casos**, cobrindo os quatro pares de camadas do Argus:

| ID | Camadas que o teste atravessa | Casos | Situação |
|---|---|---:|---|
| **TI-01** | Frontend (dashboard Next.js) ↔ Backend (API Flask) ↔ PostgreSQL | 3 | ✅ Aprovado |
| **TI-02** | Aplicação (rota Flask → caso de uso → adaptador) ↔ PostgreSQL | 3 | ✅ Aprovado |
| **TI-03** | Módulos internos: worker de ingestão ↔ fila SQS ↔ PostgreSQL | 2 | ✅ Aprovado |
| **TI-04** | Módulos internos: ETL bronze → silver → gold ↔ PostgreSQL | 3 | ✅ Aprovado |

&emsp; **Resultado consolidado: 11 casos executados, 11 aprovados, 0 reprovados.**
A execução completa está registrada em
[`evidencias/testes-integracao.txt`](evidencias/testes-integracao.txt).

### Componentes envolvidos e resultado esperado da interação

&emsp; A tabela abaixo identifica, para cada teste, quem conversa com quem, por qual
mecanismo, e o que se espera dessa conversa. O "resultado esperado da interação" é
sempre uma afirmação sobre a **travessia** — não sobre o comportamento interno de
nenhuma das pontas.

| ID | Componente de origem | Componente de destino | Mecanismo de comunicação | Resultado esperado da interação |
|---|---|---|---|---|
| TI-01 | Dashboard Next.js estático (navegador Chromium) | API Flask de leitura | HTTP/JSON, com token de acesso na sessão do navegador | O filtro escolhido na tela aparece na *query string* enviada; e a tabela desenhada contém exatamente as linhas do JSON recebido |
| TI-01 | API Flask de leitura | PostgreSQL | Conexão TCP, SQL sobre as tabelas `gold.feature_bucket` e `silver.session_event` | O recorte pedido é aplicado no banco (SQL), e não no cliente: mudar o filtro muda o conjunto que volta |
| TI-02 | Rota Flask (`interfaces`) → caso de uso (`application`) → adaptador `PostgresEventRepository` (`infrastructure`) | PostgreSQL (`silver.session_event`) | Chamada de método através da porta de repositório; SQL parametrizado | A linha gravada no banco reaparece na resposta HTTP campo a campo, e o identificador do usuário é substituído pelo *hash* na travessia |
| TI-03 | Fila SQS `argus-events` | `EventConsumer` → `EventRepository` → PostgreSQL (`bronze.event`) | Mensagem JSON na fila; `INSERT ... ON CONFLICT` no banco | Mensagem válida vira linha; mensagem inválida vai para a fila de descarte sem travar a válida; reentrega da mesma mensagem não duplica a linha |
| TI-04 | `bronze.change_log` → função SQL `bronze.merge_todas()` | Módulo `argus_processing.etl` → `silver.signal_bucket` → `gold.feature_bucket` | Chamadas de função SQL e marcadores de progresso (`etl.watermark_*`) | O mesmo valor atravessa as três camadas sem se deformar; cada marcador avança na medida exata do que foi processado; ciclo ocioso não reprocessa |

### Vocabulário usado nesta seção

&emsp; Três termos aparecem com frequência e não são óbvios fora do projeto:

- **Fila de descarte (DLQ, *dead-letter queue*).** Fila separada para onde vai a
  mensagem que o consumidor não conseguiu processar. Serve para que um dado ruim
  saia de circulação registrado — com o motivo da recusa anexado — em vez de ser
  reentregue para sempre ou descartado em silêncio.
- **Entrega ao menos uma vez (*at-least-once*).** Garantia do SQS: a fila promete
  que a mensagem chega, mas não promete que chega **uma só vez**. Se a confirmação
  de processamento se perder, a mesma mensagem é entregue de novo. Cabe ao destino
  ser *idempotente* — processar duas vezes e produzir o mesmo resultado de uma.
- **Marcador de progresso (*watermark*).** Linha no banco que registra até onde uma
  etapa da ETL já processou. É o que torna o processamento incremental: cada
  execução lê só o que entrou depois do marcador e o avança ao terminar.
- **Camadas bronze, silver e gold.** Organização em três estágios: `bronze` guarda
  o dado bruto como chegou, `silver` o dado normalizado no esquema comum, e `gold`
  o dado agregado e pronto para as consultas do dashboard.

### Ambiente de execução

| Item | Valor |
|---|---|
| **Data da execução** | 17/09/2026 |
| **Sistema** | Linux 7.0.0-31-generic, x86_64 |
| **Banco de dados** | PostgreSQL 16.14 em contêiner Docker (`argus-pg`), porta 55432, base `argus_test` |
| **Ferramentas** | pytest 8.4.2 (backend, Python 3.13) · pytest 9.1.1 (worker, Python 3.12; processing, Python 3.13) · Playwright 1.62.1 com Chromium 151.0.7922.34 |
| **Dublês usados** | Apenas o SQS, dublado em memória com `moto` ≥ 5.0 (TI-03). Banco, API, navegador e site são reais em todos os testes |

&emsp; A escolha de rodar contra um **PostgreSQL de verdade**, e não contra um dublê,
é uma regra do projeto registrada em [`apps/basica/AGENTS.md`](../apps/basica/AGENTS.md):
a parte difícil deste sistema mora no SQL, e um dublê que respondesse "ok" a tudo
testaria apenas o dublê. Quando o banco não está no ar, as suítes que dependem dele
são **puladas**, e não quebradas — o portão de qualidade continua válido numa máquina
sem Docker.

### Localização no repositório

| Caminho | Papel |
|---|---|
| [`apps/basica/frontend/tests/e2e/integracao-camadas.spec.ts`](../apps/basica/frontend/tests/e2e/integracao-camadas.spec.ts) | Código do TI-01 |
| [`apps/basica/frontend/tests/e2e/fixture.sql`](../apps/basica/frontend/tests/e2e/fixture.sql) | Dados de entrada do TI-01, carregados no PostgreSQL |
| [`apps/basica/frontend/playwright.config.ts`](../apps/basica/frontend/playwright.config.ts) | Sobe o Flask e o site estático que o TI-01 usa |
| [`apps/basica/backend/tests/integration/test_api_postgres.py`](../apps/basica/backend/tests/integration/test_api_postgres.py) | Código do TI-02 |
| [`apps/basica/backend/tests/conftest.py`](../apps/basica/backend/tests/conftest.py) | Fixtures do TI-02: banco migrado, relógio virtual congelado, aplicação Flask |
| [`apps/basica/worker/tests/integration/test_fila_banco.py`](../apps/basica/worker/tests/integration/test_fila_banco.py) | Código do TI-03 |
| [`apps/basica/worker/tests/conftest.py`](../apps/basica/worker/tests/conftest.py) | Fixtures do TI-03: filas SQS em memória e os dois consumidores |
| [`apps/basica/worker/tests/fixtures/*.json`](../apps/basica/worker/tests/fixtures/) | Dados de entrada do TI-03: os seis eventos reais exportados do BI |
| [`apps/basica/processing/tests/integration/test_camadas_medalhao.py`](../apps/basica/processing/tests/integration/test_camadas_medalhao.py) | Código do TI-04 |
| [`apps/basica/processing/tests/conftest.py`](../apps/basica/processing/tests/conftest.py) | Fixtures do TI-04: banco limpo, marcadores reiniciados, relógio virtual |
| [`apps/basica/Makefile`](../apps/basica/Makefile) | Alvos `db-local`, `test-backend`, `test-worker`, `test-processing` e `test-frontend-e2e` |
| [`apps/basica/db/migrations/`](../apps/basica/db/migrations/) | As 29 migrations aplicadas antes de qualquer teste |
| [`evidencias/testes-integracao.txt`](evidencias/testes-integracao.txt) | Saída bruta da execução dos quatro testes |

### Pré-condição comum

&emsp; Todos os testes exigem o PostgreSQL local no ar, com as migrations aplicadas:

```bash
make -C apps/basica db-local
```

&emsp; O comando sobe o contêiner `argus-pg` na porta 55432 (e não na 5432, para não
conflitar com um PostgreSQL já instalado na máquina), cria a base `argus_test` e
aplica as 29 migrations.

---

### TI-01 — Dashboard ↔ API de leitura ↔ PostgreSQL

| Campo | Conteúdo |
|---|---|
| **Identificador** | TI-01 |
| **Objetivo** | Verificar que o dashboard e a API de leitura cumprem o contrato nos dois sentidos: que a escolha do operador na tela chega ao backend como parâmetro de consulta, e que o que a tela desenha é exatamente o que o backend leu do banco |
| **Requisitos / caso de uso** | RF08 (pesquisa por atributos), RF09 (filtros cumulativos), RF11 (agrupamento por critérios), RNF02 (consulta simples em até 5 s), RNF09 (acesso apenas a autorizados). Caso de uso: o operador investiga onde um sinal se concentra, trocando agrupamento e filtro na tela Explorar |
| **Componentes envolvidos** | Navegador Chromium → site estático Next.js (127.0.0.1:3100) → HTTP → API Flask (127.0.0.1:5100) → PostgreSQL (`argus_test`) |
| **Pré-condições** | PostgreSQL no ar; migrations aplicadas; `fixture.sql` carregado; site construído com `NEXT_PUBLIC_API_URL` apontando para o Flask local; Chromium do Playwright instalado |
| **Dados de entrada** | [`fixture.sql`](../apps/basica/frontend/tests/e2e/fixture.sql): 21 linhas em `gold.feature_bucket` (fontes `prometheus`, `youbora_device`, `npaw`, `newrelic`, `apollo`) e 3 eventos de sessão em `silver.session_event`. O relógio da simulação é congelado em 2026-07-14T12:00Z para que o resultado não dependa da data em que o teste roda |
| **Procedimento de execução** | `make -C apps/basica test-frontend-e2e` — o alvo recarrega o `fixture.sql`, constrói o site estático, sobe o Flask e o servidor do site, e executa o Playwright |
| **Situação** | ✅ **Aprovado** — 3 de 3 casos |
| **Evidência** | [`evidencias/testes-integracao.txt`](evidencias/testes-integracao.txt), bloco TI-01 |

| Caso | Entrada | Resultado esperado | Resultado obtido | Situação |
|---|---|---|---|---|
| **TI-01.1** | Abrir `/explorar/` com sessão aberta; agrupamento padrão (dispositivo) | A requisição sai para a origem `http://127.0.0.1:5100` levando `dimension=entity` e `source=youbora_device`; o JSON traz grupos vindos do banco; a tabela exibe **exatamente** o mesmo conjunto de rótulos, e a linha de maior valor mostra o número agregado pelo SQL; tudo em menos de 5 s | Requisição confirmada na origem do Flask; grupos `LG webOS 3.x` e `Samsung Tizen`; 2 rótulos na tabela para 2 grupos no JSON, conjuntos idênticos; valor `1.737,7` renderizado na linha; resposta em 1,0 s | ✅ Aprovado |
| **TI-01.2** | Trocar o agrupamento para "Fonte" e depois aplicar o filtro de métrica `request_count` | Cada escolha vira parâmetro na *query string* (`dimension=source`, depois `dimension=source` **+** `metric=request_count`, cumulativos); o recorte é aplicado no banco: `npaw`, que só tem `bufferratio`, desaparece do resultado e da tabela | Ambas as requisições observadas com os parâmetros esperados; `npaw` presente no primeiro agrupamento e ausente após o filtro, tanto no JSON quanto na tabela; rótulos da tela iguais aos do JSON nos dois momentos | ✅ Aprovado |
| **TI-01.3** | Abrir `/explorar/` **sem** token na sessão (caso negativo) | Nenhuma requisição a `/api/v1/` sai do navegador; a tela de acesso é exibida; nenhuma linha de dado é desenhada | Lista de chamadas à API vazia; título "Acesso ao painel" visível; zero linhas na tabela | ✅ Aprovado |

&emsp; **Reprodução:**

```bash
make -C apps/basica db-local          # se o banco ainda não estiver no ar
make -C apps/basica test-frontend-e2e
```

&emsp; O alvo **pula sozinho**, sem falhar, se o PostgreSQL ou o Chromium do Playwright
não estiverem disponíveis. Para instalar o navegador:
`cd apps/basica/frontend && npx playwright install chromium`.

---

### TI-02 — Aplicação (Flask) ↔ PostgreSQL

| Campo | Conteúdo |
|---|---|
| **Identificador** | TI-02 |
| **Objetivo** | Verificar que um registro gravado no banco atravessa as quatro camadas da aplicação — rota HTTP, caso de uso, porta de repositório e adaptador SQL — e reaparece intacto na resposta, e que a travessia aplica a barreira de privacidade exigida pelo RNF10 |
| **Requisitos / caso de uso** | RF06 (armazenar para consulta posterior), RF08 (pesquisa por tipo e atributos), RF09 (filtros cumulativos), RNF10 (não expor dado pessoal desnecessário). Caso de uso: o operador busca eventos de erro de um sistema operacional específico |
| **Componentes envolvidos** | `telemetry.interfaces` (rota Flask) → `telemetry.application.use_cases` → `telemetry.ports` (porta de repositório) → `telemetry.infrastructure.postgres.PostgresEventRepository` → PostgreSQL (`silver.session_event`) |
| **Pré-condições** | PostgreSQL no ar com as migrations aplicadas; tabelas truncadas antes de cada caso; relógio da simulação congelado em 2026-07-14T12:00Z |
| **Dados de entrada** | Um evento `error` sintético (sessão `sessao-ti02`, dispositivo `device-ti02`, usuário `usuario-ti02`, sistema `NetRange`, fabricante `Philco`), gravado pelo **mesmo** código que o worker de ingestão usa em produção (`argus_worker.keys.build_row`) — o que impede que a API e o worker divirjam em silêncio sobre o formato da linha |
| **Procedimento de execução** | `cd apps/basica/backend && TEST_DATABASE_URL=... uv run pytest tests/integration -v` |
| **Situação** | ✅ **Aprovado** — 3 de 3 casos, em 4,64 s |
| **Evidência** | [`evidencias/testes-integracao.txt`](evidencias/testes-integracao.txt), bloco TI-02 |

| Caso | Entrada | Resultado esperado | Resultado obtido | Situação |
|---|---|---|---|---|
| **TI-02.1** | Evento gravado no banco; `GET /api/v1/events?event_name=error&device_os=NetRange&limit=10` | HTTP 200 com exatamente esse evento; cada campo da resposta igual ao que uma consulta SQL direta lê da tabela; o bloco `query` reporta o custo real (`scanned` ≥ `returned`) | 200 com 1 item; `event_name`, `session_id`, `device_id`, `app_bucket`, `device_os` e `route_path` idênticos à leitura SQL independente; `scanned` ≥ `returned` confirmado | ✅ Aprovado |
| **TI-02.2** | Mesmo evento; `GET /api/v1/events?session_id=sessao-ti02` | O banco guarda `usuario-ti02` em claro, mas a resposta HTTP **não** contém essa cadeia; traz `user_id_hash` com os 16 hexadecimais esperados para o salt de teste, e não traz a chave `user_id` | Identificador cru confirmado no banco; ausente do corpo da resposta; `user_id_hash` igual ao valor calculado de forma independente pelo teste; chave `user_id` ausente do item | ✅ Aprovado |
| **TI-02.3** | Evento no banco, mas filtro por um sistema operacional inexistente (caso negativo) | HTTP 200 com `items` vazio e `returned` = 0 — ausência de dado, e não falha. Um erro 500 aqui indicaria que as camadas só conversam no caminho feliz | 200 com lista vazia e `returned` = 0 | ✅ Aprovado |

&emsp; **Reprodução:**

```bash
make -C apps/basica db-local
cd apps/basica/backend
TEST_DATABASE_URL=postgresql://argus:argus@localhost:55432/argus_test \
  uv run pytest tests/integration -v
```

&emsp; O alvo `make -C apps/basica test-backend` executa esta suíte junto com as demais
do backend (175 testes no total).

---

### TI-03 — Worker de ingestão ↔ fila SQS ↔ PostgreSQL

| Campo | Conteúdo |
|---|---|
| **Identificador** | TI-03 |
| **Objetivo** | Verificar que uma mensagem postada na fila vira linha no banco; que uma mensagem inválida no mesmo lote não impede isso e termina na fila de descarte com o motivo registrado; e que a reentrega — inevitável, pela garantia de entrega ao menos uma vez do SQS — não duplica a linha já gravada |
| **Requisitos / caso de uso** | RF01 (ingestão por API única), RF04 (rejeição rastreável do inválido), RNF04 (evento inválido não impede os válidos seguintes), RNF05 (não perder silenciosamente o que já foi aceito). Caso de uso: um lote de eventos chega da borda contendo um payload malformado |
| **Componentes envolvidos** | Fila SQS `argus-events` → `argus_worker.consumer.EventConsumer` → `argus_worker.repository.EventRepository` → PostgreSQL (`bronze.event`); fila de descarte `argus-events-dlq` para o que for recusado |
| **Pré-condições** | PostgreSQL no ar com as migrations aplicadas; tabelas `bronze.*` truncadas; filas SQS criadas em memória pelo `moto`; credenciais AWS falsas injetadas, para garantir que nenhum teste alcance a nuvem real |
| **Dados de entrada** | Evento válido: a fixture `error.json`, exportada do BI do parceiro. Evento inválido: `{"event_name": "request"}` — sem `timestamp`, `session_id` nem `device_id`, exatamente o envelope mínimo que o RF04 manda recusar |
| **Procedimento de execução** | `cd apps/basica/worker && TEST_DATABASE_URL=... uv run pytest tests/integration -v` |
| **Situação** | ✅ **Aprovado** — 2 de 2 casos, em 2,57 s |
| **Evidência** | [`evidencias/testes-integracao.txt`](evidencias/testes-integracao.txt), bloco TI-03 |

| Caso | Entrada | Resultado esperado | Resultado obtido | Situação |
|---|---|---|---|---|
| **TI-03.1** | Duas mensagens na fila, na ordem **inválida → válida** (a ordem que mais machuca: se o consumidor abortasse o lote no erro, o evento válido seguinte nunca chegaria ao banco) | `bronze.event` com exatamente a linha do evento válido, com `event_name`, `session_id` e `device_id` iguais ao que entrou pela fila; a fila de descarte com exatamente uma mensagem, carregando o motivo da recusa; a fila de entrada drenada a zero, sem mensagem presa | 1 linha no banco, os três campos conferidos; 1 mensagem na fila de descarte com `FailureReason` preenchido; 0 mensagens restantes na fila de entrada | ✅ Aprovado |
| **TI-03.2** | O mesmo evento válido postado duas vezes, em ciclos separados — o que o SQS faz quando a confirmação de processamento não chega a tempo | Uma única linha em `bronze.event` depois das duas entregas, e nada na fila de descarte. A idempotência não é do consumidor nem do banco isolados: só existe na combinação dos dois | 1 linha após a primeira entrega, 1 linha após a segunda; fila de descarte vazia | ✅ Aprovado |

&emsp; **Reprodução:**

```bash
make -C apps/basica db-local
cd apps/basica/worker
TEST_DATABASE_URL=postgresql://argus:argus@localhost:55432/argus_test \
  uv run pytest tests/integration -v
```

&emsp; O alvo `make -C apps/basica test-worker` executa esta suíte junto com as demais
do worker (77 testes no total).

---

### TI-04 — ETL bronze → silver → gold ↔ PostgreSQL

| Campo | Conteúdo |
|---|---|
| **Identificador** | TI-04 |
| **Objetivo** | Verificar que um mesmo valor sobrevive às três camadas de armazenamento sem se perder nem se deformar, que cada etapa só avança seu marcador de progresso na medida do que realmente processou, e que rodar de novo sem dado novo não reprocessa |
| **Requisitos / caso de uso** | RF05 (converter os eventos para um esquema comum), RF06 (armazenar para consulta e análise posteriores). Caso de uso: o ciclo periódico da ETL promove o que chegou desde a última execução |
| **Componentes envolvidos** | `bronze.change_log` → função SQL `bronze.merge_todas()` → `argus_processing.etl.executar_bronze_silver` → `silver.signal_bucket` → `argus_processing.etl.executar_silver_gold` → `gold.feature_bucket`, com os marcadores `etl.watermark_bronze_silver` e `etl.watermark_silver_gold` |
| **Pré-condições** | PostgreSQL no ar com as migrations aplicadas; camadas `bronze`, `silver`, `gold` e `etl` truncadas; marcadores reiniciados para o estado semeado pela migration 015; relógio da simulação em 2026-07-12T12:00Z |
| **Dados de entrada** | Uma mudança em `bronze.change_log` descrevendo a inserção de um bucket de sinal: fonte `prometheus`, entidade `cdn-ti04`, métrica `p95_ms`, valor **412,5** — um número improvável de aparecer por acaso, para que encontrá-lo na camada gold prove que veio desta linha e não de outra |
| **Procedimento de execução** | `cd apps/basica/processing && TEST_DATABASE_URL=... uv run pytest tests/integration -v` |
| **Situação** | ✅ **Aprovado** — 3 de 3 casos, em 7,63 s |
| **Evidência** | [`evidencias/testes-integracao.txt`](evidencias/testes-integracao.txt), bloco TI-04 |

| Caso | Entrada | Resultado esperado | Resultado obtido | Situação |
|---|---|---|---|---|
| **TI-04.1** | A mudança bruta em `bronze.change_log`, seguida das duas etapas da ETL | O valor 412,5 aparece consolidado em `bronze.signal_bucket`, depois em `silver.signal_bucket` e depois em `gold.feature_bucket`, com `source`, `entity` e `metric` preservados em cada salto | Valor e atributos conferidos nas três camadas, um a um; a etapa bronze→silver reportou `status = sucesso` e leu até o `lsn` esperado | ✅ Aprovado |
| **TI-04.2** | A mesma mudança; inspeção dos dois marcadores antes e depois | O marcador bronze→silver passa a valer exatamente o `lsn` da última mudança lida — nem menos (reprocessaria) nem mais (pularia dado). O marcador silver→gold para uma margem de segurança atrás do fim da janela, deixando essa faixa reaberta para o ciclo seguinte, porque dado atrasado ainda pode chegar nela | Marcador bronze→silver avançou do valor anterior para exatamente o `lsn` da mudança; marcador silver→gold igual ao fim da janela menos a margem de segurança | ✅ Aprovado |
| **TI-04.3** | Um ciclo completo já executado e **nenhuma** mudança nova depois dele (caso negativo) | A segunda execução de bronze→silver responde `sem_pendencia` com 0 linhas, e a camada gold continua com uma única linha da entidade. Sem isso, um ciclo ocioso somaria o mesmo evento outra vez e o dashboard mostraria o dobro do que aconteceu | `status = sem_pendencia`, 0 linhas; 1 linha em `gold.feature_bucket` para a entidade | ✅ Aprovado |

&emsp; **Reprodução:**

```bash
make -C apps/basica db-local
cd apps/basica/processing
TEST_DATABASE_URL=postgresql://argus:argus@localhost:55432/argus_test \
  uv run pytest tests/integration -v
```

&emsp; O alvo `make -C apps/basica test-processing` executa esta suíte junto com as
demais do processamento (69 testes no total).

---

### Execução completa das suítes

&emsp; Para confirmar que os testes novos não quebraram nada, todas as suítes do
repositório foram executadas na mesma sessão:

| Suíte | Comando | Resultado |
|---|---|---|
| Worker de ingestão | `make -C apps/basica test-worker` | 77 aprovados em 24,95 s |
| Simulador | `make -C apps/basica test-simulator` | 2 aprovados em 0,01 s |
| Processamento (ETL) | `make -C apps/basica test-processing` | 69 aprovados em 98,94 s |
| API de leitura (unitários + integração + demais) | `make -C apps/basica test-backend` | 227 aprovados em 365,78 s |
| Autorizador | `make -C apps/basica test-authorizer` | 18 aprovados em 0,65 s |
| Frontend (contratos e componentes) | `make -C apps/basica test-frontend` | 24 aprovados em 3,92 s |
| Frontend integrado (Playwright) | `make -C apps/basica test-frontend-e2e` | 12 aprovados em 20,7 s |

&emsp; **Total: 429 testes aprovados, nenhum reprovado.** Os 227 do backend incluem
os 52 testes unitários da seção anterior e os 3 casos do TI-02.

&emsp; Uma observação de ambiente, registrada por honestidade de relatório: o alvo
`test-authorizer` interrompe a coleta com `NoRegionError` quando a variável
`AWS_REGION` não está definida no terminal. Não é defeito do código nem efeito dos
testes de integração — com `AWS_REGION=us-east-1` no ambiente, os 18 testes passam,
como registrado na tabela. O valor sai de `.env` na operação normal do projeto.
