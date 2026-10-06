# Avaliação do modelo real contra as trajetórias-ouro

Estado em 06/10/2026: **laço de avaliação criado; correção de prompt aplicada e
validada ao vivo com resultado parcial — a causa menor das chamadas inválidas
sumiu, mas a principal persiste porque o modelo ignora a instrução.**

Este documento registra o que a avaliação do modelo real encontrou e o que foi
mudado por causa dela. Ele é a continuação de [recorte-real-local.md](recorte-real-local.md),
que relatou a primeira investigação do agente em dados reais, na qual o modelo
desistiu alegando ausência de dados de 4xx que, na verdade, estavam no recorte.

## O que é o laço de avaliação

Até aqui, só dava para saber se o agente investigava bem rodando o fluxo real
inteiro: banco local carregado, checkpoint reconstruído da bronze e uma execução
com o Ollama. Isso é caro de repetir a cada ajuste de prompt.

O laço de avaliação resolve isso de forma barata. Cada caso sintético
(`apps/fullstack/agente/fixtures/caso-*.json`) tem um **roteiro**: uma sequência
fixa de passos que descreve a investigação esperada, sem rede. Chamamos esse
roteiro de **trajetória-ouro** — é a referência de como um investigador cuidadoso
deveria agir naquele caso. O script
[avaliar_modelo.py](../../apps/fullstack/agente/scripts/avaliar_modelo.py)
roda cada caso duas vezes: uma com a trajetória-ouro, para fixar o **desfecho**
esperado (a conclusão a que o caso deveria chegar — uma hipótese, ou a desistência
por evidência insuficiente), e outra com o modelo configurado em `OLLAMA_*`. Depois
compara os dois e mede onde o modelo diverge.

O resultado sai como tabela e como JSON em `apps/fullstack/agente/saidas/eval/`
(ignorado pelo Git). Para cada caso, o script grava o desfecho esperado e o obtido,
o número de **chamadas inválidas** (consultas que a ferramenta recusou por
argumento errado), os passos em formato inválido e a trajetória completa, com cada
consulta e a hipótese. O processo termina com código de erro se algum caso não
chegou ao desfecho esperado, então o alvo serve de porteira em iteração.

```bash
make -C apps/fullstack agente-eval       # avalia o modelo real do .env
make -C apps/fullstack agente-eval-seco  # ensaio seco: roteiro dos dois lados
```

## O que a avaliação encontrou

O modelo avaliado foi o `qwen3-coder:30b`, servido pelo Ollama da rede do Inteli.
Nas execuções em que o servidor respondeu, o padrão foi consistente:

| Caso | Desfecho esperado | Desfecho obtido | Chamadas inválidas |
|---|---|---|---|
| `caso-01-deploy` | hipotese | hipotese / resposta_invalida | 3 a 4 |
| `caso-02-borda` | hipotese | hipotese | 3 |
| `caso-03-fonte-atrasada` | evidencia_insuficiente | hipotese | 0 |

Três achados, em ordem de importância:

**1. O mau uso de ferramenta era sistemático, não azar.** Entre 6 e 7 chamadas
inválidas por execução, repetidas em casos diferentes. Isso confirma que o gargalo
é o modelo, e não o esqueleto determinístico que o cerca. O diagnóstico do script
apontou duas causas exatas:

- O modelo **copiava o texto da descrição como valor do argumento**. A descrição
  de cada ferramenta dizia, por exemplo, `"cursor": "opcional"`, e o modelo enviava
  literalmente a string `"opcional"` como valor do campo `cursor`.
- O modelo chamava `consultar_contexto` **sem `source` nem `entity`**. Essa
  ferramenta exige ao menos um dos dois, mas a regra estava escondida dentro de um
  texto que parecia um valor de exemplo. Seis das sete chamadas inválidas de uma
  execução foram esse erro.

**2. O modelo erra nos dois sentidos.** Na investigação em dados reais
([recorte-real-local.md](recorte-real-local.md)), o modelo desistiu quando não
devia. No `caso-03-fonte-atrasada`, ele fez o oposto: concluiu uma hipótese onde a
trajetória-ouro desiste. Esse caso é mais sutil — o modelo encontrou uma alta
**real** de erros 5xx (de ~0,4 para ~3,5) e a propôs como hipótese; a trajetória-ouro
desiste porque os dados que **explicariam** a causa (quebra por UF, deploy na janela)
estão defasados ou ausentes. Não é evidência inventada, e sim uma conclusão de nível
de sintoma onde a referência prefere a cautela.

**3. A latência está no limite.** Casos que exigem mais passos do modelo levaram
centenas de segundos e, com o servidor sob carga, a primeira chamada chega a não
retornar dentro do tempo-limite do cliente, terminando o caso como
`erro_de_execucao` sem nenhuma investigação.

## O que foi mudado

**Correção de prompt, versão `2.3.0`** (em
[prompt.py](../../apps/fullstack/agente/src/argus_agente/prompt.py)), mirando as
duas causas das chamadas inválidas:

- A descrição de cada ferramenta deixou de usar valores de exemplo. Os argumentos
  agora aparecem como listas de **nomes**, separados em obrigatórios e opcionais,
  com as regras numa `nota`. Não existe mais a string `"opcional"` para o modelo
  copiar. Uma verificação offline confirma que a mensagem de abertura enviada ao
  modelo não contém mais nenhum desses valores copiáveis.
- A exigência de `source` ou `entity` no `consultar_contexto` passou a ser
  explícita, tanto na descrição da ferramenta quanto numa linha própria do prompt.
- Linhas novas dizem ao modelo para não enviar o texto da descrição como valor e
  lembram que deploys e eventos operacionais vêm por `consultar_contexto`, nunca
  por uma série inventada em `consultar_serie`.

A decisão de **não** forçar mais cautela no `caso-03` foi deliberada: o objetivo é
fazer o agente funcionar em dados reais, e o erro original ali foi desistir cedo
demais. Empurrar o modelo para a cautela recriaria exatamente aquele problema.

## Status da validação

A correção foi medida ao vivo sob o prompt `2.3.0`, com o servidor respondendo de
forma intermitente (o `caso-02` foi interrompido por queda do servidor no meio da
investigação, e o `caso-03` não chegou a rodar neste ciclo). O resultado é
**parcial**:

| Caso | Chamadas inválidas, antes | Chamadas inválidas, com `2.3.0` | O que sobrou |
|---|---|---|---|
| `caso-01-deploy` | 3 a 4 | 4 | `consultar_contexto` sem `source`/`entity` |
| `caso-02-borda` | 3 | 1 (caso cortado pelo servidor) | `consultar_contexto` sem `source`/`entity` |

Dois aprendizados, um de cada lado:

- **A causa menor sumiu.** O modelo não envia mais a string `"opcional"` como
  valor copiado da descrição. A reestruturação da descrição das ferramentas
  resolveu esse ponto de forma estrutural: o valor que ele copiava não existe mais
  na entrada.
- **A causa principal persiste.** O modelo continua chamando `consultar_contexto`
  sem `source` nem `entity`, mesmo com a exigência agora explícita no prompt, e
  ainda **repete a mesma chamada inválida** depois de o erro pedir que não repita.
  Uma instrução de texto não fez o `qwen3-coder:30b` fornecer um argumento
  obrigatório. Isso é um limite de aderência do modelo, não um problema da
  descrição — e é a evidência mais forte, até aqui, de que o gargalo é o modelo.

A latência do servidor compartilhado ainda atrapalha a medição: um dos casos
terminou como `erro_de_execucao` por queda no meio da investigação, e a primeira
chamada chega a levar centenas de segundos. Uma execução limpa dos três casos,
num momento de menor carga, ainda é útil para fechar a tabela, mas não muda o
aprendizado principal.

## Próximos passos

- **Testar um modelo instruct/reasoning no lugar do `qwen3-coder:30b`.** Como a
  instrução de prompt não resolveu a chamada inválida de `consultar_contexto`,
  este é agora o passo de maior retorno; o laço de avaliação já dá o baseline
  (`caso-01` com 4 inválidas) para comparar de forma objetiva.
- Rodar `agente-eval` com o servidor menos ocupado e fechar a tabela dos três
  casos num ciclo limpo.
- Avaliar um remédio em código para a chamada sem `source`/`entity`, já que o
  modelo não cumpre a instrução sozinho — por exemplo, uma mensagem de erro mais
  diretiva ou uma recusa que oriente a próxima chamada, sem preencher o argumento
  pelo modelo.
- Decidir o tratamento do `caso-03`: aceitar a conclusão de nível de sintoma como
  válida, ou ajustar a trajetória-ouro para refletir o que se espera do agente.
