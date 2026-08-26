# Rotas esperadas pelo frontend

## 1. Objetivo

&emsp;Este documento descreve as URLs públicas do dashboard e os contratos HTTP
que a interface espera da API de leitura e do motor de hipóteses. Serve como
contrato entre frontend e backend: o que já é chamado, o que ainda é mockado e
o que precisa existir para substituir os snapshots demonstrativos.

&emsp;O dashboard é um site estático (`output: "export"`, `trailingSlash: true`).
Em produção as páginas viram `/rota/index.html`. As chamadas de dados saem do
navegador para a base configurada no build; o frontend **não** possui rotas
Next.js de API (`app/api`).

| Variável de ambiente | Papel |
|---|---|
| `NEXT_PUBLIC_API_URL` | Base da API de leitura de eventos. Obrigatória no build. |
| `NEXT_PUBLIC_HYPOTHESES_SOURCE` | `mock` ou `api`. Obrigatória no build. |
| `NEXT_PUBLIC_HYPOTHESES_API_URL` | Base do motor de hipóteses. Obrigatória se a fonte for `api`. |

&emsp;Os alvos `make -C apps/basica frontend-dev` e `frontend-build` copiam
`ARGUS_API_URL`, `HYPOTHESES_SOURCE` e `HYPOTHESES_API_URL` para as variáveis
públicas acima.

## 2. Rotas do dashboard (Next.js)

&emsp;O route group `(operations)` não entra na URL. A entrada `/` redireciona
para `/agora`. Com `trailingSlash`, o export estático também responde em
`/agora/`.

| Método | Caminho | Tela | Origem dos dados hoje | Requisitos |
|---|---|---|---|---|
| `GET` | `/` | Redireciona para `/agora` | — | — |
| `GET` | `/agora` | Degradações e sinais em tempo real | Mock em `agora/_mocks` | RF12, RF13, RF15, RF16 |
| `GET` | `/explorar` | Exploração por tipo, período e dimensão | Mock em `explorar/_mocks` | RF08–RF12 |
| `GET` | `/comparar` | Janela atual contra referências históricas | Mock em `comparar/_mocks` | RF14, US05 |
| `GET` | `/hipoteses` | Causas prováveis ranqueadas | Mock ou `GET /api/v1/hypotheses` | RF17, RNF08 |
| `GET` | `/timeline` | Seis fontes em um eixo temporal | Mock em `timeline/_mocks` | US01, US06, RF16 |
| `GET` | `/recorte` | População afetada e mapa de calor | Mock em `recorte/_mocks` | US07, US08, RF16 |

&emsp;O cliente HTTP `src/lib/events/api.ts` (`GET /api/v1/events`) existe, mas a
página raiz deixou de montar o monitor ao vivo. Enquanto `/` redireciona para
`/agora`, esse cliente **não** é exercido pelas rotas da navegação.

### 2.1 Query string das páginas

&emsp;Parâmetros lidos ou emitidos pelo frontend. Timeline e Recorte **ainda não
consomem** `hipotese`, `t`, `segmento` nem `sinal`; os links já os escrevem
para o encadeamento futuro.

| Parâmetro | Onde | Quem lê hoje | Significado |
|---|---|---|---|
| `demoState` | qualquer rota operacional | `OperationsUiProvider` | Força estado de UI (`ready`, `loading`, `refreshing`, `empty`, `partial`, `stale`, `error`) na demonstração. |
| `hipotese` | `/timeline`, `/recorte` | ninguém | Identificador da hipótese selecionada (`player-build`, `cdn-pop`, …). |
| `t` | `/timeline` | ninguém | Âncora ISO 8601 da linha do tempo (`timelineAnchor`). |
| `segmento` | `/recorte` | ninguém | Chave do recorte associado à hipótese. |
| `sinal` | `/timeline`, `/recorte` | ninguém | Identificador do sinal em desvio vindo de `/agora`. |

Exemplos emitidos pela interface:

```text
/hipoteses?demoState=error
/timeline?hipotese=player-build&t=2026-08-18T22:58:12Z
/recorte?hipotese=player-build&segmento=webos-3x-lg-nordeste-2026.3.0
/timeline?sinal=startup-errors-lg
/recorte?sinal=startup-errors-lg
```

### 2.2 Filtros de escopo compartilhados pela UI

&emsp;A barra de escopo das telas demonstrativas usa chips com estes `id`s. Quando
a API substituir o mock, o frontend espera poder enviá-los como query string
(hoje só Hipóteses encaminha `from`/`to`; os chips de escopo ainda não são
reenviados ao HTTP).

| Chip (`id`) | Rótulo | Query esperada no backend | Equivalente na API de eventos |
|---|---|---|---|
| `plataforma` | plataforma | `plataforma` ou `device_os` | `device_os` |
| `fabricante` | fabricante | `fabricante` ou `device_manufacturer` | `device_manufacturer` |
| `regiao` | região | `regiao` | não existe na API de eventos atual |
| `app` | app | `app` ou `app_version` | `app_version` |

Períodos da moldura operacional (estado React compartilhado, não query da
página): `15 min`, `30 min`, `3 h`, `24 h`. Em Hipóteses viram `from`/`to` ISO
8601 UTC.

## 3. Rotas HTTP já consumidas

### 3.1 `GET {NEXT_PUBLIC_API_URL}/api/v1/events`

&emsp;Cliente: `src/lib/events/api.ts`. Limitação fixa no cliente: `limit=100`.
Polling a cada 30 s. Somente os parâmetros preenchidos são enviados.

| Query | Origem na UI | Observação |
|---|---|---|
| `limit` | fixo `100` | A API aceita 1–500; default do backend é 50. |
| `event_name` | filtro de tipo (quando ligado) | Hoje o monitor aplica tipo também no cliente. |
| `device_os` | filtro de plataforma | |
| `device_manufacturer` | filtro de fabricante | |
| `from` | início do período | ISO 8601. Ausente se o período for “tudo”. |
| `to` | fim do período | ISO 8601. |

Resposta esperada (`EventsResponse`):

```json
{
  "items": [
    {
      "event_id": "…",
      "event_name": "error",
      "occurred_at": "2026-08-18T23:04:00Z",
      "ingested_at": "2026-08-18T23:04:02Z",
      "session_id": "…",
      "device_id": "…",
      "action": null,
      "app_bucket": null,
      "app_env": "production",
      "app_target": null,
      "app_version": "2026.3.0",
      "attributes": {},
      "clock_skew": false,
      "device_manufacturer": "LG",
      "device_model": "49LJ5550-SC",
      "device_model_year": 2017,
      "device_os": "webOS",
      "device_os_version": "3.8",
      "duration_ms": null,
      "route_path": "/live"
    }
  ],
  "next_cursor": null,
  "query": {
    "strategy": "gsi1",
    "scanned": 100,
    "returned": 40,
    "queries": 1
  }
}
```

&emsp;Status diferente de 2xx vira erro de consulta. O cliente **não** envia
`cursor`; só a primeira página é usada.

### 3.2 `GET {NEXT_PUBLIC_HYPOTHESES_API_URL}/api/v1/hypotheses`

&emsp;Cliente: `hipoteses/_lib/http-source.ts`, ativo somente com
`NEXT_PUBLIC_HYPOTHESES_SOURCE=api`. Polling a cada 30 s. Timeout tratado em
`408` e `504`.

| Query | Origem |
|---|---|
| `from` | início do período da moldura, ISO 8601 |
| `to` | fim do período, ISO 8601 |
| `{chave}={valor}` | cada entrada de `filters.scope` (hoje o adapter HTTP está pronto; a tela ainda não preenche `scope`) |

JSON esperado (`HypothesesReport` em `hipoteses/_lib/types.ts`):

```json
{
  "window": {
    "from": "2026-08-18T23:00:00Z",
    "to": "2026-08-18T23:11:00Z",
    "label": "20:00–20:11"
  },
  "generated": 4,
  "discarded": 11,
  "scope": [
    { "id": "plataforma", "label": "plataforma", "value": "webOS 3.x" }
  ],
  "summary": { "sessions": 41209, "trafficShare": 3.1, "sources": 6 },
  "hypotheses": [
    {
      "id": "player-build",
      "category": "Player / build",
      "title": "Rollout 2026.3.0 quebrou o fallback DASH→HLS em webOS 3.x",
      "score": 87,
      "confidence": "alta",
      "timelineAnchor": "2026-08-18T22:58:12Z",
      "segment": "webos-3x-lg-nordeste-2026.3.0",
      "factors": [
        {
          "id": "temporal",
          "label": "Coincidência temporal com deploy",
          "weight": 0.32,
          "contribution": 29.4,
          "rationale": "…"
        }
      ],
      "evidence": [
        { "source": "tsuru_event", "detail": "deploy globoplay-tv · 19:58:12" }
      ]
    }
  ],
  "discardedHypotheses": [
    {
      "id": "waf",
      "score": 14,
      "title": "DDoS / bloqueio de borda",
      "reason": "Cloud Armor sem pico de bloqueio na janela."
    }
  ]
}
```

Invariantes que a tela assume:

- `confidence` é exatamente `"alta"`, `"média"` ou `"baixa"`;
- em cada hipótese, a soma dos `weight` vale `1` e a soma das `contribution`
  vale o `score`;
- `trafficShare` é percentual (ex.: `3.1` → “3,1% do tráfego”).

Erros mapeados pelo adapter:

| Situação | Código interno | Estado de UI |
|---|---|---|
| Falha de rede | `ARG-HYP-OFFLINE` | `offline` |
| `408` / `504` | `ARG-HYP-HTTP-…` | `timeout` |
| Outro HTTP não 2xx | `ARG-HYP-HTTP-{status}` | `server` |
| Corpo não JSON | `ARG-HYP-INVALID-JSON` | `invalid-response` |

&emsp;Esta rota **não** existe na API Flask de eventos. Enquanto o motor não
estiver publicado, o build deve usar `HYPOTHESES_SOURCE=mock`.

## 4. Rotas da API de leitura que o frontend passará a esperar

&emsp;As telas Agora, Explorar, Comparar, Timeline e Recorte ainda usam fixtures.
Abaixo está o mapeamento para os endpoints **já implementados** em
`backend/src/telemetry/interfaces/http.py`. Sem esses contratos, as telas não
conseguem sair do mock.

Filtros cumulativos comuns (`EventFilters`), reutilizáveis em eventos, métricas
e histórico de dispositivo:

| Query | Uso no frontend |
|---|---|
| `session_id` | Timeline de uma sessão (Mariana / US06) |
| `device_id` | Histórico de aparelho legado (US08) |
| `event_name` | Abas de Explorar (`request`, `screen_view`, `video_view`, `session`, `vitals`, `error`) |
| `app_env` | ambiente |
| `app_target` | aplicação / alvo |
| `app_version` | chip `app` |
| `app_bucket` | bucket da app |
| `device_os` | chip `plataforma` |
| `device_manufacturer` | chip `fabricante` |
| `device_model` | agrupamento Modelo |
| `route_path` | agrupamento Rota |
| `from` / `to` | período da moldura, ISO 8601 |
| `limit` | página (eventos: 1–500; breakdown/facets: 1–100) |
| `cursor` | próxima página de eventos |

### 4.1 Por tela

#### Agora

| Recurso da UI | Rota esperada |
|---|---|
| Lista recente / sinais derivados de eventos | `GET /api/v1/events?from&to&event_name&device_os&device_manufacturer&app_version` |
| Sugestão de valores dos selects | `GET /api/v1/facets?field=event_name&field=device_os&field=device_manufacturer&field=app_version` |
| Volume e tendência por tipo | `GET /api/v1/metrics/timeseries?interval=1&from&to` (intervalo em minutos, 1–1440) |
| Concentração por fabricante/modelo | `GET /api/v1/metrics/breakdown?dimension=device_manufacturer` (ou `device_model`) |

&emsp;Não há endpoint de “degradação ativa” nem de baseline circadiano na API de
leitura. Título, ×baseline e “sem reclamação aberta” continuam conceituais até
o detector/motor expor um contrato próprio.

#### Explorar

| Recurso da UI | Rota esperada |
|---|---|
| Volumes por tipo de evento | `GET /api/v1/metrics/breakdown?dimension=event_name&from&to` |
| Série empilhada eventos × erros | `GET /api/v1/metrics/timeseries?interval=…&from&to` (erros: mesmo path com `event_name=error`) |
| Tabela agrupada | `GET /api/v1/metrics/breakdown?dimension={campo}` |
| Comparação com o dia anterior | `GET /api/v1/metrics/timeseries?compare=true&from&to` |
| Erros mais frequentes / busca | `GET /api/v1/events?event_name=error&from&to` (atributos em `attributes`) |
| Valores de filtro (RF10) | `GET /api/v1/facets?field=…` |

Mapeamento das dimensões da UI para `dimension`:

| Agrupar por (UI) | `dimension` |
|---|---|
| Modelo | `device_model` |
| Versão | `app_version` |
| Rota | `route_path` |
| UF | **não suportado** na API atual |
| ISP | **não suportado** na API atual |

`BREAKDOWN_FIELDS` aceitos hoje: `event_name`, `app_env`, `app_target`,
`app_version`, `app_bucket`, `device_os`, `device_manufacturer`, `device_model`,
`route_path`, `device_model_year`.

#### Comparar

| Recurso da UI | Rota esperada |
|---|---|
| Série atual × referência | `GET /api/v1/metrics/timeseries?interval=…&from&to&compare=true` |
| Significância / delta de métricas | mesmo timeseries; σ e “pico ao vivo anterior” **não** existem no backend atual |
| Cronologia de mudanças entre janelas | **não** existe na API de eventos (depende de change events / Tsuru) |

`compare=true` pede à API a série do período imediatamente anterior de mesma
duração. Referências “semana passada” e “último pico ao vivo” exigem o cliente
calcular outro par `from`/`to` ou um contrato novo.

#### Timeline

Dois modos distintos; só o primeiro já tem rota:

| Recurso da UI | Rota esperada |
|---|---|
| Linha do tempo de **uma sessão** (US06) | `GET /api/v1/sessions/{session_id}?limit=200` |
| Detalhe de um evento | `GET /api/v1/sessions/{session_id}/events/{event_id}` |
| Histórico de um aparelho | `GET /api/v1/devices/{device_id}?from&to` |
| Seis raias (NPAW, Prometheus, New Relic, Apollo, Tsuru, ServiceNow) | **não** existem na API de eventos; o mock é multi-fonte |

#### Recorte

| Recurso da UI | Rota esperada |
|---|---|
| Amostra de sessões/eventos do recorte | `GET /api/v1/events?device_os&device_manufacturer&app_version&event_name=error&from&to` |
| Participação por dimensão | `GET /api/v1/metrics/breakdown?dimension=device_model` |
| Mapa dispositivo × região | região **não** é dimensão da API atual |
| Lift tráfego vs erros | dois breakdowns (todos os eventos vs `event_name=error`); o frontend calcula a razão |

### 4.2 Contratos resumidos dos endpoints ainda não ligados

#### `GET /api/v1/sessions/{session_id}`

Query: `limit` (1–1000, default 200). 404 se a sessão não existir.

#### `GET /api/v1/sessions/{session_id}/events/{event_id}`

Sem query. 404 se o par sessão/evento não existir.

#### `GET /api/v1/devices/{device_id}`

Mesmos filtros de `/events` (incluindo `from`, `to`, `limit`, `cursor`). O
`device_id` do path substitui o da query.

#### `GET /api/v1/metrics/breakdown`

Query obrigatória: `dimension`. Opcionais: filtros comuns e `limit` (1–100,
default 20). 422 se `dimension` faltar ou for inválida.

#### `GET /api/v1/metrics/timeseries`

Query: filtros comuns, `interval` (minutos, 1–1440, default 60), `compare`
(`1`/`true`/`yes`). Sem `from`, o backend usa a janela padrão da API.

#### `GET /api/v1/facets`

Query: `field` repetível (default: `event_name`, `app_env`, `app_target`,
`device_os`, `device_manufacturer`) e `limit` (1–100, default 20). 422 se o
campo não estiver em `FACET_FIELDS`.

### 4.3 Rotas da API de leitura que o dashboard não usa

São da operação da API, não do Next.js:

| Método | Caminho | Papel |
|---|---|---|
| `GET` | `/` | Índice da API de leitura |
| `GET` | `/health/live` | Liveness |
| `GET` | `/health/ready` | Readiness (DynamoDB) |
| `GET` | `/docs` | Swagger UI |
| `GET` | `/openapi.json` | OpenAPI 3.1 |
| `GET` | `/favicon.ico` | 204 |

Ingestão **não** passa por estas rotas. Eventos entram pelo API Gateway de
ingest (`ARGUS_INGEST_URL`), fora do contrato do dashboard.

### 4.4 Mapa de ações da interface e chamadas necessárias

Esta seção transforma os controles visíveis do frontend em tarefas de
integração. A coluna “Ação HTTP” indica o que deve acontecer quando os dados
mockados forem substituídos por dados reais.

Legenda:

- **Local**: altera somente estado da interface ou navega para outra tela.
- **API existente**: o endpoint já está implementado no backend.
- **Contrato ausente**: a interface precisa de um novo endpoint ou de uma
  extensão do contrato atual.

#### 4.4.1 Controles compartilhados

| Controle | Ação atual | Ação HTTP necessária | Situação |
|---|---|---|---|
| Links Agora, Explorar, Comparar, Hipóteses, Timeline e Recorte | Navega entre as telas e preserva demoState | A tela de destino deve executar sua própria query com o escopo compartilhado | Local; integração pendente |
| Abrir menu de navegação no mobile | Abre o drawer lateral | Nenhuma | Local |
| Período 15 min, 30 min, 3 h ou 24 h | Atualiza o período global em React | Enviar from/to ISO 8601 em todas as queries da tela | Parcial; Explorar e Hipóteses usam o período, as demais ainda não |
| Alternar tema claro/escuro | Altera o tema no navegador | Nenhuma | Local |
| Botão Escopo no mobile | Abre o painel de filtros | Nenhuma diretamente; o fechamento deve disparar a query da tela | Local |
| Selects da barra de escopo | Atualizam filtros da tela quando existe callback | Mapear plataforma para device_os, fabricante para device_manufacturer, app para app_version e região para um contrato regional | Parcial; várias telas usam valores mockados |
| Limpar filtros / limpar | Remove ou restaura os filtros da tela | Refazer a query sem os filtros removidos | Parcial; atualmente apenas estado local |
| Voltar ao estado normal | Remove demoState da URL | Nenhuma | Local |
| Rever filtros em estado vazio ou erro | Restaura o conjunto inicial de filtros | Refazer a query após a restauração | Local hoje; deve invalidar a query real |
| Tentar novamente / Atualizar agora | Refaz a consulta atual | Repetir a mesma requisição, mantendo from, to e escopo | API existente quando a tela estiver ligada |
| Continuar com último resultado | Mantém os dados válidos anteriores | Nenhuma nova chamada; registrar que a tela está stale | Local |

O período e o escopo devem ser tratados como estado de investigação, não apenas
como estado visual. Para preservar o recorte ao navegar, recomenda-se
serializar os valores na URL ou em um estado compartilhado que seja consumido
por todas as telas. Atualmente apenas demoState é preservado nos links.

#### 4.4.2 Tela Agora

Arquivo principal:
apps/basica/frontend/src/app/(operations)/agora/_components/agora-screen.tsx

| Controle ou ação | Dados que devem mudar | Endpoint necessário | Parâmetros principais | Situação atual |
|---|---|---|---|---|
| Select plataforma | Escopo dos sinais e da degradação | GET /api/v1/events, /api/v1/metrics/timeseries e /api/v1/metrics/breakdown | device_os, from, to | Mock/local |
| Select fabricante | Escopo dos sinais e da degradação | Os mesmos endpoints | device_manufacturer, from, to | Mock/local |
| Select região | Escopo regional | Novo contrato regional ou fonte externa | uf/region, from, to | Sem suporte de ponta a ponta |
| Select app | Escopo por versão | Os mesmos endpoints | app_version, from, to | Mock/local |
| Restaurar recorte principal | Volta para LG, webOS 3.x, Nordeste e 2026.3.0 | Refazer todas as queries da tela | Escopo inicial e janela atual | Local |
| Ver detalhes de um sinal | Abre drawer com valor atual, baseline, limiar, tendência e interpretação | GET /api/v1/anomalies ou novo endpoint de detalhe de sinal | signal_id, run_id e/ou from/to | O drawer existe, mas os dados vêm de mock |
| Ver hipóteses ranqueadas | Navega para /hipoteses | GET /api/v1/hypotheses na tela de destino | from, to e escopo | Link existe; endpoint Flask não existe |
| Abrir na Timeline | Navega com sinal, hipótese ou âncora temporal | GET /api/v1/sessions/{session_id} para sessão ou novo endpoint multi-fonte | sinal, hipotese, t, session_id | Link existe; Timeline ainda usa mock |
| Ver no Recorte | Navega para o recorte associado | GET /api/v1/events e breakdowns na tela de destino | sinal, hipotese, segmento, from/to | Link existe; Recorte ainda usa mock |
| Outras degradações abertas | Lista degradações e severidade | GET /api/v1/anomalies ou novo endpoint de degradações | run_id, from, to, limit | Backend possui anomalies, mas não entrega necessariamente o contrato visual completo |

Dados que o backend ainda precisa fornecer para reproduzir o cabeçalho de Agora:

- título da degradação ativa;
- valor atual e baseline;
- multiplicador em relação ao baseline;
- limiar e número de buckets consecutivos;
- sessões impactadas;
- tempo desde a detecção;
- estado de reclamações/incidentes;
- lista de sinais ordenada por impacto.

Esses dados não podem ser derivados apenas de GET /api/v1/events. É necessário
um contrato de detector/anomalias ou uma camada de agregação.

#### 4.4.3 Tela Explorar

Arquivo principal:
apps/basica/frontend/src/app/(operations)/explorar/_components/explorar-screen.tsx

| Controle ou ação | Dados que devem mudar | Endpoint necessário | Parâmetros principais | Situação atual |
|---|---|---|---|---|
| Remover filtro pelo botão X | Escopo ativo | Todas as queries da tela | Remover a chave correspondente | Local; deve refazer queries |
| Botão + filtro | Abre opções de filtros removidos | Nenhum ao abrir; consultar facets para opções reais | field repetível | Menu local; facets não é consumido |
| Selecionar filtro inativo | Adiciona o filtro ao escopo | GET /api/v1/facets e queries do conteúdo | field, limite e valor selecionado | Local/mock |
| Limpar escopo | Remove todos os filtros | Refazer timeseries, breakdown e events sem o escopo | from, to | Local |
| Como usar / Ocultar guia | Mostra ou esconde a orientação | Nenhuma | — | Local |
| Cards de tipo de evento | Troca request, screen_view, video_view, session, vitals ou error | GET /api/v1/metrics/timeseries e GET /api/v1/metrics/breakdown | event_name, interval, from, to | Mock |
| Presets de período | Troca a janela temporal | GET /api/v1/metrics/timeseries | interval, from, to | O estado existe, mas a query é mock |
| Alça início da janela | Ajusta from | GET /api/v1/metrics/timeseries | from atualizado, to, interval | Local |
| Alça fim da janela | Ajusta to | GET /api/v1/metrics/timeseries | from, to atualizado, interval | Local |
| Alternar Modelo | Tabela por modelo | GET /api/v1/metrics/breakdown | dimension=device_model | Backend existente; adapter ausente |
| Alternar Versão | Tabela por versão | GET /api/v1/metrics/breakdown | dimension=app_version | Backend existente; adapter ausente |
| Alternar Rota | Tabela por rota | GET /api/v1/metrics/breakdown | dimension=route_path | Backend existente; adapter ausente |
| Alternar UF | Tabela por UF | GET /api/v1/metrics/breakdown | dimension=uf | Whitelist e dados precisam ser confirmados |
| Alternar ISP | Tabela por ISP | GET /api/v1/metrics/breakdown | dimension=isp | Whitelist e dados precisam ser confirmados |
| Busca por nome de erro | Lista de erros frequentes | GET /api/v1/events?event_name=error ou novo breakdown por atributo | event_name=error, from, to, texto em attributes | Busca atual é local sobre mock |

O endpoint de timeseries já retorna count e by_event_name. O frontend deverá
transformar esses campos em volume total e volume com erro. A tabela de
distribuição exige uma combinação de breakdown do total e breakdown com
event_name=error para calcular taxa de erro por grupo.

O campo “vs. ontem” exige uma segunda janela ou compare=true. A busca por
códigos como dash_shaka_playback:6_6002 não é atendida por dimension no contrato
atual; se a busca precisar ser server-side, o backend deve expor uma dimensão
segura de código/categoria de erro ou um endpoint específico.

#### 4.4.4 Tela Comparar

Arquivo principal:
apps/basica/frontend/src/app/(operations)/comparar/_components/comparar-content.tsx

| Controle ou ação | Dados que devem mudar | Endpoint necessário | Parâmetros principais | Situação atual |
|---|---|---|---|---|
| Ontem, mesmo horário | Série e valores da janela do dia anterior | GET /api/v1/metrics/timeseries | from, to, compare=true ou duas janelas explícitas | Mock |
| Semana passada | Série e valores da mesma faixa da semana anterior | GET /api/v1/metrics/timeseries | from, to da janela histórica | Mock; frontend precisa calcular a janela |
| Última janela estável | Série de uma janela classificada como estável | Novo contrato de referências ou timeseries com janela descoberta | reference_id, from, to | Ausente |
| Pico ao vivo anterior | Série do pico ao vivo anterior | Novo endpoint de referências/live-events ou janela calculada pelo cliente | event_key/reference_id, from, to | Ausente |
| Gráfico atual x referência | Buckets atuais, referência e pontos fora do envelope | GET /api/v1/metrics/timeseries | interval, from, to, compare | Backend entrega série e comparação básica |
| Métricas comparadas | Valor atual, valor histórico, delta e total | GET /api/v1/metrics/timeseries e/ou breakdown | Filtros da moldura | Mock |
| Significância sigma | Desvio-padrão por métrica | Novo contrato estatístico | baseline, stddev/sigma, reference_id | Não existe na API de eventos |
| O que mudou entre janelas | Deploy, autoscale, WAF e mudanças de infraestrutura | Novo GET /api/v1/changes ou integração com fontes de mudança | from, to, scope | Ausente |

compare=true no backend significa “janela imediatamente anterior de mesma
duração”. Isso não é suficiente para descobrir sozinho “semana passada”,
“última janela estável” ou “pico ao vivo anterior”. Essas referências precisam
de cálculo no frontend ou de um contrato de catálogo de referências.

#### 4.4.5 Tela Hipóteses

Arquivos principais:
apps/basica/frontend/src/app/(operations)/hipoteses/_components/hipoteses-screen.tsx
apps/basica/frontend/src/app/(operations)/hipoteses/_lib/http-source.ts

| Controle ou ação | Dados que devem mudar | Endpoint necessário | Parâmetros principais | Situação atual |
|---|---|---|---|---|
| Carregar a tela | Relatório, ranking, escopo e resumo | GET /api/v1/hypotheses | from, to e filtros de scope | Adapter HTTP pronto; endpoint não existe na API Flask |
| Selecionar uma hipótese | Painel de score, fatores e evidências | Nenhuma nova chamada se o relatório já trouxer o detalhe | hypothesis_id local | Local |
| Tentar novamente | Reexecuta o relatório | GET /api/v1/hypotheses | Mesmos filtros da tentativa anterior | Implementado no adapter/query |
| Abrir na timeline | Navega com hipótese e âncora | Query da Timeline | hipotese, t | Link existe; parâmetros ainda não são lidos |
| Ver recorte afetado | Navega com hipótese e segmento | Queries do Recorte | hipotese, segmento | Link existe; parâmetros ainda não são lidos |
| Feedback da hipótese | Não existe botão na tela atual | POST /api/v1/hypotheses/{hypothesis_id}/feedback | agree, partial ou disagree | Contrato futuro; sem UI |

Os selects de escopo exibidos a partir do relatório ainda não possuem
onFilterChange na página de Hipóteses. Portanto, eles aparecem como controles,
mas não alteram a consulta. Para torná-los funcionais, a tela precisa manter
scope no estado/queryKey e reenviar os valores ao adapter.

#### 4.4.6 Tela Timeline

Arquivo principal:
apps/basica/frontend/src/app/(operations)/timeline/_components/timeline-content.tsx

| Controle ou ação | Dados que devem mudar | Endpoint necessário | Parâmetros principais | Situação atual |
|---|---|---|---|---|
| Abrir Timeline por sessão | Eventos cronológicos e resumo | GET /api/v1/sessions/{session_id} | session_id, limit=200 | Backend existente; não consumido |
| Abrir detalhe de evento | Evento completo | GET /api/v1/sessions/{session_id}/events/{event_id} | session_id, event_id | Backend existente; não há botão dedicado na Timeline atual |
| Abrir histórico de aparelho | Eventos do aparelho no período | GET /api/v1/devices/{device_id} | device_id, from, to, limit, cursor | Backend existente; não consumido |
| Timeline de seis fontes | Deploy, QoE, CDN, backend, identidade e incidentes | Novo endpoint multi-fonte ou composição das APIs gold | sinal/hipótese, from, to | Mock |
| Âncora da hipótese | Centraliza o gráfico no instante indicado | O endpoint multi-fonte deve aceitar a âncora | hipotese, t | Parâmetros são emitidos, mas não lidos |
| Fechar ou retornar da tela | Navegação normal | Nenhuma | — | Local |

Os filtros exibidos no ScreenFrame da Timeline são montados com valores mockados
e sem callback de alteração. Eles devem ser conectados ao estado de escopo antes
da troca da fonte de dados.

#### 4.4.7 Tela Recorte

Arquivo principal:
apps/basica/frontend/src/app/(operations)/recorte/_components/recorte-content.tsx

| Controle ou ação | Dados que devem mudar | Endpoint necessário | Parâmetros principais | Situação atual |
|---|---|---|---|---|
| Select de região | Heatmap e indicadores do recorte | Novo contrato regional ou breakdown/crosstab | region/uf, from, to | Local/mock |
| Participação por modelo | Volume e taxa por dispositivo | GET /api/v1/metrics/breakdown, duas consultas total/erro | dimension=device_model, filtros do recorte | Backend existente; adapter ausente |
| Mapa dispositivo x região | Matriz de taxa de erro | Novo GET de crosstab ou endpoint regional | dimensions=device_model,uf; event_name=error | Não existe na API atual |
| Lift tráfego x erros | Percentual de tráfego e percentual de erros | Dois GET /api/v1/metrics/breakdown | uma consulta total e outra com event_name=error | Pode ser calculado no frontend |
| Amostra de sessões | Eventos representativos do recorte | GET /api/v1/events | device_os, device_manufacturer, app_version, event_name=error, from, to, limit | Backend existente; não consumido |
| Clique no resumo da sessão | Abre o drawer da sessão | GET /api/v1/sessions/{session_id} | session_id, limit=200 | Drawer atual usa fixture |
| Abrir sessão | Mesmo comportamento do clique no resumo | GET /api/v1/sessions/{session_id} | session_id | Drawer atual usa fixture |
| Fechar drawer da sessão | Fecha detalhe e devolve foco | Nenhuma | — | Local |
| Ajustes do recorte | Alteram a população e recalculam especificidade/cobertura | Refazer events e métricas com filtros alterados | app, route_path, device_os, manufacturer, região | Atualmente são cartões informativos sem ação |
| Hipótese/segmento/sinal na URL | Inicializa o recorte vindo de outra tela | O backend deve receber o escopo correspondente | hipotese, segmento, sinal | Emitido pelos links, mas não lido |

O heatmap exige uma agregação por duas dimensões. Não é possível produzi-lo
com uma única chamada atual de breakdown, que aceita somente uma dimension por
vez. O contrato regional deve definir nomes, valores, nulos e a fórmula da taxa.

#### 4.4.8 Monitor legado na rota raiz

O componente
apps/basica/frontend/src/app/(operations)/(dashboard)/_components/dashboard-screen.tsx
mantém um monitor conectado a GET /api/v1/events, mas a página raiz redireciona
para /agora. Ele não deve ser confundido com a experiência atual das seis
etapas.

Se esse monitor for reativado, seus controles precisam ser tratados assim:

| Controle | Ação HTTP |
|---|---|
| Período | Refazer GET /api/v1/events com from/to |
| Plataforma, fabricante e tipo de evento | Enviar device_os, device_manufacturer e event_name; hoje parte do filtro é local |
| Busca textual | Continuar local ou criar busca por attributes |
| Limpar | Refazer a consulta sem os filtros |
| Linha de evento selecionada | Usar GET /api/v1/sessions/{session_id}/events/{event_id} para detalhe completo |
| Ver atributos recebidos | Pode usar o payload já retornado; não exige nova rota |

## 4.5 Adaptadores frontend que precisam ser criados

Para evitar que cada tela monte URLs e trate erros de forma diferente, o
frontend deve centralizar os seguintes clientes:

| Adapter sugerido | Endpoint | Consumidores |
|---|---|---|
| fetchEvents | GET /api/v1/events | Agora, Explorar, Recorte e monitor legado |
| fetchFacets | GET /api/v1/facets | Barra de escopo e filtros de Explorar |
| fetchBreakdown | GET /api/v1/metrics/breakdown | Agora, Explorar e Recorte |
| fetchTimeseries | GET /api/v1/metrics/timeseries | Agora, Explorar e Comparar |
| fetchSessionTimeline | GET /api/v1/sessions/{session_id} | Timeline e Recorte |
| fetchEventDetail | GET /api/v1/sessions/{session_id}/events/{event_id} | Detalhe de evento |
| fetchDeviceHistory | GET /api/v1/devices/{device_id} | Timeline e Recorte |
| fetchHypotheses | GET /api/v1/hypotheses | Hipóteses; já existe com seleção mock/api |
| fetchClock | GET /api/v1/clock | Cabeçalho “Ao vivo”, se o relógio virtual for adotado |
| fetchGoldSeries | GET /api/v1/series | Timeline e Comparar, se as séries gold forem a fonte escolhida |
| fetchSources | GET /api/v1/sources | Resumos de fontes e estado parcial |
| fetchIncidents | GET /api/v1/incidents | Incidentes e referências históricas |
| fetchLiveEvents | GET /api/v1/live-events | Referência “pico ao vivo anterior” |
| fetchAnomalies | GET /api/v1/anomalies | Sinais e degradações, após o detector |

Todos os adapters devem:

1. receber um objeto tipado de filtros;
2. remover parâmetros vazios;
3. codificar valores com URLSearchParams;
4. aceitar AbortSignal;
5. diferenciar erro HTTP, timeout, rede indisponível e JSON inválido;
6. validar o formato mínimo da resposta antes de renderizar;
7. usar queryKey que inclua período, escopo e seleção ativa;
8. expor next_cursor quando a tela puder paginar.

## 4.6 Checklist de implementação por tela

### Agora

- [ ] Criar query de eventos/métricas com período e escopo.
- [ ] Criar query de facets para os quatro filtros.
- [ ] Definir contrato de sinais/anomalias e degradação ativa.
- [ ] Ligar “Ver detalhes” ao payload real.
- [ ] Preservar o escopo nos links para Hipóteses, Timeline e Recorte.

### Explorar

- [ ] Criar query de timeseries.
- [ ] Criar query de breakdown por dimensão.
- [ ] Calcular volume, taxa de erro e variação contra a referência.
- [ ] Ligar busca de erros a events ou a um endpoint de erro agregado.
- [ ] Habilitar UF e ISP somente quando houver dados e contrato.
- [ ] Refazer as queries ao mover as alças temporais.

### Comparar

- [ ] Criar query para a janela atual.
- [ ] Criar query para cada referência.
- [ ] Definir contrato de sigma/envelope histórico.
- [ ] Definir catálogo de referências estável e pico ao vivo.
- [ ] Criar integração de change events.

### Hipóteses

- [ ] Publicar ou configurar o serviço de GET /api/v1/hypotheses.
- [ ] Ligar filtros de escopo ao estado e ao adapter.
- [ ] Validar invariantes de score, peso, contribuição e confidence.
- [ ] Ler hipotese e t na Timeline.
- [ ] Ler hipotese e segmento no Recorte.
- [ ] Criar feedback somente quando houver UI e autorização para escrita.

### Timeline

- [ ] Implementar modo sessão com session_id.
- [ ] Implementar detalhe de evento.
- [ ] Definir a fonte das seis raias.
- [ ] Implementar âncora temporal e sinal selecionado.
- [ ] Substituir o mock por dados atribuídos à fonte original.

### Recorte

- [ ] Implementar eventos filtrados do recorte.
- [ ] Implementar breakdown total e de erros.
- [ ] Definir e implementar heatmap de duas dimensões.
- [ ] Implementar abertura de sessão real.
- [ ] Tornar os ajustes do recorte ações reais ou marcá-los explicitamente como informativos.

## 4.7 Critério de conclusão da integração

Uma tela só deve ser considerada integrada quando:

- cada controle que altera dados atualiza o estado de filtros;
- o estado de filtros aparece na queryKey;
- a chamada HTTP contém os parâmetros equivalentes;
- loading, vazio, erro, stale e refreshing são tratados;
- os dados exibidos vêm da resposta da API, não de fixture;
- links entre telas preservam o contexto necessário;
- a API de backend possui contrato documentado para todos os campos exibidos;
- existe teste ou verificação reproduzível para a ação principal da tela.

## 5. Rotas do motor de hipóteses ainda não consumidas

&emsp;Definidas em [hipoteses.md](./hipoteses.md) §14.2. O frontend hoje só lista
o relatório. Detalhe por id e feedback humano são o próximo contrato.

| Método | Caminho | Papel | Estado no frontend |
|---|---|---|---|
| `GET` | `/api/v1/hypotheses` | Relatório da janela | Adapter HTTP pronto |
| `GET` | `/api/v1/hypotheses/{hypothesis_id}` | Detalhe, evidências, âncoras | Não chamado; o relatório já traz detalhe inline |
| `POST` | `/api/v1/hypotheses/{hypothesis_id}/feedback` | `agree` / `partial` / `disagree` | Sem UI |

Query prevista na arquitetura para a listagem: `from`, `to`, `status`
(`generated`, …), `type` (família). O cliente atual envia só `from`, `to` e
escopo livre.

## 6. Lacunas de contrato (API atual vs telas)

| Necessidade da UI | Na API de eventos hoje |
|---|---|
| Região / UF / ISP | Ausente |
| Baseline, σ, degradação nomeada | Ausente (detector) |
| Evento ao vivo / pico editorial como referência | Ausente |
| Change events (deploy, autoscale, WAF) | Ausente nesta API |
| Fontes NPAW, Prometheus, New Relic, Apollo, Tsuru, ServiceNow | Ausente; só telemetria normalizada do pipeline |
| Relatório de hipóteses | Ausente nesta API; outro host |

## 7. Referências

- Código das páginas: `apps/basica/frontend/src/app/(operations)/`
- Cliente de eventos: `apps/basica/frontend/src/lib/events/api.ts`
- Cliente de hipóteses: `apps/basica/frontend/src/app/(operations)/hipoteses/_lib/`
- Rotas Flask: `apps/basica/backend/src/telemetry/interfaces/http.py`
- OpenAPI gerada: `GET /openapi.json` no host da API de leitura
- [Interface gráfica](./frontend.md)
- [Arquitetura de hipóteses](./hipoteses.md)
- [Requisitos](./requisitos.md)
- [Entendimento de UX](./entendimento_ux.md)
