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

&emsp; Vale dizer desde já que esses defeitos não são hipotéticos. Um deles apareceu
durante este trabalho, e o relato está no TI-05: um evento que atravessa a
ingestão inteira em segundos e depois fica horas sem aparecer na tela.

### Panorama dos cinco testes

&emsp; Foram planejados, implementados e executados cinco testes de integração,
somando treze casos. Os quatro primeiros cobrem pares de camadas que rodam na
máquina de desenvolvimento. O quinto exercita a pilha publicada na AWS, e é o
único com um caso reprovado. A reprovação é real: foi investigada até a causa
raiz, virou um achado sobre o sistema e resultou numa correção de schema, em vez
de ser contornada afrouxando o teste.

| Teste | Camadas que ele atravessa | Casos | Situação |
|---|---|---:|---|
| TI-01 | Dashboard Next.js, API Flask de leitura e PostgreSQL | 3 | Aprovado |
| TI-02 | Rota Flask, caso de uso, adaptador de repositório e PostgreSQL | 3 | Aprovado |
| TI-03 | Worker de ingestão, fila SQS e PostgreSQL | 2 | Aprovado |
| TI-04 | ETL incremental entre as camadas bronze, silver e gold, no PostgreSQL | 3 | Aprovado |
| TI-05 | Pilha publicada na AWS, da borda HTTP até a API de leitura | 2 | 1 aprovado, 1 reprovado |

&emsp; No total, treze casos implementados e executados, doze aprovados e um
reprovado. O caso reprovado é o TI-05.2, cuja causa raiz está identificada: o
evento chegou ao banco, mas a ETL não o promoveu para a camada consultável dentro
do prazo do teste. A execução completa, com a saída bruta de cada suíte, está em
[`evidencias/testes-integracao.txt`](evidencias/testes-integracao.txt).

&emsp; Este relatório usa os mesmos três estados adotados em
[`testes-carga-inicial.md`](testes-carga-inicial.md), para que uma afirmação forte
e uma fraca não pareçam iguais a quem lê rápido. Um teste preparado é aquele cujo
cenário e automação existem no repositório. Um teste executado foi de fato rodado,
e sua saída está registrada na evidência. Um teste aprovado é o que, além de
executado, satisfez todos os critérios de aceite do caso.

### Componentes envolvidos e o que se espera de cada travessia

&emsp; O critério desta entrega pede que se identifiquem os componentes envolvidos e
o resultado esperado da interação entre eles. Convém deixar claro o que conta como
resultado esperado aqui: é sempre uma afirmação sobre a travessia, sobre o que
acontece no caminho entre duas peças, e nunca sobre o comportamento interno de
nenhuma das pontas isoladamente. Isso último já é assunto dos testes unitários.

&emsp; No TI-01 conversam o dashboard e a API de leitura, por HTTP com JSON, levando
o token de acesso guardado na sessão do navegador; e, logo atrás, a API e o
PostgreSQL, por conexão TCP e SQL sobre as tabelas `gold.feature_bucket` e
`silver.session_event`. Espera-se duas coisas dessa conversa. Na ida, que o filtro
escolhido pelo operador apareça na query string que o navegador envia. Na volta,
que a tabela desenhada contenha exatamente as linhas que vieram no JSON, nem uma a
mais inventada no cliente, nem uma a menos perdida na renderização. E espera-se
que o recorte seja aplicado no banco, e não na tela: trocar o filtro tem que mudar
o conjunto que volta pela rede.

&emsp; No TI-02 a conversa é interna à aplicação de leitura, atravessando as quatro
camadas da sua arquitetura: a rota Flask em `telemetry.interfaces`, o caso de uso
em `telemetry.application`, a porta de repositório em `telemetry.ports` e o
adaptador `PostgresEventRepository` em `telemetry.infrastructure`, que fala SQL
parametrizado com a tabela `silver.session_event`. Espera-se que a linha gravada
no banco reapareça campo a campo na resposta HTTP, e que a travessia aplique a
barreira de privacidade: o banco guarda o identificador do usuário em claro,
porque a ingestão não o transforma, e a API só pode devolver o hash.

&emsp; No TI-03 conversam a fila SQS `argus-events`, o `EventConsumer`, o
`EventRepository` e a tabela `bronze.event`, com a fila de descarte
`argus-events-dlq` recebendo o que for recusado. A mensagem trafega em JSON e a
escrita usa `INSERT ... ON CONFLICT`. Espera-se que a mensagem válida vire linha,
que a inválida saia de circulação pela fila de descarte sem travar a válida que
vem atrás, e que a reentrega da mesma mensagem não duplique a linha já gravada.

&emsp; No TI-04 conversam módulos internos do processamento com o banco: a tabela
`bronze.change_log`, a função SQL `bronze.merge_todas()`, o módulo
`argus_processing.etl` e as tabelas `silver.signal_bucket` e `gold.feature_bucket`,
coordenados pelos marcadores de progresso `etl.watermark_bronze_silver` e
`etl.watermark_silver_gold`. Espera-se que o mesmo valor atravesse as três camadas
sem se deformar, que cada marcador avance na medida exata do que foi processado, e
que um ciclo sem dado novo não reprocesse nada.

&emsp; O TI-05 tem duas travessias distintas, e por isso dois casos. A primeira é
entre um cliente HTTP qualquer e o Lambda authorizer que guarda as duas APIs
publicadas, por HTTPS com o cabeçalho `Authorization: Bearer`. Espera-se que a
borda recuse, com 401 ou 403, a requisição sem token, a com token desconhecido e a
que apresenta o token da audiência errada, aceitando somente o token da própria
audiência. A segunda travessia é o pipeline inteiro: da rota `POST /v1/events` no
API Gateway para a fila SQS por integração direta, sem Lambda no caminho de
escrita, daí para o event-worker no ECS Fargate, para o RDS PostgreSQL, para a ETL
e finalmente para `GET /api/v1/events`. Espera-se que um evento aceito na borda
apareça na API de leitura dentro do prazo, com os campos preservados. A espera faz
parte do contrato, e não é defeito: a ingestão é assíncrona por projeto, de modo
que a borda enfileira e responde de imediato, e quem grava é o worker.

### Vocabulário usado nesta seção

&emsp; Alguns termos aparecem com frequência e não são óbvios para quem chega de
fora do projeto.

&emsp; Fila de descarte, ou DLQ, de dead-letter queue, é uma fila separada para onde
vai a mensagem que o consumidor não conseguiu processar. Ela existe para que um
dado ruim saia de circulação de forma registrada, com o motivo da recusa anexado,
em vez de ser reentregue indefinidamente ou descartado em silêncio.

&emsp; Entrega ao menos uma vez, ou at-least-once, é a garantia que o SQS oferece: a
fila promete que a mensagem chega, mas não promete que chega uma única vez. Se a
confirmação de processamento se perder no caminho, a mesma mensagem é entregue de
novo. Cabe ao destino ser idempotente, ou seja, produzir o mesmo resultado
processando duas vezes ou uma.

&emsp; Marcador de progresso, ou watermark, é uma linha no banco que registra até
onde uma etapa da ETL já processou. É o que torna o processamento incremental:
cada execução lê apenas o que entrou depois do marcador e o avança ao terminar.
Cada linha que entra na camada bronze recebe um número de ordem, o `lsn`, e é por
ele que o marcador se orienta.

&emsp; Bronze, silver e gold nomeiam os três estágios do armazenamento. A bronze
guarda o dado bruto como ele chegou, a silver guarda o dado normalizado no esquema
comum, e a gold guarda o dado agregado e pronto para as consultas do dashboard.

### Ambiente de execução

&emsp; Os quatro primeiros testes rodaram em 17 de setembro de 2026, num Linux
7.0.0-31-generic sobre x86_64, contra um PostgreSQL 16.14 em contêiner Docker (o
`argus-pg`, na porta 55432, base `argus_test`). As ferramentas foram o pytest
8.4.2 no backend com Python 3.13, o pytest 9.1.1 no worker com Python 3.12 e no
processamento com Python 3.13, e o Playwright 1.62.1 com Chromium 151.0.7922.34
para o teste de interface.

&emsp; O único dublê usado em toda a suíte é o SQS, reproduzido em memória pelo
`moto` na versão 5 ou superior, no TI-03. Banco, API, navegador e site são reais
em todos os testes. O TI-05 não usa dublê nenhum: ele roda contra a pilha
publicada no AWS Academy Learner Lab, na região `us-east-1`, composta de API
Gateway HTTP, Lambda authorizer, Lambda da API de leitura, SQS, ECS Fargate com os
serviços `event-worker`, `merge-worker` e `processing`, e RDS PostgreSQL.

&emsp; Rodar contra um PostgreSQL de verdade, em vez de um dublê, não é preferência
de quem escreveu estes testes: é regra do projeto, registrada em
[`apps/basica/AGENTS.md`](../apps/basica/AGENTS.md). A justificativa é que a parte
difícil deste sistema mora no SQL, e um dublê que respondesse "ok" a tudo estaria
testando apenas o dublê. A contrapartida é que, quando o banco não está no ar, as
suítes que dependem dele são puladas, e não quebradas, de modo que o portão de
qualidade continua útil numa máquina sem Docker.

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
| [`apps/basica/.env.example`](../apps/basica/.env.example) | Nomes das variáveis que o TI-05 lê do ambiente; as URLs e tokens reais ficam no `.env`, que não é versionado |
| [`apps/basica/db/migrations/030_indice_lsn_em_evento.sql`](../apps/basica/db/migrations/030_indice_lsn_em_evento.sql) | Correção de schema nascida do diagnóstico do TI-05 |
| [`apps/basica/processing/tests/test_plano_da_etl.py`](../apps/basica/processing/tests/test_plano_da_etl.py) | Teste que sustenta essa correção |
| [`apps/basica/Makefile`](../apps/basica/Makefile) | Alvos `db-local`, `env`, `auth-show-ingest`, `test-backend`, `test-worker`, `test-processing` e `test-frontend-e2e` |
| [`evidencias/testes-integracao.txt`](evidencias/testes-integracao.txt) | Saída bruta da execução dos cinco testes |

### Pré-condição comum

&emsp; Os quatro testes locais exigem o PostgreSQL no ar, com as migrations
aplicadas:

```bash
make -C apps/basica db-local
```

&emsp; O comando sobe o contêiner `argus-pg` na porta 55432, e não na 5432, para não
conflitar com um PostgreSQL já instalado na máquina; cria a base `argus_test`; e
aplica as 30 migrations em ordem.

---

### TI-01: dashboard, API de leitura e PostgreSQL

&emsp; O objetivo do TI-01 é verificar que o dashboard e a API de leitura cumprem o
contrato nos dois sentidos, ou seja, que a escolha do operador na tela chega ao
backend como parâmetro de consulta e que o que a tela desenha é exatamente o que o
backend leu do banco. Os requisitos exercitados são o RF08, de pesquisa por
atributos, o RF09, de filtros cumulativos, o RF11, de agrupamento por critérios, o
RNF02, que limita a consulta simples a cinco segundos, e o RNF09, de acesso apenas
a autorizados. O caso de uso por trás disso é o operador investigando onde um
sinal se concentra, trocando agrupamento e filtro na tela Explorar.

&emsp; Os componentes envolvidos, na ordem em que a requisição os encontra, são o
navegador Chromium, o site estático Next.js servido em 127.0.0.1:3100, o protocolo
HTTP, a API Flask em 127.0.0.1:5100 e o PostgreSQL da base `argus_test`. Como
pré-condição, o banco precisa estar no ar com as migrations aplicadas e o
`fixture.sql` carregado, o site precisa ter sido construído apontando
`NEXT_PUBLIC_API_URL` para o Flask local, e o Chromium do Playwright precisa estar
instalado.

&emsp; Os dados de entrada vêm de
[`fixture.sql`](../apps/basica/frontend/tests/e2e/fixture.sql): vinte e uma linhas
em `gold.feature_bucket`, distribuídas entre as fontes `prometheus`,
`youbora_device`, `npaw`, `newrelic` e `apollo`, mais três eventos de sessão em
`silver.session_event`. O relógio da simulação é congelado em 2026-07-14T12:00Z, e
essa congelação é deliberada: sem ela o resultado dependeria da data em que o
teste roda, e a suíte começaria a falhar sozinha semanas depois, sem nenhuma
mudança de código. O procedimento de execução é um alvo só,
`make -C apps/basica test-frontend-e2e`, que recarrega o `fixture.sql`, constrói o
site estático, sobe o Flask e o servidor do site e executa o Playwright.

&emsp; Situação: aprovado nos três casos. A evidência está no bloco TI-01 de
[`evidencias/testes-integracao.txt`](evidencias/testes-integracao.txt).

&emsp; No caso TI-01.1, a entrada é abrir a tela `/explorar/` com sessão aberta, no
agrupamento padrão por dispositivo. Esperava-se que a requisição saísse para a
origem `http://127.0.0.1:5100` levando `dimension=entity` e `source=youbora_device`,
que o JSON trouxesse grupos vindos do banco, que a tabela exibisse exatamente o
mesmo conjunto de rótulos, que a linha de maior valor mostrasse o número agregado
pelo SQL e que tudo isso levasse menos de cinco segundos. O que se obteve foi a
requisição confirmada na origem do Flask, os grupos `LG webOS 3.x` e
`Samsung Tizen`, dois rótulos na tabela para os dois grupos do JSON, com os
conjuntos idênticos, o valor 1.737,7 renderizado na linha e a resposta em um
segundo. Caso aprovado.

&emsp; No caso TI-01.2, a entrada é trocar o agrupamento para Fonte e em seguida
aplicar o filtro de métrica `request_count`. Esperava-se que cada escolha virasse
parâmetro na query string, primeiro `dimension=source` e depois `dimension=source`
somado a `metric=request_count`, de forma cumulativa, e que o recorte fosse
aplicado no banco, fazendo `npaw`, que só tem `bufferratio`, desaparecer tanto do
resultado quanto da tabela. O que se obteve foi exatamente isso: ambas as
requisições saíram com os parâmetros esperados, `npaw` apareceu no primeiro
agrupamento e sumiu depois do filtro, no JSON e na tela, e os rótulos exibidos
coincidiram com os do JSON nos dois momentos. Caso aprovado.

&emsp; O caso TI-01.3 é o negativo, e a entrada é abrir `/explorar/` sem token na
sessão. Esperava-se que nenhuma requisição a `/api/v1/` saísse do navegador, que a
tela de acesso fosse exibida e que nenhuma linha de dado fosse desenhada. O que se
obteve foi a lista de chamadas à API vazia, o título "Acesso ao painel" visível e
zero linhas na tabela. Caso aprovado. Este caso importa porque prova que a
barreira do RNF09 vale para a comunicação, e não apenas para a pintura da tela.

&emsp; Para reproduzir:

```bash
make -C apps/basica db-local          # se o banco ainda não estiver no ar
make -C apps/basica test-frontend-e2e
```

&emsp; O alvo pula sozinho, sem falhar, quando o PostgreSQL ou o Chromium do
Playwright não estão disponíveis. Para instalar o navegador, o comando é
`cd apps/basica/frontend && npx playwright install chromium`.

---

### TI-02: aplicação Flask e PostgreSQL

&emsp; O objetivo do TI-02 é verificar que um registro gravado no banco atravessa as
quatro camadas da aplicação de leitura, quais sejam a rota HTTP, o caso de uso, a
porta de repositório e o adaptador SQL, e reaparece intacto na resposta; e que
essa travessia aplica a barreira de privacidade exigida pelo RNF10. Os requisitos
exercitados são o RF06, de armazenar para consulta posterior, o RF08, de pesquisa
por tipo e atributos, o RF09, de filtros cumulativos, e o próprio RNF10, de não
expor dado pessoal desnecessário. O caso de uso é o operador buscando eventos de
erro de um sistema operacional específico.

&emsp; Os componentes envolvidos são `telemetry.interfaces`, que expõe a rota Flask,
`telemetry.application.use_cases`, que orquestra, `telemetry.ports`, que define a
porta de repositório, o adaptador
`telemetry.infrastructure.postgres.PostgresEventRepository` e, no fim, a tabela
`silver.session_event` no PostgreSQL. As pré-condições são o banco no ar com as
migrations aplicadas, as tabelas truncadas antes de cada caso e o relógio da
simulação congelado em 2026-07-14T12:00Z.

&emsp; O dado de entrada é um evento de erro sintético, na sessão `sessao-ti02`, do
dispositivo `device-ti02`, do usuário `usuario-ti02`, com sistema `NetRange` e
fabricante `Philco`. Ele é gravado pelo mesmo código que o worker de ingestão usa
em produção, a função `argus_worker.keys.build_row`, e essa escolha tem uma razão
precisa: é o que impede que a API de leitura e o worker de ingestão divirjam em
silêncio sobre o formato da linha. Se o teste montasse um `INSERT` à mão, estaria
testando o `INSERT` do teste. O procedimento é
`cd apps/basica/backend && TEST_DATABASE_URL=... uv run pytest tests/integration -v`.

&emsp; Situação: aprovado nos três casos, em 4,64 segundos. A evidência está no
bloco TI-02 do arquivo de evidências.

&emsp; No caso TI-02.1, a entrada é o evento no banco e a consulta
`GET /api/v1/events?event_name=error&device_os=NetRange&limit=10`, com dois
filtros cumulativos. Esperava-se HTTP 200 trazendo exatamente esse evento, com
cada campo da resposta igual ao que uma consulta SQL direta lê da tabela, e o
bloco `query` reportando o custo real da consulta, com `scanned` maior ou igual a
`returned`. O que se obteve foi o 200 com um item, os campos `event_name`,
`session_id`, `device_id`, `app_bucket`, `device_os` e `route_path` idênticos à
leitura SQL feita de forma independente pelo teste, e a relação entre `scanned` e
`returned` confirmada. Caso aprovado.

&emsp; No caso TI-02.2, a entrada é o mesmo evento e a consulta por sessão.
Esperava-se que o banco guardasse `usuario-ti02` em claro, mas que a resposta HTTP
não contivesse essa cadeia em lugar nenhum, trazendo em seu lugar um
`user_id_hash` com os dezesseis hexadecimais previstos para o salt de teste, e
nenhuma chave `user_id`. O que se obteve confirma os dois lados: o identificador
cru está no banco, some da resposta, e o hash bate com o valor que o teste calcula
por conta própria. Caso aprovado.

&emsp; O caso TI-02.3 é o negativo. A entrada é o evento no banco e um filtro por um
sistema operacional que não existe em linha nenhuma. Esperava-se HTTP 200 com
`items` vazio e `returned` igual a zero, isto é, ausência de dado, e não falha. Um
erro 500 aqui indicaria que as camadas só conversam no caminho feliz. O que se
obteve foi o 200 com lista vazia. Caso aprovado.

&emsp; Para reproduzir:

```bash
make -C apps/basica db-local
cd apps/basica/backend
TEST_DATABASE_URL=postgresql://argus:argus@localhost:55432/argus_test \
  uv run pytest tests/integration -v
```

&emsp; O alvo `make -C apps/basica test-backend` executa esta suíte junto com as
demais do backend.

---

### TI-03: worker de ingestão, fila SQS e PostgreSQL

&emsp; O objetivo do TI-03 é verificar três propriedades que só existem na
combinação da fila com o banco. Primeiro, que uma mensagem postada na fila vira
linha gravada. Segundo, que uma mensagem inválida no mesmo lote não impede isso e
termina na fila de descarte com o motivo registrado. Terceiro, que a reentrega,
inevitável pela garantia de entrega ao menos uma vez do SQS, não duplica a linha.
Os requisitos exercitados são o RF01, de ingestão por uma API única, o RF04, de
rejeição rastreável do inválido, o RNF04, segundo o qual um evento inválido não
impede os válidos seguintes, e o RNF05, de não perder silenciosamente o que já foi
aceito. O caso de uso é um lote de eventos chegando da borda com um payload
malformado no meio.

&emsp; Os componentes envolvidos são a fila SQS `argus-events`, o
`argus_worker.consumer.EventConsumer`, o `argus_worker.repository.EventRepository`
e a tabela `bronze.event`, mais a fila de descarte `argus-events-dlq` para o que
for recusado. As pré-condições são o banco no ar com as migrations aplicadas, as
tabelas da camada bronze truncadas, as filas SQS criadas em memória pelo `moto` e
credenciais AWS falsas injetadas no ambiente, estas últimas para garantir que
nenhum teste alcance a nuvem real por engano.

&emsp; Os dados de entrada são dois. O evento válido é a fixture `error.json`,
exportada do BI do parceiro, portanto com o formato que o sistema recebe de
verdade. O evento inválido é `{"event_name": "request"}`, sem `timestamp`, sem
`session_id` e sem `device_id`, que é exatamente o envelope mínimo que o RF04 manda
recusar. O procedimento é
`cd apps/basica/worker && TEST_DATABASE_URL=... uv run pytest tests/integration -v`.

&emsp; Situação: aprovado nos dois casos, em 2,57 segundos. A evidência está no
bloco TI-03 do arquivo de evidências.

&emsp; No caso TI-03.1, a entrada são duas mensagens na fila, postadas na ordem
inválida primeiro e válida depois. A ordem não é arbitrária: é a que mais machuca,
porque se o consumidor abortasse o lote ao encontrar o erro, o evento válido
seguinte nunca chegaria ao banco. Esperava-se encontrar em `bronze.event`
exatamente a linha do evento válido, com `event_name`, `session_id` e `device_id`
iguais ao que entrou pela fila; a fila de descarte com exatamente uma mensagem,
carregando o motivo da recusa; e a fila de entrada drenada a zero, sem mensagem
presa. O que se obteve foi uma linha no banco com os três campos conferidos, uma
mensagem na fila de descarte com o atributo `FailureReason` preenchido e nenhuma
mensagem restante na fila de entrada. Caso aprovado.

&emsp; No caso TI-03.2, a entrada é o mesmo evento válido postado duas vezes, em
ciclos separados, que é o que o SQS faz quando a confirmação de processamento não
chega a tempo. Esperava-se uma única linha em `bronze.event` depois das duas
entregas, e nada na fila de descarte. Convém notar por que este caso pertence a um
teste de integração e não a um unitário: a idempotência não é propriedade do
consumidor nem do banco isoladamente, ela só existe na combinação dos dois. O que
se obteve foi uma linha após a primeira entrega, uma linha após a segunda e a fila
de descarte vazia. Caso aprovado.

&emsp; Para reproduzir:

```bash
make -C apps/basica db-local
cd apps/basica/worker
TEST_DATABASE_URL=postgresql://argus:argus@localhost:55432/argus_test \
  uv run pytest tests/integration -v
```

&emsp; O alvo `make -C apps/basica test-worker` executa esta suíte junto com as
demais do worker.

---

### TI-04: ETL incremental entre bronze, silver e gold

&emsp; O objetivo do TI-04 é verificar que um mesmo valor sobrevive às três camadas
de armazenamento sem se perder nem se deformar, que cada etapa só avança seu
marcador de progresso na medida do que realmente processou, e que rodar de novo
sem dado novo não reprocessa nada. Os requisitos exercitados são o RF05, de
converter os eventos para um esquema comum, e o RF06, de armazenar para consulta e
análise posteriores. O caso de uso é o ciclo periódico da ETL promovendo o que
chegou desde a última execução.

&emsp; Os componentes envolvidos são a tabela `bronze.change_log`, a função SQL
`bronze.merge_todas()`, as funções `etl.executar_bronze_silver` e
`etl.executar_silver_gold` do módulo `argus_processing`, e as tabelas
`silver.signal_bucket` e `gold.feature_bucket`, tudo coordenado pelos marcadores
`etl.watermark_bronze_silver` e `etl.watermark_silver_gold`. As pré-condições são
o banco no ar com as migrations aplicadas, as camadas bronze, silver, gold e etl
truncadas, os marcadores reiniciados para o estado semeado pela migration 015 e o
relógio da simulação em 2026-07-12T12:00Z.

&emsp; O dado de entrada é uma mudança em `bronze.change_log` descrevendo a inserção
de um bucket de sinal da fonte `prometheus`, entidade `cdn-ti04`, métrica `p95_ms`
e valor 412,5. O valor foi escolhido por ser improvável de aparecer por acaso:
encontrá-lo na camada gold prova que ele veio desta linha, e não de outra. O
procedimento é
`cd apps/basica/processing && TEST_DATABASE_URL=... uv run pytest tests/integration -v`.

&emsp; Situação: aprovado nos três casos, em 7,63 segundos. A evidência está no
bloco TI-04 do arquivo de evidências.

&emsp; No caso TI-04.1, a entrada é a mudança bruta em `bronze.change_log`, seguida
das duas etapas da ETL. Esperava-se que o valor 412,5 aparecesse consolidado em
`bronze.signal_bucket`, depois em `silver.signal_bucket` e depois em
`gold.feature_bucket`, com `source`, `entity` e `metric` preservados em cada salto.
As asserções intermediárias existem para localizar em qual travessia o dado se
perderia, caso se perdesse. O que se obteve foi o valor e os atributos conferidos
nas três camadas, uma a uma, com a etapa bronze para silver reportando sucesso e
leitura até o `lsn` esperado. Caso aprovado.

&emsp; No caso TI-04.2, a entrada é a mesma mudança, com inspeção dos dois
marcadores antes e depois. Esperava-se que o marcador bronze para silver passasse
a valer exatamente o `lsn` da última mudança lida, nem menos, o que faria
reprocessar, nem mais, o que faria pular dado; e que o marcador silver para gold
parasse uma margem de segurança atrás do fim da janela, deixando essa faixa
reaberta para o ciclo seguinte, já que dado atrasado ainda pode chegar nela. O que
se obteve confirma os dois comportamentos. Caso aprovado.

&emsp; O caso TI-04.3 é o negativo, e retrata o pipeline em repouso. A entrada é um
ciclo completo já executado, sem nenhuma mudança nova depois dele. Esperava-se que
a segunda execução de bronze para silver respondesse `sem_pendencia` com zero
linhas, e que a camada gold continuasse com uma única linha da entidade. Sem essa
propriedade, um ciclo ocioso somaria o mesmo evento outra vez e o dashboard
mostraria o dobro do que aconteceu. O que se obteve foi exatamente o esperado.
Caso aprovado.

&emsp; Para reproduzir:

```bash
make -C apps/basica db-local
cd apps/basica/processing
TEST_DATABASE_URL=postgresql://argus:argus@localhost:55432/argus_test \
  uv run pytest tests/integration -v
```

&emsp; O alvo `make -C apps/basica test-processing` executa esta suíte junto com as
demais do processamento.

---

### TI-05: a pilha publicada na AWS

&emsp; Os quatro testes anteriores rodam na máquina, e é isso que os torna
repetíveis. A contrapartida é que existem costuras do sistema que eles não
alcançam por construção, porque só existem na nuvem: a integração direta entre o
API Gateway e o SQS, sem Lambda no caminho de escrita; o Lambda authorizer, que
valida o Bearer antes de qualquer integração; a separação de audiência entre os
dois tokens; e o comportamento do pipeline assíncrono inteiro, com fila, worker no
Fargate, RDS e ETL. O TI-05 existe para cobrir essas quatro.

&emsp; Os requisitos exercitados são o RF01, de ingestão por uma API única, o RF06,
de armazenar para consulta, o RNF05, de não perder o que já foi aceito, o RNF09,
de acesso apenas a autorizados, e o RNF10, de não expor dado pessoal. O caso de
uso é o mais simples e o mais central do produto: um dispositivo publica um evento
na API e o operador o encontra no painel.

&emsp; Os componentes envolvidos, na ordem da travessia, são a rota
`POST /v1/events` do API Gateway HTTP, o Lambda authorizer com o token de
ingestão, a fila SQS `argus-events`, o event-worker no ECS Fargate, a tabela
`bronze.event` no RDS PostgreSQL, a ETL que promove de bronze para silver em
ciclos, a tabela `silver.session_event` e, no fim, a rota `GET /api/v1/events`
servida por Lambda, novamente atrás do authorizer, desta vez com o token de
leitura. Como pré-condição, a pilha precisa estar publicada e no ar, as variáveis
`ARGUS_INGEST_URL`, `ARGUS_API_URL`, `ARGUS_INGEST_TOKEN` e `ARGUS_READ_TOKEN`
precisam estar no ambiente, e o event-worker e a ETL precisam estar em execução.
Faltando qualquer uma dessas condições, o teste é pulado, e não quebrado, o que
mantém `make test-backend` verde em qualquer máquina sem credencial.

&emsp; O dado de entrada é um evento de erro único por execução, na sessão
`ti05-` seguida de um identificador aleatório, carimbado um minuto atrás do
instante virtual lido em `GET /api/v1/clock`. Esse carimbo virtual é obrigatório e
merece explicação: a API de leitura só mostra linha cujo `available_at` seja menor
ou igual ao instante da simulação, e no grão de sessão o `available_at` é o
próprio `ts` do evento. Um evento carimbado com a hora da máquina ficaria
invisível, e o teste falharia sem que nada estivesse errado no sistema.

&emsp; O procedimento é
`cd apps/basica/backend && uv run pytest tests/integration/test_implantacao.py -v -rs`,
com o `.env` carregado no ambiente. Situação: um caso aprovado e um reprovado. A
evidência, com a saída do pytest e as medições de cada fronteira do pipeline, está
no bloco TI-05 do arquivo de evidências.

&emsp; No caso TI-05.1, a entrada são quatro requisições à mesma rota de leitura:
uma sem token, uma com token de forma válida e valor desconhecido, uma com o token
da audiência errada, isto é, o de ingestão, que não serve para ler, e uma com o
token correto. Esperava-se que as três primeiras fossem recusadas com 401 ou 403
pelo authorizer, antes mesmo de alcançarem a Lambda da aplicação, e que a quarta
respondesse 200 com o corpo do relógio. Foi o que aconteceu: as três recusadas, a
quarta com 200 e o campo `sim_now` presente. Caso aprovado. Nenhum teste local
poderia afirmar isso, porque o authorizer só existe na borda do API Gateway e o
Flask local roda sem ele.

&emsp; No caso TI-05.2, a entrada é o evento único enviado por `POST /v1/events` com
o token de ingestão, seguido de consulta repetida a
`GET /api/v1/events?session_id=...` até o evento aparecer ou o prazo de trezentos
segundos se esgotar. Esperava-se que a borda aceitasse com 2xx e que o evento
aparecesse na leitura dentro do prazo, com `event_name` e `device_id` preservados
e sem `user_id` na resposta. A borda aceitou e o evento foi gravado no banco, mas
ele não apareceu na leitura em trezentos segundos, ao longo de vinte e nove
tentativas. Caso reprovado. A causa raiz está na subseção seguinte.

#### Diagnóstico do caso reprovado

&emsp; A reprovação foi investigada instrumentando cada fronteira do pipeline, em
vez de se supor uma causa. O resultado dessa medição é que o evento não se perdeu
em lugar nenhum: ele atravessou quatro das cinco fronteiras e parou na quinta.

&emsp; A primeira fronteira, entre o cliente e o authorizer, é o próprio caso
TI-05.1, que passou. A segunda, entre o API Gateway e o SQS, foi confirmada pelo
código de resposta 2xx do `POST`. A terceira, entre o SQS e o event-worker, foi
confirmada pela métrica `MessagesReceived` do worker no CloudWatch, que registrou
uma mensagem recebida, e pela profundidade das filas, que estavam todas vazias,
inclusive a de descarte, o que descarta a hipótese de recusa. A quarta, entre o
worker e a tabela `bronze.event`, foi confirmada pela métrica `ItemsWritten`, que
registrou um item gravado no mesmo minuto do `POST`.

&emsp; A quinta fronteira, entre `bronze.event` e `silver.session_event`, é onde o
dado parou. A consulta direta à rota de leitura, feita com janela ampla e
explícita, devolveu zero itens com `scanned` igual a zero, o que significa que a
camada consultável não tinha a linha.

&emsp; A explicação está em como a ETL é incremental. Cada linha que entra na camada
bronze recebe um número de ordem, o `lsn`. A ETL guarda um marcador dizendo até
que `lsn` já processou, e em cada ciclo lê um lote a partir dali e avança o
marcador. É isso que impede reprocessar o que já foi feito, e é isso que coloca um
evento recém-chegado numa fila atrás de tudo que ainda não foi processado. A
distância entre o marcador e o evento foi medida, e é grande: a métrica
`RowsLoaded` do serviço de carga registra 115.971.059 linhas gravadas na bronze em
14 de setembro, enquanto o marcador da ETL estava em `lsn` 28.404.255. Faltavam,
portanto, cerca de 87,5 milhões de linhas. Em cinco ciclos consecutivos medidos, a
ETL processou 50.000 linhas a cada 16,2 minutos, o que dá aproximadamente 185 mil
linhas por hora e leva a uma estimativa de 470 horas, algo perto de vinte dias de
execução contínua, para o marcador alcançar o evento do teste. Como o laboratório
encerra as tarefas do ECS ao fim da sessão, o tempo de calendário seria ainda
maior.

&emsp; O prazo de trezentos segundos, portanto, errou por um fator de cerca de 5.700,
e nenhum prazo razoável funcionaria. Aumentá-lo para horas produziria um teste que
ninguém roda, o que equivale a desligar o alarme em vez de atender ao chamado. O
prazo ficou como está.

#### A correção que o diagnóstico produziu

&emsp; Investigar por que cada ciclo leva dezesseis minutos para processar cinquenta
mil linhas levou a um defeito de schema, e não apenas a uma condição operacional.
Duas funções da ETL filtram a tabela `bronze.event` pela coluna `_lsn`: a
`etl.proxima_faixa_lsn`, que decide a faixa de cada ciclo, e a
`silver.build_session_event`, que faz a promoção propriamente dita. Só que
`bronze.event` é particionada por `ts` e não tinha índice algum em `_lsn`. Não há
poda de partição possível, porque a chave de particionamento é outra coluna, nem
índice a usar. O plano de execução resultante é uma varredura sequencial de todas
as partições, duas vezes por ciclo, com custo proporcional ao tamanho da tabela em
vez de proporcional ao tamanho do lote.

&emsp; Vale a comparação com `bronze.change_log`, que nasceu certa: ela tem
`PRIMARY KEY (lsn)` e é particionada por `lsn`, de modo que a mesma consulta ali é
poda de partição seguida de leitura por índice.

&emsp; A migration
[`030_indice_lsn_em_evento.sql`](../apps/basica/db/migrations/030_indice_lsn_em_evento.sql)
cria o índice que faltava. Medido no banco local com 300 mil linhas, o plano
deixou de ser varredura sequencial e passou a ser leitura por índice sem acesso à
tabela, caindo de 48,7 para 12,6 milissegundos. O ganho de quatro vezes nesse
volume não é o ponto principal; o que importa é que a forma do custo muda, porque
a varredura cresce com a tabela e a leitura por índice cresce com o que se pede.

&emsp; A migration vem acompanhada do teste
[`test_plano_da_etl.py`](../apps/basica/processing/tests/test_plano_da_etl.py), que
verifica o plano de execução, e não o tempo de relógio. Medir tempo em teste
produz um portão instável, que reprova consulta correta em máquina carregada e
acaba ignorado por todos. O teste popula a tabela com `_lsn` descorrelacionado de
`ts`, que é o caso real, e então exige que nenhuma partição seja varrida
sequencialmente. Ele foi verificado nos dois sentidos: falha nos três casos quando
o índice não existe e passa quando ele existe.

&emsp; Uma ressalva de honestidade: não é possível afirmar que esse índice explica
os dezesseis minutos inteiros. O `EXPLAIN` contra a tabela real exigiria acesso ao
RDS, que não é acessível de fora, e as agregações das outras duas funções de
construção também podem pesar. O que está demonstrado é o defeito estrutural e a
direção da correção.

#### O que este resultado diz sobre o sistema

&emsp; O primeiro achado é que o frescor de ponta a ponta da implantação é hoje
medido em horas, e não em minutos, e que o limite está na ETL, não na fila. A
ingestão faz sua parte em segundos: aceita, enfileira, consome e grava. O relatório
de carga registra uma amostra de frescor de 38 minutos e 32 segundos; a situação
medida aqui é pior que aquela amostra.

&emsp; O segundo é que a tabela `silver.session_event` está vazia na implantação,
conforme mostra o `scanned` igual a zero mesmo com janela ampla. O serviço
`simulator` está com zero tarefas, de modo que não há quem publique evento de
sessão, e o evento do teste é o único do sistema. As telas continuam funcionando
porque consomem as tabelas da camada gold, alimentadas pela carga histórica do
parceiro.

&emsp; Sobre o acúmulo já existente, cabe registrar o que a documentação do projeto
não diz. Existe o alvo `make etl`, que executa `gold.rebuild_tudo()`, um recompute
completo e idempotente da silver e da gold a partir da bronze, numa chamada só em
vez de lotes de cinquenta mil. Ele exige `DATABASE_URL` e, como o RDS não é
acessível de fora, roda de dentro da VPC ou por túnel. Nenhum artefato do
repositório estabelece qual dos dois caminhos é o previsto depois de uma carga em
massa; pelo contrário, o [`plano-argus-v3.md`](plano-argus-v3.md) descreve o
recompute completo como o que existia até a migration 015, que introduziu a ETL
incremental por marcador. Qual usar é uma decisão operacional em aberto, e este
relatório apenas a aponta. Nenhuma ação foi tomada sobre a infraestrutura durante
este trabalho.

&emsp; Por fim, vale notar o que falta de instrumentação. Não existe métrica de
distância entre o marcador e a ponta da sequência. Se existisse, o acúmulo teria
aparecido em 14 de setembro, quando a carga foi feita, e não num teste de
integração três dias depois.

#### Segredo e evidência

&emsp; Nenhum endpoint, identificador de conta ou token aparece neste artefato nem na
evidência, conforme a regra registrada em
[`apps/basica/AGENTS.md`](../apps/basica/AGENTS.md). O teste lê todos eles do
ambiente, sua função `_falha_sem_vazar` impede que uma mensagem de falha os
imprima, e a saída capturada passou por filtro de redação antes de ser versionada.
O token de leitura não é recuperável da AWS, que guarda apenas o seu SHA-256; o de
ingestão volta com `make auth-show-ingest`.

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

---

### Execução das suítes

&emsp; Para confirmar que os testes novos não quebraram nada, todas as suítes do
repositório foram executadas na mesma sessão de trabalho.

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

&emsp; São 432 testes aprovados nas suítes que rodam sem credencial de nuvem, e mais
o TI-05, que executado com credencial aprovou um caso e reprovou outro. Os 227 do
backend incluem os 52 testes unitários da seção anterior e os 3 casos do TI-02. Os
2 pulados naquela linha são justamente os casos do TI-05, que ficam de fora quando
`make test-backend` roda sem os tokens da pilha publicada, e por isso o TI-05 tem
linha própria na tabela, com o resultado da execução feita com credencial.

&emsp; Uma observação de ambiente, registrada por honestidade de relatório: o alvo
`test-authorizer` interrompe a coleta com `NoRegionError` quando a variável
`AWS_REGION` não está definida no terminal. Não é defeito do código nem efeito dos
testes de integração, e com `AWS_REGION=us-east-1` no ambiente os 18 testes passam,
como registrado na tabela. O valor sai do `.env` na operação normal do projeto.
