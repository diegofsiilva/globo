# Arquitetura final da aplicação

## 1. Diagrama de implantação

<p align="center"><sub>Figura 1 - Diagrama de implantação</sub></p>

<div align="center">

![Diagrama de implantação](./assets/arquitetura-implantacao-final.png)

</div>

<p align="center"><sup>Fonte: autoria própria (2026).</sup></p>

O diagrama parte da `arquitetura-implantacao-v4` e reúne as mudanças que fizemos na
Sprint 4, quando levamos o caminho síncrono do Auto Scaling Group (ASG) baseado em
Amazon Elastic Compute Cloud (EC2) para o Amazon Elastic Kubernetes Service (EKS)
Auto Mode e mantivemos o pipeline assíncrono no Amazon Elastic Container Service
(ECS) Fargate.

### 1.1 Escopo e leitura do diagrama

O Argus usa uma arquitetura distribuída híbrida dentro de uma Amazon Virtual Private
Cloud (VPC) própria na região `us-east-1` e, no diagrama, o limite externo da VPC, as
duas zonas de disponibilidade e as sub-redes públicas e privadas mostram onde os
recursos são implantados, enquanto as caixas internas representam serviços
gerenciados, ambientes de execução e artefatos de software. Os grupos tracejados,
como o cluster EKS, indicam apenas um agrupamento lógico e não uma nova sub-rede.

No diagrama, usamos linhas laranja para o caminho assíncrono de escrita e
processamento, linhas azuis para o caminho síncrono de consulta e linhas cinzas
tracejadas para dependências operacionais, como imagens, segredos, logs e métricas.
Como algumas relações envolvem requisição e resposta ou operações nos dois sentidos,
optamos por não usar setas, mantendo as cores como principal referência visual para
mostrar que os dois caminhos compartilham o PostgreSQL, mas seguem gatilhos e
estratégias de escala diferentes.

1. **Ingestão assíncrona.** Aplicações cliente enviam eventos e mudanças ao API
   Gateway. A integração direta publica nas filas do Amazon Simple Queue Service
   (SQS). Depois, `event_worker` e
   `merge_worker`, executados no ECS Fargate, consomem em *long polling* e persistem
   os dados no Amazon Relational Database Service (RDS). O SQS absorve picos e as
   filas de mensagens não processadas (DLQs, do inglês *dead-letter queues*) isolam
   mensagens que falharam após cinco tentativas.
2. **Processamento e carga.** `processing` e `simulator` permanecem como serviços
   Fargate. O `loader` é uma task avulsa que lê os Parquets do bucket de origem e
   executa a carga em lote no banco.
3. **Consulta síncrona.** O navegador acessa um único Application Load Balancer
   (ALB), criado pelo Ingress do EKS, que encaminha `/` ao frontend nginx e `/api` e
   `/health` à API Flask. Os dois `Services` são `ClusterIP`, portanto somente o
   Ingress publica o sistema externamente.
4. **Persistência.** O backend consulta apenas as views `v_*` com o usuário de
   leitura, enquanto workers, loader e o Job de migration possuem acessos próprios.
   A porta 5432 é privada e liberada somente pelos *security groups* previstos.
5. **Operação.** Amazon Elastic Container Registry (ECR), Identity and Access
   Management (IAM), Secrets Manager, CloudWatch, Simple Notification Service (SNS),
   Terraform e Kustomize formam o plano transversal de imagens, identidade, segredos,
   observabilidade e infraestrutura como código.

### 1.2 Componentes e justificativas

| Componente / nó | Responsabilidade e artefatos implantados | Justificativa técnica |
|---|---|---|
| **Amazon API Gateway + Lambda authorizer** | Expõe `POST /v1/events` e `POST /v1/changes`, integra diretamente com o SQS e valida o token Bearer pelo hash armazenado no Secrets Manager. | A integração direta reduz componentes intermediários e latência na borda. O authorizer centraliza a autenticação, usa cache de cinco minutos e falha de forma fechada quando o segredo não pode ser validado. |
| **Amazon SQS e DLQs** | Mantém filas independentes para eventos e mudanças, ambas com política de redrive para DLQ após cinco tentativas. | Desacopla recepção e processamento, absorve rajadas e preserva mensagens problemáticas para diagnóstico e reprocessamento sem bloquear toda a ingestão. |
| **Amazon ECS Fargate** | Executa os serviços `event_worker`, `merge_worker`, `processing` e `simulator`, além da task avulsa `loader`. | O pipeline assíncrono já recebe estado desejado, reinicialização e isolamento por task sem administrar servidores. Ele permanece no Fargate porque os consumidores precisam de IAM por task para acessar SQS, S3 e outros serviços AWS. |
| **Amazon EKS Auto Mode** | Orquestra o caminho síncrono no namespace `argus`, reunindo os Deployments do frontend e do backend, Services, Ingress, Horizontal Pod Autoscalers (HPAs), Pod Disruption Budgets (PDBs) e o Job `argus-db-migrate`. | Substitui o contêiner iniciado manualmente pelo `user_data` do ASG por reconciliação contínua, reposição de pods, escalonamento e *rolling update*. O Auto Mode fornece compute, rede e controlador de ALB gerenciados, compatíveis com as restrições de IAM do Learner Lab. |
| **Ingress + Application Load Balancer** | Publica um único endereço, encaminhando a rota `/` para `argus-frontend` e as rotas `/api` e `/health` para `argus-backend`, enquanto o ALB registra diretamente os IPs dos pods e verifica `/health/live`. | Uma origem única elimina o CORS entre dashboard e API, desacopla a imagem do frontend do hostname do ambiente e evita o custo e a operação de dois balanceadores, enquanto o health check retira alvos não saudáveis sem acoplar a vida do pod à disponibilidade do banco. |
| **Deployment `argus-frontend`** | Serve o export estático do Next.js em nginx, com 2 réplicas mínimas, HPA até 4, sondas, PDB e atualização gradual sem indisponibilidade. | O dashboard deixa de depender do website S3 e passa a ter a mesma origem da API. Réplicas e distribuição entre zonas mantêm a interface disponível durante reinícios, atualizações e perda de um pod. |
| **Deployment `argus-backend`** | Executa Flask + gunicorn na porta 5000, com 2 a 6 pods, HPA por CPU, `startupProbe`, `livenessProbe`, `readinessProbe`, PDB e `preStop`. | A separação das sondas evita reiniciar todos os pods durante uma falha do RDS: a readiness remove o pod do tráfego, enquanto a liveness confirma apenas a saúde do processo. `maxUnavailable: 0` mantém capacidade durante o deploy. |
| **Job `argus-db-migrate`** | Usa a imagem `processing` para aplicar as migrations e criar ou atualizar o usuário de leitura antes do deploy da aplicação. | Migration é execução finita, portanto um Job representa melhor seu ciclo de vida. Ele fica fora da base Kustomize porque o template de Job é imutável e precisa ser recriado a cada nova versão. |
| **Amazon RDS PostgreSQL 16** | Mantém as camadas `bronze`, `silver`, `gold`, `etl`, `detect`, o relógio `sim.now()` e as views `v_*`, com um DB subnet group que abrange as duas zonas de disponibilidade (AZs) e permite habilitar o modo Multi-AZ. | O modelo relacional preserva transações, constraints, MERGE por LSN e consultas analíticas, enquanto a instância privada e o usuário de leitura com menor privilégio reduzem a exposição. No laboratório, mantivemos o Multi-AZ desligado por custo, mas em produção ele deve ser habilitado. |
| **VPC, sub-redes, Network Address Translation (NAT) e Internet Gateway** | Mantém EKS, Fargate e RDS nas sub-redes privadas, enquanto ALB, NAT e bastion ficam nas públicas, com o NAT cuidando da saída dos workloads e o Internet Gateway atendendo apenas os recursos públicos. | A topologia em duas zonas reduz o domínio de falha e impede a entrada direta da internet nos contêineres e no banco, enquanto as tags `kubernetes.io/role/*` ajudam o EKS a identificar onde deve criar o ALB e os nós. |
| **Bastion Host** | É o ponto de entrada usado pela equipe para acessar os recursos privados por Secure Shell (SSH) e, quando necessário, chegar ao RDS por uma conexão temporária, sempre a partir de um bloco Classless Inter-Domain Routing (CIDR) autorizado. | Ao concentrar o acesso administrativo no bastion, evitamos expor o SSH e o PostgreSQL diretamente à internet e mantemos um caminho mais fácil de acompanhar e auditar, enquanto o endpoint público do EKS também permanece limitado por CIDR no ambiente de laboratório. |
| **Amazon Simple Storage Service (S3)** | O bucket `origem` armazena os Parquets e o manifesto usados na carga inicial, enquanto buckets separados recebem os access logs do ALB. | O S3 oferece alta durabilidade para objetos imutáveis e evidências operacionais, mas deixou de hospedar o frontend da arquitetura ativa porque o dashboard passou a ser servido por uma imagem nginx no EKS. |
| **Amazon ECR** | Armazena seis imagens: `backend`, `frontend`, `worker`, `simulator`, `processing` e `loader`, publicadas com tag derivada do SHA. | A versão explícita torna o deploy rastreável e permite rollback sem a ambiguidade de `latest`. Backend e frontend são publicados para `amd64` e `arm64`, pois os nós EKS e o Fargate usam arquiteturas diferentes. |
| **CloudWatch + SNS** | Centraliza logs, métricas, VPC Flow Logs e alarmes, enquanto o SNS encaminha as notificações operacionais. | Ao reunir a observabilidade de aplicação, rede e infraestrutura, conseguimos acompanhar indisponibilidade, backlog, erros da API e pressão no banco nas duas plataformas de orquestração. |
| **IAM + Secrets Manager + Secret do Kubernetes** | O IAM define os papéis de acesso, o Secrets Manager protege credenciais e hashes e o comando `make k8s-secret` injeta cinco valores no Secret `argus-backend` sem gravá-los em arquivo ou no estado do Terraform. | Como IAM Roles for Service Accounts (IRSA) e Pod Identity são bloqueados no Learner Lab, movemos para o EKS apenas os workloads que não chamam APIs da Amazon Web Services (AWS) e mantivemos os workers no Fargate, onde continuam usando IAM por task. |
| **Terraform + Kustomize** | O Terraform provisiona a infraestrutura na AWS, enquanto a base Kustomize descreve os objetos comuns e os overlays `aws` e `kind` adaptam entrada, imagens, réplicas e configuração para cada ambiente. | Essa combinação mantém a infraestrutura e a orquestração reproduzíveis, revisáveis e portáveis, sem fixar conta, repositório ou hostname do laboratório nos manifestos. |

### 1.3 Por que o EC2 deixou o caminho principal

Na arquitetura v4, usamos instâncias EC2 em um Auto Scaling Group para executar a API
de leitura, com cada instância iniciando o contêiner pelo `user_data` e recebendo
tráfego do Application Load Balancer. A solução funcionava, mas a recuperação
dependia da substituição de uma instância inteira e cada atualização da aplicação
exigia um novo ciclo do ASG.

Na arquitetura final, levamos o frontend e o backend para o EKS Auto Mode e passamos a
contar com reposição automática de pods, atualização gradual, HPA e PDB, além de
publicar o dashboard e a API pelo mesmo Ingress e pelo mesmo ALB. Com isso, o caminho
síncrono ficou mais simples de operar e passou a se recuperar mais rápido quando um
contêiner apresenta falha.

Isso não significa que o EC2 tenha saído da VPC, apenas que ele deixou de fazer parte
do fluxo principal. O card de ASG/EC2 aparece separado no diagrama para representar
uma alternativa antiga, mantida como referência de contingência, mas, caso seja
reativado, o ASG volta a executar a API nas sub-redes privadas e a receber tráfego
pelo ALB. A posição do card fora da área principal indica que ele está inativo e não
que as instâncias seriam executadas fora da VPC.

As principais mudanças entre as duas versões foram estas:

| Elemento da v4 | Arquitetura final | Estado |
|---|---|---|
| API de leitura em contêiner iniciado por `user_data` no ASG/EC2 | `Deployment argus-backend` no EKS | Retirado do fluxo principal. A configuração anterior foi mantida como referência para contingência |
| Dashboard estático no website S3 | `Deployment argus-frontend` com nginx no EKS | Substituído para oferecer origem única com a API |
| Migration como task avulsa do ECS | `Job argus-db-migrate` | Substituído. `loader`, workers, simulador e processamento continuam no ECS Fargate |

A escolha por duas plataformas foi intencional, já que o EKS atende às necessidades
do frontend e da API de leitura, enquanto o Fargate continua adequado para os workers
e para as tasks de processamento, que já são desacoplados pelo SQS e precisam de IAM
por task para acessar outros serviços da AWS.

No diagrama, `min = 0` e `desired = 0` representam a intenção de não manter instâncias
do ASG legado em execução durante a operação normal, embora a configuração atual
ainda exija um mínimo de duas instâncias e precise ser revista antes que esse caminho
possa ser usado como um fallback real.


## 2. Inventário de contêineres, Docker e Kubernetes


### 2.1 Dockerfiles

> Listar cada Dockerfile, o serviço ou imagem gerada, a finalidade do contêiner e o componente correspondente no diagrama.


### 2.2 Execução local

> Informar os arquivos usados para executar a aplicação localmente, incluindo sua finalidade e os serviços iniciados.


### 2.3 Orquestração e infraestrutura Terraform

> Listar os arquivos de orquestração e infraestrutura, os recursos declarados e a forma como eles implantam ou conectam os componentes da arquitetura.


## 3. Plano de recuperação de falhas

> Documentar as estratégias de recuperação da aplicação diante de falhas de serviços, contêineres, rede, banco de dados e infraestrutura.

### 3.1 Objetivos e níveis de severidade

> Informar os objetivos de recuperação, incluindo RTO, RPO, níveis de severidade, impacto esperado e responsáveis pelo acionamento.


### 3.2 Estratégias implementadas

> Descrever replicação de serviços, fallback automático, políticas de reinicialização, health checks, substituição de instâncias e rollback de versões.


### 3.3 Procedimento de resposta

> Descrever as etapas para detectar, conter, recuperar e validar a normalização após uma falha.


### 3.4 Limitações e decisões pendentes

> Registrar limitações conhecidas, dependências de configuração, riscos residuais e decisões arquiteturais ainda pendentes.


## 4. Evidências de validação

> Inserir evidências do diagrama, da execução dos contêineres, da infraestrutura implantada e dos testes de recuperação de falhas.

