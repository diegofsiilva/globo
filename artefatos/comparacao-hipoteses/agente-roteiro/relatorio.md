# Lote do piloto de hipoteses com IA

Resultados experimentais. Uma hipotese aqui e explicacao candidata, nao
causa confirmada; a leitura e humana.

Casos: 3. evidencia insuficiente: 1, hipotese: 2

| Caso | Desfecho | Chamadas | Fatos citados | Contestada | Observacao |
|---|---|---|---|---|---|
| caso-01-deploy | hipotese | 5 | 14 | sim | - |
| caso-02-borda | hipotese | 5 | 12 | sim | - |
| caso-03-fonte-atrasada | evidencia insuficiente | 4 | 0 | nao | - |

## caso-01-deploy

- Desfecho: **hipotese**
- Recorte: `synthetic:101:2db402383094d32e` em `2026-08-20T20:15:00+00:00`
- Digest: `2163e85b3f0516af`
- Modelo: `caso-01-deploy`, prompt `2.2.0`

**Causa candidata.** Possivel regressao apos o deploy do playback: o erro 5xx sobe a partir das 19h

Evidencias a favor: 3. Contrarias: 1. Lacunas: 2.

Consultas:
- `inventariar_fatos` {'limit': 200} -> 4 itens
- `consultar_serie` {'source': 'prometheus', 'entity': 'playback', 'metric': 'http_5xx_rate', 'inicio': '2026-08-20T17:00:00Z', 'fim': '2026-08-20T20:00:00Z', 'limit': 200} -> 13 itens
- `consultar_serie` {'source': 'newrelic', 'entity': 'playback', 'metric': 'apdex', 'inicio': '2026-08-20T17:00:00Z', 'fim': '2026-08-20T20:00:00Z', 'limit': 200} -> 13 itens
- `consultar_contexto` {'inicio': '2026-08-20T17:00:00Z', 'fim': '2026-08-20T20:00:00Z', 'entity': 'playback', 'kinds': ['context'], 'limit': 200} -> 1 itens
- `consultar_serie` {'source': 'rpaas', 'entity': 'playback.video.globo.com', 'metric': 'requests_total', 'inicio': '2026-08-20T17:00:00Z', 'fim': '2026-08-20T20:00:00Z', 'limit': 200} -> 13 itens

## caso-02-borda

- Desfecho: **hipotese**
- Recorte: `synthetic:102:ae91e7cf3fbb5d5d` em `2026-08-20T20:15:00+00:00`
- Digest: `8883086fe9517a33`
- Modelo: `caso-02-borda`, prompt `2.2.0`

**Causa candidata.** Possivel bloqueio na borda: o 4xx do RPaaS sobe a partir das 19h sem efeito no backend

Evidencias a favor: 2. Contrarias: 1. Lacunas: 3.

Consultas:
- `consultar_serie` {'source': 'rpaas', 'entity': 'playback.video.globo.com', 'metric': 'http_4xx_rate', 'inicio': '2026-08-20T17:00:00Z', 'fim': '2026-08-20T20:00:00Z', 'limit': 200} -> 13 itens
- `consultar_serie` {'source': 'cloudarmor', 'entity': 'edge', 'metric': 'blocked_requests', 'inicio': '2026-08-20T17:00:00Z', 'fim': '2026-08-20T20:00:00Z', 'limit': 200} -> 13 itens
- `consultar_serie` {'source': 'newrelic', 'entity': 'playback', 'metric': 'apdex', 'inicio': '2026-08-20T17:00:00Z', 'fim': '2026-08-20T20:00:00Z', 'limit': 200} -> 13 itens
- `consultar_serie` {'source': 'prometheus', 'entity': 'playback', 'metric': 'http_5xx_rate', 'inicio': '2026-08-20T17:00:00Z', 'fim': '2026-08-20T20:00:00Z', 'limit': 200} -> 13 itens
- `consultar_contexto` {'inicio': '2026-08-20T17:00:00Z', 'fim': '2026-08-20T20:00:00Z', 'entity': 'globo', 'kinds': ['context'], 'limit': 200} -> 1 itens

## caso-03-fonte-atrasada

- Desfecho: **evidencia insuficiente**
- Recorte: `synthetic:103:f21ef51161bddac9` em `2026-08-20T20:15:00+00:00`
- Digest: `7d6f5c466892350f`
- Modelo: `caso-03-fonte-atrasada`, prompt `2.2.0`

Lacunas declaradas:
- quebra do erro por UF: a serie existe, mas o ultimo dado disponivel e de 19/08 (ainda_indisponivel)
- deploy ou evento operacional na janela (sem_dado)
- metricas internas do backend, como apdex do playback (sem_dado)

Consultas:
- `consultar_serie` {'source': 'prometheus', 'entity': 'playback', 'metric': 'http_5xx_rate', 'inicio': '2026-08-20T17:00:00Z', 'fim': '2026-08-20T20:00:00Z', 'limit': 200} -> 13 itens
- `consultar_serie` {'source': 'npaw_geo', 'entity': 'globo', 'metric': 'error_rate', 'dimension_type': 'uf', 'dimension_value': 'SP', 'inicio': '2026-08-20T17:00:00Z', 'fim': '2026-08-20T20:00:00Z', 'limit': 200} -> 0 itens (sem_fatos_no_recorte_consultado)
- `consultar_contexto` {'inicio': '2026-08-20T17:00:00Z', 'fim': '2026-08-20T20:00:00Z', 'entity': 'playback', 'kinds': ['context'], 'limit': 200} -> 0 itens (sem_fatos_no_recorte_consultado)
- `consultar_serie` {'source': 'rpaas', 'entity': 'playback.video.globo.com', 'metric': 'requests_total', 'inicio': '2026-08-20T17:00:00Z', 'fim': '2026-08-20T20:00:00Z', 'limit': 200} -> 13 itens
