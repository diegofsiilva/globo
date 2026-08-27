# Arquitetura inicial da solução — Argus v3

&emsp; Este artefato detalha a arquitetura da solução Argus v3: seus componentes,
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
| (c) Justificativa da arquitetura e das tecnologias | Seção 4 |
| (d) Plano detalhado de implantação na AWS | Seção 5 |

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

<sub>Figura 1 — Implantação do Argus v3 na AWS, região `us-east-1`</sub>

![Diagrama de implantação do Argus v3](assets/arquitetura-implantacao-v3.svg)

<sup>Fonte: material produzido pelos autores (2026).</sup>

</div>

&emsp; No AWS Academy Learner Lab, a configuração de referência utiliza a VPC e as
sub-redes públicas da conta, com IP público nas tasks para evitar o custo de um NAT
Gateway. Isso não abre portas de entrada nos containers: o security group das tasks
não possui regra de ingresso. O RDS aceita conexões na porta 5432 apenas desse
security group e, quando configurado para manutenção, do CIDR explícito do
desenvolvedor. A configuração recomendada para produção é usar sub-redes privadas,
RDS privado e VPC endpoints ou NAT conforme a política da organização.

---

## 3. Nós, componentes de software e conexões

### 3.1 Clientes e fontes externas

&emsp; **Aplicação cliente ou simulador de eventos** envia eventos de sessão à rota
`POST /v1/events`. **O simulador de CDC**, executado em ECS Fargate, envia mudanças à
rota `POST /v1/changes`. Os dois caminhos usam HTTPS até o API Gateway.

&emsp; **Navegador do usuário** acessa o site estático pelo endpoint de website do S3
e consulta os dados pela API de leitura. O endpoint de website do S3 usa **HTTP** na
configuração atual; a API Gateway usa HTTPS. CloudFront ainda não foi provisionado.

### 3.2 Armazenamento de origem e carga inicial

&emsp; O **bucket S3 `origem`** (`s3_origem.tf`) armazena o dump e os 33 arquivos
Parquet usados na carga inicial. O bucket é versionado e funciona como fonte
imutável e recuperável do processo de bootstrap.

&emsp; A task Fargate **`loader`** (`ecs_loader.tf`) é executada sob demanda. Ela lê os
Parquet por `S3 GetObject`, usa `COPY FROM STDIN` pelo driver `psycopg` e valida as
contagens contra `_manifest.json`. Não é um serviço contínuo e não passa pelas filas
de ingestão.

### 3.3 Borda de ingestão e filas

&emsp; O **API Gateway de ingestão** é uma HTTP API com duas rotas. Cada rota possui
integração direta `SQS-SendMessage`, sem Lambda intermediária:

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
para o security group do RDS.

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

&emsp; As migrations `001` a `023` constroem esse contrato no estado de referência
de `develop`. O serviço `processing` executa três atividades concorrentes no mesmo
container:

1. Bronze → Silver e materialização dos fatos de análise;
2. Silver → Gold e publicação de checkpoints;
3. canário de qualidade, detector EWMA, regras, pontuação e persistência de
   hipóteses.

&emsp; A coordenação da análise fica no PostgreSQL. Reivindicações de posse
(*claims*), concessões temporárias (*leases*), sinais de vida (*heartbeats*), retomada
(*takeover*) e tokens de exclusão (*fencing*) impedem duas réplicas de publicar o
mesmo checkpoint e impedem um worker com concessão expirada de confirmar resultados.
As conexões Python com o banco usam **PostgreSQL/TCP 5432, SQL por meio de `psycopg`
e `psycopg_pool`** — não JDBC.

### 3.6 Consulta e apresentação

&emsp; O **API Gateway de leitura** invoca a função **Lambda `read_api`**, que executa
Flask empacotado com `apig-wsgi`. A Lambda entra na VPC com o mesmo security group das
tasks e consulta o RDS como `argus_api`. Esse usuário herda apenas o papel de leitura
com `SELECT` nas views públicas; não possui acesso direto às tabelas-base.

&emsp; O **bucket S3 `frontend`** publica o export estático do Next.js. O navegador
baixa HTML, CSS e JavaScript pelo endpoint HTTP do website e faz chamadas HTTPS à API
de leitura. Como não existe CloudFront, o dashboard não possui HTTPS próprio na
configuração atual.

### 3.7 Operação, segurança e observabilidade

&emsp; O **Amazon ECR** mantém quatro imagens: `worker`, `simulator`, `processing` e
`loader`. Os dois workers compartilham a imagem `worker`, mas usam comandos distintos.
O **IAM** separa execution role e task role quando a conta permite criar roles; no
Learner Lab, a `LabRole` é reutilizada por limitação do ambiente.

&emsp; O **CloudWatch** recebe logs e métricas de API Gateway, Lambda, ECS, SQS e RDS.
Os alarmes cobrem DLQs, idade das filas, serviços abaixo do número desejado de tasks,
erros das APIs, CPU, armazenamento e conexões do RDS, atraso do relógio virtual,
fontes silenciosas e falhas ou backlog do motor de análise. O **SNS** distribui os
alarmes quando há uma assinatura confirmada.

&emsp; **CloudFront e EventBridge Scheduler são planejados, mas não estão
provisionados.** O processamento atual usa laços internos de longa duração no serviço
ECS; o diagrama representa o EventBridge apenas como evolução possível.

### 3.8 Matriz de conexões

| Origem | Destino | Comunicação | Finalidade |
|---|---|---|---|
| Simulador | API Gateway de ingestão | HTTPS `POST /v1/changes` | Publicar mudanças reproduzidas |
| Aplicação cliente | API Gateway de ingestão | HTTPS `POST /v1/events` | Publicar eventos de sessão |
| API Gateway | SQS | Integração AWS `SQS-SendMessage` | Enfileirar sem Lambda intermediária |
| SQS `changes` | `merge_worker` | AWS SDK, long polling | Consumir mudanças |
| SQS `events` | `event_worker` | AWS SDK, long polling | Consumir eventos |
| S3 `origem` | `loader` | HTTPS `S3 GetObject` | Ler Parquet e manifesto |
| Componentes Python | RDS | PostgreSQL/TCP 5432 via `psycopg` | Persistência, ETL e consulta |
| Navegador | S3 `frontend` | HTTP `GET` | Baixar o dashboard estático |
| Navegador | API Gateway de leitura | HTTPS `GET` | Consultar dados e hipóteses |
| API Gateway de leitura | Lambda `read_api` | Invocação AWS | Executar a API Flask |
| ECR | Tasks Fargate | HTTPS | Baixar imagens dos containers |
| Serviços | CloudWatch/SNS | Logs, métricas e alarmes | Operação e notificação |

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

&emsp; A variável `db_publicly_accessible` possui valor padrão `false`. O arquivo de
exemplo do Learner Lab altera explicitamente o valor para `true` e restringe o acesso
ao CIDR informado em `db_allowed_cidr`; `0.0.0.0/0` é recusado pela validação. Da mesma
forma, `assign_public_ip = true` evita o NAT Gateway, mas o security group das tasks
continua sem regras de entrada. Essas concessões são próprias do laboratório e não
representam a postura recomendada para produção.

### 4.8 Limitação do website S3

&emsp; O site estático em S3 reduz custo e permanece disponível quando os serviços do
laboratório são pausados. A contrapartida é o endpoint HTTP, sem certificado e sem
autenticação na borda. CloudFront com HTTPS, política de cache e controle de acesso é
uma melhoria planejada para um ambiente produtivo.

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
| API Gateway HTTP API | Ingestão e leitura | `apigateway*.tf`, `api_read.tf` |
| SQS + DLQs | Buffer e redrive dos dois fluxos | `sqs.tf`, `sqs_changes.tf` |
| ECS Fargate | Workers, simulador, processamento, loader e migration | `ecs*.tf` |
| ECR | Quatro imagens de container | `ecr.tf` |
| RDS PostgreSQL 16 | Persistência transacional e analítica | `rds.tf` |
| S3 `origem` | Dump, Parquet e manifesto | `s3_origem.tf` |
| S3 `frontend` | Website estático | `frontend_s3.tf` |
| Lambda | API de leitura Flask | `api_read.tf` |
| IAM | Roles e policies | `iam.tf` |
| CloudWatch + SNS | Logs, métricas, alarmes e notificações | `observability.tf` |

### 5.3 Ordem de implantação

#### Passo 1 — preparar e validar os artefatos

```bash
make -C apps/basica install
make -C apps/basica lambda-build
make -C apps/basica lint
```

&emsp; O pacote da Lambda precisa existir antes do `terraform plan`. O lint valida
Python e formatação/estrutura do Terraform antes de qualquer alteração na AWS.

#### Passo 2 — criar a infraestrutura com os serviços desligados

```bash
cd apps/basica/infra
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform validate
terraform plan \
  -var="worker_desired_count=0" \
  -var="processing_desired_count=0" \
  -var="simulator_desired_count=0"
terraform apply \
  -var="worker_desired_count=0" \
  -var="processing_desired_count=0" \
  -var="simulator_desired_count=0"
```

&emsp; Esse passo cria VPC bindings, security groups, RDS, buckets, filas, APIs,
cluster ECS, repositórios ECR, Lambda, alarmes e task definitions sem iniciar
containers cujas imagens ainda não foram publicadas.

#### Passo 3 — construir e publicar as imagens no ECR

```bash
cd ../../..
make -C apps/basica push
```

&emsp; O comando publica `worker`, `simulator`, `processing` e `loader`. Em versões
subsequentes, a tag deve identificar o commit para permitir auditoria e rollback.

#### Passo 4 — aplicar as migrations e criar o usuário de leitura

&emsp; No Learner Lab, com o RDS público restrito ao CIDR do desenvolvedor:

```bash
make -C apps/basica db-url
# exportar DATABASE_URL conforme a saída anterior
make -C apps/basica migrate
DB_READER_PASSWORD='<senha do terraform.tfvars>' make -C apps/basica db-reader
```

&emsp; Com RDS privado, as migrations podem ser executadas pela task `migration`
dentro da VPC:

```bash
cd apps/basica/infra
terraform output -raw migration_run_command | bash
```

&emsp; As migrations são aplicadas somente depois que o RDS e a imagem
`processing` existem. Esse ordenamento corrige a dependência que estava invertida na
versão anterior do documento.

#### Passo 5 — executar a carga inicial

```bash
make -C apps/basica origem-sync
make -C apps/basica load
```

&emsp; A task `loader` lê os 33 Parquet, usa `COPY FROM STDIN`, executa `ANALYZE` e
compara as contagens com `_manifest.json`. O simulador deve permanecer desligado até
a conclusão dessa etapa.

#### Passo 6 — ativar os serviços

```bash
cd apps/basica/infra
terraform apply
cd ../../..
make -C apps/basica sim-on
```

&emsp; O primeiro `apply` ativa os workers e o processamento conforme os valores do
`terraform.tfvars`. O simulador é ligado separadamente após a carga para não tentar
reproduzir mudanças sobre tabelas vazias.

#### Passo 7 — publicar o dashboard

```bash
make -C apps/basica env
make -C apps/basica frontend-install
make -C apps/basica frontend-deploy
```

&emsp; A URL da API é incorporada ao build do Next.js. A saída de
`frontend-deploy` informa o endpoint HTTP público do website S3.

### 5.4 Verificação pós-implantação

```bash
make -C apps/basica smoke
make -C apps/basica postman
make -C apps/basica count
make -C apps/basica dlq
make -C apps/basica logs SERVICO=processing
```

&emsp; Além dos comandos, devem ser verificados:

- migrations `001` a `023` registradas como aplicadas;
- 33 tabelas carregadas com contagens iguais ao `_manifest.json`;
- mensagem sintética chegando à bronze e atravessando o ETL;
- publicação de checkpoint Gold e conclusão de um run de análise;
- views ocultando linhas com `available_at > sim.now()`;
- Lambda consultando somente como usuário de leitura;
- DLQs vazias, serviços estáveis e alarmes sem falha ativa;
- dashboard acessível por HTTP e chamadas da API respondendo por HTTPS.

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
| Website S3 usa HTTP | CloudFront com HTTPS é evolução planejada |
| RDS público no exemplo do Learner Lab | Acesso limitado ao CIDR; padrão da variável continua `false` |
| Tasks em sub-redes públicas no laboratório | Security group sem ingress; produção deve preferir sub-redes privadas |
| Estado local do Terraform | Preferir backend remoto; nunca descartar state sem validar conta e recursos |
| Classe `db.t3.medium` indisponível no laboratório | Confirmar oferta antes do apply; avaliar `small` ou `micro` |
| EventBridge não provisionado | O processamento roda em laços internos no ECS |
| Escalabilidade automática não configurada | `desired_count` é fixo; escalabilidade horizontal é evolução futura |
| Propagação de deletes para Silver/Gold | Validar e implementar política explícita antes de depender desse comportamento |
| APIs sem autenticação completa | Restringir origens não substitui autenticação; adicionar authorizer em produção |

---

## 7. Conclusão

&emsp; A arquitetura atende ao objetivo de reproduzir dois fluxos assíncronos,
preservar a história das mudanças, gerar camadas analíticas consistentes e expor
resultados auditáveis ao dashboard. Os componentes implantáveis estão separados por
responsabilidade, mas compartilham o PostgreSQL de forma deliberada para reduzir custo
e complexidade no MVP. O plano de implantação respeita as dependências reais entre
Terraform, ECR, migrations, carga inicial, serviços e frontend.

&emsp; CloudFront, autenticação completa, sub-redes privadas e auto scaling permanecem
como evoluções. Esses itens não devem ser apresentados como implementados no estado
atual.

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
| Terraform em `apps/basica/infra` | Topologia AWS, rede, segurança, observabilidade e ordem operacional |
