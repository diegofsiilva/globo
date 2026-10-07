# Arquitetura inicial da solução 

&emsp; Este artefato detalha a arquitetura da solução Linceu v3: seus componentes,
tecnologias, fluxos de comunicação, decisões arquiteturais e plano de implantação
na AWS. O estado descrito considera a implementação consolidada na branch
`develop`, incluindo ingestão, carga inicial, processamento incremental,
coordenação por checkpoints, detecção, geração de hipóteses, API de leitura e
dashboard.

&emsp; O arquivo segue a ordem dos quatro critérios da entrega. Detalhes de modelo de
dados e processamento foram mantidos em apêndices para não interromper a leitura do
relatório principal.

| Critério | Onde está documentado |
|---|---|
| (a) Diagrama de implantação | Seção 2 |
| (b) Nós, componentes e conexões | Seção 3 |
| (c) Justificativa da arquitetura e das tecnologias | Seção 4 (tabela de decisões em 4.9) |
| (d) Plano detalhado de implantação na AWS | Seção 5 |

### Escopo deste artefato

&emsp; Este documento foi entregue na **Sprint 2** e descreve a arquitetura daquela
entrega. A Sprint 3 acrescentou uma camada de infraestrutura que não existia aqui:
VPC gerenciada, sub-redes privadas, NAT Gateway, bastion host, Auto Scaling Group e
Application Load Balancer. Para não deixar o artefato descrevendo um ambiente que já
não é o atual, as seções afetadas foram atualizadas, e **cada acréscimo da Sprint 3
está marcado como tal**. O que não tiver marca é da entrega original.

&emsp; O artefato da Sprint 3, com o diagrama de implantação em nuvem, o plano de deploy
com CloudFront e as evidências de aplicação, é
[`infraestrutura-integracao.md`](infraestrutura-integracao.md).

### O que mudou na revisão da Sprint 2

&emsp; Esta versão descreve o ambiente **efetivamente implantado**, e não a intenção de
projeto. As diferenças em relação à revisão anterior:

| Item | Antes | Agora |
|---|---|---|
| Autenticação das APIs | Ausente; a URL era a única barreira | Lambda authorizer com Bearer, duas audiências, hashes no Secrets Manager |
| Transporte do dashboard | CDN com HTTPS e bucket privado | Website S3 em HTTP, compatível com as permissões do Learner Lab |
| Migrations | 001–023 | 001–027 |
| Acesso ao RDS | Público, restrito ao CIDR do desenvolvedor | Privado; administração pela task `migration` dentro da VPC |
| Tag das imagens | `latest` | SHA do commit; `latest` só como apelido no ECR |
| Bucket de origem | Descrito como contendo o dump | Apenas Parquet e manifesto; o dump não foi publicado |
| Observabilidade | Logs em texto | Log JSON por requisição, correlacionado por `X-Request-Id` |

### Acrescentado na Sprint 3 — camada de rede

&emsp; Nada abaixo fazia parte da entrega da Sprint 2. Na Sprint 2 o stack **consumia** a
VPC padrão da conta, e não havia sub-rede privada, NAT Gateway nem observabilidade de
rede. A Sprint 3 declarou a rede como recurso, em `infra/vpc.tf`.

| Item | Sprint 2 | Sprint 3 |
|---|---|---|
| Rede | VPC padrão da conta, consumida via `data "aws_vpc" "default"` | **VPC gerenciada**, `10.0.0.0/16`, declarada em `infra/vpc.tf` |
| Sub-redes | As públicas que a conta já trazia | Duas públicas e duas privadas, em duas AZs |
| Endereço das tasks | IP público em sub-rede pública | Sem IP público, em sub-rede privada |
| Saída para a internet | Direta, pelo Internet Gateway da VPC padrão | **NAT Gateway**, com tabela de rota privada |
| Observabilidade de rede | Inexistente | **VPC Flow Logs**, `traffic_type = ALL`, entregues em S3 |
| Tráfego para o S3 | Pela internet | Gateway endpoint, sem sair da AWS |
| Sub-redes do RDS | Subnet group sobre as sub-redes padrão | Subnet group sobre as sub-redes privadas |
| Acesso administrativo | Somente a task avulsa `migration` | Acrescido o **bastion host** em sub-rede pública |
| Caminho de leitura | Lambda atrás do API Gateway | **Auto Scaling Group de EC2 atrás de um ALB** |

&emsp; As seções 2, 4.7, 4.9 e 5.2 deste artefato foram atualizadas para refletir essa
camada. O desenho anterior continua acessível por variável: `create_network = false` com
`assign_public_ip = true` devolve o stack ao comportamento da Sprint 2.

---

## 1. Contexto e escopo

&emsp; A primeira versão do MVP foi projetada como um coletor de eventos com API
Gateway, SQS, ECS Fargate e DynamoDB. O aprofundamento com o parceiro mostrou que o
Argus já mantém 33 tabelas tratadas em produção. A responsabilidade da solução passou
a ser consumir e reproduzir mudanças dessas tabelas, materializar o estado corrente e
derivar produtos analíticos para investigação de incidentes.

&emsp; A arquitetura atual possui dois fluxos de entrada independentes:

1. **Mudanças das tabelas do Argus (CDC simulado):** o simulador reproduz alterações
   do conjunto de dados histórico e publica *change events* em uma fila própria.
2. **Eventos de sessão:** os eventos emitidos pelas aplicações são recebidos por uma
   segunda rota e uma segunda fila.

&emsp; Os dois fluxos convergem no RDS PostgreSQL. A partir dele, o serviço de
processamento constrói as camadas analíticas, publica checkpoints consistentes,
executa o canário de qualidade, o detector e o motor determinístico de hipóteses. A
API de leitura expõe somente views autorizadas ao dashboard.

### 1.1 Legenda de estado

- **Implementado:** existe no código e na infraestrutura Terraform de referência.
- **Condicional:** existe no Terraform, mas depende de variáveis do ambiente.
- **Planejado:** melhoria arquitetural registrada, ainda sem recurso Terraform.

---

## 2. Diagrama de implantação do sistema

&emsp; A Figura 1 é um diagrama de implantação inspirado na notação UML. Os nós usam
estereótipos específicos para serviços gerenciados, como `«database»`,
`«message queue»` e `«object storage»`; `«execution environment»` é reservado aos
ambientes que executam código da equipe. As setas informam o mecanismo ou protocolo
de comunicação efetivamente usado.

<div align="center">

<sub>Figura 1 — Implantação do Linceu na AWS, região `us-east-1`</sub>

![Diagrama de implantação do Linceu v3](assets/arquitetura-implantacao-v3.svg)

<sup>Fonte: material produzido pelos autores (2026).</sup>

</div>

&emsp; Arquivo editável. O SVG é escrito à mão e versionado como fonte em
`assets/arquitetura-implantacao-v3.svg`; não há binário intermediário de ferramenta.
Editar o SVG e regerar o PNG:

```bash
rsvg-convert -w 3300 -b white \
  artefatos/assets/arquitetura-implantacao-v3.svg \
  -o artefatos/assets/arquitetura-implantacao-v3.png
```

&emsp; Os estereótipos usam a notação de nó tridimensional com `«artifact»` para os
componentes de software implantados em cada nó. O traço tracejado laranja marca o que é
planejado e não provisionado, que hoje é apenas o EventBridge Scheduler.

&emsp; **[Sprint 3] A rede passou a ser gerenciada pelo projeto.** Na entrega da Sprint 2,
que é a descrita no diagrama acima, o stack consumia a VPC padrão da conta, com IP
público nas tasks para evitar o custo de um NAT Gateway, e não havia sub-rede privada
nem NAT. A Sprint 3 acrescentou `infra/vpc.tf`, que declara uma VPC própria de
`10.0.0.0/16`, com duas sub-redes públicas, duas privadas, Internet Gateway, NAT
Gateway, gateway endpoint de S3 e VPC Flow Logs. As tasks, a API de leitura e o RDS
passaram a viver nas sub-redes privadas, sem endereço público, alcançando os serviços
da AWS pelo NAT. O
detalhamento, as justificativas e as evidências de aplicação estão em
[`infraestrutura-integracao.md`](infraestrutura-integracao.md).

&emsp; O ganho é de defesa em profundidade: antes, o único controle que impedia alguém
de alcançar as tasks era o security group sem regra de entrada; agora some também a
rota. **O RDS continua privado** (`db_publicly_accessible = false`) e aceita conexões na
porta 5432 apenas dos security groups autorizados; não há regra para CIDR externo. O
acesso administrativo ao banco, para migrations e inspeção, segue pela task avulsa
`migration`, que roda dentro da própria VPC, agora com o bastion host como caminho
adicional para inspeção interativa.

&emsp; O desenho anterior continua acessível por variável: `create_network = false` com
`assign_public_ip = true` devolve o stack à VPC padrão da conta.

&emsp; Até a adequação do RNF09 o laboratório usava `db_publicly_accessible = true`
com o IP do desenvolvedor em `db_allowed_cidr`. A exposição do banco dependia, na
prática, de uma linha de `terraform.tfvars` e da rede em que alguém estivesse
trabalhando: trocar de rede quebrava o acesso e esquecer de reverter deixava a
instância alcançável de fora. A task `migration` resolve o mesmo problema sem essa
dependência.

---

## 3. Nós, componentes de software e conexões

### 3.1 Clientes e fontes externas

&emsp; **Aplicação cliente ou simulador de eventos** envia eventos de sessão à rota
`POST /v1/events`. **O simulador de CDC**, executado em ECS Fargate, envia mudanças à
rota `POST /v1/changes`. Os dois caminhos usam HTTPS até o API Gateway e **apresentam
o token Bearer de audiência `ingest`** (seção 3.7).

&emsp; **Navegador do usuário** acessa diretamente o endpoint de website do S3 por
**HTTP** e consulta os dados pela API de leitura, esta sim em HTTPS, apresentando o
token de audiência `dashboard`. Os objetos do bucket são públicos para leitura; não
há permissão pública de escrita nem de listagem. Como a página que recebe o token não
tem TLS, este modo é uma compatibilidade temporária do Learner Lab e deve ser usado
apenas em rede confiável.

### 3.2 Armazenamento de origem e carga inicial

&emsp; O bucket S3 `origem` (`s3_origem.tf`) armazena os 35 arquivos Parquet e o
manifesto usados na carga inicial, cerca de 199 MiB. O bucket é versionado e
funciona como fonte imutável e recuperável do processo de bootstrap.

&emsp; O dump bruto de 4 GB não está no bucket. Ele permanece apenas na máquina de
quem executou a conversão; o alvo `make origem-sync` sabe subi-lo, mas isso não foi
feito no ambiente publicado. A carga inicial não precisa dele: quem o `loader` lê é o
Parquet derivado. Registrar isso importa porque o dump é dado cedido pelo parceiro e
não redistribuível: a sua ausência no bucket é uma característica do ambiente, e não
uma pendência.

&emsp; A task Fargate **`loader`** (`ecs_loader.tf`) é executada sob demanda. Ela lê os
Parquet por `S3 GetObject`, usa `COPY FROM STDIN` pelo driver `psycopg` e valida as
contagens contra `_manifest.json`. Não é um serviço contínuo e não passa pelas filas
de ingestão.

### 3.3 Borda de ingestão e filas

&emsp; O **API Gateway de ingestão** é uma HTTP API com duas rotas. Cada rota possui
integração direta `SQS-SendMessage`, sem Lambda intermediária, e **exige o token
Bearer de audiência `ingest`**:

- `POST /v1/changes` → fila `changes`;
- `POST /v1/events` → fila `events`.

&emsp; Cada fila possui sua própria **dead-letter queue (DLQ)** e redrive após cinco
tentativas. A separação impede que uma rajada de CDC bloqueie eventos de sessão e
permite observar backlog e falhas de cada fluxo de forma independente.

### 3.4 Execução na VPC

&emsp; O cluster **Amazon ECS Fargate** executa quatro serviços e duas tasks
avulsas:

| Componente | Tipo | Responsabilidade |
|---|---|---|
| `merge_worker` | serviço | Consome `changes`, grava `bronze.change_log` e aplica o estado corrente por LSN |
| `event_worker` | serviço | Consome `events`, valida o contrato e grava `bronze.event` |
| `simulator` | serviço | Controla o relógio virtual e reproduz as mudanças históricas |
| `processing` | serviço | Executa ETL, checkpoints, qualidade, detecção e hipóteses |
| `loader` | task avulsa | Realiza a carga inicial das 33 tabelas por Parquet |
| `migration` | task avulsa | Aplica migrations dentro da VPC quando o RDS não é público |

&emsp; `merge_worker`, `event_worker`, `simulator`, `processing`, `loader`,
`migration` e a Lambda de leitura usam o security group das tasks. Esse grupo não
aceita conexões de entrada e possui saída HTTPS para serviços AWS e saída TCP 5432
para o security group do RDS. A Lambda do authorizer é a única exceção: ela não entra
na VPC, porque o seu único destino é o Secrets Manager, e uma função numa sub-rede sem
NAT expiraria em toda chamada, o que devolveria 403 em tudo.

&emsp; As task definitions referenciam a imagem pelo **SHA do commit**, e não por
`latest`. Com `latest`, a task definition não muda quando a imagem muda: o Terraform vê
a mesma string, não propõe nada, e o serviço continua executando o digest anterior até
alguém forçar um deploy à mão. Foi assim que event worker, merge worker e processing
chegaram a executar builds diferentes entre si sem que nada aparecesse no `plan`. Com o
SHA, a task definition muda junto com o código, a diferença aparece no `plan` e o
rollback é escolher o SHA anterior. `latest` continua sendo publicado no ECR como
apelido, mas nenhum recurso do Terraform aponta para ele.

### 3.5 Persistência e processamento

&emsp; O nó central é o **Amazon RDS PostgreSQL 16**, dimensionado por padrão como
`db.t3.medium` com 100 GB gp3. A instância recebe as seguintes camadas lógicas:

| Schema | Responsabilidade |
|---|---|
| `sim` | Relógio virtual, execuções e falhas simuladas |
| `bronze` | Log append-only, estado corrente das 33 tabelas e eventos de sessão |
| `silver` | Canonicalização temporal e versões imutáveis dos fatos de análise |
| `gold` | Features, qualidade, hipóteses, evidências e views de leitura |
| `etl` | Watermarks, execuções e checkpoints publicados |
| `detect` | Runs, claims, cursor, baseline, anomalias e coordenação da análise |

&emsp; As migrations `001` a `026` constroem esse contrato. As três últimas foram
acrescentadas depois da medição de desempenho contra o volume real: `024` alinha
`available_at` dos eventos de deploy à linha do tempo simulada, `025` indexa
(fonte, métrica, tempo) e `026` indexa o baseline horário, que eram as duas consultas
mantendo `/series/facets` e `/signals` acima do teto de 5 s do RNF02.

&emsp; Migration aplicada é imutável: `tools/migrate.py` guarda o checksum de cada
arquivo e aborta quando ele muda. Alteração de schema é sempre um arquivo novo.

&emsp; O serviço `processing` executa três atividades concorrentes no mesmo
container:

1. Bronze → Silver e materialização dos fatos de análise;
2. Silver → Gold e publicação de checkpoints;
3. canário de qualidade, detector EWMA, regras, pontuação e persistência de
   hipóteses.

&emsp; A coordenação da análise fica no PostgreSQL. Reivindicações de posse
(*claims*), concessões temporárias (*leases*), sinais de vida (*heartbeats*), retomada
(*takeover*) e tokens de exclusão (*fencing*) impedem duas réplicas de publicar o
mesmo checkpoint e impedem um worker com concessão expirada de confirmar resultados.
As conexões Python com o banco usam PostgreSQL sobre TCP 5432, com SQL por meio de
`psycopg` e `psycopg_pool`, e não JDBC.

### 3.6 Consulta e apresentação

&emsp; O **API Gateway de leitura** consulta primeiro o authorizer (seção 3.7) e só
então invoca a função **Lambda `read_api`**, que executa Flask empacotado com
`apig-wsgi`. A Lambda entra na VPC com o mesmo security group das tasks e consulta o
RDS como `argus_api`. Esse usuário herda apenas o papel de leitura com `SELECT` nas
views públicas; não possui acesso direto às tabelas-base.

&emsp; O **bucket S3 `frontend`** guarda o export estático do Next.js e habilita
**website hosting**. Os quatro bloqueios de acesso público ficam desligados e a policy
concede a qualquer principal apenas `s3:GetObject` sobre os objetos desse bucket. Não
há permissão pública de escrita, alteração de policy ou listagem do bucket.

&emsp; O endpoint de website completa as rotas do export estático: o Next.js escreve
`agora/index.html`, e o acesso a `/agora/` resolve esse arquivo sem uma função de
borda. `index.html` é o documento inicial e `404.html` é o documento de erro.

&emsp; O deploy (`make frontend-deploy`) sincroniza `frontend/out/` diretamente com o
bucket usando `aws s3 sync --delete` e imprime a URL HTTP do website. Não existe cache
de CDN para invalidar. O artefato publicado inclui `build-info.json` com commit, data
UTC e versão, sem endpoint nem identificador de conta.

### 3.7 Operação, segurança e observabilidade

#### Autenticação

&emsp; As três rotas de dado ficam atrás de um **Lambda authorizer** do tipo `REQUEST`
(payload 2.0, respostas simples, cache de cinco minutos por token). São dois tokens
aleatórios de 256 bits, um por audiência:

| Audiência | Quem usa | Onde vale |
|---|---|---|
| `dashboard` | dashboard, Swagger, Postman de leitura | API de leitura |
| `ingest` | simulador, replay de eventos, Postman de escrita | API de ingestão |

&emsp; O Secrets Manager guarda apenas o SHA-256 de cada token. O valor em claro
existe em dois lugares: no terminal de quem executou `make auth-rotate`, que o imprime
uma única vez, e, só no caso do token de ingestão, num segundo segredo que a task do
simulador lê
pelo bloco `secrets` da task definition. Usar `environment` ali exporia o token em
qualquer `aws ecs describe-task-definition`, que é uma chamada de leitura: o token
vazaria para quem tem permissão de olhar a infraestrutura, sem nenhuma permissão sobre
os dados. Nem o `terraform.tfstate` nem o repositório chegam a ver o valor.

&emsp; SHA-256 simples basta porque o segredo tem 256 bits de entropia real; um KDF
lento protege senha escolhida por humano, e não existe dicionário para forçar um valor
destes. A comparação usa `hmac.compare_digest`, em tempo constante, e o laço sobre as
audiências não interrompe no acerto, porque sair mais cedo revelaria a posição da
audiência que casou.

&emsp; Os códigos de resposta separam dois casos que uma leitura de log precisa
distinguir: **401** quando o cabeçalho `Authorization` falta, respondido pelo próprio
API Gateway sem invocar a função, e **403** quando o token está presente e não confere.
O primeiro é cliente desconfigurado; o segundo é tentativa com credencial inválida. Um
alarme sobre o volume de 4xx cobre a segunda situação.

&emsp; São três as rotas públicas, todas declaradas explicitamente sem authorizer,
já que no API Gateway a rota específica vence o proxy:

| Rota | Por que é pública |
|---|---|
| `GET /health/live` | Sonda de vida. Responde `{"status": "ok"}` fixo, sem tocar no banco, e precisa continuar respondendo mesmo com o Secrets Manager indisponível |
| `GET /docs` | O Swagger UI é aberto por navegação, e navegação não carrega cabeçalho `Authorization`. Protegida, a rota devolveria 401 antes de a página renderizar, e não haveria onde clicar em "Authorize" |
| `GET /openapi.json` | O próprio Swagger a busca ao carregar, antes de qualquer interação do usuário e portanto antes de haver token |

&emsp; As duas rotas de documentação expõem a forma da API, ou seja, nomes de rota,
parâmetros e descrições, nunca dado do parceiro. Toda rota que devolve dado continua
exigindo o Bearer, e o botão "Authorize" do Swagger é o que o fornece: quem descobrir a
URL lê o contrato e não consegue executar nada contra ele. Protegê-las não tornaria o
sistema mais seguro; tornaria o Swagger inutilizável, e a verificação passaria a
depender de `curl`.

&emsp; `/health/ready` **não** é pública: ela consulta o banco, e o resultado já revela
se há dado do parceiro carregado.

&emsp; Limitação assumida e documentada: o token identifica um serviço, e não uma
pessoa. Não há como saber qual integrante fez uma consulta, e a resposta a um vazamento
é rotacionar os dois tokens, não revogar um usuário. Identidade individual exigiria o
Cognito, com um pool de usuários, um fluxo de login e um cadastro para manter, o que
está fora do escopo deste MVP. A escolha por authorizer, e não por API key, segue a
recomendação da própria AWS, que registra a chave de API como mecanismo de medição e
limitação de consumo, e não de autorização.[^apikeys]

[^apikeys]: AWS. *Use API keys with usage plans for REST APIs*. Disponível em:
https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-api-usage-plans.html

#### Imagens, papéis e observabilidade

&emsp; O **Amazon ECR** mantém quatro imagens: `worker`, `simulator`, `processing` e
`loader`. Os dois workers compartilham a imagem `worker`, mas usam comandos distintos.
O **IAM** separa execution role e task role quando a conta permite criar roles; no
Learner Lab, a `LabRole` é reutilizada por limitação do ambiente. O token de ingestão é
resolvido pela **execution role**, e não pela task role: o ECS busca o valor antes de o
container existir, e conceder à task role faria a task falhar em
`ResourceInitializationError`, sem nenhum log da aplicação indicando o motivo.

&emsp; O **CloudWatch** recebe logs e métricas de API Gateway, Lambda, ECS, SQS e RDS.
A API de leitura emite uma linha de log JSON por requisição, com `request_id`, rota,
método, status, latência e a audiência autorizada. Duas regras valem para todo campo
novo: nenhum token entra no log, nem truncado nem em hash; e a query string entra
apenas como a lista de nomes dos parâmetros, porque `session_id`, `device_id` e
`user_id` viajam por ali. O RNF10 vale também para o CloudWatch, e redigir na resposta
enquanto se vaza no log não seria redigir.

&emsp; O cabeçalho `X-Request-Id` é propagado de ponta a ponta: o cliente pode enviá-lo,
o API Gateway o registra no access log, a API o devolve no cabeçalho e no corpo de erro
(RFC 7807), e o dashboard o exibe no código de referência que o operador cita ao
relatar uma falha. É o que torna o RNF11 verificável, porque separa uma falha de
consulta de uma de ingestão ou de processamento sem depender de correlação por horário,
que num sistema com relógio virtual sequer bate.

&emsp; Os alarmes cobrem DLQs, idade das filas, serviços abaixo do número desejado de
tasks, erros das APIs, volume de 4xx, CPU, armazenamento e conexões do RDS, atraso do
relógio virtual, fontes silenciosas e falhas ou backlog do motor de análise. O SNS
distribui os alarmes quando há uma assinatura confirmada.

&emsp; O alarme de atraso do relógio virtual só existe com o simulador ligado. Com
`simulator_desired_count = 0` ninguém publica `LagSimSeconds`, e o tratamento por
ausência (`breaching`) o deixava em ALARM permanente, num alarme vermelho descrevendo
uma situação deliberada. Alarme que fica aceso o tempo todo deixa de ser lido, e perde
também a capacidade de avisar quando o pipeline parar de verdade.

&emsp; **EventBridge Scheduler continua planejado e não provisionado.** O processamento
usa laços internos de longa duração no serviço ECS; o diagrama o representa apenas como
evolução possível.

### 3.8 Matriz de conexões

| Origem | Destino | Comunicação | Finalidade |
|---|---|---|---|
| Simulador | API Gateway de ingestão | HTTPS `POST /v1/changes`, Bearer `ingest` | Publicar mudanças reproduzidas |
| Aplicação cliente | API Gateway de ingestão | HTTPS `POST /v1/events`, Bearer `ingest` | Publicar eventos de sessão |
| API Gateway (ingestão e leitura) | Lambda `authorizer` | Invocação AWS, cache de 5 min | Autorizar a requisição antes da integração |
| Lambda `authorizer` | Secrets Manager | HTTPS `GetSecretValue` | Ler os SHA-256 dos tokens |
| API Gateway | SQS | Integração AWS `SQS-SendMessage` | Enfileirar sem Lambda intermediária |
| SQS `changes` | `merge_worker` | AWS SDK, long polling | Consumir mudanças |
| SQS `events` | `event_worker` | AWS SDK, long polling | Consumir eventos |
| S3 `origem` | `loader` | HTTPS `S3 GetObject` | Ler Parquet e manifesto |
| Secrets Manager | Task `simulator` | Resolução de `secrets` pela execution role | Injetar o token de ingestão sem expô-lo na task definition |
| Componentes Python | RDS | PostgreSQL/TCP 5432 via `psycopg` | Persistência, ETL e consulta |
| Navegador | S3 `frontend` | **HTTP** `GET` pelo endpoint de website | Baixar os objetos públicos do dashboard estático |
| Navegador | API Gateway de leitura | HTTPS `GET`, Bearer `dashboard` | Consultar dados e hipóteses |
| API Gateway de leitura | Lambda `read_api` | Invocação AWS | Executar a API Flask |
| ECR | Tasks Fargate | HTTPS | Baixar imagens dos containers, por tag de SHA |
| Serviços | CloudWatch/SNS | Logs JSON, métricas e alarmes | Operação e notificação |

---

## 4. Justificativa da arquitetura e das tecnologias

### 4.1 Estilo arquitetural e relação com microsserviços

&emsp; A solução adota uma **arquitetura distribuída, orientada a eventos e baseada
em serviços**. Ingestão, simulação, carga, processamento, leitura e apresentação
possuem unidades de execução separadas. As filas desacoplam produtores e consumidores
no tempo, e cada serviço pode ser implantado ou interrompido sem interromper todos os
demais.

&emsp; Apesar dessa separação, a solução **não implementa microsserviços estritos**.
Os serviços compartilham uma instância PostgreSQL e um modelo de dados coordenado por
migrations. Essa é uma decisão deliberada para o MVP e para o Learner Lab: evita custo
operacional, duplicação de dados e transações distribuídas, enquanto preserva
fronteiras claras de responsabilidade. Uma evolução para bancos independentes por
serviço só se justificaria quando autonomia organizacional, escala ou isolamento de
falhas compensassem essa complexidade.

### 4.2 PostgreSQL em vez de DynamoDB

&emsp; O DynamoDB atendia ao MVP quando a aplicação controlava o formato dos eventos.
O CDC de 33 tabelas heterogêneas exige joins, constraints, SQL analítico, transações e
reconstrução das camadas. O PostgreSQL também permite manter o log genérico em
`jsonb`, o estado corrente tipado e as views temporais no mesmo mecanismo de
consistência.

### 4.3 API Gateway integrado diretamente ao SQS

&emsp; As rotas de entrada não executam regra de negócio na borda. Por isso, integrar
o API Gateway diretamente ao SQS elimina uma Lambda intermediária, reduz custo e
remove um ponto de falha sem perder comportamento necessário. A validação e a
idempotência permanecem nos workers consumidores.

### 4.4 Duas filas e dois workers

&emsp; Mudanças de tabelas e eventos de sessão possuem contratos, volumes e destinos
diferentes. Filas e consumidores separados evitam bloqueio entre fluxos, produzem
métricas independentes e permitem evolução ou escalabilidade horizontal por serviço.
O custo é a duplicação de alguns recursos SQS e ECS, aceitável diante do isolamento
obtido.

### 4.5 Lambda para leitura e Fargate para processamento contínuo

&emsp; A API de leitura é intermitente e adequada ao modelo sob demanda da Lambda. Os
workers usam consulta longa (*long polling*), pools de conexão e laços contínuos; por
isso, Fargate oferece um ciclo de vida mais previsível. O Terraform atual usa
`desired_count` fixo e **não configura Application Auto Scaling**. O Fargate permite
adicionar escalabilidade horizontal posteriormente, mas essa capacidade não deve ser
descrita como já implementada.

### 4.6 Processamento determinístico no mesmo serviço

&emsp; ETL, checkpoints e análise são threads diferentes dentro do serviço
`processing`. A consistência não depende de memória compartilhada: transações,
watermarks, claims, leases e fencing residem no PostgreSQL. Essa escolha reutiliza uma
task definition e um conjunto de alarmes, sem criar filas ou serviços adicionais para
atividades cuja coordenação já é transacional.

### 4.7 Adaptações de rede ao Learner Lab

&emsp; [Sprint 3] A postura padrão passou a ser a recomendada: `create_network = true`
e `assign_public_ip = false`, com as tasks em sub-rede privada saindo pelo NAT Gateway.
Na Sprint 2 o padrão era o oposto, com `assign_public_ip = true` sobre a VPC padrão da
conta e sem NAT, o que evitava o custo mas deixava o security group sem regra de
entrada como único controle de ingresso. O custo do NAT, de cerca de US$ 32/mês
cobrados por hora existindo, é a razão pela qual o desenho anterior existia, e a razão
pela qual a
variável de volta foi mantida: em sessões de laboratório em que a rede não está sendo
demonstrada, `create_network = false` com `assign_public_ip = true` economiza esse valor
sem alterar código. A combinação inversa é recusada no `plan`, porque põe a task numa
sub-rede sem rota para o Internet Gateway.

&emsp; Duas restrições do laboratório foram confirmadas na aplicação e condicionam o
desenho. A `LabRole` não confia em `vpc-flow-logs.amazonaws.com`, o que inviabiliza
entregar os Flow Logs ao CloudWatch Logs com `create_iam_roles = false`; daí o destino
padrão ser um bucket S3, que usa política de bucket em vez de papel IAM. E a SCP da
organização nega `s3:GetBucketObjectLockConfiguration`, chamada que o provider AWS faz
ao reler qualquer `aws_s3_bucket` recém-criado; as variáveis `flow_logs_bucket_name` e
`alb_logs_bucket_name` contornam isso aceitando buckets criados fora do Terraform. As
duas estão detalhadas em [`infraestrutura-integracao.md`](infraestrutura-integracao.md).

&emsp; Um NAT único, e não um por zona, é decisão de custo consciente: com um só, a
queda daquela AZ derruba a saída das duas sub-redes privadas.

&emsp; `db_publicly_accessible` permanece `false`, inclusive no laboratório. A
alternativa, que era um banco público restrito à faixa de endereços de quem estivesse
trabalhando, foi descartada porque fazia a exposição do dado do parceiro depender de
uma linha de
`tfvars` e da rede de alguém. A task `migration`, que roda dentro da VPC, dá o mesmo
acesso administrativo sem essa dependência, ao custo de uma chamada `run-task` em vez
de um `psql` direto.

### 4.8 Website S3 no Learner Lab

&emsp; O site estático no endpoint de website do S3 reduz custo, permanece disponível
quando os serviços do laboratório são pausados e usa apenas operações permitidas pelo
papel `voclabs`. O bucket concede leitura pública somente aos objetos do dashboard; a
API e os dados continuam separados e protegidos pelo token Bearer.

&emsp; A contrapartida é relevante: o endpoint serve **somente HTTP**. Como o dashboard
pede um token colado pelo operador, um intermediário de rede pode observar a
credencial ou alterar o JavaScript entregue e capturá-la. O armazenamento do token
apenas em `sessionStorage` reduz persistência local, mas não corrige a ausência de TLS.
Por isso esta arquitetura é um fallback temporário para demonstração em rede confiável,
e não a postura recomendada para produção.

&emsp; Alternativas avaliadas:

| Alternativa | Por que não |
|---|---|
| Website S3 em HTTP | Escolhido temporariamente porque é suportado pelo papel do laboratório; exige rede confiável e rotação após suspeita de exposição |
| CDN gerenciada com TLS e bucket privado | As operações necessárias não são permitidas pelo papel `voclabs` desta sessão |
| Certificado próprio no ACM com domínio da equipe | Exigiria um domínio registrado e uma zona de DNS que o laboratório não tem onde hospedar |
| Servir o dashboard pela própria Lambda | Transformaria arquivo estático em invocação cobrada por requisição e acrescentaria cold start ao carregamento da página |

### 4.9 Tabela de decisões arquiteturais

| # | Decisão | Alternativa descartada | Atributo de qualidade | Falha prevista e mitigação | Custo | Rollback |
|---|---|---|---|---|---|---|
| 1 | PostgreSQL em vez de DynamoDB | DynamoDB com GSIs | Adequação funcional: agregação e janela temporal em SQL | Instância única é ponto de falha; `db_multi_az` disponível, desligado por custo | ~US$ 60/mês em `db.t3.medium` | Snapshot do RDS antes de migration destrutiva |
| 2 | Integração direta API Gateway → SQS | Lambda intermediária | Desempenho e custo: sem cold start no caminho de ingestão | Payload inválido só é detectado no worker; DLQ com motivo registrado | Por requisição | Rota é declarativa; reverter é um `apply` |
| 3 | Duas filas e dois workers | Fila única com roteamento no consumidor | Confiabilidade: rajada de CDC não bloqueia evento de sessão | Backlog independente por fluxo, com alarme próprio | Duas filas + duas DLQ, custo desprezível | — |
| 4 | Lambda para leitura, Fargate para processamento | Fargate para tudo | Custo: uso intermitente do dashboard | Cold start de ENI na VPC; memória de 1024 MB medida contra o banco real | ~US$ 0 ocioso | — |
| 5 | Lambda authorizer com token compartilhado | API key; Cognito | Segurança (RNF09) dentro do escopo do MVP | Token identifica serviço, não pessoa; rotação por `make auth-rotate` | Invocação com cache de 5 min | Remover `authorization_type` das rotas |
| 6 | Hash do token no Secrets Manager | Token em claro no Terraform | Segurança: o valor não entra no state nem no repositório | Perda do token de leitura exige rotação dos dois | Dois segredos | Rotacionar |
| 7 | Website S3 público para leitura | CDN com TLS e bucket privado | Compatibilidade com as permissões do Learner Lab e baixo custo | HTTP expõe a página e o token a intermediários; uso restrito a rede confiável e ambiente temporário | Armazenamento e requisições S3 | Migrar para hospedagem HTTPS quando o ambiente permitir |
| 8 | Tag de imagem por SHA do commit | `latest` | Capacidade de manutenção: o `plan` mostra o que muda | Build de árvore suja é recusado por `make push` | — | Apontar o SHA anterior |
| 9 | Amostragem uniforme em `/timeline` | Truncar o excedente | Desempenho sem perder cobertura da janela | Perda de resolução, sinalizada por `truncated` | — | Elevar `LIMITE_POR_RAIA` |
| 10 | Índices `025` e `026` | Cache na aplicação | Desempenho (RNF02) sem risco de servir dado velho | Custo de escrita nos índices, desprezível neste volume | Armazenamento | Migration nova que remove o índice |
| 11 | **[Sprint 3]** VPC gerenciada com sub-rede privada e NAT | Continuar na VPC padrão com IP público nas tasks | Segurança: defesa em profundidade no ingresso — sem rota, além de sem regra | NAT em AZ única é ponto de falha; declarado, não escondido | ~US$ 32/mês | `create_network = false` com `assign_public_ip = true` |
| 12 | **[Sprint 3]** Flow Logs em S3 | CloudWatch Logs | Observabilidade de rede compatível com a `LabRole`, que não confia no serviço de flow logs | Consulta exige baixar arquivo, sem Logs Insights | Centavos no volume do laboratório | `flow_logs_destination = "cloudwatch"` numa conta sem a restrição |

---

## 5. Plano detalhado de implantação na AWS

### 5.1 Pré-requisitos e segurança do estado

1. Configurar AWS CLI, Docker, Terraform, Python 3.12, `uv`, Node.js 20 e `make`.
2. Confirmar a conta e a sessão com `aws sts get-caller-identity` e uma chamada com
   permissão real, como `aws ec2 describe-vpcs`.
3. Definir `AWS_PROFILE` e `AWS_REGION=us-east-1` antes de executar Terraform.
4. Copiar `terraform.tfvars.example` para `terraform.tfvars` e preencher role,
   senhas e CIDR; o arquivo não deve ser versionado.
5. Preferir backend remoto para o `terraform.tfstate` e revisar o account ID antes de
   cada aplicação em uma nova sessão do Learner Lab.

&emsp; O state **não deve ser apagado ou “resetado” enquanto ainda representar
recursos existentes**. Se o Learner Lab fornecer outra conta, primeiro deve-se
confirmar a mudança do account ID, preservar uma cópia do state anterior e iniciar um
backend, chave ou workspace correspondente à nova conta. Descartar o state sem essa
verificação pode duplicar recursos e retirar seu gerenciamento do Terraform.

### 5.2 Recursos provisionados

| Recurso AWS | Finalidade | Arquivo Terraform principal |
|---|---|---|
| VPC, sub-redes, IGW, NAT, rotas, endpoint S3, Flow Logs **[Sprint 3]** | Rede gerenciada e sua observabilidade | `vpc.tf`, `vpc_logs.tf` |
| API Gateway HTTP API | Ingestão e leitura | `apigateway*.tf`, `api_read.tf` |
| Lambda `authorizer` | Verificação do token Bearer nas duas APIs | `auth.tf` |
| Secrets Manager | SHA-256 dos tokens e token de ingestão em claro | `auth.tf`, `rds.tf` |
| SQS + DLQs | Buffer e redrive dos dois fluxos | `sqs.tf`, `sqs_changes.tf` |
| ECS Fargate | Workers, simulador, processamento, loader e migration | `ecs*.tf` |
| ECR | Quatro imagens de container, marcadas pelo SHA do commit | `ecr.tf` |
| RDS PostgreSQL 16 | Persistência transacional e analítica, **privado** | `rds.tf` |
| S3 `origem` | Parquet e manifesto da carga inicial | `s3_origem.tf` |
| S3 `frontend` | Export estático, website HTTP e leitura pública somente dos objetos | `frontend_s3.tf` |
| Lambda `read_api` | API de leitura Flask | `api_read.tf` |
| IAM | Roles e policies | `iam.tf` |
| CloudWatch + SNS | Logs, métricas, alarmes e notificações | `observability.tf` |

### 5.3 Ordem de implantação

&emsp; A ordem abaixo respeita as dependências reais entre os recursos. Cada passo só
é possível depois do anterior; inverter dois deles produz uma falha cuja causa não é
óbvia na mensagem de erro.

> **Segurança → infraestrutura → imagens → migrations → carga → serviços → Lambda →
> frontend → smoke → evidências**

#### Passo 1 — segurança: conferir a conta e preparar os artefatos

```bash
export AWS_PROFILE=g4 AWS_REGION=us-east-1
aws sts get-caller-identity --profile g4 --query Account --output text
```

&emsp; O id da conta do Learner Lab **muda a cada sessão** e está dentro de
`existing_role_arn` no `terraform.tfvars`. Confirmá-lo antes de qualquer `plan` evita
que o state passe a descrever uma conta que já não existe.

```bash
make -C apps/fullstack install
make -C apps/fullstack lambda-build   # empacota read_api E authorizer
make -C apps/fullstack check
```

&emsp; Os dois zips precisam existir antes do `terraform plan`: o Terraform calcula o
hash de cada arquivo para saber se a função mudou. Ambos são reprodutíveis: o build
fixa o `mtime` dos arquivos antes de compactar, sem o que todo `plan` proporia
atualizar as funções mesmo sem mudança de código, e o ruído esconderia a alteração
real no meio do plano.

#### Passo 2 — infraestrutura, com os serviços desligados

```bash
cd apps/fullstack/infra
cp terraform.tfvars.example terraform.tfvars   # preencher role e senhas
terraform init
terraform validate
terraform plan  -var="worker_desired_count=0" \
                -var="processing_desired_count=0" \
                -var="simulator_desired_count=0"
terraform apply -var="worker_desired_count=0" \
                -var="processing_desired_count=0" \
                -var="simulator_desired_count=0"
```

&emsp; Cria security groups, RDS, buckets, endpoint de website S3, filas, APIs,
authorizer, segredos, cluster ECS, repositórios ECR, Lambdas, alarmes e task
definitions, sem iniciar containers cujas imagens ainda não existem.

#### Passo 3 — gerar e publicar os tokens

```bash
cd ../../..
make -C apps/fullstack auth-rotate
```

&emsp; Gera os dois tokens de 256 bits, grava os **hashes** no Secrets Manager e
imprime os valores em claro **uma única vez**. Guarde-os agora: o de leitura não tem
como ser recuperado; o de ingestão pode ser relido com `make auth-show-ingest`.

&emsp; Este passo vem antes de subir os serviços: o simulador falha ao iniciar sem
`CHANGES_TOKEN`, e falhar cedo é melhor que subir, avançar o relógio virtual e só
descobrir o problema quando todo lote voltar 401, o que deixaria o relógio à frente do
dado efetivamente ingerido.

#### Passo 4 — construir e publicar as imagens no ECR

```bash
make -C apps/fullstack push
```

&emsp; Publica `worker`, `simulator`, `processing` e `loader`, cada uma com duas tags:
o SHA do commit, que é o que a task definition referencia, e `latest`, apenas como
apelido. O alvo recusa publicar a partir de uma árvore com alteração não commitada,
porque uma imagem assim não corresponde a commit nenhum e o rollback deixaria de ter
para onde voltar.

#### Passo 5 — aplicar as migrations e criar o usuário de leitura

```bash
make -C apps/fullstack migrate-status-aws   # o que já está aplicado
make -C apps/fullstack migrate-aws          # aplica as pendentes, até a 026
```

&emsp; As duas rodam pela task `migration`, dentro da VPC. O RDS é privado e não há
rota da máquina de quem trabalha até a porta 5432, nem deve haver. Acompanhe com
`make logs SERVICO=processing`.

&emsp; O usuário de leitura ainda precisa de uma conexão de escrita; ele é criado uma
única vez, na primeira implantação:

```bash
make -C apps/fullstack db-url
# exportar DATABASE_URL conforme a saída
DB_READER_PASSWORD='<a mesma de read_api_db_password>' make -C apps/fullstack db-reader
```

&emsp; As migrations só podem ser aplicadas depois que o RDS e a imagem `processing`
existem; daí a ordem entre os passos 4 e 5.

#### Passo 6 — carga inicial

```bash
make -C apps/fullstack origem-sync
make -C apps/fullstack load
```

&emsp; A task `loader` lê os Parquet, usa `COPY FROM STDIN`, executa `ANALYZE` e
compara as contagens com `_manifest.json`. São de 20 a 30 minutos para 68,7 milhões de
linhas. O simulador permanece desligado até a conclusão: reproduzir mudança sobre
tabela vazia não produz nada.

#### Passo 7 — ativar os serviços

```bash
cd apps/fullstack/infra && terraform apply && cd ../../..
make -C apps/fullstack sim-on
make -C apps/fullstack digests
```

&emsp; O `apply` ativa workers e processamento conforme o `terraform.tfvars`, com
`processing_desired_count = 1`. `make digests` confere que cada serviço está executando
a tag do commit atual, que é a verificação que faltava quando as task definitions
apontavam para `latest`.

#### Passo 8 — publicar o dashboard

```bash
make -C apps/fullstack env
make -C apps/fullstack frontend-install
make -C apps/fullstack frontend-deploy
```

&emsp; A URL da API entra no bundle em tempo de build; o token, não. Ele é colado pelo
operador na tela de acesso e vive apenas em `sessionStorage`. O alvo sincroniza o
bucket e imprime a URL HTTP do website S3. Esta publicação deve ser usada somente
em rede confiável devido à ausência de TLS na página que recebe o token.

#### Passo 9 — smoke

```bash
export ARGUS_READ_TOKEN='<o token de leitura do passo 3>'
make -C apps/fullstack smoke
```

&emsp; O smoke verifica, nesta ordem: **401 sem token**, **403 com token inválido**,
**200 em `/health/live` sem token**, e então cada rota autenticada com status, latência
e tamanho da resposta. Ele falha se qualquer rota passar de 5 s (RNF02).

#### Passo 10 — evidências

```bash
export ARGUS_INGEST_TOKEN=$(make -C apps/fullstack auth-show-ingest)
make -C apps/fullstack postman-evidencia
make -C apps/fullstack count
make -C apps/fullstack dlq
cd apps/fullstack/infra && terraform plan     # precisa terminar sem mudanças
```

&emsp; `postman-evidencia` executa a coleção completa e versiona um resumo sanitizado,
com commit, ambiente, contagens, duração e falhas. O JSON completo do Newman não é
versionado: ele carrega os cabeçalhos de cada requisição, inclusive o `Authorization`.

### 5.4 Verificação pós-implantação

&emsp; Além dos comandos do passo 10, devem ser verificados:

- migrations `001` a `026` registradas como aplicadas;
- 33 tabelas carregadas com contagens iguais ao `_manifest.json`;
- `make lambda-hash` mostrando o mesmo hash local e `CodeSha256` publicado, para as
  duas funções;
- `make digests` sem nenhum serviço marcado como `ATRAS`;
- mensagem sintética chegando à bronze e atravessando o ETL;
- publicação de checkpoint Gold e conclusão de um run de análise;
- views ocultando linhas com `available_at > sim.now()`;
- Lambda consultando somente como usuário de leitura;
- DLQs vazias, serviços estáveis e nenhum alarme em ALARM;
- **dashboard acessível pelo endpoint HTTP do website S3**, em rede confiável, com a
  tela de acesso aparecendo antes de qualquer consulta e o acesso liberado após o
  token;
- `terraform plan` terminando com zero alterações.

### 5.5 Rollback e recuperação

- Os serviços ECS usam *deployment circuit breaker* com reversão da task definition.
- Imagens devem usar tags imutáveis por commit para permitir retorno à versão
  anterior.
- Migrations são progressivas; antes de mudanças destrutivas deve ser criado um
  snapshot do RDS e preparado um plano de correção *forward-only*.
- `terraform plan` deve ser revisado antes de todo apply. Destruições inesperadas
  bloqueiam a implantação.
- Em laboratório, `make pause` reduz os serviços a zero sem apagar o RDS. O comando
  de destruição remove banco, filas e buckets e não faz parte do fluxo normal de
  rollback.

---

## 6. Riscos e limitações conhecidas

| Risco ou limitação | Situação e mitigação |
|---|---|
| **Token identifica serviço, não pessoa** | Assumido e documentado. Não há como saber qual integrante fez uma consulta; a resposta a um vazamento é rotacionar os dois tokens (`make auth-rotate`), não revogar um usuário. Identidade individual exigiria Cognito, fora do escopo do MVP |
| **Dashboard servido por HTTP** | O website S3 não oferece TLS. Um intermediário pode ler o token ou alterar a página para capturá-lo. Usar somente em rede confiável, não reutilizar o token em outros sistemas e rotacioná-lo após qualquer suspeita de exposição; produção exige hospedagem HTTPS |
| **Token do dashboard vive no navegador** | Só em `sessionStorage`, por aba, descartado ao fechá-la. Não entra no bundle, na URL, em `localStorage`, em cookie nem em log. Isso reduz persistência local, mas não protege o token durante o carregamento da página HTTP |
| **Propagação da rotação leva até 10 min** | Cinco minutos de cache do authorizer no API Gateway mais cinco do cache em memória da função. Aceitável para rotação planejada; num vazamento, apagar a versão do segredo derruba o acesso no próximo ciclo |
| Tasks em sub-redes públicas no laboratório | Security group sem ingress; produção deve preferir sub-redes privadas com NAT ou VPC endpoints |
| Estado local do Terraform | Preferir backend remoto; nunca descartar state sem validar conta e recursos |
| Classe `db.t3.medium` indisponível no laboratório | Confirmar oferta antes do apply; avaliar `small` ou `micro` |
| EventBridge não provisionado | O processamento roda em laços internos no ECS |
| Escalabilidade automática não configurada | `desired_count` é fixo; escalabilidade horizontal é evolução futura |
| Propagação de deletes para Silver/Gold | Validar e implementar política explícita antes de depender desse comportamento |
| Instância RDS única | `db_multi_az` existe e está desligado por custo; um snapshot precede toda migration destrutiva |
| Dump bruto fora do bucket de origem | A carga inicial usa o Parquet derivado, que está lá. O dump é dado do parceiro, não redistribuível; a ausência é característica do ambiente, não pendência |

---

## 7. Conclusão

&emsp; A arquitetura atende ao objetivo de reproduzir dois fluxos assíncronos,
preservar a história das mudanças, gerar camadas analíticas consistentes e expor
resultados auditáveis ao dashboard. Os componentes implantáveis estão separados por
responsabilidade, mas compartilham o PostgreSQL de forma deliberada para reduzir custo
e complexidade no MVP. O plano de implantação respeita as dependências reais entre
Terraform, ECR, migrations, carga inicial, serviços e frontend.

&emsp; Autenticação Bearer nas três APIs, website S3 público para leitura, RDS privado,
imagens marcadas pelo SHA do commit e log estruturado correlacionado por
`X-Request-Id` compõem a configuração atual. A hospedagem HTTPS do dashboard volta a
ser uma evolução necessária, ao lado de identidade individual por Cognito, sub-redes
privadas, auto scaling e EventBridge Scheduler. Nenhuma delas deve ser apresentada
como implementada.

---

## Apêndice A — Modelo de dados

&emsp; A bronze separa o `change_log` append-only do estado corrente tipado. Essa
separação permite acomodar novas colunas no log sem migration imediata e reconstruir
as camadas derivadas. A Silver canonicaliza tempo e mantém versões de fatos por LSN.
A Gold materializa features, qualidade, hipóteses e evidências. Views públicas aplicam
a barreira temporal `available_at <= sim.now()` e limitam o acesso da API.

&emsp; O conjunto inclui 33 tabelas de origem e aproximadamente 68,7 milhões de
linhas. A tabela `prom_point` é mantida porque oferece a granularidade de um minuto
necessária à timeline e às comparações; `signal_bucket`, com quinze minutos, não
preserva sozinho a sequência temporal exigida pelas telas.

---

## Apêndice B — ETL, checkpoints e coordenação

&emsp; O ETL Bronze → Silver avança por LSN. O ETL Silver → Gold avança por
`available_at` com margem de segurança. Watermark, linhas produzidas e execução são
confirmados na mesma transação.

&emsp; Cada ciclo Gold concluído publica um checkpoint append-only com
`ready_through` e `source_lsn`. O motor de análise captura uma fotografia consistente,
executa qualidade, EWMA e regras determinísticas e só publica o resultado se ainda
possuir o token de exclusão (*fencing token*). Retentativas preservam `input_lsn` e
`sim_now`, evitando resultados diferentes para a mesma entrada.

```text
bronze.change_log
        ↓
silver.analysis_fact_version
        ↓
etl.gold_checkpoint
        ↓
claim + fotografia consistente
        ↓
qualidade → EWMA → regras → pontuação
        ↓
commit protegido por fencing
        ↓
views públicas → Lambda → dashboard
```

---

## Apêndice C — Proveniência das decisões

| Origem | Contribuição |
|---|---|
| [Lucidchart — UML Deployment Diagram](https://www.lucidchart.com/pages/uml-deployment-diagram) | Notação-base de nós, ambientes de execução, artefatos e caminhos de comunicação |
| Conversas com o parceiro | Mudança de produtor de telemetria para consumidor de dados já tratados |
| Documentação do conjunto de dados | Chaves, tempos, fontes, vocabulários e limitações conhecidas |
| Análise exploratória | Volumes, nulos, granularidades e relações disponíveis |
| Telas do dashboard | Recortes temporais, dimensões e nível de detalhe necessário |
| Código e migrations de `develop` | Estado implementado de ingestão, ETL, checkpoints, detector e hipóteses |
| Terraform em `apps/fullstack/infra` | Topologia AWS, rede, segurança, observabilidade e ordem operacional |
