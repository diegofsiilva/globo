# Análise de rotas: backend x frontend

## Objetivo

Este documento compara as rotas esperadas pelo frontend com as rotas
implementadas no backend e registra o que ainda precisa ser integrado ou
desenvolvido.

Escopo analisado:

- Backend Flask em `apps/basica/backend`.
- Frontend Next.js em `apps/basica/frontend`.
- Contrato de rotas esperado pelo frontend fornecido como referência.

Esta análise não altera o contrato atual da API nem implementa as lacunas.

## Resumo executivo

O backend já possui as principais rotas de leitura de eventos, investigação e
métricas. O maior problema atual é que o frontend ainda não utiliza essas
rotas: somente `GET /api/v1/events` é chamado de fato.

A rota principal que está ausente no backend é:

```text
GET /api/v1/hypotheses
```

Ela deve pertencer a um motor de hipóteses separado ou continuar sendo atendida
por dados mockados até que esse serviço seja publicado.

## 1. Rotas de navegação do frontend

| Rota do frontend | Situação | Observação |
|---|---|---|
| `/` | Parcialmente divergente | Renderiza o dashboard diretamente; o contrato previa redirecionamento para `/agora`. |
| `/agora` | Existe | Ainda renderiza o mesmo dashboard genérico. |
| `/explorar` | Existe | Não possui consulta própria de métricas. |
| `/comparar` | Existe | Não possui consulta própria de comparação. |
| `/hipoteses` | Existe | Não possui tela/adapter de hipóteses. |
| `/timeline` | Existe | Não possui consulta de sessão, evento ou dispositivo. |
| `/recorte` | Existe | Não possui consulta própria do recorte. |

Embora as seis URLs estejam declaradas, todas passam por
`src/app/[section]/page.tsx` e montam o mesmo `DashboardPage`. Portanto, a
navegação existe visualmente, mas as funcionalidades específicas de cada tela
ainda não foram implementadas.

## 2. Rotas de leitura já implementadas no backend

### 2.1 Eventos e investigação

| Endpoint | Backend | Frontend atual | O que precisa ser feito |
|---|---|---|---|
| `GET /api/v1/events` | Implementado | Consumido | Expandir o envio de filtros e, quando necessário, paginação. |
| `GET /api/v1/sessions/{session_id}` | Implementado | Não consumido | Ligar à Timeline para exibir os eventos cronológicos e o resumo da sessão. |
| `GET /api/v1/sessions/{session_id}/events/{event_id}` | Implementado | Não consumido | Usar no detalhe de um evento selecionado, se necessário. |
| `GET /api/v1/devices/{device_id}` | Implementado | Não consumido | Ligar ao histórico de aparelho da Timeline/Recorte. |

As rotas estão definidas em `backend/src/telemetry/interfaces/http.py` e usam
os casos de uso de `backend/src/telemetry/application/use_cases.py`.

### 2.2 Métricas e filtros

| Endpoint | Backend | Frontend atual | O que precisa ser feito |
|---|---|---|---|
| `GET /api/v1/facets?field=...` | Implementado | Não consumido | Carregar opções dos filtros pela API. |
| `GET /api/v1/metrics/breakdown?dimension=...` | Implementado | Não consumido | Usar em Agora, Explorar e Recorte para agrupamentos e distribuição. |
| `GET /api/v1/metrics/timeseries?...` | Implementado | Não consumido | Usar nos gráficos de volume, tendência e comparação. |

O backend aceita filtros cumulativos como `event_name`, `app_version`,
`device_os`, `device_manufacturer`, `device_model`, `route_path`, `from`
e `to`. Também possui paginação por `cursor` em consultas de eventos.

## 3. Rota ausente: hipóteses

### `GET /api/v1/hypotheses`

Essa rota não está registrada no Flask e não existe adapter correspondente no
frontend atual.

O contrato esperado prevê:

- janela analisada (`from`, `to` e `label`);
- quantidade de hipóteses geradas e descartadas;
- escopo aplicado;
- resumo de sessões, tráfego e fontes;
- hipóteses ranqueadas com `score`, `confidence`, fatores e evidências;
- hipóteses descartadas e respectivos motivos.

Implementação necessária:

1. Definir se o endpoint ficará em um serviço separado ou na API Flask.
2. Publicar o contrato JSON `HypothesesReport`.
3. Implementar autenticação, timeout e tratamento de erros, se for um serviço separado.
4. Criar o adapter no frontend.
5. Trocar a fonte `mock` por `api` somente quando o serviço estiver disponível.

As rotas futuras de detalhe e feedback também não estão implementadas:

```text
GET  /api/v1/hypotheses/{hypothesis_id}
POST /api/v1/hypotheses/{hypothesis_id}/feedback
```

## 4. O que o frontend atual realmente envia

O cliente `src/lib/events-api.ts` possui suporte tipado para `eventName`,
`platform`, `manufacturer`, `from` e `to`, mas o `EventMonitor` chama
`fetchEvents` apenas com o período.

Consequentemente:

- período: enviado ao backend como `from` e `to`;
- tipo de evento: filtrado somente no navegador;
- plataforma: filtrada somente no navegador;
- fabricante: filtrado somente no navegador;
- versão da aplicação: não é enviada como filtro;
- busca textual: filtrada somente no navegador;
- status “atenção/normal”: calculado somente no navegador.

Para integrar corretamente:

1. Incluir os filtros ativos na chave e na função de consulta do React Query.
2. Enviar `event_name`, `device_os`, `device_manufacturer` e `app_version`
   ao backend quando aplicável.
3. Definir se a busca textual continuará local ou se será criado filtro por
   atributos.
4. Implementar paginação usando `next_cursor` quando a tela precisar de mais
   que os 100 eventos atuais.

## 5. Lacunas de dados e contrato

### 5.1 Região, UF e ISP

As telas esperam análise por região/UF/ISP, mas o fluxo atual não oferece isso
de ponta a ponta.

- O backend lista `uf` e `isp` entre as colunas permitidas para agrupamento.
- `EventFilters` não possui campos `uf` e `isp`.
- `filters_from_query()` não extrai `uf`, `isp` ou `regiao` da URL.
- As migrações indicam que esses valores ainda podem estar nulos nos eventos de
  telemetria.

É necessário decidir e implementar uma das opções:

1. adicionar esses campos ao contrato de eventos e preenchê-los no pipeline;
2. consultar uma fonte regional separada;
3. manter os controles da interface desabilitados até existir uma fonte válida.

Também é necessário padronizar os nomes dos parâmetros. A interface usa
`plataforma`, `fabricante`, `regiao` e `app`, enquanto a API usa
principalmente `device_os`, `device_manufacturer`, `uf`, `isp` e
`app_version`.

### 5.2 Detecção e baseline

As telas esperam informações que não são fornecidas pelas rotas básicas de
eventos:

- baseline circadiano;
- desvio padrão ou sigma;
- degradação ativa nomeada;
- referência de pico ao vivo anterior;
- eventos de mudança, deploy, autoscale ou WAF.

`GET /api/v1/anomalies` já existe na camada gold, mas depende do detector e
pode retornar uma lista vazia. Essa rota não substitui sozinha o contrato de
degradação e baseline esperado pelo frontend.

### 5.3 Timeline de múltiplas fontes

O backend possui `/api/v1/series` e `/api/v1/sources` na camada gold, mas
ainda não há uma rota que entregue diretamente as seis raias esperadas:

```text
NPAW, Prometheus, New Relic, Apollo, Tsuru e ServiceNow
```

Será necessário transformar as séries gold no frontend ou definir um contrato
específico de timeline multi-fonte.

## 6. Comparação de períodos

`GET /api/v1/metrics/timeseries?compare=true` já compara a janela atual com a
janela imediatamente anterior de mesma duração.

Isso atende à comparação básica, mas não cobre diretamente:

- semana passada;
- último pico ao vivo;
- cronologia de mudanças entre as janelas.

Para semana passada, o frontend pode calcular outro par de `from`/`to`. Para
o último pico e mudanças, é necessário um endpoint ou fonte adicional.

## 7. Rotas auxiliares disponíveis no backend

As seguintes rotas já existem, mas não são utilizadas pelo frontend atual:

| Endpoint | Finalidade |
|---|---|
| `GET /api/v1/clock` | Relógio virtual da simulação. |
| `GET /api/v1/series` | Séries agregadas da camada gold. |
| `GET /api/v1/sources` | Fontes disponíveis e recência. |
| `GET /api/v1/incidents` | Janelas rotuladas de incidentes. |
| `GET /api/v1/live-events` | Calendário de transmissões ao vivo. |
| `GET /api/v1/anomalies` | Resultado disponível do detector. |
| `GET /health/live` | Liveness da aplicação. |
| `GET /health/ready` | Readiness com verificação do banco. |
| `GET /docs` | Swagger UI. |
| `GET /openapi.json` | Especificação OpenAPI. |

## 8. Ordem recomendada de implementação

### Prioridade 1 — Integrar o que já existe

1. Separar a renderização das seis telas.
2. Criar clientes frontend para `facets`, `breakdown` e `timeseries`.
3. Enviar filtros de escopo ao backend.
4. Ligar Timeline a sessões, detalhes de eventos e histórico de dispositivos.
5. Ligar Recorte aos eventos e breakdowns correspondentes.

### Prioridade 2 — Implementar hipóteses

1. Definir o serviço responsável.
2. Publicar `GET /api/v1/hypotheses`.
3. Implementar estados de loading, timeout, offline, resposta inválida e erro
   de servidor.
4. Integrar a tela de Hipóteses.

### Prioridade 3 — Completar contratos analíticos

1. Definir a origem de UF, região e ISP.
2. Definir baseline, sigma e degradações.
3. Definir a integração com change events.
4. Definir a timeline multi-fonte.
5. Implementar detalhe e feedback de hipóteses.

## Conclusão

Não é necessário criar novamente as sete rotas básicas de leitura: elas já
estão implementadas no backend. O trabalho imediato está principalmente no
frontend, que precisa consumir essas rotas e deixar de usar um único dashboard
para todas as seções.

A única rota principal ausente é `GET /api/v1/hypotheses`. As demais lacunas
dependem de integração frontend, qualidade/preenchimento dos dados regionais e
novos contratos para detecção, mudanças e múltiplas fontes.
