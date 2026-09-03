# Infraestrutura e integração

> **Este arquivo é um template.** Todo bloco de citação marcado `PREENCHER`,
> `DECIDIR` ou `EVIDÊNCIA` é instrução, não conteúdo: diz o que escrever ali e o
> que precisa ser mostrado no vídeo. Marcadores `{{ }}` são lacunas. Remova todas
> as instruções e marcadores antes do commit da entrega — um bloco `PREENCHER`
> sobrevivente é lido pelo avaliador como seção incompleta.
>
> Convenções herdadas dos demais artefatos: parágrafos abrem com `&emsp;`,
> figuras vão centralizadas com legenda `Figura N — ...` e fonte, tabelas
> resumem decisões, e o texto descreve **o ambiente efetivamente implantado**,
> não a intenção de projeto. O que ainda não existe é marcado como tal.

&emsp; {{Parágrafo de abertura: o que este artefato cobre — provisionamento da
infraestrutura em nuvem e integração front-end/back-end —, sobre qual branch e
qual conta AWS o texto foi escrito, e a data da verificação.}}

## Divergências de nomenclatura

> **PREENCHER** · Registre as divergências entre a especificação e o repositório
> antes que o avaliador as encontre sozinho. O `backend.md` já faz isso na
> abertura; siga o mesmo padrão. As duas conhecidas hoje estão pré-listadas.

| Especificação | Repositório | Tratamento |
|---|---|---|
| `infraestrutura_integracao.md` (seção de vídeos) e `infraestrutura-integracao.md` (cabeçalho) | `artefatos/infraestrutura-integracao.md` | {{Adotado o hífen, coerente com `arquitetura-inicial.md`}} |
| `/apps/fullstack` | `apps/basica` | {{Renomear a pasta **ou** registrar a divergência — decidir, ver seção 10}} |
| {{ }} | {{ }} | {{ }} |

## Rastreabilidade da rubrica

> **PREENCHER** · Mantenha esta tabela atualizada até a véspera da entrega. São
> dez itens de peso 1,0. `Status` aceita apenas: `não iniciado`, `provisionado`,
> `documentado`, `filmado`, `pronto`.

| # | Item da rubrica | Peso | Onde está | Status |
|---|---|---|---|---|
| R-a | Diagrama de implantação com ênfase em nuvem | 1,0 | Seção 2 | {{ }} |
| R-b | Descrição dos componentes e justificativa | 1,0 | Seção 3 | {{ }} |
| R-c | Plano de deploy na AWS, incluindo CloudFront | 1,0 | Seção 4 | {{ }} |
| R-d | Análise de impacto nos ODS da ONU | 1,0 | Seção 6 | {{ }} |
| V1-a | VPC, subnets pública/privada, NAT, logs distribuídos | 1,0 | Seções 3.1 e 7 | {{ }} |
| V1-b | Bastion Host com regras seguras de acesso | 1,0 | Seções 3.2 e 7 | {{ }} |
| V1-c | ASG de EC2 com política de escalonamento + ALB | 1,0 | Seções 3.3, 5 e 7 | {{ }} |
| V1-d | Banco de dados em RDS | 1,0 | Seções 3.4 e 7 | {{ }} |
| V2-a | Testes de validação funcional | 1,0 | Seção 8 | {{ }} |
| V2-b | Comunicação entre serviços em ambiente integrado | 1,0 | Seção 8 | {{ }} |

---

## 1. Contexto e escopo

&emsp; O Argus é um sistema de telemetria e correlação de falhas para a cadeia de
entrega de streaming do Grupo Globo. Aplicações cliente enviam eventos a uma API de
ingestão; o pipeline normaliza, persiste e expõe os dados a um dashboard que apresenta
a linha do tempo do incidente e as hipóteses de causa provável. A arquitetura
consolidada até a sprint anterior está descrita em
[`arquitetura-inicial.md`](arquitetura-inicial.md); este artefato cobre o que muda na
camada de infraestrutura e na integração entre front-end e back-end.

&emsp; A topologia anterior executa inteiramente sobre a VPC padrão da conta do AWS
Academy Learner Lab. As tasks recebem endereço público (`assign_public_ip = true`)
porque essa era a forma de obter saída para a internet sem provisionar um NAT Gateway,
e o dashboard é servido pelo endpoint de website do Amazon S3, que atende somente em
HTTP. Nenhuma das duas escolhas foi apresentada como definitiva: `arquitetura-inicial.md`
registra a primeira como “concessão do laboratório e não a postura recomendada para
produção” (§4.7) e a segunda como “fallback temporário para demonstração em rede
confiável” (§4.8), esta com a consequência explícita de que o token colado pelo
operador trafega em claro e pode ser observado por um intermediário de rede.

&emsp; Esta revisão paga essas duas dívidas e acrescenta a camada de escalabilidade
horizontal que faltava ao caminho de leitura. O sistema passa a ter rede própria, com
sub-redes públicas e privadas distribuídas em duas zonas de disponibilidade; as cargas
de trabalho deixam de ter endereço público e alcançam a internet por NAT Gateway; o
acesso administrativo passa a ser mediado por um bastion host; a API consumida pelo
dashboard deixa de ser uma função sem servidor e executa em instâncias Amazon EC2 sob
um Auto Scaling Group, atrás de um Application Load Balancer; e a entrega do front-end
passa por uma distribuição do Amazon CloudFront, que fornece o TLS ausente.

&emsp; A migração é deliberadamente parcial. O **caminho síncrono** — a requisição que
o dashboard faz e cuja latência o usuário percebe — é o que recebe grupo de
escalonamento e balanceador, porque é onde a variação de carga é observável e onde a
perda de uma instância tem efeito imediato sobre a experiência. O **caminho assíncrono**
de ingestão permanece em filas com consumidores no ECS Fargate: o desacoplamento por
SQS já absorve rajada, o backlog da fila é a métrica de saúde natural desse fluxo, e
reescrevê-lo sobre EC2 acrescentaria risco de regressão sem ganho arquitetural
correspondente. A seção 3.8 registra a decisão junto com a alternativa descartada.

### 1.1 Legenda de estado

- **Implementado:** existe no código e na infraestrutura Terraform aplicada.
- **Condicional:** existe no Terraform, mas depende de variáveis do ambiente.
- **Planejado:** decisão registrada, ainda sem recurso Terraform.

### 1.2 O que mudou nesta revisão

> **ATUALIZAR A CADA APLICAÇÃO** · A coluna `Estado` reflete o que existe na conta,
> não a intenção. Enquanto um item estiver como `Planejado`, o texto correspondente
> nas seções 3 e 4 descreve projeto; ao aplicar, trocar o estado aqui e verificar se
> a redação daquela seção passou para o presente do indicativo.

| Item | Antes | Agora | Estado |
|---|---|---|---|
| Ambiente de rede | VPC padrão da conta, apenas sub-redes públicas | VPC dedicada, sub-redes públicas e privadas em duas AZs | Planejado |
| Saída para a internet das cargas | Endereço público na própria task | NAT Gateway em sub-rede pública | Planejado |
| Acesso administrativo | Task avulsa `migration` dentro da VPC | Bastion host, com a task `migration` mantida | Planejado |
| API de leitura | AWS Lambda (Flask por `lambda_handler`) | EC2 em Auto Scaling Group atrás de ALB | Planejado |
| Elasticidade do caminho síncrono | Concorrência da Lambda, implícita | Política de escalonamento declarada no ASG | Planejado |
| Entrega do dashboard | Endpoint de website S3, somente HTTP | CloudFront com TLS e bucket privado por OAC | Planejado |
| Observabilidade de rede | Log de aplicação e alarmes do CloudWatch | Acrescidos VPC Flow Logs e access logs do ALB | Planejado |
| Ingestão e processamento | API Gateway → SQS → ECS Fargate | Inalterado, realocado para sub-rede privada | Planejado |
| Banco de dados | RDS PostgreSQL 16 privado na VPC padrão | RDS PostgreSQL 16 em subnet group privado da VPC dedicada | Planejado |

### 1.3 Fora de escopo

&emsp; Este artefato não redescreve o que já está documentado em outro lugar do
repositório. Modelo de dados, migrations, ETL, checkpoints e coordenação do
processamento estão em [`arquitetura-inicial.md`](arquitetura-inicial.md) e em seus
apêndices; os endpoints da API de leitura e a autenticação por token Bearer, em
[`backend.md`](backend.md); as telas do dashboard e as decisões de interface, em
[`frontend.md`](frontend.md); a origem e a correlação dos dados cedidos pelo parceiro,
em [`correlacao_dados.md`](correlacao_dados.md). Referência cruzada substitui cópia:
um mesmo fato mantido em dois artefatos diverge no commit seguinte.

&emsp; Permanece igualmente fora de escopo a camada agêntica de correlação, que
pertence ao roadmap de produção e não ao recorte implantado — distinção estabelecida
em [`entendimento_negocio.md`](entendimento_negocio.md) e preservada aqui.

---

## 2. Diagrama de implantação do sistema — peso 1,0

> **PREENCHER** · O diagrama é o item mais barato de perder ponto e o mais fácil de
> acertar. Exigências: notação de implantação (estereótipos `«execution environment»`,
> `«database»`, `«message queue»`, `«object storage»`), **fronteiras de rede
> desenhadas** — a VPC, cada zona de disponibilidade, cada sub-rede — e setas
> rotuladas com o protocolo e a porta reais. Todo recurso citado na seção 3 precisa
> aparecer aqui, e vice-versa; a matriz de conexões da seção 3.7 é o checklist
> cruzado dessa correspondência.
>
> Erros que custam nota: sub-rede privada desenhada sem o NAT visível; ALB colocado
> dentro da sub-rede privada; RDS sem indicação de zona de disponibilidade; bastion
> sem a seta mostrando de onde parte o SSH.

<div align="center">

<sub>Figura 1 — Implantação do Argus na AWS, região `us-east-1`</sub>

![Diagrama de implantação do Argus v4](assets/arquitetura-implantacao-v4.png)

<sup>Fonte: material produzido pelos autores (2026).</sup>

</div>

&emsp; {{Parágrafo de leitura do diagrama: o que a figura mostra, o que o traço
tracejado significa e qual é o caminho da requisição do dashboard. Escrever **depois**
de a topologia estar aplicada, para descrever o que existe e não o que se pretendia.}}

### 2.1 Fonte editável e exportação

&emsp; A fonte do diagrama é [`assets/arquitetura-implantacao-v4.drawio`](assets/arquitetura-implantacao-v4.drawio),
em XML não comprimido — mesma convenção de `der-dynamodb.drawio` e
`diagrama_casos_de_uso.drawio`, que mantém o arquivo legível no `diff` do Git. O PNG
publicado no relatório é gerado a partir dele e commitado junto; **os dois arquivos
andam sempre no mesmo commit**, sob pena de a figura do relatório divergir da fonte.

&emsp; O diagrama v3 (`assets/arquitetura-implantacao-v3.svg`) permanece intacto,
porque é a figura referenciada por [`arquitetura-inicial.md`](arquitetura-inicial.md).
Editá-lo no lugar faria o artefato da sprint anterior exibir infraestrutura que não
existia quando aquele texto foi escrito.

**Exportar o PNG**

&emsp; O conteúdo do diagrama ocupa cerca de 1855 × 1285 px na escala 1. As opções
abaixo produzem um PNG de aproximadamente 3750 × 2610 px, nítido quando o avaliador
amplia a figura e ainda leve o bastante para o repositório.

| Opção do diálogo `Arquivo → Exportar como → PNG` | Valor | Motivo |
|---|---|---|
| Zoom | **200 %** | A fonte dos rótulos é 10 pt; abaixo disso o texto embaça ao ampliar |
| Borda | **10** | Evita que a caixa externa encoste na margem da imagem |
| Tamanho | **Diagrama** | Recorta no conteúdo; `Página` deixa faixa branca inútil |
| Fundo transparente | **desmarcado** | Fundo transparente vira preto no tema escuro do GitHub e apaga o texto |
| Cor de fundo | **branco** | — |
| Somente seleção | **desmarcado** | — |
| Sombra | **desmarcado** | Aumenta o arquivo sem ganho de leitura |
| Grade | **desmarcado** | — |
| Incluir cópia do meu diagrama | **desmarcado** | O `.drawio` já é versionado; embutir o XML no PNG cria uma segunda fonte da verdade que diverge |

&emsp; Equivalente em linha de comando (`npm i -g @drawio/drawio-desktop-cli` ou o
binário do aplicativo):

```bash
drawio -x -f png -s 2 -b 10 --crop \
  -o artefatos/assets/arquitetura-implantacao-v4.png \
     artefatos/assets/arquitetura-implantacao-v4.drawio
```

&emsp; **Conferir depois de exportar:** abrir o PNG em 100 % e ler o rótulo menor —
se não der para ler, exportar de novo em 300 %. O Markdown do GitHub reduz a figura
à largura da coluna de leitura, cerca de 880 px, o que torna os rótulos ilegíveis em
linha; o leitor precisa clicar na imagem para vê-la em tamanho real, e é por isso que
o PNG exportado tem de ser grande. Se o arquivo passar de 2 MB, reexportar em 150 %
antes de comprometer o peso do repositório.

### 2.2 Convenções de notação

| Elemento | Significado |
|---|---|
| Retângulo com título no canto superior | Fronteira de rede: nuvem, VPC, zona de disponibilidade, sub-rede |
| Traço contínuo | Recurso provisionado |
| Traço tracejado | Recurso planejado, ainda sem correspondente na conta |
| `«…»` | Estereótipo do nó, na notação de implantação |
| Rótulo da seta | Protocolo e porta efetivamente usados |
| Contorno laranja tracejado atravessando as AZs | Auto Scaling Group, que é um agrupamento lógico e não um recurso de rede |

---

## 3. Componentes e justificativa da arquitetura — peso 1,0

> **PREENCHER** · Este item pede duas coisas distintas e a segunda é a que
> costuma faltar: **descrição** de cada componente e **justificativa** da escolha.
> Justificativa não é "o ALB distribui carga entre as instâncias" — isso é
> descrição. Justificativa é qual alternativa foi descartada, contra qual atributo
> de qualidade, e a que custo. Use a ficha padrão abaixo para cada componente;
> o campo que não se aplicar recebe `—`, nunca some.

**Ficha padrão de componente**

| Campo | Conteúdo |
|---|---|
| Papel no sistema | {{ }} |
| Configuração efetiva | {{tipo de instância, tamanho, AZs, parâmetros relevantes}} |
| Entradas / saídas | {{quem chama, o que chama, por qual porta e protocolo}} |
| Estado | {{Implementado / Condicional / Planejado}} |
| Alternativa descartada | {{ }} |
| Modo de falha previsto e mitigação | {{ }} |
| Custo estimado | {{ordem de grandeza no Learner Lab}} |
| Arquivo Terraform | {{ }} |

### 3.1 Rede — VPC, sub-redes, NAT e rotas

> **PREENCHER** · Esta subseção sustenta o item V1-a. Precisa conter, em texto e
> não só em tabela: o CIDR da VPC e o de cada sub-rede; quantas AZs e por quê
> (o ALB exige no mínimo duas, e o Multi-AZ do RDS também); qual tabela de rotas
> pertence a qual sub-rede e para onde aponta a rota `0.0.0.0/0` em cada uma —
> Internet Gateway na pública, NAT Gateway na privada; e por que os hosts privados
> precisam de saída (atualização de pacotes, chamadas às APIs da AWS, pull de
> imagem no ECR). Explicite a diferença entre NAT Gateway e Internet Gateway:
> o NAT permite saída sem permitir entrada, e é isso que torna a sub-rede privada.
>
> **DECIDIR** · VPC endpoints para S3, ECR, Secrets Manager e CloudWatch Logs
> reduzem custo e tráfego pelo NAT. Se não forem usados, diga que a decisão foi
> consciente e qual o custo dela.

| Sub-rede | Tipo | CIDR | AZ | Rota `0.0.0.0/0` | O que executa |
|---|---|---|---|---|---|
| {{ }} | pública | {{ }} | {{ }} | Internet Gateway | {{ALB, NAT Gateway, bastion}} |
| {{ }} | privada | {{ }} | {{ }} | NAT Gateway | {{EC2 da aplicação, RDS}} |

**Grupos de segurança**

> **PREENCHER** · Uma linha por SG. A coluna de origem deve referenciar **outro
> security group**, não um CIDR, sempre que possível — é o que caracteriza regra
> segura e é exatamente o que o item V1-b avalia. `0.0.0.0/0` só é aceitável na
> porta 443/80 do ALB e, com ressalva escrita, na 22 do bastion.

| Security group | Regra de entrada | Origem | Regra de saída | Destino |
|---|---|---|---|---|
| `{{alb}}` | TCP 443, TCP 80 | `0.0.0.0/0` | TCP {{porta app}} | `{{sg-app}}` |
| `{{app}}` | TCP {{porta app}} | `{{sg-alb}}` | TCP 5432, TCP 443 | `{{sg-rds}}`, saída |
| `{{bastion}}` | TCP 22 | {{CIDR restrito — justificar}} | TCP 22, TCP 5432 | `{{sg-app}}`, `{{sg-rds}}` |
| `{{rds}}` | TCP 5432 | `{{sg-app}}`, `{{sg-bastion}}` | — | — |

**Observabilidade da rede (logs distribuídos)**

> **PREENCHER** · O item V1-a pede "observabilidade com logs distribuídos"
> explicitamente dentro do tópico de VPC. Cubra: VPC Flow Logs (destino, formato,
> retenção, o que se consegue responder com eles); agente CloudWatch nas instâncias
> do ASG, com o caminho do arquivo de log da aplicação e o log group de destino;
> logs de acesso do ALB em S3; e como uma requisição é correlacionada de ponta a
> ponta — o repositório já emite `X-Request-Id` por requisição, então diga onde
> esse identificador entra e sai. Nomeie os log groups pelo nome real.

| Fonte | Destino | Retenção | Pergunta que responde |
|---|---|---|---|
| VPC Flow Logs | {{log group}} | {{ }} | {{tráfego rejeitado, origem de conexão inesperada}} |
| Aplicação (EC2) | {{log group}} | {{ }} | {{erro por requisição, latência}} |
| Access logs do ALB | {{bucket}} | {{ }} | {{código de resposta, tempo de backend}} |
| {{ }} | {{ }} | {{ }} | {{ }} |

### 3.2 Acesso administrativo — Bastion Host

> **PREENCHER** · Item V1-b. O que precisa estar escrito: por que existe um host
> intermediário em vez de acesso direto às instâncias privadas; em qual sub-rede
> ele está e por quê; qual o tipo de instância e por que o menor possível; como a
> chave SSH é gerenciada e onde **não** está (não no repositório); qual CIDR de
> origem é permitido na porta 22 e o que acontece quando alguém troca de rede;
> e o que é possível fazer a partir dele — acesso às instâncias da aplicação e
> túnel para a porta 5432 do RDS.
>
> **DECIDIR** · AWS Systems Manager Session Manager elimina a porta 22 aberta e a
> chave SSH, mas depende de perfil IAM e de endpoints/NAT, e o papel `voclabs`
> pode não permitir tudo. Se optar por bastion clássico, escreva por que — e se
> testar o Session Manager e ele funcionar, mostre os dois no vídeo: um bastion
> sem porta 22 aberta ao mundo é o cenário mais forte possível para este item.

```bash
# {{Acesso a uma instância privada através do bastion}}
ssh -J ec2-user@{{ip-bastion}} ec2-user@{{ip-privado}}

# {{Túnel para o RDS privado, para inspeção com psql local}}
ssh -N -L 5432:{{endpoint-rds}}:5432 ec2-user@{{ip-bastion}}
```

### 3.3 Camada de aplicação — Auto Scaling Group de EC2 e Application Load Balancer

> **PREENCHER** · Item V1-c, e o de maior densidade técnica. Descreva:
>
> - **Launch template** — AMI, tipo de instância, perfil IAM, `user_data`
>   (como o código chega à instância: pull de artefato do S3, imagem do ECR,
>   `git clone`?), e por que versionado.
> - **Auto Scaling Group** — `min`, `max`, `desired`, quais sub-redes, qual tipo
>   de health check (`ELB` e não `EC2`, senão uma instância com o processo morto
>   continua no grupo), `health_check_grace_period` e por que esse valor.
> - **Política de escalonamento** — a rubrica pede a política, não só o grupo.
>   Escolha entre *target tracking* (mais simples, use `ALBRequestCountPerTarget`
>   ou `ASGAverageCPUUtilization`) e *step scaling*, declare o valor-alvo e
>   justifique-o com a carga esperada. Registre cooldown e warmup.
> - **Application Load Balancer** — listeners, target group, protocolo, caminho
>   e códigos aceitos do health check, intervalo e limiar; cross-zone; se o
>   listener 80 redireciona para 443.
>
> **EVIDÊNCIA** · O vídeo precisa mostrar o ASG escalando de fato. Planeje o
> gatilho agora: um teste de carga contra o DNS do ALB até a política disparar,
> com a aba "Activity" do ASG aberta. Ver seção 7.

| Parâmetro | Valor | Justificativa |
|---|---|---|
| Tipo de instância | {{ }} | {{ }} |
| `min` / `desired` / `max` | {{ }} | {{ }} |
| Métrica de escalonamento | {{ }} | {{ }} |
| Valor-alvo | {{ }} | {{ }} |
| Health check do target group | {{caminho, intervalo, limiar}} | {{ }} |
| Zonas de disponibilidade | {{ }} | {{ }} |

### 3.4 Persistência — Amazon RDS

> **PREENCHER** · Item V1-d. Aproveite o que já está escrito em
> `arquitetura-inicial.md` §3.5 e §4.2 (PostgreSQL em vez de DynamoDB) em vez de
> reescrever. O que precisa ser novo aqui: a instância agora está em subnet group
> privado; quem tem rota até ela; `multi_az` ligado ou desligado e o custo da
> decisão; backup automático, janela e retenção; criptografia em repouso; e como
> as migrations são aplicadas na topologia nova.

### 3.5 Entrega do front-end — S3 e CloudFront

> **PREENCHER** · Descrição do bucket, da política de acesso e da distribuição.
> O plano de inclusão do CloudFront fica na seção 4.4; aqui só o papel do
> componente. Registre a limitação conhecida: `arquitetura-inicial.md` §4.8
> afirma que as operações de CDN não são permitidas pelo papel `voclabs`.
> **Revalide isso** antes de escrever — se o CloudFront provisionar, a seção 4.4
> descreve algo real em vez de hipotético, e o problema de token trafegando em
> HTTP claro deixa de existir.

### 3.6 Pipeline assíncrono e demais serviços

> **PREENCHER** · API Gateway, SQS, DLQs, workers, ECR, Secrets Manager. Se
> permanecerem como estão, resuma e aponte para `arquitetura-inicial.md` §3 —
> não duplique. Se algum deles mudou de sub-rede na topologia nova, isso precisa
> ser dito, porque muda a rota de saída e o custo de NAT.

### 3.7 Matriz de conexões

> **PREENCHER** · Uma linha por seta do diagrama da seção 2. Serve de checklist
> cruzado: seta sem linha aqui é seta não justificada; linha sem seta é
> componente esquecido no desenho.

| Origem | Destino | Protocolo / porta | Autenticação | Rede |
|---|---|---|---|---|
| {{ }} | {{ }} | {{ }} | {{ }} | {{pública / privada}} |

### 3.8 Tabela de decisões arquiteturais

> **PREENCHER** · Mesmo formato de `arquitetura-inicial.md` §4.9, com as decisões
> **desta** sprint. Candidatas: EC2 em ASG para o caminho síncrono coexistindo com
> Fargate no assíncrono; NAT Gateway em vez de IP público nas cargas; bastion
> versus Session Manager; CloudFront à frente de S3 e ALB versus website S3 em
> HTTP; Multi-AZ ligado ou desligado.

| # | Decisão | Alternativa descartada | Atributo de qualidade | Falha prevista e mitigação | Custo | Rollback |
|---|---|---|---|---|---|---|
| 1 | {{ }} | {{ }} | {{ }} | {{ }} | {{ }} | {{ }} |

---

## 4. Plano de deploy na AWS — peso 1,0

> **PREENCHER** · "Detalhado" é o critério. Um leitor que nunca viu o projeto deve
> conseguir reproduzir o ambiente do zero seguindo esta seção, sem perguntar nada.
> Cada passo precisa de comando literal, saída esperada e o motivo de estar naquela
> posição da ordem. O repositório já tem `DEPLOY-WINDOWS.md` e `rodar-aws.ps1` —
> mantenha o runbook lá e aqui a descrição do plano, com ponteiro cruzado, em vez
> de duas cópias que divergem na semana seguinte.

### 4.1 Pré-requisitos

> **PREENCHER** · Ferramentas e versões; verificação de conta e sessão
> (`aws sts get-caller-identity` e uma chamada com permissão real); variáveis de
> ambiente; preenchimento do `terraform.tfvars`; e o aviso sobre o `terraform.tfstate`
> — não apagar o state enquanto ele representar recursos existentes, e confirmar o
> account ID a cada nova sessão do Learner Lab.

### 4.2 Recursos provisionados

| Recurso AWS | Finalidade | Arquivo Terraform |
|---|---|---|
| VPC, sub-redes, IGW, NAT, tabelas de rota | {{ }} | `{{vpc.tf}}` |
| Bastion Host | {{ }} | `{{bastion.tf}}` |
| Launch template + Auto Scaling Group | {{ }} | `{{asg.tf}}` |
| Application Load Balancer + target group | {{ }} | `{{alb.tf}}` |
| RDS PostgreSQL | {{ }} | `rds.tf` |
| CloudFront + certificado ACM | {{ }} | `{{cloudfront.tf}}` |
| {{demais recursos herdados}} | {{ }} | {{ }} |

### 4.3 Ordem de implantação

> **PREENCHER** · Ordem por dependência real, com o motivo de cada precedência —
> o valor da seção está aí, não na lista. Esqueleto sugerido, a ser confirmado
> contra o que o Terraform realmente exige:
>
> 1. Rede primeiro: sem sub-rede não há subnet group de RDS nem ASG.
> 2. Segurança: SGs e perfis IAM antes de qualquer recurso que os referencie.
> 3. RDS: leva dezenas de minutos; iniciar cedo evita bloquear os passos seguintes.
> 4. Artefato da aplicação publicado (imagem no ECR ou pacote no S3) **antes** do
>    launch template, senão a instância sobe e não encontra o que executar.
> 5. Launch template, ALB e target group, e só então o ASG apontando para eles.
> 6. Migrations do banco antes de liberar tráfego: instância saudável contra
>    schema inexistente falha o health check e entra em ciclo de substituição.
> 7. Front-end publicado; distribuição CloudFront por último, pois depende da
>    origem existir.
>
> Registre também as armadilhas já conhecidas do ambiente: aspas obrigatórias em
> `-flag=valor` no PowerShell, `Compress-Archive` proibido para pacote de Lambda,
> conta nova exigindo apply em duas etapas.

```bash
{{comando}}
# saída esperada: {{ }}
```

### 4.4 Inclusão do AWS CloudFront

> **PREENCHER** · Subseção exigida nominalmente pela rubrica — não a dilua dentro
> de 4.3. Ela precisa responder: **por que**, **como** e **com que consequência**.
>
> **Por que.** Hoje o dashboard é servido pelo endpoint de website do S3, que só
> fala HTTP; o operador cola um token na página, e um intermediário de rede pode
> lê-lo ou alterar o JavaScript entregue (`arquitetura-inicial.md` §4.8). O
> CloudFront resolve isso com TLS, e não apenas "melhora a latência" — cite o
> ganho de segurança primeiro, é o argumento mais forte.
>
> **DECIDIR — o ponto de maior valor desta seção.** Duas topologias possíveis:
>
> - *Uma origem*: CloudFront apenas à frente do S3. O dashboard passa a HTTPS,
>   mas as chamadas à API continuam indo direto ao ALB. Se o ALB não tiver
>   certificado, a página HTTPS chamará um endpoint HTTP e o navegador bloqueia
>   por conteúdo misto — problema novo, criado pela própria mudança.
> - *Duas origens*: um comportamento padrão apontando para o S3 e outro, em
>   `/api/*`, apontando para o ALB. Front e API passam a compartilhar origem,
>   o conteúdo misto desaparece, o CORS deixa de ser necessário e o certificado
>   fica num lugar só. É a topologia recomendada aqui; se escolher a outra,
>   escreva por quê.
>
> **Como.** Descreva, na ordem: origem(ns) e Origin Access Control para manter o
> bucket privado (o bucket deixa de ter leitura pública — diga isso, é uma
> melhoria de segurança que vale citar); cache policy por comportamento — estático
> com TTL longo, `/api/*` com cache desabilitado e encaminhamento do cabeçalho
> `Authorization`, que por padrão o CloudFront remove e faz toda chamada
> autenticada retornar 401; `viewer_protocol_policy = redirect-to-https`;
> certificado no ACM **na região us-east-1**, obrigatória para CloudFront;
> domínio próprio ou o `*.cloudfront.net` padrão; e invalidação no deploy do
> front, com o comando literal.
>
> **Consequência.** Tempo de propagação da distribuição, custo, e o que acontece
> se o papel `voclabs` recusar a criação — cenário registrado em
> `arquitetura-inicial.md` §4.8 e que precisa ser revalidado. Se recusar, esta
> seção descreve o plano com a recusa documentada (print do erro), e não some.

| Comportamento | Caminho | Origem | Cache | Cabeçalhos encaminhados |
|---|---|---|---|---|
| Padrão | `/*` | {{S3 via OAC}} | {{TTL longo}} | {{nenhum}} |
| API | `/api/*` | {{ALB}} | {{desabilitado}} | `Authorization`, {{ }} |

```bash
# {{Invalidação após publicar nova versão do front}}
aws cloudfront create-invalidation --distribution-id {{ID}} --paths "/*"
```

### 4.5 Verificação pós-implantação

> **PREENCHER** · Roteiro de aceite executável, com o resultado esperado de cada
> comando. É também o roteiro do Vídeo 2 — escreva uma vez, use duas.

| # | Verificação | Comando | Resultado esperado |
|---|---|---|---|
| 1 | Instâncias saudáveis no target group | {{ }} | {{`healthy` em todas}} |
| 2 | ALB responde | {{ }} | {{HTTP 200}} |
| 3 | Instância privada sem IP público, mas com saída | {{ }} | {{ }} |
| 4 | RDS inacessível de fora, acessível pelo bastion | {{ }} | {{ }} |
| 5 | Front pelo CloudFront em HTTPS | {{ }} | {{ }} |
| 6 | Logs chegando aos log groups | {{ }} | {{ }} |

---

## 5. Alta disponibilidade, escalonamento e rollback

> **PREENCHER** · A descrição do artefato pede explicitamente estas práticas, e
> "políticas de rollback baseadas em auto scale groups" é uma frase específica —
> não responda com "usamos Git". Rollback baseado em ASG significa versão de
> launch template.

### 5.1 Alta disponibilidade

> **PREENCHER** · O que sobrevive à perda de uma instância, de uma AZ e do banco.
> Seja honesto sobre o que **não** sobrevive: se `multi_az` está desligado por
> custo, o RDS é ponto único de falha e isso precisa estar escrito, com o valor
> da variável que reverte a decisão.

| Falha | Efeito | Recuperação | Automática? |
|---|---|---|---|
| Uma instância do ASG | {{ }} | {{substituição pelo health check}} | {{sim}} |
| Uma zona de disponibilidade | {{ }} | {{ }} | {{ }} |
| Instância do RDS | {{ }} | {{ }} | {{ }} |
| NAT Gateway | {{ }} | {{ }} | {{ }} |

### 5.2 Política de escalonamento

> **PREENCHER** · Métrica, valor-alvo, cooldown, warmup, e o raciocínio por trás
> do número. Inclua o comportamento de *scale in*, que é onde mora o risco:
> instância removida no meio de uma requisição. Cubra o *deregistration delay*
> do target group e, se houver processamento em andamento, proteção contra
> encerramento.

### 5.3 Estratégia de deploy e rollback

> **PREENCHER** · O mecanismo concreto:
>
> - Nova versão da aplicação gera **nova versão do launch template**; o ASG passa
>   a apontar para ela.
> - `instance_refresh` substitui as instâncias gradualmente, com
>   `min_healthy_percentage` e, se usado, checkpoints — descreva os valores.
> - Rollback = apontar o ASG para a **versão anterior** do launch template e
>   disparar novo refresh. Escreva o comando.
> - O que dispara o rollback: qual métrica, qual alarme, qual limiar, e quem
>   decide. Rollback sem gatilho definido é intenção, não política.
> - Rollback do banco é separado e não é automático — snapshot antes de migration
>   destrutiva, e o procedimento de restauração.

```bash
# {{Rollback: voltar o ASG para a versão anterior do launch template}}
{{comando}}
```

### 5.4 Observabilidade e alarmes

> **PREENCHER** · Tabela de alarmes com limiar, ação e destino da notificação.
> Um alarme sem destinatário não é observabilidade. Se houver painel no CloudWatch,
> diga quais métricas ele agrega — é bom material de vídeo.

| Alarme | Métrica | Limiar | Ação |
|---|---|---|---|
| {{ }} | {{ }} | {{ }} | {{ }} |

---

## 6. Análise de impacto nos ODS da ONU — peso 1,0

> **PREENCHER** · O erro típico é listar ODS bonitos sem ligação causal com o
> sistema. O critério de "foi mais longe" aqui é profundidade: cada ODS precisa de
> **meta numerada** (9.1, 9.c, 12.2, 13.2 — não apenas "ODS 9"), do **mecanismo**
> pelo qual este sistema em particular a afeta, de um **indicador observável** e da
> **evidência** que sustenta a afirmação. Sem mecanismo, é retórica.
>
> Ancoragem no domínio real do projeto — observabilidade de streaming para o Grupo
> Globo, com correlação de falhas por plataforma, modelo de aparelho, UF e
> operadora (`entendimento_negocio.md`). Candidatos com ligação defensável:
>
> - **ODS 9** (infraestrutura resiliente, indústria inclusiva e inovação) —
>   metas 9.1, 9.4 e 9.c. Mecanismo direto: redução do tempo entre sintoma e
>   hipótese acionável, e suporte deliberado a protocolos e dispositivos legados,
>   que é decisão de projeto documentada, não efeito colateral.
> - **ODS 10** (redução das desigualdades) — o recorte por UF, operadora e modelo
>   de aparelho torna visível a degradação que afeta desproporcionalmente quem tem
>   aparelho antigo ou rede pior; sem esse recorte a média esconde o problema.
> - **ODS 12** (consumo e produção responsáveis) — meta 12.2. Diagnóstico mais
>   rápido reduz reprocessamento e provisionamento defensivo "por precaução".
> - **ODS 13** (ação climática) — pegada de carbono do próprio sistema. Este é o
>   ODS onde o impacto **negativo** é honesto e deve aparecer.
>
> Evite ODS sem ligação causal (3, 4, 16 costumam ser forçados aqui). Melhor três
> ODS bem argumentados do que sete listados.

### 6.1 Método

&emsp; {{Como os ODS foram selecionados, qual fonte foi usada para as metas, e o
que conta como evidência nesta análise.}}

### 6.2 Impactos positivos

| ODS | Meta | Mecanismo neste sistema | Indicador | Evidência |
|---|---|---|---|---|
| {{ }} | {{ }} | {{ }} | {{ }} | {{ }} |

### 6.3 Impactos negativos e mitigação

> **PREENCHER** · Obrigatório, e é o que separa análise de propaganda. O sistema
> mantém RDS e instâncias EC2 ligados continuamente, retém logs e trafega dados —
> tudo consome energia. Trate: dimensionamento mínimo do ASG versus desperdício
> ocioso; retenção de log como custo ambiental além de financeiro; escolha de
> região e a intensidade de carbono da rede elétrica; e o desligamento do ambiente
> de laboratório fora de uso. Reconhecer o custo e mostrar a mitigação pontua mais
> do que negá-lo.

| ODS afetado | Impacto negativo | Mitigação adotada | Mitigação possível, não adotada |
|---|---|---|---|
| {{ }} | {{ }} | {{ }} | {{ }} |

### 6.4 Limites da análise

&emsp; {{O que não foi medido e por quê — por exemplo, ausência de medição real de
consumo energético, estimativas baseadas em tipo de instância e não em telemetria.}}

---

## 7. Vídeo 1 — Infraestrutura provisionada

> **PREENCHER** · Duração exigida: **5 a 7 minutos**. Fora da faixa, o item cai.
> São quatro subitens de peso 1,0, e o avaliador procura evidência no console da
> AWS — tela do console, recurso real, não slide. Grave com o console em inglês ou
> português, mas de forma consistente, e com a fonte grande o bastante para leitura.
>
> Regra que mais custa nota: **falar sobre o recurso não é evidenciar o recurso.**
> Cada item precisa da tela correspondente aberta e do valor visível.

**Link:** {{URL}}

**Roteiro e evidências**

| Tempo | Item | Tela do console | O que precisa estar visível | O que dizer |
|---|---|---|---|---|
| 0:00–0:30 | Abertura | — | — | {{nome do grupo, integrantes, o que será mostrado}} |
| 0:30–2:00 | V1-a rede | VPC → Your VPCs, Subnets, Route tables, NAT gateways | CIDR da VPC; sub-redes públicas e privadas em AZs distintas; rota `0.0.0.0/0` → IGW na pública e → NAT na privada | {{por que a privada não tem rota para o IGW e mesmo assim tem saída}} |
| 2:00–2:40 | V1-a logs | CloudWatch → Log groups; VPC → Flow logs | Log groups com eventos recentes; um flow log e um log de aplicação abertos | {{como se correlaciona uma requisição entre as camadas}} |
| 2:40–3:30 | V1-b bastion | EC2 → Instances; Security Groups | Bastion na sub-rede pública; regra de entrada da porta 22 com origem restrita; SG da aplicação aceitando 22 apenas do SG do bastion | {{por que a origem não é `0.0.0.0/0`}} |
| 3:30–3:50 | V1-b prova | Terminal | SSH no bastion e salto para uma instância privada, ou túnel até o RDS | {{ }} |
| 3:50–5:20 | V1-c ASG + ALB | EC2 → Auto Scaling Groups (abas Details, Activity); Load Balancers; Target Groups | `min`/`desired`/`max`; política de escalonamento com métrica e valor-alvo; targets `healthy`; listener e health check do ALB | {{qual métrica dispara e por quê}} |
| 5:20–6:10 | V1-c escalonamento ao vivo | Terminal com teste de carga + aba Activity do ASG | Carga subindo, alarme disparando, nova instância entrando em serviço | {{ }} |
| 6:10–6:50 | V1-d RDS | RDS → Databases (Connectivity & security) | `Publicly accessible: No`; subnet group privado; SG; Multi-AZ; backup | {{quem consegue alcançar o banco e por qual caminho}} |
| 6:50–7:00 | Fechamento | — | — | {{ }} |

> **EVIDÊNCIA — preparar antes de gravar.** O escalonamento ao vivo é o trecho que
> mais falha na hora. Ensaie: escolha a ferramenta de carga, confirme que a métrica
> escolhida realmente cruza o limiar com a carga que você consegue gerar, e verifique
> o tempo entre o alarme e a instância `InService` — se passar de dois minutos,
> corte o tempo morto na edição ou reduza o cooldown para a demonstração.
> Plano B, caso o escalonamento não dispare a tempo: alterar `desired` manualmente
> e mostrar a atividade resultante, dizendo com todas as letras que foi manual.

**Checklist antes de gravar**

- [ ] Ambiente aplicado e estável; nenhum recurso em estado de erro.
- [ ] Credenciais, tokens e IDs de conta fora de quadro ou borrados.
- [ ] Duração entre 5 e 7 minutos.
- [ ] Áudio audível; console legível em tela cheia.
- [ ] Vídeo acessível sem login e com o link testado numa janela anônima.

---

## 8. Vídeo 2 — Integração front-end e back-end

> **PREENCHER** · Duração exigida: **2 a 4 minutos**. Dois subitens de peso 1,0:
> validação funcional e comunicação entre serviços em ambiente integrado. O
> segundo é o mais esquecido — não basta a tela funcionar; é preciso mostrar a
> requisição atravessando os serviços. As abas Network e Console do navegador,
> mais o log do back-end aparecendo no CloudWatch para aquela mesma requisição,
> resolvem o item de forma inequívoca. Use o `X-Request-Id` como fio condutor.

**Link:** {{URL}}

| Tempo | Item | O que mostrar | Resultado esperado |
|---|---|---|---|
| 0:00–0:20 | Abertura | {{aplicação no ar, pela URL pública}} | {{ }} |
| 0:20–1:20 | V2-a funcional | {{fluxo principal ponta a ponta}} | {{ }} |
| 1:20–2:00 | V2-a caso de erro | {{entrada inválida ou não autenticada}} | {{erro tratado, sem stack trace exposto}} |
| 2:00–3:00 | V2-b comunicação | {{aba Network: chamada do front à API pelo ALB/CloudFront, com status e cabeçalhos}} | {{ }} |
| 3:00–3:40 | V2-b rastro | {{mesma requisição localizada no log do back-end no CloudWatch}} | {{correlação pelo identificador}} |
| 3:40–4:00 | Fechamento | — | {{ }} |

### 8.1 Testes de validação funcional

> **PREENCHER** · Tabela dos casos demonstrados. Inclua ao menos um caminho de
> erro: sistema que só é mostrado no caminho feliz sugere que o caminho triste não
> foi testado. Se houver suíte automatizada, cite o comando e onde ela vive —
> execução de teste em vídeo vale mais do que navegação manual.

| # | Caso | Pré-condição | Passos | Resultado esperado | Resultado obtido |
|---|---|---|---|---|---|
| 1 | {{ }} | {{ }} | {{ }} | {{ }} | {{ }} |

### 8.2 Comunicação entre serviços

> **PREENCHER** · Descreva o caminho completo de uma requisição, nomeando cada
> salto e o mecanismo de autenticação em cada um. Exemplo de forma:
> navegador → CloudFront → ALB → instância do ASG → RDS, e o retorno.
> Registre o que acontece quando um salto falha.

| Salto | Origem → destino | Protocolo | Autenticação | Falha esperada se indisponível |
|---|---|---|---|---|
| 1 | {{ }} | {{ }} | {{ }} | {{ }} |

---

## 9. Riscos e limitações conhecidas

> **PREENCHER** · Seção de honestidade técnica, e o repositório já tem cultura
> disso (`arquitetura-inicial.md` §6). Candidatos: dependência da sessão do
> Learner Lab e do account ID que muda; recursos que o papel `voclabs` recusa;
> ausência de backend remoto para o `terraform.tfstate`; custo do NAT Gateway
> contra o orçamento do laboratório; RDS sem Multi-AZ; carga inicial indisponível
> sem o dump de 4,15 GB. Cada risco com impacto e mitigação — risco listado sem
> mitigação é lista de desculpas.

| Risco | Impacto | Probabilidade | Mitigação | Responsável |
|---|---|---|---|---|
| {{ }} | {{ }} | {{ }} | {{ }} | {{ }} |

---

## 10. Checklist de entrega

> **PREENCHER** · A organização do repositório é avaliada à parte do conteúdo
> deste artefato. Percorra antes de criar a tag.

**Controle de versão**

- [ ] Tag `SPRINT{{X}}` criada na data da entrega.
- [ ] Commits significativos de **todos** os integrantes.
- [ ] Commits distribuídos ao longo das duas semanas, não concentrados no último dia.

**Estrutura**

- [ ] Raiz contém apenas `README.md`, `.gitignore`, logos e as pastas `/artefatos`, `/apps`, `/slides` e opcionalmente `/assets`.
- [ ] Decisão tomada sobre `apps/basica` versus `/apps/fullstack` da especificação — renomear ou documentar a divergência.
- [ ] `terraform.tfvars`, `.tfstate` e segredos fora do versionamento.

**README**

- [ ] Logos, título, nome e número do grupo, integrantes.
- [ ] Problema e solução em um parágrafo.
- [ ] Descrição das pastas.
- [ ] Instruções de execução local **e** na AWS.
- [ ] Passo a passo de clone e execução por um desenvolvedor novo, via Codespaces ou VS Code, acionável por um comando.

**Documentação do código**

- [ ] Cabeçalho descritivo em cada módulo ou classe.
- [ ] Docstrings (Python) e JSDoc (JS) com parâmetros, retorno e comportamento.
- [ ] Novos arquivos Terraform com comentário de cabeçalho explicando o recurso.

**Execução**

- [ ] Aplicação no ar nos recursos do laboratório, sem erro no fluxo típico.
- [ ] Execução local verificada por alguém que não a implementou.

**Este artefato**

- [ ] Todos os blocos `PREENCHER`, `DECIDIR` e `EVIDÊNCIA` removidos.
- [ ] Nenhum marcador `{{ }}` restante.
- [ ] Links dos dois vídeos testados em janela anônima.
- [ ] Tabela de rastreabilidade da rubrica com todos os itens em `pronto`.

---

## Apêndice A — Variáveis e saídas do Terraform

> **PREENCHER** · Variáveis novas introduzidas nesta sprint, com valor padrão e
> efeito, e as saídas úteis (DNS do ALB, IP do bastion, endpoint do RDS, domínio
> do CloudFront). Poupa a próxima pessoa de ler o `variables.tf` inteiro.

| Variável | Padrão | Efeito |
|---|---|---|
| {{ }} | {{ }} | {{ }} |

## Apêndice B — Comandos de verificação e diagnóstico

> **PREENCHER** · Os comandos que você acabou usando repetidamente durante o
> provisionamento. Este apêndice se escreve sozinho se for preenchido enquanto o
> trabalho acontece, e não na véspera.

```bash
{{comando}}   # {{o que responde}}
```

## Apêndice C — Proveniência das decisões

> **PREENCHER** · Data, decisão e quem participou, para as decisões da seção 3.8.
> Serve de defesa quando alguém pergunta por que a arquitetura mudou entre sprints.

| Data | Decisão | Origem | Participantes |
|---|---|---|---|
| {{ }} | {{ }} | {{reunião, orientação, restrição da rubrica}} | {{ }} |
