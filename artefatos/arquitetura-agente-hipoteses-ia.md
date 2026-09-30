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

## 3. Esboço da arquitetura alternativa

```text
bronze.change_log → silver.analysis_fact_version → checkpoint temporal
                                                    │
                              leitor de fatos com recorte imutável
                                                    │
                              ferramentas de investigação limitadas
                                                    │
                         agente IA: observar → consultar → contrastar
                                                    │
                            hipótese estruturada ou evidência insuficiente
                                                    │
                              validador de referências e tempo
                                                    │
                             registro experimental → revisão humana

Em paralelo: checkpoint → detector → 11 regras → hipóteses do motor atual
```

O **leitor de fatos** é o seam principal do MVA. Sua interface recebe a
identidade do checkpoint e devolve um recorte imutável mais funções de consulta
limitadas; a implementação esconde SQL, versionamento e seleção temporal. O
agente não recebe credenciais de banco nem SQL livre. A forma de acesso ao banco
será definida no Dia 2; as permissões atuais do `argus_reader` cobrem apenas
views públicas e não autorizam supor leitura direta de
`silver.analysis_fact_version`.

O **agente** decide o que investigar e quais explicações testar. Uma primeira
interface pequena é `investigar(recorte, ferramentas) -> resultado`. Dentro dela,
o ciclo pode consultar séries, comparar uma janela anterior e abrir fatos de
contexto, sempre dentro do mesmo recorte. O modelo não recebe respostas do motor
atual nem rótulos de incidentes. Limites de chamadas, linhas e tempo impedem
uma investigação indefinida.

O **validador** confere formato, IDs citados, proveniência, disponibilidade
temporal e limites. Ele não decide se a causa sugerida é verdadeira. Afirmações
causais sem lastro, contradições ignoradas ou ausência de observações devem
seguir para revisão como limitação ou resultar em `insufficient_evidence`,
conforme o contrato de saída a ser fechado no Dia 2.

### Sequência mínima de uma investigação

1. Selecionar um checkpoint e um recorte de tempo/escopo; registrar seu digest.
2. Mostrar ao agente um inventário pequeno de fontes e métricas disponíveis,
   incluindo lacunas de cobertura, sem classificação prévia de anomalias.
3. O agente solicita consultas sobre os fatos e compara o período investigado
   com contexto anterior causalmente disponível.
4. O agente propõe uma causa candidata e tenta encontrar evidência contrária;
   se não houver sustentação suficiente, responde `insufficient_evidence`.
5. Validar as referências e guardar o resultado com modelo, versão do prompt,
   parâmetros, consultas executadas, checkpoint e digest.
6. Uma pessoa avalia se o resultado ajudou a investigação. Só então comparar
   com a saída do motor determinístico para o mesmo checkpoint.

## 4. Escopo do MVA e decisões seguintes

**Valor a demonstrar:** em um caso selecionado, o agente produz uma explicação
que um investigador consegue conferir abrindo as evidências citadas, ou expõe
honestamente a falta de dados. O primeiro protótipo pode ser executado por CLI
e registrar JSON/Markdown local; não precisa de tela, tabela de produção ou
publicação automática.

**Fora do Dia 1:** escolha de modelo/provedor, prompt final, novas permissões
SQL, migração de banco, integração com a API/frontend e métrica de qualidade
calculada. O refinador Ollama existente na API apenas redige respostas a partir
de hipóteses já publicadas; a geração alternativa descrita aqui é um fluxo
distinto.

No Dia 2, fechar quatro decisões para implementação paralela por duas pessoas:

| Decisão | Responsável sugerido | Critério de aceite |
|---|---|---|
| Interface e acesso ao recorte de fatos | Pessoa dos dados | Mesmo checkpoint produz o mesmo conjunto e não expõe futuro. |
| Ferramentas de consulta e limites | Pessoa dos dados, com revisão conjunta | Cada resposta é limitada, paginável ou agregada e rastreável a fatos. |
| Formato da hipótese e estratégia de investigação | Pessoa do agente | A saída cita fatos a favor/contra e admite insuficiência. |
| Casos de avaliação | Ambas | Casos cobrem evidência suficiente, contraditória e fonte atrasada. |

O protótipo deve permanecer em execução experimental separada. O guia do
`apps/fullstack/processing` preserva o ciclo atual como determinístico; uma
integração produtiva requer uma decisão arquitetural posterior e validação com
os responsáveis pelo projeto.
