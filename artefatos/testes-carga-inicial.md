# Testes de carga e resiliência (RNF04, RNF05, RNF11)

&emsp; Este documento registra a execução e os resultados dos testes de resiliência do fluxo de ingestão por CDC descrito em `plano-argus-v3.md`: API Gateway, fila de mudanças, worker de mesclagem (`merge worker`) e o banco PostgreSQL com as camadas bronze, silver e gold. O objetivo central é verificar que uma falha, seja um evento malformado ou uma interrupção de infraestrutura, não derruba o sistema nem causa perda silenciosa de dado. O documento cobre o tratamento de eventos inválidos, dois cenários de falha temporária (fila cheia e timeout), um cenário adicional que combina os dois mecanismos de falha, a verificação de integridade dos marcadores incrementais do ETL, e a visualização implementada para acompanhar latência, throughput, erros e uso de CPU.

## 1. Ferramental e ambiente

&emsp; A carga foi gerada com K6, escolhido por suportar taxa de chegada constante de requisições e por rodar tanto localmente quanto em container, sem depender de infraestrutura adicional. O alvo dos testes foi a rota de ingestão de mudanças, que aceita o evento, grava numa fila e devolve a confirmação de forma assíncrona, antes de qualquer validação de conteúdo.

&emsp; A visualização usa Grafana com CloudWatch como única fonte de dado, sem Prometheus. As quatro métricas exigidas (latência, throughput, erros por segundo e CPU) já existem nativamente no CloudWatch: API Gateway expõe contagem de requisições e latência por percentil, SQS expõe o tamanho e a idade das mensagens nas filas, e ECS e RDS expõem utilização de CPU por serviço e por instância de banco. Subir um Prometheus separado exigiria infraestrutura nova só para duplicar um dado que a nuvem já fornece, o que não se justifica para este projeto. A seção 4 detalha a implementação.

&emsp; Durante a preparação dos testes, a instância de banco então em uso na Sprint esgotou seu espaço de armazenamento por causa do volume acumulado de eventos do simulador, o que interrompeu a ingestão por um período. Diante da limitação de custo do ambiente acadêmico, que impede redimensionar ou restaurar uma instância existente, a equipe optou por provisionar uma instância de teste isolada, com o mesmo esquema aplicado do zero, para não misturar o resultado dos testes de resiliência com o incidente de capacidade. Essa instância de teste não substitui o ambiente de referência do projeto e não faz parte do desenho de arquitetura descrito em `plano-argus-v3.md`.

&emsp; Um erro real foi encontrado e corrigido durante a preparação dos testes: a função que mescla o log de mudanças na tabela corrente do bronze não incorporava a chave primária enviada separadamente do conteúdo alterado, o que fazia colunas obrigatórias chegarem vazias e o registro ser rejeitado. A correção passou a fundir a chave com o conteúdo antes da gravação, e o gerador de carga foi reescrito com um construtor de evento por tabela de origem, já que as seis tabelas monitoradas têm esquemas e chaves diferentes entre si.

## 2. Teste de tratamento de eventos inválidos (RNF04)

&emsp; O objetivo central deste teste é garantir que um evento incorreto não interrompa o recebimento dos demais e que a causa da falha seja identificável posteriormente. Foram exercitados cinco tipos de item inválido dentro de um lote misto, cada um repetido três vezes: tabela de origem ausente, tabela desconhecida, tipo de operação inválido, chave primária vazia e atualização sem o conteúdo alterado. Além desses, foi enviado um corpo de requisição inteiro malformado, que não chega a ser separado em itens individuais.

&emsp; A rejeição acontece de forma assíncrona, dentro do worker de mesclagem, e não no momento da requisição: a integração entre o API Gateway e a fila encaminha o conteúdo recebido sem validá-lo, de modo que toda requisição desta suíte retorna sucesso imediato. O worker é quem separa os itens válidos dos inválidos, processa os primeiros normalmente e desvia os segundos para a fila de rejeitados na primeira tentativa, sem esperar o número máximo de tentativas nativo do serviço de fila.

| Critério de aceite | Resultado |
|---|---|
| Cada caso de item inválido é identificável na fila de rejeitados | 18 de 18 casos aparecem com a causa específica registrada |
| Eventos válidos do mesmo lote de um item inválido continuam sendo processados | 150 de 150 eventos válidos confirmados no log de mudanças, sem perda |
| O caso de corpo inteiro malformado não contamina eventos válidos do mesmo corpo | confirmado: nenhum evento válido do mesmo corpo malformado aparece como processado |
| O worker não trava nem reinicia por causa de payload malformado | confirmado por observação da contagem de tarefas em execução durante o teste |

&emsp; A tabela a seguir reproduz uma amostra real capturada da fila de rejeitados nesta sprint, com o motivo exato registrado pelo worker para cada tipo de caso (o mesmo gerador de evento inválido foi reaproveitado no cenário de aprofundamento da seção 4, o que permitiu recapturar a mesma amostra em outra execução).

| Caso enviado | Motivo registrado na fila de rejeitados |
|---|---|
| Chave primária vazia (`pk: {}`) | `pk vazia: o MERGE nao tem como identificar a linha` |
| Tabela de origem desconhecida | `tabela desconhecida: 'tabela_fantasma_k6'. Tabela nova exige migration` |
| Tipo de operação inválido (`op: "x"`) | `Input should be 'i', 'u', 'd' or 'r'` |
| Campo `source_table` ausente | `source_table: Field required` |
| Atualização sem conteúdo alterado (`op: "u"` sem `after`) | `op='u' exige after, que veio vazio` |
| Corpo inteiro do POST malformado | `JSON invalido: Expecting value: line 1 column 15` |

&emsp; Cada linha identifica exatamente o campo e a regra de validação que causou a rejeição, e não apenas o fato de que algo falhou. É essa especificidade que permite a um operador diferenciar, sem consultar o código, se um evento foi rejeitado por um problema de schema, de tipo, ou de conteúdo ausente, o que resolve diretamente a exigência de que a falha seja identificável posteriormente.

&emsp; O resultado confirma que a rejeição funciona por item dentro de um lote misto, e não por lote inteiro, exceto no caso degenerado de um corpo de requisição que não pode nem ser interpretado como uma lista de itens, situação em que a perda se limita ao próprio corpo malformado e não se propaga a outras requisições.
