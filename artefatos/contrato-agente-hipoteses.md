# Contratos do agente de hipóteses

&emsp; Este documento mostra o que entra e o que sai do agente, com exemplos de JSON e o código que impõe cada formato. Ele complementa a [arquitetura do agente](arquitetura-agente-hipoteses-ia.md), que explica o funcionamento geral. Aqui importa a forma dos dados: quais campos existem, o que cada um significa e o que o código recusa.

## 1. Quatro contratos

&emsp; Existem quatro contratos. A mensagem de abertura é a primeira entrada do modelo, com o recorte e o inventário. As ferramentas de leitura são as consultas que o modelo pode fazer durante a investigação. O passo do modelo é a resposta que ele devolve a cada turno. O registro do caso é o arquivo gravado ao fim de cada investigação, para auditoria.

&emsp; Uma regra organiza os quatro: o modelo descreve, e o executor registra. O histórico de consultas, o consumo do orçamento e a identidade do recorte são escritos pelo código. Nada disso depende do que o modelo afirma sobre si mesmo.

## 2. Mensagem de abertura

&emsp; A mensagem de abertura é montada na função `mensagem_de_abertura`, em [prompt.py](../apps/fullstack/agente/src/argus_agente/prompt.py). Ela é um JSON com quatro blocos. Nenhum deles contém anomalia, score, hipótese publicada ou rótulo de incidente.

```json
{
  "recorte": {
    "recorte_id": "database:12:8634faaab06af08",
    "presente_simulado": "2026-08-21T08:00:00+00:00",
    "observacoes_de": "2026-08-21T02:00:00+00:00",
    "observacoes_ate": "2026-08-21T07:45:00+00:00",
    "nota_de_escopo": "checkpoint 12 de br1|playback.video.globo.com, janela de 360 min"
  },
  "ferramentas": [
    {"nome": "inventariar_fatos", "para_que": "...", "argumentos": {"...": "..."}}
  ],
  "orcamento": {
    "chamadas_restantes": 12,
    "itens_por_resposta": 200,
    "segundos_restantes": 300
  },
  "inventario": [
    {
      "source": "rpaas",
      "entity": "br1|playback.video.globo.com",
      "metric": "error_4xx_rate_pct",
      "pontos": 24,
      "primeiro_evento": "2026-08-21T02:00:00Z",
      "ultimo_evento": "2026-08-21T07:45:00Z",
      "buckets_vazios": 0,
      "atraso_tipico_segundos": 900
    }
  ]
}
```

&emsp; O `recorte_id` é um identificador opaco. O modelo o usa como referência, mas não consegue inventá-lo nem alterá-lo, porque ele resolve dentro do leitor o checkpoint, o presente simulado e o conjunto de fatos. O recorte não tem janela própria: o limite superior é sempre o presente simulado. Os campos `observacoes_de` e `observacoes_ate` apenas indicam onde há dados, para que o agente não gaste chamadas pedindo períodos vazios.

&emsp; O inventário lista o que existe e a cobertura de cada série, sem classificar nada como anormal. Ele não traz `fact_id`. Uma linha do inventário descreve uma série e não observa valor algum, então não pode servir de evidência. O código do inventário está em `inventariar_fatos`, no [leitor.py](../apps/fullstack/agente/src/argus_agente/leitor.py).

&emsp; Uma série atrasada aparece no inventário com o último evento disponível antes da janela investigada. Não existe um campo separado com a lista de séries a caminho. Quando o modelo pede uma janela sem dados, a resposta vem vazia com a limitação `sem_fatos_no_recorte_consultado`, e isso é o sinal de que o dado ainda não chegou ou não existe.

## 3. Ferramentas de leitura

&emsp; As ferramentas são três, e o modelo só pode chamá-las pelo nome. Nenhuma aceita SQL, nome de tabela ou um horário posterior ao presente simulado. O despacho que escolhe a função pelo nome está em `despachar`, em [ferramentas.py](../apps/fullstack/agente/src/argus_agente/ferramentas.py).

&emsp; A ferramenta `inventariar_fatos` aceita só os argumentos `limit` e `cursor`. Serve para ler o inventário em páginas, quando ele é grande demais para uma resposta.

```json
{"action": "consultar", "rationale": "ver o que existe antes de escolher",
 "tool": "inventariar_fatos", "arguments": {}}
```

&emsp; A ferramenta `consultar_serie` devolve os pontos de uma métrica dentro de uma janela. Exige `source`, `entity`, `metric`, `inicio` e `fim`, e aceita opcionalmente o par `dimension_type` e `dimension_value`. A janela precisa começar antes de terminar, e não pode terminar depois do presente simulado. A implementação está em `consultar_serie`, no [leitor.py](../apps/fullstack/agente/src/argus_agente/leitor.py).

```json
{"action": "consultar", "rationale": "ver como o 4xx se comporta na madrugada",
 "tool": "consultar_serie",
 "arguments": {"source": "rpaas", "entity": "br1|playback.video.globo.com",
               "metric": "error_4xx_rate_pct",
               "inicio": "2026-08-21T02:00:00Z", "fim": "2026-08-21T08:00:00Z"}}
```

&emsp; A ferramenta `consultar_contexto` devolve fatos que podem sustentar ou enfraquecer uma explicação, como deploys e transmissões ao vivo. Exige a janela e pelo menos uma entre `source` e `entity`. Aceita também `kinds`, que escolhe entre fatos de métrica e de contexto. Um evento entra na resposta se a sua duração se sobrepõe à janela, e não apenas se começa dentro dela.

```json
{"action": "consultar", "rationale": "procurar mudança operacional próxima do efeito",
 "tool": "consultar_contexto",
 "arguments": {"entity": "br1|playback.video.globo.com", "kinds": ["context"],
               "inicio": "2026-08-21T02:00:00Z", "fim": "2026-08-21T08:00:00Z"}}
```

&emsp; Toda resposta de ferramenta tem o mesmo formato. O exemplo a seguir é ilustrativo: os valores são arredondados e os identificadores encurtados. Ela traz `recorte_id`, o nome da ferramenta, a lista `items`, a quantidade `returned`, o indicador `has_more`, o cursor `next_cursor` e a lista `limitations`. Cada item traz o `fact_id` que o originou, e só esses identificadores podem ser citados como evidência. Uma página tem no máximo 200 itens. Para ler a próxima, o agente faz uma nova chamada com o cursor, e ela consome do orçamento.

```json
{
  "recorte_id": "database:12:8634faaab06af08",
  "tool": "consultar_serie",
  "items": [
    {"fact_id": "3e57a052e63f…", "event_start": "2026-08-21T02:00:00Z",
     "value": 2.6, "kind": "metric", "metric": "error_4xx_rate_pct"}
  ],
  "returned": 24,
  "has_more": false,
  "next_cursor": null,
  "limitations": []
}
```

&emsp; Quando não há dados na janela, a resposta vem com `items` vazio e uma limitação, e nunca com uma série de zeros. Um vazio não prova que o evento não ocorreu. Ele pode significar que o dado ainda não chegou ou que a série não existe no recorte. Um pedido inválido, como uma janela que termina depois do presente simulado, é recusado com erro explícito e também consome uma chamada.

## 4. Passo do modelo

&emsp; A cada turno, o modelo devolve um único objeto JSON com o campo `action`. Os três valores possíveis são `consultar`, `concluir` e `desistir`. O esquema completo fica em `ESQUEMA_PASSO`, em [contrato.py](../apps/fullstack/agente/src/argus_agente/contrato.py), e é enviado ao servidor do modelo junto com a requisição, para restringir a forma da resposta.

```python
ESQUEMA_PASSO = {
    "type": "object",
    "additionalProperties": False,
    "required": ["action", "rationale"],
    "properties": {
        "action": {"enum": list(ACOES)},
        "rationale": {"type": "string", "maxLength": 600},
        "tool": {"enum": list(FERRAMENTAS)},
        "arguments": _ARGUMENTOS,
        "answer": ESQUEMA_HIPOTESE,
        "gaps": {"type": "array", "maxItems": 6, "items": _LACUNA},
    },
}
```

&emsp; O campo `rationale` é uma frase que explica o motivo do passo. Ele fica no registro, para que a revisão veja o raciocínio de cada turno. Um `concluir` precisa trazer o objeto `answer`. Um `desistir` precisa trazer ao menos uma lacuna.

&emsp; Uma lacuna tem um motivo, que pertence a um conjunto fechado: `sem_dado`, quando a informação não existe no recorte; `ainda_indisponivel`, quando a fonte ainda não entregou; `fora_do_catalogo`, quando o que se procura não é medido por nenhuma fonte; e `limite_de_ferramenta`, quando a ferramenta não consegue responder à pergunta. Separar os dois primeiros é o que impede o sistema de tratar atraso de fonte como se o problema não existisse.

## 5. A hipótese final

&emsp; Uma conclusão é o objeto `answer`. Ele reúne a explicação candidata, as evidências a favor, as evidências contra, as explicações rivais, o instante do efeito e as lacunas. O exemplo abaixo foi tirado de uma saída real do checkpoint 12. Os identificadores e alguns textos foram encurtados para caber na leitura, e o campo `checagens` é acrescentado pelo código depois da validação.

```json
{
  "statement": "Possível causa candidata para a degradação na plataforma playback: um problema na infraestrutura ou no backend, compatível com o aumento dos erros 4xx e 5xx a partir das 04:15 e a queda no RPM.",
  "scope": {"entity": "br1|playback.video.globo.com"},
  "effect_start": "2026-08-21T04:15:00+00:00",
  "evidence_for": [
    {
      "fact_ids": ["429bb1b5a172…", "a50e04631338…"],
      "observation": "Aumento significativo nos erros 4xx a partir das 04:15",
      "reading": "Os valores de 4xx sobem de forma clara nesse intervalo"
    },
    {
      "fact_ids": ["0a36aadc7773…", "5f5498f4f86e…"],
      "observation": "Queda progressiva no RPM a partir das 03:00",
      "reading": "O volume de requisições cai ao longo da madrugada"
    }
  ],
  "evidence_against": [
    {
      "fact_ids": ["3e57a052e63f…"],
      "observation": "Os erros 5xx não apresentam um padrão crescente constante",
      "reading": "A alta dos 5xx existe, mas é menos consistente que a dos 4xx"
    }
  ],
  "alternativas": [
    {
      "explicacao": "Problemas de infraestrutura ou backend",
      "veredito": "sustentada",
      "fact_ids": ["0a36aadc7773…"],
      "observation": "Queda no RPM e aumento de 4xx e 5xx coincidem com o período"
    },
    {
      "explicacao": "Ataque ou sobrecarga de tráfego",
      "veredito": "nao_verificada",
      "fact_ids": [],
      "observation": "Não há dados de tráfego anormal ou de ataque no período"
    }
  ],
  "gaps": [],
  "checagens": [
    {
      "lado": "evidence_for",
      "observation": "Aumento significativo nos erros 4xx a partir das 04:15",
      "status": "confirmado",
      "serie": "rpaas/error_4xx_rate_pct",
      "antes": 3.4148,
      "depois": 9.4113,
      "variacao": 1.756
    }
  ]
}
```

&emsp; O campo `statement` diz qual série muda, em que direção e a partir de quando. Ele é uma explicação candidata, e a linguagem precisa ser não conclusiva, com palavras como "possível" ou "compatível com". O campo `effect_start` é o instante em que a mudança começa nos dados. O código exige esse campo, porque a checagem numérica precisa dele para comparar o antes e o depois.

&emsp; Cada evidência separa duas coisas. A `observation` diz o que o dado mostra. A `reading` diz por que aquilo pesa a favor ou contra. Essa separação permite que a revisão discorde da leitura sem precisar refazer a observação. As explicações rivais seguem a mesma ideia: cada uma recebe um veredito, e os vereditos `sustentada` e `refutada` precisam citar fatos consultados.

## 6. Regras de validação

&emsp; O validador confere se a conclusão pode ser verificada. Ele não julga se a causa é verdadeira. Está em [validador.py](../apps/fullstack/agente/src/argus_agente/validador.py), na função `interpretar`. As regras são estas.

&emsp; Todo `fact_id` citado precisa ter aparecido em alguma resposta de ferramenta nesta investigação. Uma referência inventada é recusada, porque seria indistinguível de uma evidência real.

&emsp; A evidência contrária é obrigatória. Uma lacuna declarada não substitui uma observação que pudesse derrubar a hipótese. O trecho que impõe a regra é este:

```python
if not contra:
    problemas.append(
        "evidence_against vazio: cite pelo menos um fato, entre os consultados, "
        "que enfraquece a hipotese, mesmo que ela continue sendo a melhor"
    )
```

&emsp; São necessárias ao menos duas explicações rivais. Os vereditos `sustentada` e `refutada` exigem fatos citados, e o veredito `nao_verificada` existe para registrar o que os dados não alcançam, sem fingir uma conclusão.

&emsp; O enunciado não pode afirmar causa com certeza. Expressões como "causa raiz", "com certeza" ou "comprovado" são recusadas. A evidência a favor não pode ser vazia, a hipótese precisa de um escopo com entidade, e o `effect_start` precisa ser um instante válido.

&emsp; Quando uma regra falha, o modelo recebe a lista exata de problemas e tem uma nova tentativa. Se a segunda resposta também falhar, o caso termina como resposta inválida, e isso fica no registro.

## 7. Checagem numérica

&emsp; Depois da validação, cada evidência passa por uma checagem em [checagem.py](../apps/fullstack/agente/src/argus_agente/checagem.py), que compara o texto com a série real. Ela confere se a direção afirmada bate com a direção medida e se a intensidade descrita bate com a magnitude medida. A direção é medida pela média antes e depois do `effect_start`, e uma variação de 10% ou mais conta como alta ou queda.

&emsp; Cada evidência recebe um status. O status `confirmado` significa que o texto bate com a série. O status `contradito` significa que o texto afirma uma direção e a série foi em outra, e isso recusa a conclusão. O status `exagero` significa que a frase usa um adjetivo de intensidade, como "significativo", mas a variação relativa é menor que 50%. O status `indeterminado` significa que a checagem não conseguiu decidir, porque a evidência mistura séries, cita um fato desconhecido, ou usa uma frase sem direção clara. Nesse último caso nada é contradito.

&emsp; Os campos de cada checagem registram o que foi medido: a série, a média antes, a média depois, a variação relativa e as direções afirmada e medida. Esses valores ficam no registro para que a revisão possa conferir a decisão.

## 8. Registro do caso

&emsp; Cada investigação gera um arquivo JSON. A função `escrever_caso`, em [registro.py](../apps/fullstack/agente/src/argus_agente/registro.py), grava o registro completo. A forma do registro é definida pela classe `RegistroDoCaso`, em [contrato.py](../apps/fullstack/agente/src/argus_agente/contrato.py), e a versão do esquema é a `2.2.0`.

```json
{
  "case_id": "checkpoint-12-br1|playback.video.globo.com-360m",
  "schema_version": "2.2.0",
  "criado_em": "2026-10-05T18:12:04+00:00",
  "recorte": {
    "checkpoint_id": "12",
    "origin": "database",
    "sim_now": "2026-08-21T08:00:00+00:00",
    "input_lsn": 15008891,
    "recorte_id": "database:12:8634faaab06af08",
    "digest": "8b9c0ecb58a7ae02…"
  },
  "modelo": {"provedor": "ollama", "model": "qwen3-coder:30b", "temperatura": 0.0, "tentativas": 2},
  "prompt_version": "2.2.0",
  "entrada": "{\"recorte\": …}",
  "desfecho": "hipotese",
  "contestada": true,
  "passos": [
    {
      "ordem": 1,
      "acao": "consultar",
      "rationale": "ver como o 4xx se comporta na madrugada",
      "problemas": [],
      "saida_bruta": "{\"action\": \"consultar\", …}"
    }
  ],
  "consultas": [
    {
      "ordem": 1,
      "ferramenta": "consultar_serie",
      "argumentos": {"source": "rpaas", "limit": 200},
      "retornadas": 24,
      "fact_ids": ["429bb1b5a172…"],
      "duracao_ms": 1,
      "tem_mais": false,
      "limitacoes": [],
      "erro": null
    }
  ],
  "metricas": {
    "consumo": {"chamadas": 3, "itens": 72, "passos": 4, "passos_invalidos": 0}
  }
}
```

&emsp; O campo `entrada` guarda a mensagem de abertura exatamente como o modelo a recebeu. O campo `saida_bruta` de cada passo guarda o texto que o modelo devolveu, mesmo quando foi rejeitado. Assim, uma rejeição pode ser comparada com o que o modelo de fato escreveu, e não apenas com o motivo que o validador apontou.

&emsp; O digest é o resumo do conjunto de fatos expostos ao agente, incluindo os papéis de cada fato. Ele permite confirmar que duas execuções viram os mesmos dados. O `recorte_id` deriva desse digest.

&emsp; Cada caso termina em um dos cinco desfechos abaixo, todos gravados. O desfecho `hipotese` indica que a conclusão passou em todas as verificações. O desfecho `evidencia_insuficiente` indica que o agente desistiu e declarou as lacunas. O desfecho `teto_atingido` indica que um limite de orçamento foi alcançado antes da conclusão. O desfecho `resposta_invalida` indica que duas respostas seguidas violaram o formato. O desfecho `erro_de_execucao` cobre falhas do modelo, do leitor ou do banco.

&emsp; Os três últimos desfechos são limitações do piloto e não produzem hipótese. Eles aparecem no relatório do lote com o mesmo destaque dos demais, porque um relatório que esconde falhas não permite avaliar o piloto.

## 9. Limitações conhecidas

&emsp; O recorte real usado nos testes foi reconstruído a partir da bronze, e não é uma reprodução do fluxo de captura de mudanças. Isso significa que os fatos têm os mesmos valores da origem, mas não passaram pelo mesmo caminho de processamento. Essa diferença deve ser lembrada ao interpretar os casos.

&emsp; A checagem numérica confere as observações das evidências, mas não o enunciado geral da hipótese. Um enunciado pode afirmar que duas séries sobem, enquanto a checagem só confere uma delas. Como o limiar de intensidade é relativo, uma variação pequena em valor absoluto pode passar como significativa.

&emsp; O inventário informa o último evento disponível de cada série, mas não há um campo dedicado para listar as séries que ainda vão chegar. O agente percebe um atraso pela comparação entre a janela investigada e o último evento disponível.
