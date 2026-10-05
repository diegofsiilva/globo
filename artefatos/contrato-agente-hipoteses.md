# Contratos do piloto de hipóteses com IA

> Acompanha a arquitetura descrita em
> [`arquitetura-agente-hipoteses-ia.md`](arquitetura-agente-hipoteses-ia.md).
> Descreve uma execução experimental; nada aqui está publicado no produto.

Este documento cobre o lado do **agente**: o que ele recebe, o que ele responde
e o que fica gravado. O contrato de **leitura** — nomes das ferramentas,
argumentos e envelope de resposta — não é definido aqui: ele é a seção 3.4 do
documento de arquitetura, e é implementado pelo leitor de fatos em
[`leitor.py`](../apps/fullstack/agente/src/argus_agente/leitor.py).
Houve um período em que os dois documentos especificavam contratos diferentes
para as mesmas três ferramentas; a seção 3.4 é a que vale.

| Contrato | Quem produz | Onde está definido |
|---|---|---|
| Entrada da investigação | Executor, a partir do recorte | [`prompt.py`](../apps/fullstack/agente/src/argus_agente/prompt.py) |
| Ferramentas de leitura | Pessoa dos dados | Arquitetura, seção 3.4 |
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
    "recorte_id": "synthetic:101:2db402383094d32e",
    "presente_simulado": "2026-08-20T20:15:00+00:00",
    "observacoes_de": "2026-08-20T17:00:00Z",
    "observacoes_ate": "2026-08-20T20:00:00Z",
    "nota_de_escopo": "janela de 3 h em um dia útil, horário nobre"
  },
  "ferramentas": [{"nome": "inventariar_fatos", "...": "..."}],
  "orcamento": {
    "chamadas_restantes": 12,
    "itens_por_resposta": 200,
    "segundos_restantes": 300
  },
  "inventario": [
    {
      "source": "prometheus",
      "kind": "metric",
      "entity": "playback",
      "metric": "http_5xx_rate",
      "count": 13,
      "event_start_min": "2026-08-20T17:00:00Z",
      "event_start_max": "2026-08-20T20:00:00Z",
      "available_at_min": "2026-08-20T17:01:00Z",
      "available_at_max": "2026-08-20T20:01:00Z",
      "has_null_value": false,
      "has_null_sample_size": true,
      "group_ref": "a25aaa1b…"
    }
  ]
}
```

O `recorte_id` é opaco para o modelo: ele resolve, dentro do leitor, o
checkpoint, o `sim_now`, o `input_lsn` e o conjunto de fatos elegíveis. O
recorte não tem janela própria — o limite superior é o presente simulado, e
`observacoes_de` / `observacoes_ate` apenas dizem onde há observação, para o
agente não gastar chamada pedindo períodos vazios.

O **inventário** lista o que existe e quanta cobertura há, sem classificar nada
como anormal. Ele é a única visão global que o agente recebe, e **não devolve
`fact_id`**: uma linha de inventário descreve uma série, não observa nada, e por
isso não pode sustentar uma hipótese. Isso não depende de uma regra do
validador — o leitor simplesmente não expõe identificador no inventário.

### Fonte atrasada, sem vazar o futuro

Fatos com `available_at` posterior ao presente simulado não entram no recorte, e
o piloto não anuncia que eles existem. Mesmo assim, atraso de fonte continua
observável: o inventário mostra, por série, até quando há observação. No caso
`caso-03-fonte-atrasada`, a quebra por UF aparece no inventário com
`event_start_max` em 19/08, enquanto o efeito investigado é de 20/08. Pedir a
janela do incidente devolve página vazia com `sem_fatos_no_recorte_consultado`,
e é isso que permite ao agente registrar a lacuna como `ainda_indisponivel` em
vez de concluir que a métrica está normal.

É menos explícito do que um bloco dedicado a declarar as séries a caminho, que
chegou a ser proposto aqui. Esse bloco exigiria mudança no leitor e continua em
aberto na seção 6.

## 2. Ferramentas de leitura

As três ferramentas são as da seção 3.4 da arquitetura:
`inventariar_fatos`, `consultar_serie` e `consultar_contexto`. Este documento
não repete a especificação delas. O que importa para o lado do agente:

- **A validação semântica é do leitor, não do validador do agente.** Janela
  invertida ou posterior ao presente simulado, dimensão sem par tipo/valor,
  valor `?` ou `(desconhecido)`, série que não consta do inventário: tudo isso é
  recusado por quem conhece o recorte. O validador do agente só confere nome de
  ferramenta e tipo de argumento, antes de gastar chamada.
- **Pedido recusado consome uma chamada.** A recusa entra no rastro e volta ao
  modelo como dado, em vez de derrubar o caso — investigação real também esbarra
  em consulta que não existe.
- **Toda resposta traz `items`, `returned`, `has_more`, `next_cursor` e
  `limitations`.** Paginação consome mais uma chamada do teto do caso.
- **Cada item traz o `fact_id`** que o originou. Só esses identificadores podem
  ser citados como evidência.

## 3. Passo do modelo

O modelo responde **um passo por vez**, sempre com um único objeto JSON. Três
ações são possíveis.

```json
{"action": "consultar", "rationale": "procurar mudanca operacional proxima do efeito",
 "tool": "consultar_contexto",
 "arguments": {"entity": "playback", "kinds": ["context"],
               "inicio": "2026-08-20T17:00:00Z", "fim": "2026-08-20T20:00:00Z"}}
```

```json
{"action": "desistir", "rationale": "ha efeito, mas nada disponivel separa as causas",
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
  "statement": "Possivel regressao apos o deploy do playback: o erro 5xx sobe de 0,4% para 8,1% no bucket seguinte ao deploy",
  "scope": {"entity": "playback"},
  "effect_start": "2026-08-20T19:00:00+00:00",
  "evidence_for": [
    {
      "fact_ids": ["0415ff63…:1220"],
      "observation": "deploy do playback as 18:54, encerrado as 18:58",
      "reading": "mudanca operacional seis minutos antes do inicio do efeito"
    },
    {
      "fact_ids": ["c3a9e5d1…:1200"],
      "observation": "http_5xx_rate passa de 0,4 para 8,1 as 19:00",
      "reading": "o degrau coincide com o deploy, nao com uma subida gradual"
    }
  ],
  "evidence_against": [
    {
      "fact_ids": ["7b22f04e…:1021"],
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
responde se a resposta pode ser conferida. Estas regras rejeitam um passo e
geram **um** pedido de correção; a segunda falha encerra o caso.

| Regra | Por quê |
|---|---|
| Todo `fact_id` citado precisa ter vindo de uma ferramenta nesta investigação | Referência inventada é indistinguível de evidência real na leitura |
| `evidence_for` não pode ser vazia | Hipótese sem sustentação já tem a ação `desistir` |
| `evidence_against` ou `gaps` precisa ter ao menos um item | O Dia 1 definiu hipótese sem tentativa de refutação como incompleta |
| `statement` não pode afirmar causa de forma conclusiva | A saída é explicação candidata — mesma regra do RN-H11 do motor atual |
| `scope.entity` é obrigatório | Hipótese sem escopo não é verificável |
| `desistir` exige ao menos uma lacuna com motivo do catálogo | Desistência sem motivo não ensina nada à revisão |

Citar uma linha de inventário como evidência não precisa de regra: o inventário
não devolve `fact_id`, então qualquer identificador inventado a partir dele cai
na primeira regra da tabela.

Uma situação vira **aviso**, e não rejeição, porque pode ser legítima: o mesmo
`fact_id` aparecendo a favor e contra. O aviso acompanha a hipótese até a
revisão.

Uma hipótese cuja `evidence_against` não está vazia é marcada como
**contestada**. Isso não a invalida; muda como ela deve ser lida.

## 5. Registro do caso

O que o executor grava por caso investigado:

```json
{
  "case_id": "caso-01-deploy",
  "schema_version": "2.0.0",
  "recorte": {
    "checkpoint_id": "101",
    "origin": "synthetic",
    "sim_now": "2026-08-20T20:15:00+00:00",
    "input_lsn": 1300,
    "recorte_id": "synthetic:101:2db402383094d32e",
    "digest": "2163e85b3f0516af…"
  },
  "modelo": {"provedor": "ollama", "model": "qwen3-coder:30b", "temperatura": 0.0},
  "prompt_version": "2.0.0",
  "entrada": "{\"recorte\": …}",
  "desfecho": "hipotese",
  "contestada": true,
  "consultas": [
    {
      "ordem": 4,
      "ferramenta": "consultar_contexto",
      "argumentos": {"entity": "playback", "kinds": ["context"], "limit": 200,
                     "inicio": "2026-08-20T17:00:00Z", "fim": "2026-08-20T20:00:00Z"},
      "retornadas": 1,
      "fact_ids": ["0415ff63…:1220"],
      "duracao_ms": 1,
      "tem_mais": false,
      "limitacoes": [],
      "erro": null
    }
  ],
  "metricas": {
    "consumo": {"chamadas": 5, "itens": 44, "passos": 6, "passos_invalidos": 0},
    "fatos_vistos": 40
  }
}
```

O campo `entrada` guarda a mensagem de abertura exatamente como o modelo a
recebeu. Sem ela, um resultado estranho não pode ser atribuído à entrada ou ao
modelo.

O `digest` é o do leitor: resume os `fact_id` **e os papéis** expostos no
recorte. É ele que torna a reexecução comparável e, no Dia 6, o que garante que
o agente e o motor determinístico falem do mesmo material. O `recorte_id`
deriva dele.

Cinco desfechos são possíveis, e todos são gravados:

| Desfecho | Significado |
|---|---|
| `hipotese` | O agente concluiu e a saída passou no validador |
| `evidencia_insuficiente` | O agente desistiu, com lacunas declaradas |
| `teto_atingido` | Chamadas ou tempo acabaram antes da conclusão |
| `resposta_invalida` | Duas respostas seguidas fora do contrato |
| `erro_de_execucao` | Modelo indisponível, caso ilegível ou falha inesperada |

Os três últimos são limitação do piloto, não hipótese. Eles aparecem no
relatório do lote exatamente como os outros — um lote que esconde as falhas não
serve para decidir se o piloto continua.

## 6. Estado das decisões abertas

1. **Onde o leitor de fatos mora.** Fechado: o leitor e o acesso ao checkpoint
   real estão no pacote do agente (`leitor.py` e `banco.py`). As CLIs em
   `tools/` apenas chamam esses módulos. Não há mais ponte por caminho.
2. **Declarar as séries a caminho.** Decidido: não há bloco explícito. O
   inventário já informa, por série, o último evento disponível
   (`event_start_max`) e o `available_at_max`. Um atraso de fonte aparece como
   uma série cujo último dado fica antes da janela investigada. Um bloco
   separado mudaria o contrato do leitor sem ganho de informação para o agente.
3. **Casos sobre dado real.** Feito, com uma ressalva. O checkpoint 12 foi
   reconstruído a partir de `bronze.signal_bucket` por
   [`scripts/reconstruir_recorte_real.sql`](../apps/fullstack/agente/scripts/reconstruir_recorte_real.sql),
   porque o banco local não tem `change_log` para essa série. O recorte foi
   escolhido por inspeção manual da série bruta, não a partir de nenhum
   resultado do motor. A investigação do agente sobre ele **ainda não rodou**:
   o servidor do Ollama estava saturado durante toda a sessão.
4. **O que fazer com `role`.** Decidido: o agente não recebe `role`. O papel
   `subject` marca os fatos que o pipeline considera do intervalo analisado, o
   que é uma classificação do próprio motor e aproximaria o agente da resposta
   dele. `role` continua no digest, então a comparação do Dia 6 ainda verifica
   o mesmo material.
