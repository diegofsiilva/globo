# Infraestrutura e integração

&emsp; Este artefato documenta a evolução da infraestrutura em nuvem do Argus e a
integração entre o front-end e o back-end. A **arquitetura v4 foi desenvolvida na
Sprint 3, a sprint atual**, e esta revisão foi realizada em 8 de setembro de 2026 na
branch `docs/relatórioimplementaçãov2`, considerando como destino a nova conta do AWS
Academy Learner Lab atribuída ao grupo. O estado foi confrontado com os arquivos
versionados no repositório: nesta data, a infraestrutura da versão 4 ainda é uma
topologia de destino. Os novos recursos de rede, computação e entrega ainda não estão
declarados no Terraform nem provisionados; o modo Multi-AZ do RDS já é uma opção do
código, mas permanece desativado. Por isso, o texto distingue explicitamente o que já
existe na versão 3, o que foi desenvolvido como arquitetura v4 na Sprint 3 e o que
permanece planejado para provisionamento.

## Divergências de nomenclatura

| Especificação | Repositório | Tratamento |
|---|---|---|
| `infraestrutura_integracao.md` na seção de vídeos e `infraestrutura-integracao.md` no cabeçalho | `artefatos/infraestrutura-integracao.md` | Foi adotado o nome com hífen, coerente com os demais artefatos de arquitetura e com os links internos do repositório. |
| `/apps/fullstack` | `apps/basica` | A pasta existente foi mantida porque `basica` identifica o produto dentro do monorepo. Este artefato, o README da raiz e os comandos de execução usam o caminho real. |

## Rastreabilidade da rubrica

&emsp; A tabela cruza os nove itens avaliados, que somam 10 pontos, com as seções deste
artefato. O status registra o estado verificável em 8 de setembro de 2026.

| # | Item da rubrica | Peso | Onde está | Status |
|---|---|---|---|---|
| R-a | Diagrama de implantação com ênfase em nuvem | 1,5 | Seção 2 | pronto |
| R-b | Descrição dos componentes e justificativa | 1,5 | Seção 3 | não iniciado |
| R-c | Plano de deploy na AWS, incluindo CloudFront | 1,0 | Seção 4 | não iniciado |
| V1-a | VPC, sub-redes pública e privada, NAT, logs distribuídos | 1,0 | Seções 3.1 e 6 | não iniciado |
| V1-b | Bastion Host com regras seguras de acesso | 1,0 | Seções 3.2 e 6 | não iniciado |
| V1-c | ASG de EC2 com política de escalonamento + ALB | 1,0 | Seções 3.3, 5 e 6 | não iniciado |
| V1-d | Banco de dados em RDS | 1,0 | Seções 3.4 e 6 | não iniciado |
| V2-a | Testes de validação funcional | 1,0 | Seção 7 | não iniciado |
| V2-b | Comunicação entre serviços em ambiente integrado | 1,0 | Seção 7 | não iniciado |

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

&emsp; A versão 4 foi desenhada para pagar essas duas dívidas e acrescentar a camada
de escalabilidade horizontal que faltava ao caminho de leitura. A topologia prevê uma
VPC própria, com sub-redes públicas e privadas distribuídas em duas zonas de
disponibilidade; cargas de trabalho sem endereço público, com saída pelo NAT Gateway;
acesso administrativo mediado por bastion host; API de leitura executada em instâncias
Amazon EC2 de um Auto Scaling Group, atrás de um Application Load Balancer; e entrega
do front-end por Amazon CloudFront, com TLS e bucket S3 privado. Essas mudanças ainda
não substituíram os recursos da versão 3 no Terraform versionado.

&emsp; A migração proposta é deliberadamente parcial. O **caminho síncrono** — a
requisição que o dashboard faz e cuja latência o usuário percebe — recebe o grupo de
escalonamento e o balanceador, porque é onde a variação de carga é observável e a perda
de uma instância tem efeito imediato sobre a experiência. O **caminho assíncrono** de
ingestão continua em filas com consumidores no ECS Fargate: o desacoplamento por SQS
já absorve rajadas, o backlog da fila é a métrica natural de saúde desse fluxo, e
reescrevê-lo sobre EC2 acrescentaria risco de regressão sem ganho arquitetural
correspondente. A seção 3.8 registra a decisão e a alternativa descartada.

### 1.1 Legenda de estado

- **Implementado:** existe no código e na infraestrutura Terraform aplicada.
- **Condicional:** existe no Terraform, mas depende de variáveis do ambiente.
- **Planejado:** decisão registrada, ainda sem recurso Terraform.

### 1.2 O que mudou nesta revisão

&emsp; A comparação abaixo usa como base a arquitetura da versão 3. A coluna
**Estado** registra a situação dos acréscimos da versão 4 na data de corte deste
documento. Como os respectivos recursos ainda não existem no Terraform versionado,
todos permanecem planejados; os componentes herdados da versão 3 continuam descritos
em [`arquitetura-inicial.md`](arquitetura-inicial.md).

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

## 2. Diagrama de implantação do sistema — peso 1,5

<div align="center">

<sub>Figura 1 — Topologia de implantação da versão 4 do Argus na AWS, região `us-east-1`</sub>

[![Diagrama de implantação da versão 4 do Argus](assets/arquitetura-implantacao-v4.png)](assets/arquitetura-implantacao-v4.png)

<sup>Fonte: material produzido pelos autores (2026).</sup>

</div>

&emsp; A Figura 1 representa a topologia de destino da versão 4 e mantém visíveis os
dois estados necessários para interpretá-la. Os nós em azul-cinza são componentes já
presentes na versão 3; os nós em roxo são os acréscimos previstos nesta revisão. O
laranja tracejado identifica o standby do RDS Multi-AZ, que não está provisionado na
configuração de referência porque `db_multi_az` permanece desativado. Os retângulos
tracejados azuis não são recursos de rede: apenas agrupam logicamente o Auto Scaling
Group e o Application Load Balancer que atravessam as duas zonas de disponibilidade.
O estado de provisionamento dos acréscimos roxos é o registrado na seção 1.2, portanto
a figura documenta o desenho aprovado e não funciona, por si só, como evidência de
implantação.

&emsp; No caminho de leitura, o navegador estabelece HTTPS na porta 443 com o
CloudFront. A distribuição usa o bucket S3 privado como origem do conteúdo estático,
por Origin Access Control, e encaminha `/api/*`, sem cache e com o cabeçalho
`Authorization`, ao ALB público. O balanceador termina HTTPS e envia HTTP na porta
8000 para as instâncias privadas do Auto Scaling Group; a API consulta somente as
views autorizadas do RDS pela porta 5432. No caminho assíncrono, aplicações cliente
publicam eventos no API Gateway, que os entrega ao SQS; os serviços no ECS Fargate
consomem as filas por long polling e persistem no mesmo RDS. O NAT Gateway fornece
somente saída às sub-redes privadas. O acesso operacional parte da estação do
administrador, com origem restrita, passa pelo bastion host por SSH na porta 22 e pode
estabelecer um túnel até o banco sem torná-lo público.

### 2.1 Fonte editável e exportação

&emsp; A fonte do diagrama é [`assets/arquitetura-implantacao-v4.svg`](assets/arquitetura-implantacao-v4.svg),
SVG escrito à mão e versionado como fonte — mesma convenção do
`arquitetura-implantacao-v3.svg`, do qual herda o vocabulário visual: nós
tridimensionais com estereótipo, caixas de artefato aninhadas, faixa transversal de
operação e o traço laranja tracejado para o que ainda não existe. Não há binário
intermediário de ferramenta. O PNG publicado no relatório é gerado a partir do SVG e
commitado junto; **os dois arquivos andam sempre no mesmo commit**, sob pena de a
figura divergir da fonte.

&emsp; O diagrama v3 permanece intacto, porque é a figura referenciada por
[`arquitetura-inicial.md`](arquitetura-inicial.md). Editá-lo no lugar faria o artefato
da sprint anterior exibir infraestrutura que não existia quando aquele texto foi
escrito.

**Exportar o PNG**

&emsp; O SVG declara uma prancheta de 3760 × 2479 px. O PNG publicado tem 3760 × 2454
px porque a exportação recorta 25 px de margem inferior vazia, sem atingir nós,
rótulos ou conexões. Essa resolução permite ampliar a figura sem perder a leitura.
Os comandos abaixo cobrem a exportação integral e a versão recortada usada no
relatório:

```bash
# opção 1 — rsvg-convert, mesma linha usada no v3
rsvg-convert -w 3760 -b white \
  artefatos/assets/arquitetura-implantacao-v4.svg \
  -o artefatos/assets/arquitetura-implantacao-v4.png

# opção 2 — Chromium headless, quando o rsvg-convert não estiver disponível
chrome --headless --disable-gpu --hide-scrollbars \
  --window-size=3760,2454 --default-background-color=FFFFFFFF \
  --screenshot=artefatos/assets/arquitetura-implantacao-v4.png \
  artefatos/assets/arquitetura-implantacao-v4.svg
```

&emsp; No GitHub, a figura é reduzida à largura da coluna de leitura; a própria imagem
funciona como link para o arquivo em resolução integral. O PNG versionado tem 3760 ×
2454 px e fundo branco, o que preserva a legibilidade dos rótulos quando ampliado e
evita perda de contraste no tema escuro.

### 2.2 Convenções de notação

| Elemento | Significado |
|---|---|
| Nó tridimensional | Nó de implantação: ambiente de execução, serviço gerenciado ou dispositivo |
| Preenchimento azul-cinza | Nó que **já existia na arquitetura v3** e foi apenas realocado na rede |
| Preenchimento roxo | Nó **acrescentado nesta revisão** — não tem correspondente no diagrama v3 |
| Preenchimento laranja tracejado | Nó **planejado e não provisionado** na configuração de referência |
| Caixa branca interna `«artifact»` | Artefato de software implantado naquele nó |
| Retângulo com título no canto superior | Fronteira de rede: VPC, zona de disponibilidade, sub-rede — toda essa camada é nova nesta revisão |
| Retângulo tracejado sem preenchimento | Agrupamento lógico — Auto Scaling Group e balanceador — que atravessa as zonas de disponibilidade e não é recurso de rede |
| `«…»` | Estereótipo do nó |
| Rótulo da seta | Protocolo e porta efetivamente usados |
| Faixa inferior tracejada | Serviços transversais ao ASG, ao Fargate e ao RDS |

&emsp; Os nós em roxo são a resposta visual à pergunta “o que esta sprint acrescentou”:
Internet Gateway, NAT Gateway, bastion host, os dois nós do Application Load Balancer,
as duas instâncias EC2 do Auto Scaling Group, a distribuição CloudFront e a estação do
administrador. O RDS standby aparece em laranja porque é acréscimo **e** ainda não está
provisionado — quando `db_multi_az` for ativado e aplicado, ele passa para roxo.

---

## 3. Componentes e justificativa da arquitetura — peso 1,5

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
> com a aba "Activity" do ASG aberta. Ver seção 6.

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

&emsp; A implantação da arquitetura v4 parte de uma conta nova do AWS Academy Learner
Lab, criada para a Sprint 3. O computador usado no deploy precisa das ferramentas
abaixo. Os comandos do `Makefile` devem ser executados no Git Bash ou WSL, pois usam
recursos de shell POSIX; os comandos de preparação desta subseção podem ser executados
no PowerShell.

| Ferramenta | Versão mínima ou requisito | Uso no projeto |
|---|---|---|
| Git | Versão estável atual | Clonar o repositório e identificar o SHA usado nas imagens |
| AWS CLI | 2.x | Autenticar no Learner Lab e consultar ou operar os recursos AWS |
| Terraform | 1.9 ou superior | Inicializar, validar, planejar e aplicar a infraestrutura |
| Docker Desktop | Buildx habilitado e suporte a `linux/arm64` | Construir as imagens dos serviços para o Amazon ECR |
| Python | 3.12 ou superior | Executar migrations, carga, testes e ferramentas do projeto |
| uv | Versão estável atual | Criar os ambientes Python a partir dos arquivos `pyproject.toml` |
| Node.js e npm | Node.js 20 ou superior | Instalar, testar e gerar o export estático do dashboard |
| GNU Make e Bash | Disponíveis no Git Bash ou WSL | Executar os alvos de instalação, build, deploy e verificação |

&emsp; Antes de configurar credenciais, as versões instaladas devem ser conferidas. A
execução pode continuar quando todos os comandos abaixo responderem sem erro e o
Terraform indicar uma versão igual ou superior a 1.9.

```powershell
git --version
aws --version
terraform version
docker version
docker buildx version
python --version
uv --version
node --version
npm --version
make --version
```

#### 4.1.1 Credenciais e validação da conta

&emsp; As credenciais temporárias devem ser copiadas de **AWS Details → AWS CLI** no
Learner Lab e armazenadas somente no profile local `g4`. O access key, o secret key e
o session token não entram no repositório, no `.env` nem no `terraform.tfvars`. Como
as credenciais expiram, a validação é repetida antes de cada `plan` e `apply`.

```powershell
$env:AWS_PROFILE = "g4"
$env:AWS_REGION = "us-east-1"

$taskAccountId = aws sts get-caller-identity `
  --profile g4 `
  --query Account `
  --output text

if ($LASTEXITCODE -ne 0 -or $taskAccountId -notmatch '^\d{12}$') {
  throw "Não foi possível confirmar a conta ativa do Learner Lab."
}

aws ec2 describe-vpcs `
  --profile g4 `
  --region us-east-1 `
  --max-results 5 `
  --query 'Vpcs[].{VpcId:VpcId,Cidr:CidrBlock}' `
  --output table

if ($LASTEXITCODE -ne 0) {
  throw "A sessão existe, mas não possui uma credencial válida para operar a EC2."
}
```

&emsp; A segunda chamada é necessária porque testa uma permissão usada pelo deploy,
em vez de verificar apenas a identidade. O valor de `$taskAccountId` deve corresponder
à conta nova da Sprint 3. O ARN a informar em `existing_role_arn` pode ser conferido
sem digitação manual:

```powershell
$taskRoleArn = "arn:aws:iam::${taskAccountId}:role/LabRole"
$taskRoleArn
```

&emsp; Se a conta não for a esperada, nenhum comando Terraform deve ser executado.

#### 4.1.2 Isolamento do state anterior

&emsp; O `terraform.tfstate` existente descreve a conta anterior e não pode ser usado
na conta nova. Reutilizá-lo faria o Terraform procurar recursos que não existem na
sessão atual. Como a conta nova começou vazia, não há recurso da versão anterior a ser
preservado nela; o RDS e os demais componentes da v4 podem nascer diretamente na nova
VPC. O state, o backup e o `terraform.tfvars` anteriores devem ser movidos para um
diretório protegido fora do repositório antes da inicialização.

```powershell
Set-Location apps/basica/infra

$taskStamp = Get-Date -Format "yyyyMMdd-HHmmss"
$taskStateArchive = Join-Path $env:USERPROFILE "argus-state-archive\$taskStamp"
New-Item -ItemType Directory -Path $taskStateArchive -Force | Out-Null

foreach ($taskLocalFile in @("terraform.tfstate", "terraform.tfstate.backup", "terraform.tfvars")) {
  if (Test-Path -LiteralPath $taskLocalFile) {
    Move-Item -LiteralPath $taskLocalFile -Destination $taskStateArchive
  }
}

Copy-Item -LiteralPath "terraform.tfvars.example" -Destination "terraform.tfvars"
```

&emsp; O diretório de arquivo contém state e valores sensíveis e, portanto, não deve
ser sincronizado com o Git. Quando as permissões da conta permitirem criar o bucket e
o mecanismo de lock, [`backend.tf.example`](../apps/basica/infra/backend.tf.example)
deve ser usado como base para um backend remoto criptografado. Se o laboratório negar
esses recursos, o state permanece local sob responsabilidade de um único operador por
janela de implantação.

#### 4.1.3 Configuração do ambiente

&emsp; O novo `terraform.tfvars` deve ser preenchido com valores exclusivos da conta
atual. Nenhuma senha, token ou identificação real deve ser copiada para arquivos
versionados.

| Campo | Configuração para a primeira aplicação | Motivo |
|---|---|---|
| `region` | `"us-east-1"` | Região adotada pelo diagrama e pelos recursos do projeto |
| `create_iam_roles` | `false` | O Learner Lab normalmente bloqueia `iam:CreateRole` |
| `existing_role_arn` | ARN da `LabRole` formado com o account ID confirmado | Impede referência à role da conta anterior |
| `db_password_from_secrets_manager` | Conforme as permissões da conta; `false` quando o Secrets Manager for negado | Mantém um caminho compatível com o laboratório |
| `db_password`, `read_api_db_password` e `user_id_hash_salt` | Valores novos, longos e distintos | Evita reutilização de segredos da conta anterior |
| `db_publicly_accessible` | `false` | O RDS deve permanecer nas sub-redes privadas |
| `db_allowed_cidr` | `""` | Remove acesso direto ao PostgreSQL pela internet |
| `assign_public_ip` | `false` | As cargas privadas obtêm saída pelo NAT Gateway |
| `worker_desired_count` | `0` | Evita iniciar workers antes de as imagens existirem no ECR |
| `processing_desired_count` | `0` | Evita iniciar processamento antes da carga e das imagens |
| `simulator_desired_count` | `0` | O relógio virtual só é ligado depois da carga inicial |
| `db_multi_az` | `false` no laboratório ou `true` quando o orçamento permitir | A decisão de custo e disponibilidade deve permanecer explícita |

&emsp; Antes do `terraform init`, os valores de exemplo devem ser eliminados e a
classe escolhida para o RDS precisa estar disponível na região.

```powershell
$taskExampleValues = Select-String `
  -LiteralPath "terraform.tfvars" `
  -Pattern "000000000000|troque-|203\.0\.113\.10"

if ($taskExampleValues) {
  throw "O terraform.tfvars ainda contém valores de exemplo."
}

aws rds describe-orderable-db-instance-options `
  --profile g4 `
  --region us-east-1 `
  --engine postgres `
  --engine-version 16 `
  --db-instance-class db.t3.medium `
  --query 'OrderableDBInstanceOptions[].DBInstanceClass' `
  --output text

terraform init -reconfigure
terraform fmt -check -recursive
terraform validate
```

&emsp; A consulta do RDS deve retornar `db.t3.medium`; se retornar vazio, a classe
precisa ser trocada por outra oferecida pelo laboratório e a limitação deve ser
registrada. A preparação termina quando `terraform validate` responde
`Success! The configuration is valid.`. O `plan` e os dois `apply` ficam para a ordem
de implantação da seção 4.3.

#### 4.1.4 Dados necessários para a carga

&emsp; O dump bruto do parceiro não é versionado. Antes do deploy, a equipe deve
confirmar a disponibilidade autorizada de `argus_dump.sql` ou dos Parquet já gerados.
Sem nenhum dos dois, é possível validar a integração com fixtures, mas não reproduzir
a carga das 33 tabelas nem os testes sobre 68,7 milhões de linhas.

```powershell
Set-Location ../../..

Test-Path -LiteralPath "argus_dump.sql"
Test-Path -LiteralPath "data/parquet/_manifest.json"
```

&emsp; Pelo menos uma das duas verificações deve retornar `True`. Se apenas o dump
estiver disponível, `make -C apps/basica parquet` gera os Parquet antes da
sincronização com o bucket de origem.

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

> **PREENCHER** · Procedimento de aceite executável, com o resultado esperado de
> cada comando.

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

## 6. Vídeo 1 — Infraestrutura provisionada

- **Duração:** 5 a 7 minutos.
- **Critérios cobertos:** VPC e logs distribuídos, sub-redes públicas e privadas com
  NAT Gateway, bastion host, Auto Scaling Group de EC2, Application Load Balancer e
  Amazon RDS.
- **Link:** pendente de gravação e publicação.

---

## 7. Vídeo 2 — Integração front-end e back-end

- **Duração:** 2 a 4 minutos.
- **Critérios cobertos:** testes de validação funcional e comunicação prática entre o
  front-end e o back-end no ambiente integrado.
- **Link:** pendente de gravação e publicação.

---

## 8. Riscos e limitações conhecidas

&emsp; A topologia da versão 4 melhora isolamento, disponibilidade e transporte, mas
não elimina as restrições do AWS Academy Learner Lab nem os riscos de uma migração de
infraestrutura. A tabela separa limitações confirmadas no ambiente atual de riscos que
precisam ser tratados antes da gravação das evidências e da publicação da entrega.

| Risco | Impacto | Probabilidade | Mitigação | Responsável |
|---|---|---|---|---|
| Mudança da conta e expiração das credenciais do Learner Lab | O account ID, a `LabRole`, os endpoints e os recursos do state anterior deixam de representar o ambiente ativo; um `plan` executado com credenciais incorretas pode orientar uma implantação na conta errada. | Alta | Confirmar a identidade com `aws sts get-caller-identity --profile g4` antes de cada `plan` e `apply`; criar um state separado para cada conta; atualizar `existing_role_arn` e nunca reutilizar automaticamente o state da conta anterior. | Equipe de infraestrutura |
| Estado do Terraform armazenado localmente | Perda do arquivo impede o Terraform de relacionar o código aos recursos criados; dois integrantes aplicando estados diferentes podem causar divergência ou duplicação. | Média | Usar o modelo de backend remoto em [`backend.tf.example`](../apps/basica/infra/backend.tf.example) quando as permissões permitirem. Enquanto o state for local, definir um único responsável por janela de implantação, manter cópia criptografada e comparar conta e recursos antes de qualquer recuperação. | Equipe de infraestrutura |
| Restrições da `LabRole` para CloudFront, OAC, políticas e papéis IAM | O plano pode funcionar em uma conta AWS comum e falhar no laboratório, impedindo o bucket privado, o TLS do front-end ou a criação de identidades dedicadas. | Alta | Validar previamente as ações exigidas pela topologia na conta nova. Quando houver negação, registrar a operação e o erro, reutilizar somente papéis autorizados e documentar o fallback do laboratório sem apresentá-lo como equivalente à arquitetura de produção. | Equipe de infraestrutura e segurança |
| Recursos da versão 4 ainda ausentes do Terraform versionado | O diagrama não é reproduzível e não serve como evidência de infraestrutura provisionada; as seções de deploy e os vídeos permanecem bloqueados. | Alta | Implementar VPC, sub-redes, rotas, NAT, bastion, launch template, ASG, ALB, CloudFront e observabilidade como código; revisar o `terraform plan`; aplicar primeiro com capacidade de aplicação zerada, publicar os artefatos e somente depois ativar os serviços. | Equipe de infraestrutura |
| NAT Gateway único para cargas distribuídas em duas zonas de disponibilidade | Uma falha na zona do NAT interrompe o acesso externo das cargas privadas da outra zona; além disso, o custo fixo estimado em cerca de US$ 32 por mês pode consumir parte relevante do crédito do laboratório. | Média | Em produção, usar um NAT por zona e uma tabela de rotas privada por AZ. No laboratório, se o orçamento exigir um único NAT, registrar o ponto único de falha, monitorar o gasto e manter procedimento de recriação em outra zona. | Equipe de infraestrutura |
| RDS com `db_multi_az = false` | A instância permanece um ponto único de falha e uma indisponibilidade do banco interrompe leitura, ingestão e processamento. | Média | Ativar e aplicar `db_multi_az` quando houver orçamento, validar o failover e manter backups automáticos. Antes de migrations destrutivas, criar snapshot e separar o rollback do banco do rollback das instâncias do ASG. | Equipe de infraestrutura e dados |
| Regra SSH do bastion dependente do CIDR do administrador | Uma origem ampla expõe a porta 22; uma origem desatualizada bloqueia o acesso operacional quando a rede do administrador muda. | Média | Restringir a entrada a um CIDR `/32`, nunca usar `0.0.0.0/0`, manter chaves individuais e rotacionáveis e revisar a regra antes e depois da manutenção. Preferir Session Manager quando as permissões do laboratório permitirem. | Equipe de infraestrutura e segurança |
| Política incorreta do CloudFront para `/api/*` | A omissão do cabeçalho `Authorization` faz as chamadas retornarem 401; habilitar cache para respostas autenticadas pode servir dados fora do contexto correto. | Média | Criar comportamento específico para `/api/*`, desabilitar o cache, encaminhar `Authorization` e os parâmetros necessários e testar sessões distintas antes da publicação. O comportamento padrão permanece exclusivo para os arquivos estáticos do S3 via OAC. | Equipe de infraestrutura e back-end |
| Dataset bruto fora do repositório e da nova conta | Sem o `argus_dump.sql` ou os Parquet derivados, a carga completa das 33 tabelas e a reprodução dos testes com 68,7 milhões de linhas não podem ser refeitas na conta nova. | Alta | Preservar o dump apenas em armazenamento autorizado, gerar os Parquet e o manifesto antes da janela de implantação e sincronizá-los com o bucket de origem. Usar fixtures somente para validar o fluxo funcional, registrando que elas não comprovam escala real. | Equipe de dados |
| Migração da API de Lambda para EC2 incompatível com o schema ou com o health check | Instâncias novas podem falhar o health check, entrar em ciclo de substituição ou receber tráfego antes de as migrations necessárias estarem aplicadas. | Média | Manter migrations retrocompatíveis, aplicar alterações de banco antes de liberar a nova versão, validar `/health` no target group e preservar a versão anterior do launch template para rollback por `instance refresh`. | Equipe de back-end, dados e infraestrutura |

---

## 9. Checklist de entrega

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
