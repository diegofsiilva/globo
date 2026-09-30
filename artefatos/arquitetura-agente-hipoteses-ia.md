# Arquitetura inicial do agente de hipóteses com IA

> Proposta de MVA — Dia 1. Este documento descreve uma alternativa experimental;
> não representa comportamento já implementado ou publicado no Argus.

## 1. Problema e primeira adição de valor

O motor atual detecta anomalias e gera hipóteses por 11 famílias de regras. A
alternativa proposta começa antes dessa geração: um agente investiga os fatos
disponíveis em um checkpoint e formula suas próprias explicações candidatas.
Ele não recebe as anomalias, os candidatos, o score ou as hipóteses do motor
atual. A primeira adição de valor é produzir, para **um recorte de incidente**,
uma hipótese verificável com referências aos fatos consultados, ou declarar que
a evidência é insuficiente. A decisão sobre a causa continua humana.

As duas abordagens podem ser comparadas depois sobre o mesmo checkpoint. A
comparação não transforma a saída do motor atual em resposta correta para a IA.

## 2. Fatos que o agente poderá consultar

### Fonte e unidade de observação

A fonte proposta é `silver.analysis_fact_version`, que normaliza mudanças do
`bronze.change_log`. O identificador de uma observação é
`(fact_key, version_lsn)`. O [contrato `Fact`](../apps/fullstack/processing/src/argus_processing/domain.py)
contém `role`, `kind`, `event_start`, `event_end`, `available_at`, `source`,
`entity`, `metric`, `dimension_type`, `dimension_value`, `value`, `sample_size`
e `attributes`. Esses campos descrevem um fato; nenhum deles é, por si só, uma
causa confirmada.

O recorte deve ser fixado por `checkpoint_id`, `sim_now` e `input_lsn`. Para cada
`fact_key`, somente a última versão com `version_lsn <= input_lsn` pode entrar;
ela precisa ter `available_at <= sim_now`, `event_start <= sim_now` e não estar
marcada como excluída. O agente vê um conjunto imutável ao longo da investigação.
Reexecuções devem registrar um digest desse conjunto. A seleção atual do
processamento em [`claim_and_capture`](../apps/fullstack/processing/src/argus_processing/analysis_repository.py)
serve de referência para essas invariantes, mas o agente não deve tomar posse
do cursor nem reutilizar o commit protegido do motor determinístico.

### Categorias iniciais

| Categoria consultável | Fatos normalizados disponíveis | Pergunta que ajuda a investigar |
|---|---|---|
| Métricas de serviço e infraestrutura | Buckets de sinais de Prometheus, New Relic, Apollo e fontes afins | O erro, a latência ou a saúde do serviço mudou no período? |
| Borda e proteção | Volume e taxas 4xx/5xx do RPaaS; sinais do Cloud Armor | A degradação aparece na borda ou em bloqueios? |
| Mudanças operacionais | Deploys e eventos do Tsuru | Houve mudança temporalmente próxima ao efeito? |
| Experiência de reprodução | Player, dispositivo, geografia, QoE, sessões ativas e erros de reprodução | O impacto aparece em quais recortes de usuários? |
| Contexto editorial | Eventos ao vivo e sua janela | O aumento de volume coincide com programação esperada? |

Este é um catálogo de **tipos de fato**, não uma lista de tabelas liberadas para
SQL arbitrário. A interface do agente deverá devolver somente campos
selecionados, com identificador e proveniência. `attributes` exige seleção
explícita por fonte antes de chegar ao modelo, para evitar carga irrelevante ou
identificadores de usuário. O conjunto exato de métricas e atributos aceitos
fica para o contrato de ferramentas do Dia 2.

### Limites semânticos dos dados

- UF e ISP são dimensões marginais separadas. O agente não pode afirmar um
  cruzamento `UF × ISP` ausente dos dados.
- Valores `?` e `(desconhecido)` não definem um recorte confiável.
- Latências percentis nulas do RPaaS não devem ser apresentadas como medidas.
- Um 4xx do RPaaS não identifica sozinho falha de autorização de playback;
  isso depende do vhost catalogado.
- Fatos NPAW/Youbora podem chegar com atraso causal de 28 horas. Mesmo se o
  evento ocorreu antes, só entram após `available_at`.
- `incidents` e `incident_label` são material de avaliação retrospectiva,
  **não** entrada online do agente. Também ficam fora as anomalias,
  `gold.hypothesis_*`, feedback e scores do motor atual.

### Forma mínima entregue ao agente

Cada resposta de consulta deverá oferecer pelo menos:

```json
{
  "fact_id": "fact_key:version_lsn",
  "source": "nome-da-fonte",
  "kind": "metric",
  "entity": "entidade-catalogada",
  "metric": "metrica-catalogada",
  "event_start": "instante-do-evento",
  "available_at": "instante-de-disponibilidade",
  "value": 0,
  "sample_size": 0,
  "dimension_type": null,
  "dimension_value": null
}
```

O exemplo é um formato, não um registro real. Valores ausentes continuam
ausentes; não são convertidos em zero. Consultas agregadas devem trazer os
identificadores dos fatos que contribuíram para o resultado ou uma referência
estável ao conjunto, para permitir conferência posterior.

