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
