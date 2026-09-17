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

### O que esta seção verifica

&emsp; Os testes unitários da seção anterior olham para uma função de cada vez, com
tudo em volta substituído por um dublê, isto é, um objeto falso que responde o que
o teste mandar. Eles respondem a uma pergunta estreita e importante: esta unidade
calcula certo?

&emsp; Os testes desta seção respondem a outra pergunta. Não é se cada peça está
correta, e sim se duas camadas diferentes conseguem conversar. Cada um deles
percorre um caminho real entre componentes que rodam em processos, linguagens ou
tecnologias distintas, sem nenhum dublê no trecho que está sob teste. É por isso
que encontram uma classe de defeito que nenhum teste unitário alcança, por melhor
que ele seja: o campo que a origem grava com um nome e o destino lê com outro, o
filtro que a tela mostra ao operador mas nunca chega a enviar, o número que o banco
agrega corretamente e a interface arredonda errado na hora de desenhar.

### Panorama dos cinco testes

&emsp; Foram planejados, implementados e executados cinco testes de integração,
somando treze casos. Os quatro primeiros cobrem pares de camadas que rodam na
máquina de desenvolvimento. O quinto exercita a pilha publicada na AWS, e é o único
com um caso reprovado.

| Teste | Camadas que ele atravessa | Casos | Situação |
|---|---|---:|---|
| TI-01 | Dashboard Next.js, API Flask de leitura e PostgreSQL | 3 | Aprovado |
| TI-02 | Rota Flask, caso de uso, adaptador de repositório e PostgreSQL | 3 | Aprovado |
| TI-03 | Worker de ingestão, fila SQS e PostgreSQL | 2 | Aprovado |
| TI-04 | ETL incremental entre as camadas bronze, silver e gold | 3 | Aprovado |
| TI-05 | Pilha publicada na AWS, da borda HTTP até a API de leitura | 2 | 1 aprovado, 1 reprovado |

&emsp; No total, treze casos implementados e executados, doze aprovados e um
reprovado. O reprovado é o TI-05.2, cuja causa raiz está identificada: o evento
chegou ao banco, mas a ETL não o promoveu para a camada consultável dentro do prazo
do teste. A reprovação foi mantida como está, investigada até o fim e transformada
em correção, em vez de contornada afrouxando o prazo. A execução completa, com a
saída bruta de cada suíte, está em
[`evidencias/testes-integracao.txt`](evidencias/testes-integracao.txt).

&emsp; Este relatório usa os mesmos três estados adotados em
[`testes-carga-inicial.md`](testes-carga-inicial.md), para que uma afirmação forte e
uma fraca não pareçam iguais a quem lê rápido. Um teste preparado é aquele cujo
cenário e automação existem no repositório. Um teste executado foi de fato rodado, e
sua saída está registrada na evidência. Um teste aprovado é o que, além de
executado, satisfez todos os critérios de aceite do caso.

### Componentes envolvidos e resultado esperado da interação

&emsp; Convém deixar claro o que conta como
resultado esperado aqui: é sempre uma afirmação sobre a travessia, sobre o que
acontece no caminho entre duas peças, e nunca sobre o comportamento interno de
nenhuma das pontas isoladamente. Isso último já é assunto dos testes unitários.

| Teste | Componente de origem | Componente de destino | Mecanismo de comunicação | Resultado esperado da interação |
|---|---|---|---|---|
| TI-01 | Dashboard Next.js estático, no navegador Chromium | API Flask de leitura | HTTP com JSON, token de acesso na sessão do navegador | O filtro escolhido na tela aparece na query string enviada, e a tabela desenhada contém exatamente as linhas do JSON recebido |
| TI-01 | API Flask de leitura | PostgreSQL | Conexão TCP e SQL sobre `gold.feature_bucket` e `silver.session_event` | O recorte é aplicado no banco, e não no cliente: trocar o filtro muda o conjunto que volta pela rede |
| TI-02 | Rota Flask, caso de uso e porta de repositório | Adaptador `PostgresEventRepository` e a tabela `silver.session_event` | Chamada de método pela porta, depois SQL parametrizado | A linha gravada reaparece campo a campo na resposta HTTP, e o identificador do usuário é trocado pelo hash na travessia |
| TI-03 | Fila SQS `argus-events` | `EventConsumer`, `EventRepository` e a tabela `bronze.event` | Mensagem JSON na fila, escrita com `INSERT ... ON CONFLICT` | Mensagem válida vira linha, a inválida sai pela fila de descarte sem travar a válida seguinte, e a reentrega não duplica |
| TI-04 | `bronze.change_log` e a função `bronze.merge_todas()` | Módulo `argus_processing.etl`, `silver.signal_bucket` e `gold.feature_bucket` | Funções SQL coordenadas pelos marcadores `etl.watermark_*` | O valor atravessa as três camadas sem se deformar, cada marcador avança na medida do que processou, e ciclo ocioso não reprocessa |
| TI-05 | Cliente HTTP externo | API Gateway e o Lambda authorizer das duas APIs publicadas | HTTPS com cabeçalho `Authorization: Bearer` | A borda recusa com 401 ou 403 a requisição sem token, com token desconhecido e com token da audiência errada, aceitando só o da própria audiência |
| TI-05 | Rota `POST /v1/events` no API Gateway | Fila SQS, event-worker no Fargate, RDS, ETL e a rota `GET /api/v1/events` | Integração direta entre API Gateway e SQS, sem Lambda no caminho de escrita | Um evento aceito na borda aparece na API de leitura dentro do prazo, com os campos preservados |

&emsp; A última linha merece um comentário, porque a espera nela não é defeito. A
ingestão é assíncrona por projeto: a borda enfileira e responde de imediato, e quem
grava é o worker. O que o teste afirma é que essa espera termina, e termina dentro
de um prazo que faça sentido para quem opera o sistema.

### Vocabulário usado nesta seção

&emsp; Alguns termos aparecem com frequência e não são óbvios para quem chega de fora
do projeto.

&emsp; **Fila de descarte, ou DLQ, de dead-letter queue**, é uma fila separada para onde
vai a mensagem que o consumidor não conseguiu processar. Ela existe para que um dado
ruim saia de circulação de forma registrada, com o motivo da recusa anexado, em vez
de ser reentregue indefinidamente ou descartado em silêncio.

&emsp; **Entrega ao menos uma vez, ou at-least-once**, é a garantia que o SQS oferece: a
fila promete que a mensagem chega, mas não promete que chega uma única vez. Se a
confirmação de processamento se perder no caminho, a mesma mensagem é entregue de
novo. Cabe ao destino ser idempotente, ou seja, produzir o mesmo resultado
processando duas vezes ou uma.

&emsp; **Marcador de progresso, ou watermark**, é uma linha no banco que registra até onde
uma etapa da ETL já processou. É o que torna o processamento incremental: cada
execução lê apenas o que entrou depois do marcador e o avança ao terminar. Cada linha
que entra na camada bronze recebe um número de ordem, o `lsn`, e é por ele que o
marcador se orienta.

&emsp; **Bronze, silver e gold** nomeiam os três estágios do armazenamento. A bronze
guarda o dado bruto como ele chegou, a silver guarda o dado normalizado no esquema
comum, e a gold guarda o dado agregado e pronto para as consultas do dashboard.

### Ambiente de execução

| Item | Valor |
|---|---|
| Data da execução | 17 de setembro de 2026 |
| Sistema | Linux 7.0.0-31-generic, x86_64 |
| Banco de dados | PostgreSQL 16.14 em contêiner Docker, o `argus-pg`, na porta 55432, base `argus_test` |
| Ferramentas | pytest 8.4.2 no backend com Python 3.13; pytest 9.1.1 no worker com Python 3.12 e no processamento com Python 3.13; Playwright 1.62.1 com Chromium 151.0.7922.34 |
| Dublês usados | Apenas o SQS, reproduzido em memória pelo `moto` versão 5 ou superior, no TI-03. Banco, API, navegador e site são reais em todos os testes |
| Ambiente do TI-05 | Pilha publicada no AWS Academy Learner Lab, região `us-east-1`: API Gateway HTTP, Lambda authorizer, Lambda da API de leitura, SQS, ECS Fargate e RDS PostgreSQL. Nenhum componente dublado |

### Onde está cada coisa no repositório

| Caminho | Papel |
|---|---|
| [`apps/basica/frontend/tests/e2e/integracao-camadas.spec.ts`](../apps/basica/frontend/tests/e2e/integracao-camadas.spec.ts) | Código do TI-01 |
| [`apps/basica/frontend/tests/e2e/fixture.sql`](../apps/basica/frontend/tests/e2e/fixture.sql) | Dados de entrada do TI-01, carregados no PostgreSQL |
| [`apps/basica/frontend/playwright.config.ts`](../apps/basica/frontend/playwright.config.ts) | Sobe o Flask e o site estático que o TI-01 usa |
| [`apps/basica/backend/tests/integration/test_api_postgres.py`](../apps/basica/backend/tests/integration/test_api_postgres.py) | Código do TI-02 |
| [`apps/basica/backend/tests/conftest.py`](../apps/basica/backend/tests/conftest.py) | Fixtures do TI-02: banco migrado, relógio virtual congelado e aplicação Flask |
| [`apps/basica/worker/tests/integration/test_fila_banco.py`](../apps/basica/worker/tests/integration/test_fila_banco.py) | Código do TI-03 |
| [`apps/basica/worker/tests/conftest.py`](../apps/basica/worker/tests/conftest.py) | Fixtures do TI-03: filas SQS em memória e os dois consumidores |
| [`apps/basica/worker/tests/fixtures/*.json`](../apps/basica/worker/tests/fixtures/) | Dados de entrada do TI-03: os seis eventos reais exportados do BI |
| [`apps/basica/processing/tests/integration/test_camadas_medalhao.py`](../apps/basica/processing/tests/integration/test_camadas_medalhao.py) | Código do TI-04 |
| [`apps/basica/processing/tests/conftest.py`](../apps/basica/processing/tests/conftest.py) | Fixtures do TI-04: banco limpo, marcadores reiniciados e relógio virtual |
| [`apps/basica/backend/tests/integration/test_implantacao.py`](../apps/basica/backend/tests/integration/test_implantacao.py) | Código do TI-05 |
| [`apps/basica/.env.example`](../apps/basica/.env.example) | Nomes das variáveis que o TI-05 lê do ambiente; URLs e tokens reais ficam no `.env`, que não é versionado |
| [`apps/basica/db/migrations/030_indice_lsn_em_evento.sql`](../apps/basica/db/migrations/030_indice_lsn_em_evento.sql) | Correção de schema nascida do diagnóstico do TI-05 |
| [`apps/basica/processing/tests/test_plano_da_etl.py`](../apps/basica/processing/tests/test_plano_da_etl.py) | Teste que sustenta essa correção |
| [`apps/basica/Makefile`](../apps/basica/Makefile) | Alvos `db-local`, `env`, `auth-show-ingest`, `test-backend`, `test-worker`, `test-processing` e `test-frontend-e2e` |
| [`evidencias/testes-integracao.txt`](evidencias/testes-integracao.txt) | Saída bruta da execução dos cinco testes |

### Pré-condição comum

&emsp; Os quatro testes locais exigem o PostgreSQL no ar, com as migrations aplicadas:

```bash
make -C apps/basica db-local
```

&emsp; O comando sobe o contêiner `argus-pg` na porta 55432, e não na 5432, para não
conflitar com um PostgreSQL já instalado na máquina; cria a base `argus_test`; e
aplica as 30 migrations em ordem.

### TI-01: dashboard, API de leitura e PostgreSQL

&emsp; Este teste verifica que o dashboard e a API cumprem o contrato nos dois
sentidos. Na ida, que a escolha do operador na tela chega ao backend como parâmetro
de consulta. Na volta, que o que a tela desenha é exatamente o que o backend leu do
banco. Os testes de contrato que já existiam em `tests/contracts/` cobrem a forma do
JSON contra um dublê; o que só este teste consegue mostrar é que essa forma é a
mesma que o backend real produz a partir do banco real.

&emsp; Uma decisão do cenário merece explicação. O relógio da simulação é congelado em
2026-07-14T12:00Z, e não deixado correndo. Sem isso, o resultado dependeria da data
em que o teste roda, e a suíte começaria a falhar sozinha semanas depois, sem
nenhuma mudança de código.

| Campo | Conteúdo |
|---|---|
| Identificador | TI-01 |
| Objetivo | Verificar o contrato nos dois sentidos entre o dashboard e a API de leitura, sobre dado real do banco |
| Requisitos | RF08, pesquisa por atributos; RF09, filtros cumulativos; RF11, agrupamento por critérios; RNF02, consulta simples em até cinco segundos; RNF09, acesso apenas a autorizados |
| Caso de uso | O operador investiga onde um sinal se concentra, trocando agrupamento e filtro na tela Explorar |
| Componentes envolvidos | Navegador Chromium, site estático Next.js em 127.0.0.1:3100, HTTP, API Flask em 127.0.0.1:5100 e PostgreSQL da base `argus_test` |
| Pré-condições | Banco no ar com migrations aplicadas e `fixture.sql` carregado; site construído com `NEXT_PUBLIC_API_URL` apontando para o Flask local; Chromium do Playwright instalado |
| Dados de entrada | [`fixture.sql`](../apps/basica/frontend/tests/e2e/fixture.sql): 21 linhas em `gold.feature_bucket` nas fontes `prometheus`, `youbora_device`, `npaw`, `newrelic` e `apollo`, mais 3 eventos de sessão em `silver.session_event` |
| Procedimento | `make -C apps/basica test-frontend-e2e`, que recarrega o `fixture.sql`, constrói o site, sobe o Flask e o servidor do site, e executa o Playwright |
| Situação | Aprovado nos 3 casos |
| Evidência | Bloco TI-01 de [`evidencias/testes-integracao.txt`](evidencias/testes-integracao.txt) |

| Caso | Entrada | Resultado esperado | Resultado obtido | Situação |
|---|---|---|---|---|
| TI-01.1 | Abrir `/explorar/` com sessão aberta, no agrupamento padrão por dispositivo | A requisição sai para a origem do Flask levando `dimension=entity` e `source=youbora_device`; a tabela exibe exatamente o mesmo conjunto de rótulos do JSON; a linha de maior valor mostra o número agregado pelo SQL; tudo em menos de 5 s | Requisição confirmada na origem do Flask; grupos `LG webOS 3.x` e `Samsung Tizen`; 2 rótulos na tabela para 2 grupos no JSON, conjuntos idênticos; valor 1.737,7 renderizado; resposta em 1,0 s | Aprovado |
| TI-01.2 | Trocar o agrupamento para Fonte e depois aplicar o filtro de métrica `request_count` | Cada escolha vira parâmetro na query string, de forma cumulativa; o recorte é aplicado no banco, e `npaw`, que só tem `bufferratio`, desaparece do resultado e da tabela | Ambas as requisições saíram com os parâmetros esperados; `npaw` presente no primeiro agrupamento e ausente após o filtro, no JSON e na tela; rótulos iguais aos do JSON nos dois momentos | Aprovado |
| TI-01.3 | Abrir `/explorar/` sem token na sessão, caso negativo | Nenhuma requisição a `/api/v1/` sai do navegador; a tela de acesso é exibida; nenhuma linha de dado é desenhada | Lista de chamadas à API vazia; título "Acesso ao painel" visível; zero linhas na tabela | Aprovado |

&emsp; O caso negativo importa mais do que parece: ele prova que a barreira do RNF09
vale para a comunicação, e não apenas para a pintura da tela. Um painel que
escondesse os dados mas ainda assim consultasse a API passaria numa inspeção visual
e falharia aqui.

&emsp; Para reproduzir:

```bash
make -C apps/basica db-local          # se o banco ainda não estiver no ar
make -C apps/basica test-frontend-e2e
```

&emsp; O alvo pula sozinho, sem falhar, quando o PostgreSQL ou o Chromium do
Playwright não estão disponíveis. Para instalar o navegador, o comando é
`cd apps/basica/frontend && npx playwright install chromium`.


### TI-02: aplicação Flask e PostgreSQL

&emsp; Este teste acompanha um registro atravessando as quatro camadas da aplicação
de leitura, da rota HTTP até o SQL, e verifica que ele reaparece intacto na resposta.
Verifica também a barreira de privacidade do RNF10, que só existe nessa travessia: o
banco guarda o identificador do usuário em claro, porque a ingestão não o transforma,
e a API só pode devolver o hash.

&emsp; O dado de entrada é gravado pela função `argus_worker.keys.build_row`, a mesma
que o worker de ingestão usa em produção, e não por um `INSERT` montado no teste.
A escolha é deliberada: é o que impede que a API de leitura e o worker de ingestão
divirjam em silêncio sobre o formato da linha. Um `INSERT` próprio testaria o
`INSERT` do teste.

| Campo | Conteúdo |
|---|---|
| Identificador | TI-02 |
| Objetivo | Verificar que a linha gravada no banco atravessa as quatro camadas da aplicação e reaparece intacta, e que a travessia aplica a barreira de privacidade |
| Requisitos | RF06, armazenar para consulta posterior; RF08, pesquisa por tipo e atributos; RF09, filtros cumulativos; RNF10, não expor dado pessoal desnecessário |
| Caso de uso | O operador busca eventos de erro de um sistema operacional específico |
| Componentes envolvidos | `telemetry.interfaces`, `telemetry.application.use_cases`, `telemetry.ports`, `telemetry.infrastructure.postgres.PostgresEventRepository` e a tabela `silver.session_event` |
| Pré-condições | Banco no ar com migrations aplicadas; tabelas truncadas antes de cada caso; relógio da simulação congelado em 2026-07-14T12:00Z |
| Dados de entrada | Um evento de erro sintético na sessão `sessao-ti02`, dispositivo `device-ti02`, usuário `usuario-ti02`, sistema `NetRange`, fabricante `Philco`, gravado por `argus_worker.keys.build_row` |
| Procedimento | `cd apps/basica/backend && TEST_DATABASE_URL=... uv run pytest tests/integration -v` |
| Situação | Aprovado nos 3 casos, em 4,64 s |
| Evidência | Bloco TI-02 de [`evidencias/testes-integracao.txt`](evidencias/testes-integracao.txt) |

| Caso | Entrada | Resultado esperado | Resultado obtido | Situação |
|---|---|---|---|---|
| TI-02.1 | `GET /api/v1/events?event_name=error&device_os=NetRange&limit=10`, com dois filtros cumulativos | HTTP 200 com exatamente esse evento; cada campo igual ao que uma consulta SQL direta lê da tabela; o bloco `query` reporta o custo real, com `scanned` maior ou igual a `returned` | 200 com 1 item; `event_name`, `session_id`, `device_id`, `app_bucket`, `device_os` e `route_path` idênticos à leitura SQL independente; relação entre `scanned` e `returned` confirmada | Aprovado |
| TI-02.2 | `GET /api/v1/events?session_id=sessao-ti02` | A resposta não contém a cadeia `usuario-ti02` em lugar nenhum; traz `user_id_hash` com os 16 hexadecimais previstos para o salt de teste; não traz a chave `user_id` | Identificador cru confirmado no banco e ausente da resposta; hash igual ao valor calculado de forma independente pelo teste; chave `user_id` ausente do item | Aprovado |
| TI-02.3 | Filtro por um sistema operacional que não existe em linha nenhuma, caso negativo | HTTP 200 com `items` vazio e `returned` igual a zero, ou seja, ausência de dado, e não falha | 200 com lista vazia e `returned` igual a zero | Aprovado |

&emsp; O caso negativo existe porque um erro 500 ali indicaria que as camadas só
conversam no caminho feliz, o que é uma forma comum de integração frágil passar
despercebida.

&emsp; Para reproduzir:

```bash
make -C apps/basica db-local
cd apps/basica/backend
TEST_DATABASE_URL=postgresql://argus:argus@localhost:55432/argus_test \
  uv run pytest tests/integration -v
```

&emsp; O alvo `make -C apps/basica test-backend` executa esta suíte junto com as
demais do backend.


### TI-03: worker de ingestão, fila SQS e PostgreSQL

&emsp; Este teste verifica três propriedades que não pertencem nem à fila nem ao
banco isoladamente, e sim à combinação dos dois. A mensagem válida vira linha
gravada. A mensagem inválida no mesmo lote não impede isso e termina na fila de
descarte com o motivo registrado. E a reentrega, que o SQS faz sempre que a
confirmação de processamento não chega a tempo, não duplica a linha.

&emsp; A ordem das mensagens no primeiro caso não é arbitrária. A inválida vem antes
da válida porque é a ordem que mais machuca: se o consumidor abortasse o lote ao
encontrar o erro, o evento válido seguinte nunca chegaria ao banco, e o teste com a
ordem inversa não perceberia.

| Campo | Conteúdo |
|---|---|
| Identificador | TI-03 |
| Objetivo | Verificar que a fila e o banco, juntos, gravam o válido, isolam o inválido e não duplicam na reentrega |
| Requisitos | RF01, ingestão por uma API única; RF04, rejeição rastreável do inválido; RNF04, evento inválido não impede os válidos seguintes; RNF05, não perder silenciosamente o que já foi aceito |
| Caso de uso | Um lote de eventos chega da borda com um payload malformado no meio |
| Componentes envolvidos | Fila `argus-events`, `argus_worker.consumer.EventConsumer`, `argus_worker.repository.EventRepository`, tabela `bronze.event` e a fila de descarte `argus-events-dlq` |
| Pré-condições | Banco no ar com migrations aplicadas; tabelas da camada bronze truncadas; filas SQS criadas em memória pelo `moto`; credenciais AWS falsas injetadas, para que nenhum teste alcance a nuvem real |
| Dados de entrada | Evento válido: a fixture `error.json`, exportada do BI do parceiro. Evento inválido: `{"event_name": "request"}`, sem `timestamp`, `session_id` nem `device_id` |
| Procedimento | `cd apps/basica/worker && TEST_DATABASE_URL=... uv run pytest tests/integration -v` |
| Situação | Aprovado nos 2 casos, em 2,57 s |
| Evidência | Bloco TI-03 de [`evidencias/testes-integracao.txt`](evidencias/testes-integracao.txt) |

| Caso | Entrada | Resultado esperado | Resultado obtido | Situação |
|---|---|---|---|---|
| TI-03.1 | Duas mensagens na fila, a inválida primeiro e a válida depois | `bronze.event` com exatamente a linha do evento válido, com `event_name`, `session_id` e `device_id` iguais ao que entrou pela fila; fila de descarte com uma mensagem, carregando o motivo da recusa; fila de entrada drenada a zero | 1 linha no banco com os três campos conferidos; 1 mensagem na fila de descarte com o atributo `FailureReason` preenchido; nenhuma mensagem restante na fila de entrada | Aprovado |
| TI-03.2 | O mesmo evento válido postado duas vezes, em ciclos separados | Uma única linha em `bronze.event` depois das duas entregas, e nada na fila de descarte | 1 linha após a primeira entrega, 1 linha após a segunda; fila de descarte vazia | Aprovado |

&emsp; Para reproduzir:

```bash
make -C apps/basica db-local
cd apps/basica/worker
TEST_DATABASE_URL=postgresql://argus:argus@localhost:55432/argus_test \
  uv run pytest tests/integration -v
```

&emsp; O alvo `make -C apps/basica test-worker` executa esta suíte junto com as demais
do worker.


### TI-04: ETL incremental entre bronze, silver e gold

&emsp; Este teste acompanha um valor atravessando os três estágios de armazenamento e
verifica que ele não se perde nem se deforma no caminho. Verifica também os dois
marcadores de progresso, que são o que torna a ETL incremental, e o comportamento do
pipeline em repouso.

&emsp; O valor escolhido, 412,5, é improvável de aparecer por acaso. Encontrá-lo na
camada gold prova que ele veio da linha que o teste inseriu, e não de outra, o que
uma asserção sobre um valor comum como zero ou cem não conseguiria garantir.

| Campo | Conteúdo |
|---|---|
| Identificador | TI-04 |
| Objetivo | Verificar que o valor sobrevive às três camadas, que cada marcador avança na medida do que processou, e que ciclo sem dado novo não reprocessa |
| Requisitos | RF05, converter os eventos para um esquema comum; RF06, armazenar para consulta e análise posteriores |
| Caso de uso | O ciclo periódico da ETL promove o que chegou desde a última execução |
| Componentes envolvidos | `bronze.change_log`, a função `bronze.merge_todas()`, `etl.executar_bronze_silver`, `etl.executar_silver_gold`, `silver.signal_bucket`, `gold.feature_bucket` e os marcadores `etl.watermark_bronze_silver` e `etl.watermark_silver_gold` |
| Pré-condições | Banco no ar com migrations aplicadas; camadas bronze, silver, gold e etl truncadas; marcadores reiniciados para o estado semeado pela migration 015; relógio da simulação em 2026-07-12T12:00Z |
| Dados de entrada | Uma mudança em `bronze.change_log` descrevendo a inserção de um bucket de sinal da fonte `prometheus`, entidade `cdn-ti04`, métrica `p95_ms` e valor 412,5 |
| Procedimento | `cd apps/basica/processing && TEST_DATABASE_URL=... uv run pytest tests/integration -v` |
| Situação | Aprovado nos 3 casos, em 7,63 s |
| Evidência | Bloco TI-04 de [`evidencias/testes-integracao.txt`](evidencias/testes-integracao.txt) |

| Caso | Entrada | Resultado esperado | Resultado obtido | Situação |
|---|---|---|---|---|
| TI-04.1 | A mudança bruta em `bronze.change_log`, seguida das duas etapas da ETL | O valor 412,5 aparece em `bronze.signal_bucket`, depois em `silver.signal_bucket` e depois em `gold.feature_bucket`, com `source`, `entity` e `metric` preservados em cada salto | Valor e atributos conferidos nas três camadas, uma a uma; a etapa bronze para silver reportou sucesso e leitura até o `lsn` esperado | Aprovado |
| TI-04.2 | A mesma mudança, com inspeção dos dois marcadores antes e depois | O marcador bronze para silver passa a valer exatamente o `lsn` da última mudança lida; o marcador silver para gold para uma margem de segurança atrás do fim da janela | Marcador bronze para silver avançou para exatamente o `lsn` da mudança; marcador silver para gold igual ao fim da janela menos a margem | Aprovado |
| TI-04.3 | Um ciclo completo já executado e nenhuma mudança nova depois dele, caso negativo | A segunda execução responde `sem_pendencia` com zero linhas, e a camada gold continua com uma única linha da entidade | `sem_pendencia` com zero linhas; 1 linha em `gold.feature_bucket` para a entidade | Aprovado |

&emsp; As asserções intermediárias do primeiro caso existem para localizar em qual
travessia o dado se perderia, caso se perdesse; sem elas, um teste que falha diz
apenas que algo deu errado em algum lugar. No segundo caso, o marcador não pode
avançar nem menos, o que faria reprocessar, nem mais, o que faria pular dado; e o
marcador silver para gold deixa a margem reaberta de propósito, porque dado atrasado
ainda pode chegar nela. O terceiro caso protege contra o erro mais caro de todos num
pipeline incremental: sem ele, um ciclo ocioso somaria o mesmo evento outra vez e o
dashboard mostraria o dobro do que aconteceu.

&emsp; Para reproduzir:

```bash
make -C apps/basica db-local
cd apps/basica/processing
TEST_DATABASE_URL=postgresql://argus:argus@localhost:55432/argus_test \
  uv run pytest tests/integration -v
```

&emsp; O alvo `make -C apps/basica test-processing` executa esta suíte junto com as
demais do processamento.


### TI-05: a pilha publicada na AWS

&emsp; Os quatro testes anteriores rodam na máquina, e é isso que os torna
repetíveis. A contrapartida é que existem costuras do sistema que eles não alcançam
por construção, porque só existem na nuvem: a integração direta entre o API Gateway
e o SQS, sem Lambda no caminho de escrita; o Lambda authorizer, que valida o Bearer
antes de qualquer integração; a separação de audiência entre os dois tokens; e o
comportamento do pipeline assíncrono inteiro. O TI-05 existe para cobrir essas
quatro.

&emsp; O carimbo de tempo do evento merece explicação, porque não é o óbvio. Ele é o
instante virtual lido em `GET /api/v1/clock` menos um minuto, e não a hora da
máquina. A API de leitura só mostra linha cujo `available_at` seja menor ou igual ao
instante da simulação, e no grão de sessão o `available_at` é o próprio `ts` do
evento. Um evento carimbado com a hora real ficaria invisível, e o teste falharia sem
que nada estivesse errado no sistema.

| Campo | Conteúdo |
|---|---|
| Identificador | TI-05 |
| Objetivo | Cobrir as quatro costuras que só existem na nuvem: integração direta com o SQS, Lambda authorizer, separação de audiência entre os tokens e o pipeline assíncrono completo |
| Requisitos | RF01, ingestão por uma API única; RF06, armazenar para consulta; RNF05, não perder o que já foi aceito; RNF09, acesso apenas a autorizados; RNF10, não expor dado pessoal |
| Caso de uso | Um dispositivo publica um evento na API e o operador o encontra no painel |
| Componentes envolvidos | Rota `POST /v1/events` no API Gateway, Lambda authorizer, fila SQS `argus-events`, event-worker no ECS Fargate, tabela `bronze.event` no RDS, ETL de bronze para silver, tabela `silver.session_event` e a rota `GET /api/v1/events` em Lambda |
| Pré-condições | Pilha publicada e no ar; `ARGUS_INGEST_URL`, `ARGUS_API_URL`, `ARGUS_INGEST_TOKEN` e `ARGUS_READ_TOKEN` no ambiente; event-worker e ETL em execução. Faltando qualquer uma, o teste é pulado, e não quebrado |
| Dados de entrada | Um evento de erro único por execução, na sessão `ti05-` seguida de identificador aleatório, carimbado um minuto atrás do instante virtual lido em `GET /api/v1/clock` |
| Procedimento | `cd apps/basica/backend && uv run pytest tests/integration/test_implantacao.py -v -rs`, com o `.env` carregado no ambiente |
| Situação | 1 caso aprovado e 1 reprovado, em 310 s |
| Evidência | Bloco TI-05 de [`evidencias/testes-integracao.txt`](evidencias/testes-integracao.txt), com a saída do pytest e as medições de cada fronteira |

| Caso | Entrada | Resultado esperado | Resultado obtido | Situação |
|---|---|---|---|---|
| TI-05.1 | Quatro requisições à mesma rota de leitura: sem token; com token de forma válida e valor desconhecido; com o token da audiência errada, o de ingestão; e com o token correto | As três primeiras recusadas com 401 ou 403 pelo authorizer, antes de alcançarem a Lambda da aplicação; a quarta responde 200 com o corpo do relógio | As três recusadas; a quarta com 200 e o campo `sim_now` presente | Aprovado |
| TI-05.2 | Evento enviado por `POST /v1/events` com o token de ingestão, seguido de consulta repetida a `GET /api/v1/events?session_id=...` até aparecer ou esgotar o prazo de 300 s | A borda aceita com 2xx e o evento aparece na leitura dentro do prazo, com `event_name` e `device_id` preservados e sem `user_id` na resposta | A borda aceitou e o evento foi gravado no banco, mas não apareceu na leitura em 300 s, ao longo de 29 tentativas | Reprovado |

&emsp; O primeiro caso é o tipo de asserção que nenhum teste local consegue fazer,
porque o authorizer só existe na borda do API Gateway e o Flask local roda sem ele.
O segundo reprovou, e a subseção a seguir explica por quê.

#### Diagnóstico do caso reprovado

&emsp; A reprovação foi investigada instrumentando cada fronteira do pipeline, em vez
de se supor uma causa. O resultado é que o evento não se perdeu em lugar nenhum: ele
atravessou quatro das cinco fronteiras e parou na quinta.

| Fronteira | Como foi medida | Resultado |
|---|---|---|
| Cliente, API Gateway e authorizer | O próprio caso TI-05.1 | Atravessou |
| API Gateway e fila SQS | Código de resposta do `POST` | Atravessou, com 2xx |
| Fila SQS e event-worker | Métrica `MessagesReceived` no CloudWatch e profundidade das quatro filas | Atravessou: 1 mensagem recebida, filas e fila de descarte vazias |
| event-worker e `bronze.event` | Métrica `ItemsWritten` no CloudWatch | Atravessou: 1 item gravado no mesmo minuto do `POST` |
| `bronze.event` e `silver.session_event` | Log do serviço `processing` e avanço do marcador | Parou aqui |
| `silver.session_event` e `GET /api/v1/events` | Consulta direta com janela ampla e explícita | Não alcançado: zero itens, `scanned` igual a zero |

&emsp; A explicação está em como a ETL é incremental. Cada linha que entra na camada
bronze recebe um número de ordem, o `lsn`. A ETL guarda um marcador dizendo até que
`lsn` já processou, lê um lote a partir dali em cada ciclo e avança o marcador ao
terminar. É isso que impede reprocessar o que já foi feito, e é isso que coloca um
evento recém-chegado numa fila atrás de tudo que ainda não foi processado.

| Grandeza | Valor |
|---|---:|
| Linhas gravadas na bronze pelo serviço de carga em 14 de setembro | 115.971.059 |
| Marcador da ETL no momento do diagnóstico | `lsn` 28.404.255 |
| Linhas ainda por processar | cerca de 87.500.000 |
| Ritmo medido em cinco ciclos consecutivos | 50.000 linhas a cada 16,2 min |
| Vazão equivalente | cerca de 185.000 linhas por hora |
| Estimativa para o marcador alcançar o evento | cerca de 470 h, perto de 20 dias de execução contínua |

&emsp; O evento do teste recebeu um `lsn` na ponta da sequência, atrás de 87 milhões
de linhas. O prazo de 300 s, portanto, errou por um fator de aproximadamente 5.700, e
nenhum prazo razoável funcionaria. Aumentá-lo para horas produziria um teste que
ninguém roda, o que equivale a desligar o alarme em vez de atender ao chamado. O
prazo ficou como está. Como o laboratório encerra as tarefas do ECS ao fim da sessão,
o tempo de calendário seria ainda maior que a estimativa.

#### A correção que o diagnóstico produziu

&emsp; Investigar por que cada ciclo leva dezesseis minutos para processar cinquenta
mil linhas levou a um defeito de schema, e não apenas a uma condição operacional.
Duas funções da ETL filtram a tabela `bronze.event` pela coluna `_lsn`: a
`etl.proxima_faixa_lsn`, que decide a faixa de cada ciclo, e a
`silver.build_session_event`, que faz a promoção. A tabela é particionada por `ts` e
não tinha índice algum em `_lsn`, de modo que não há poda de partição possível, por
ser outra a chave de particionamento, nem índice a usar. O plano resultante é uma
varredura sequencial de todas as partições, duas vezes por ciclo, com custo
proporcional ao tamanho da tabela em vez de proporcional ao tamanho do lote.

&emsp; Vale a comparação com `bronze.change_log`, que nasceu certa: ela tem
`PRIMARY KEY (lsn)` e é particionada por `lsn`, de modo que a mesma consulta ali é
poda de partição seguida de leitura por índice.

| Situação | Plano de execução | Tempo, com 300 mil linhas |
|---|---|---:|
| Sem índice em `_lsn` | Varredura sequencial de todas as partições, com 250.000 linhas descartadas pelo filtro | 48,7 ms |
| Com índice em `_lsn` | Leitura por índice sem acesso à tabela, com `Heap Fetches` igual a zero | 12,6 ms |

&emsp; O ganho de quatro vezes nesse volume não é o ponto principal. O que importa é
que a forma do custo muda: a varredura cresce com a tabela, e a leitura por índice
cresce com o que se pede. A correção está na migration
[`030_indice_lsn_em_evento.sql`](../apps/basica/db/migrations/030_indice_lsn_em_evento.sql).

&emsp; Ela vem acompanhada do teste
[`test_plano_da_etl.py`](../apps/basica/processing/tests/test_plano_da_etl.py), que
verifica o plano de execução, e não o tempo de relógio. Medir tempo em teste produz
um portão instável, que reprova consulta correta em máquina carregada e acaba
ignorado por todos. O teste popula a tabela com `_lsn` descorrelacionado de `ts`, que
é o caso real, e exige que nenhuma partição seja varrida sequencialmente. Foi
verificado nos dois sentidos: falha nos três casos quando o índice não existe e passa
quando ele existe.

&emsp; Uma ressalva de honestidade: não é possível afirmar que esse índice explica os
dezesseis minutos inteiros. O `EXPLAIN` contra a tabela real exigiria acesso ao RDS,
que não é acessível de fora, e as agregações das outras duas funções de construção
também podem pesar. O que está demonstrado é o defeito estrutural e a direção da
correção.

#### O que este resultado diz sobre o sistema

&emsp; O primeiro achado é que o frescor de ponta a ponta da implantação é hoje medido
em horas, e não em minutos, e que o limite está na ETL, não na fila. A ingestão faz
sua parte em segundos: aceita, enfileira, consome e grava. O relatório de carga
registra uma amostra de frescor de 38 minutos e 32 segundos, e a situação medida aqui
é pior que aquela amostra.

&emsp; O segundo é que a tabela `silver.session_event` está vazia na implantação,
conforme mostra o `scanned` igual a zero mesmo com janela ampla. O serviço `simulator`
está com zero tarefas, de modo que não há quem publique evento de sessão, e o evento
do teste é o único do sistema. As telas continuam funcionando porque consomem as
tabelas da camada gold, alimentadas pela carga histórica do parceiro.

&emsp; Sobre o acúmulo já existente, cabe registrar o que a documentação do projeto
não diz. Existe o alvo `make etl`, que executa `gold.rebuild_tudo()`, um recompute
completo e idempotente da silver e da gold a partir da bronze, numa chamada só em vez
de lotes de cinquenta mil. Ele exige `DATABASE_URL` e, como o RDS não é acessível de
fora, roda de dentro da VPC ou por túnel. Nenhum artefato do repositório estabelece
qual dos dois caminhos é o previsto depois de uma carga em massa; pelo contrário, o
[`plano-argus-v3.md`](plano-argus-v3.md) descreve o recompute completo como o que
existia até a migration 015, que introduziu a ETL incremental por marcador. Qual usar
é uma decisão operacional em aberto, e este relatório apenas a aponta. Nenhuma ação
foi tomada sobre a infraestrutura durante este trabalho.

&emsp; Por fim, vale notar o que falta de instrumentação. Não existe métrica de
distância entre o marcador e a ponta da sequência. Se existisse, o acúmulo teria
aparecido em 14 de setembro, quando a carga foi feita, e não num teste de integração
três dias depois.

#### Segredo e evidência

&emsp; Nenhum endpoint, identificador de conta ou token aparece neste artefato nem na
evidência. O teste lê todos eles do
ambiente, sua função `_falha_sem_vazar` impede que uma mensagem de falha os imprima,
e a saída capturada passou por filtro de redação antes de ser versionada. O token de
leitura não é recuperável da AWS, que guarda apenas o seu SHA-256; o de ingestão
volta com `make auth-show-ingest`.

&emsp; Para reproduzir:

```bash
# 1. renovar a sessão do Learner Lab e atualizar ~/.aws/credentials (profile g4)
make -C apps/basica env               # reescreve as URLs a partir do Terraform
make -C apps/basica auth-show-ingest  # recupera o token de ingestão

# 2. exportar os dois tokens (o de leitura é o que se cola no painel)
export ARGUS_INGEST_TOKEN=...
export ARGUS_READ_TOKEN=...

# 3. rodar
cd apps/basica/backend
set -a && . ../.env && set +a
uv run pytest tests/integration/test_implantacao.py -v -rs
```

### Execução das suítes

&emsp; Para confirmar que os testes novos não quebraram nada, e que a migration do
índice não alterou comportamento, todas as suítes do repositório foram executadas na
mesma sessão de trabalho.

| Suíte | Comando | Resultado |
|---|---|---|
| Worker de ingestão | `make -C apps/basica test-worker` | 77 aprovados |
| Simulador | `make -C apps/basica test-simulator` | 2 aprovados |
| Processamento e ETL | `make -C apps/basica test-processing` | 72 aprovados |
| API de leitura | `make -C apps/basica test-backend` | 227 aprovados, 2 pulados |
| Autorizador | `make -C apps/basica test-authorizer` | 18 aprovados |
| Frontend, contratos e componentes | `make -C apps/basica test-frontend` | 24 aprovados |
| Frontend integrado, com Playwright | `make -C apps/basica test-frontend-e2e` | 12 aprovados |
| Pilha publicada, o TI-05 | `uv run pytest tests/integration/test_implantacao.py` | 1 aprovado, 1 reprovado |

&emsp; São 432 testes aprovados nas suítes que rodam sem credencial de nuvem, mais o
TI-05, que executado com credencial aprovou um caso e reprovou outro. Os 227 do
backend incluem os 52 testes unitários da seção anterior e os 3 casos do TI-02. Os 2
pulados naquela linha são justamente os casos do TI-05, que ficam de fora quando
`make test-backend` roda sem os tokens da pilha publicada, e por isso o TI-05 tem
linha própria na tabela.

&emsp; Uma observação de ambiente, registrada por honestidade de relatório: o alvo
`test-authorizer` interrompe a coleta com `NoRegionError` quando a variável
`AWS_REGION` não está definida no terminal. Não é defeito do código nem efeito dos
testes de integração, e com `AWS_REGION=us-east-1` no ambiente os 18 testes passam,
como registrado na tabela. O valor sai do `.env` na operação normal do projeto.
