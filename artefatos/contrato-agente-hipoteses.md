# Contratos do piloto de hipóteses com IA

> Entrega do Dia 2. Acompanha a arquitetura descrita em
> [`arquitetura-agente-hipoteses-ia.md`](arquitetura-agente-hipoteses-ia.md).
> Descreve uma execução experimental; nada aqui está publicado no produto.

Quatro contratos sustentam o piloto, e a separação entre eles é o que mantém o
resultado auditável:

| Contrato | Quem produz | Onde vive |
|---|---|---|
| Entrada da investigação | Executor, a partir do recorte | [`prompt.py`](../apps/fullstack/agente/src/argus_agente/prompt.py) |
| Ferramentas de consulta | Pessoa dos dados, consumido pelo agente | [`ferramentas.py`](../apps/fullstack/agente/src/argus_agente/ferramentas.py) |
| Passo do modelo | Modelo | [`contrato.py`](../apps/fullstack/agente/src/argus_agente/contrato.py) |
| Registro do caso | Executor | [`contrato.py`](../apps/fullstack/agente/src/argus_agente/contrato.py) |

A regra que organiza os quatro: **o modelo descreve, o executor registra**. O
histórico de consultas, o consumo de orçamento e a identidade do recorte são
escritos por código, nunca narrados pelo modelo — um histórico contado pelo
próprio investigado não serve de rastro.

## 1. Entrada da investigação

O agente recebe uma única mensagem de abertura com quatro blocos. Nenhum deles
contém anomalia, score, hipótese do motor determinístico ou rótulo de incidente.

```json
{
  "recorte": {
    "checkpoint_id": "ckpt-03-fonte-atrasada",
    "presente_simulado": "2026-08-20T20:15:00+00:00",
    "janela_inicio": "2026-08-20T17:00:00+00:00",
    "janela_fim": "2026-08-20T20:00:00+00:00",
    "nota_de_escopo": "janela de 3 h; a quebra por geografia tem atraso de fonte"
  },
  "ferramentas": [{"nome": "inventario", "...": "..."}],
  "orcamento": {
    "chamadas_restantes": 12,
    "linhas_por_resposta": 200,
    "segundos_restantes": 300
  },
  "inventario": [
    {
      "source": "prometheus",
      "entity": "playback",
      "metric": "http_5xx_rate",
      "dimension_type": null,
      "pontos": 13,
      "primeiro_evento": "2026-08-20T17:00:00+00:00",
      "ultimo_evento": "2026-08-20T20:00:00+00:00",
      "buckets_vazios": 0,
      "atraso_tipico_segundos": 60
    }
  ],
  "ainda_indisponivel": [
    {
      "source": "npaw_geo",
      "entity": "globo",
      "metric": "error_rate",
      "disponivel_a_partir_de": "2026-08-21T21:00:00+00:00"
    }
  ]
}
```

O **inventário** lista o que existe e quanta cobertura há, sem classificar nada
como anormal. `buckets_vazios` conta intervalos de 15 minutos sem ponto entre o
primeiro e o último; `atraso_tipico_segundos` é a distância mediana entre o
instante do evento e o instante em que ele ficaria disponível.

O bloco **`ainda_indisponivel`** é uma decisão de projeto do piloto, e precisa
de acordo com a pessoa dos dados. Ele declara séries que existem nesta janela
mas só chegam depois do presente simulado — o caso dos dados NPAW, com até 28
horas de atraso causal. O bloco expõe **existência e horário de chegada, nunca
valor**. Sem ele, uma fonte atrasada chega ao agente indistinguível de uma fonte
que não existe, e a lacuna seria registrada com o motivo errado. É o mesmo
princípio da RT03 de [`hipoteses.md`](hipoteses.md): atraso de fonte precisa ser
preservado, não apagado.

## 2. Ferramentas de consulta

Três ferramentas, como fixado no Dia 1. **Ferramenta**, aqui, é uma função
fechada com parâmetros declarados — não é acesso ao banco nem SQL livre.

| Ferramenta | Entrada | Saída | Limites |
|---|---|---|---|
| `inventario` | `source` (opcional) | Séries e cobertura | Teto de linhas; não é citável como evidência |
| `serie` | `source`, `entity`, `metric`, `inicio`, `fim`, e opcionalmente `dimension_type`, `dimension_value`, `agregacao` | Pontos com `fact_id`, instante e valor | Teto de linhas, com aviso de truncamento |
| `contexto` | `tipos`, `inicio`, `fim` | Fatos não métricos — deploys, eventos ao vivo | Teto de linhas; até 5 tipos por chamada |

Toda linha carrega o `fact_id` que a originou, no formato
`{fact_key}:{version_lsn}`. Quando a resposta é agregada — `agregacao` igual a
`media_por_bucket` —, a linha traz em `agrega` todos os `fact_id` que entraram
no cálculo. Sem isso, uma evidência construída sobre uma média não poderia ser
aberta na revisão.

Uma resposta vazia nunca volta muda. Ela distingue três situações, porque cada
uma leva a um motivo de lacuna diferente:

| Situação | Mensagem devolvida |
|---|---|
| A série existe, mas não neste período | `a serie existe no recorte, mas nao tem ponto no periodo pedido` |
| A série existe e ainda não chegou | `a serie existe nesta janela, mas so fica disponivel em <instante>, depois do presente simulado` |
| A fonte não está no recorte | `a fonte <nome> nao esta no recorte` |

**Pendência com a pessoa dos dados.** As assinaturas acima são o que o agente
consome e estão implementadas sobre arquivo de fixture. O adaptador que lê
`silver.analysis_fact_version` ainda não existe e precisa garantir, em código,
as mesmas duas invariantes que o dublê garante: nenhum fato com `available_at`
posterior ao `sim_now`, e nenhum fato fora da janela do recorte.

## 3. Passo do modelo

O modelo responde **um passo por vez**, sempre com um único objeto JSON. Três
ações são possíveis.

```json
{"action": "consultar", "rationale": "procurar mudanca operacional proxima do efeito",
 "tool": "contexto",
 "arguments": {"tipos": ["deploy"], "inicio": "...", "fim": "..."}}
```

```json
{"action": "desistir", "rationale": "ha efeito, mas nada no recorte separa as causas",
 "gaps": [{"missing": "quebra do erro por UF", "reason": "ainda_indisponivel"}]}
```

```json
{"action": "concluir", "rationale": "...", "answer": { "...": "a hipótese da seção 4" }}
```

Os quatro motivos de lacuna aceitos são `sem_dado`, `ainda_indisponivel`,
`fora_do_catalogo` e `limite_de_ferramenta`. Separar os dois primeiros é o que
impede o piloto de tratar atraso de fonte como ausência de problema.

## 4. A hipótese final

A hipótese entrega quatro coisas: a causa candidata, o que a sustenta, o que a
contraria e o que não foi possível verificar. O exemplo abaixo é a saída real do
caso `caso-01-deploy`, com as listas de `fact_id` encurtadas.

```json
{
  "statement": "Possivel regressao apos o deploy do playback: o erro 5xx sobe de 0,4% para 7,4% no bucket seguinte ao deploy",
  "scope": {"entity": "playback"},
  "effect_start": "2026-08-20T19:00:00+00:00",
  "evidence_for": [
    {
      "fact_ids": ["deploy:playback:1787252040:9000"],
      "observation": "deploy do playback as 18:54",
      "reading": "mudanca operacional seis minutos antes do inicio do efeito"
    },
    {
      "fact_ids": ["signal_bucket:prometheus:playback:http_5xx_rate:1787252400:1008"],
      "observation": "http_5xx_rate passa de 0,4 para 7,4 as 19:00",
      "reading": "o degrau coincide com o deploy, nao com uma subida gradual"
    }
  ],
  "evidence_against": [
    {
      "fact_ids": ["signal_bucket:rpaas:playback.video.globo.com:requests_total:1787252400:1008"],
      "observation": "requests_total permanece entre 405 mil e 421 mil",
      "reading": "o volume nao muda, entao a alternativa de pico de demanda nao se sustenta"
    }
  ],
  "gaps": [
    {"missing": "quebra do erro por regiao e ISP", "reason": "ainda_indisponivel"},
    {"missing": "conteudo do deploy, como versao ou commit", "reason": "fora_do_catalogo"}
  ]
}
```

Cada evidência separa **`observation`**, que é o que o fato mostra, de
**`reading`**, que é por que isso pesa a favor ou contra. A separação existe
para que a revisão humana possa discordar da leitura sem precisar refazer a
observação.

### Regras de validação

O validador não julga se a causa é verdadeira — isso é da revisão humana. Ele
responde se a resposta pode ser conferida. Sete regras rejeitam um passo e
geram **um** pedido de correção; a segunda falha encerra o caso.

| Regra | Por quê |
|---|---|
| Todo `fact_id` citado precisa ter vindo de uma ferramenta nesta investigação | Referência inventada é indistinguível de evidência real na leitura |
| `evidence_for` não pode ser vazia | Hipótese sem sustentação já tem a ação `desistir` |
| `evidence_against` ou `gaps` precisa ter ao menos um item | O Dia 1 definiu hipótese sem tentativa de refutação como incompleta |
| `statement` não pode afirmar causa de forma conclusiva | A saída é explicação candidata — mesma regra do RN-H11 do motor atual |
| `scope.entity` é obrigatório | Hipótese sem escopo não é verificável |
| Ferramenta e argumentos precisam existir no contrato | Argumento inventado vira erro silencioso de consulta |
| `desistir` exige ao menos uma lacuna com motivo do catálogo | Desistência sem motivo não ensina nada à revisão |

Duas situações viram **aviso**, e não rejeição, porque podem ser legítimas: uma
linha do inventário citada como evidência, e o mesmo `fact_id` aparecendo a
favor e contra. A segunda acompanha a hipótese até a revisão.

Uma hipótese cuja `evidence_against` não está vazia é marcada como
**contestada**. Isso não a invalida; muda como ela deve ser lida.

## 5. Registro do caso

O que o executor grava por caso investigado:

```json
{
  "case_id": "caso-01-deploy",
  "schema_version": "1.0.0",
  "recorte": {
    "checkpoint_id": "ckpt-01-deploy",
    "sim_now": "2026-08-20T20:15:00+00:00",
    "input_lsn": 1042300,
    "digest": "sha256:e14bb5dc3d44b4be"
  },
  "modelo": {"provedor": "ollama", "model": "qwen3-coder:30b", "temperatura": 0.0},
  "prompt_version": "1.0.0",
  "desfecho": "hipotese",
  "contestada": true,
  "consultas": [
    {
      "ordem": 4,
      "ferramenta": "contexto",
      "argumentos": {"tipos": ["deploy", "live_event"], "inicio": "...", "fim": "..."},
      "linhas": 1,
      "fact_ids": ["deploy:playback:1787252040:9000"],
      "duracao_ms": 0,
      "truncada": false,
      "vazia_porque": null
    }
  ],
  "metricas": {
    "consumo": {"chamadas": 5, "linhas": 44, "passos": 6, "passos_invalidos": 0},
    "fatos_vistos": 40
  }
}
```

O `digest` é o resumo SHA-256 dos `fact_id` elegíveis depois do corte temporal.
Ele é o que torna a reexecução comparável e, no Dia 6, o que garante que o
agente e o motor determinístico falem do mesmo material.

Cinco desfechos são possíveis, e todos são gravados:

| Desfecho | Significado |
|---|---|
| `hipotese` | O agente concluiu e a saída passou no validador |
| `evidencia_insuficiente` | O agente desistiu, com lacunas declaradas |
| `teto_atingido` | Chamadas, linhas ou tempo acabaram antes da conclusão |
| `resposta_invalida` | Duas respostas seguidas fora do contrato |
| `erro_de_execucao` | Modelo indisponível, caso ilegível ou falha inesperada |

Os três últimos são limitação do piloto, não hipótese. Eles aparecem no
relatório do lote exatamente como os outros — um lote que esconde as falhas não
serve para decidir se o piloto continua.

## 6. O que ainda depende da pessoa dos dados

1. O adaptador real sobre `silver.analysis_fact_version`, cumprindo a seção 2.
2. A decisão sobre o bloco `ainda_indisponivel`: se ele entra no contrato do
   leitor de fatos ou se o piloto passa a viver sem ele.
3. A forma de acesso ao banco. As permissões atuais do `argus_reader` cobrem
   apenas views públicas e não autorizam supor leitura direta da tabela.
4. Os casos reprodutíveis sobre dado real. Os três casos atuais são fixtures
   construídas com nomes do catálogo do projeto, não recortes do dump.
