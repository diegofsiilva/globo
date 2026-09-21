# Arquitetura final da aplicação

## 1. Diagrama de implantação

<p align="center"><sub>Figura 1 - Diagrama de implantação da modalidade EKS</sub></p>

<div align="center">

![Diagrama de implantação](./assets/arquitetura-implantacao-final.png)

</div>

<p align="center"><sup>Fonte: autoria própria (2026).</sup></p>

O diagrama parte da `arquitetura-implantacao-v4` e reúne as mudanças realizadas na
Sprint 4. O sistema mantém recursos compatíveis com o caminho anterior baseado em
Auto Scaling Group (ASG), Amazon Elastic Compute Cloud (EC2), S3 e Lambda, e acrescenta
o Amazon Elastic Kubernetes Service (EKS) Auto Mode como modalidade síncrona
alternativa. Em ambos os modos, o pipeline assíncrono permanece no Amazon Elastic
Container Service (ECS) Fargate.

### 1.1 Rota alternativa EC2/ASG

<p align="center"><sub>Figura 2 - Diagrama da rota alternativa EC2/ASG</sub></p>

<div align="center">

![Rota alternativa EC2/ASG](./assets/arquitetura-implantacao-v4.png)

</div>

<p align="center"><sup>Fonte: autoria própria (2026).</sup></p>

Esta figura mostra a implantação realizada na sprint 3: frontend no website
S3, API Flask em EC2 no ASG atrás do ALB, bastion quando habilitado e RDS privado.
Ela é usada quando `create_eks = false`. Ao habilitar o EKS, o ASG deve ser zerado
manualmente, embora o ALB legado continue declarado pelo Terraform.

### 1.2 Escopo e leitura dos diagramas

O Argus usa uma arquitetura distribuída híbrida dentro de uma Amazon Virtual Private
Cloud (VPC) própria na região `us-east-1` e, no diagrama, o limite externo da VPC, as
duas zonas de disponibilidade e as sub-redes públicas e privadas mostram onde os
recursos são implantados, enquanto as caixas internas representam serviços
gerenciados, ambientes de execução e artefatos de software. Os grupos tracejados,
como o cluster EKS, indicam apenas um agrupamento lógico e não uma nova sub-rede.

No diagrama, são usadas linhas laranja para o caminho assíncrono de escrita e
processamento, linhas azuis para o caminho síncrono de consulta e linhas cinzas
tracejadas para dependências operacionais, como imagens, segredos, logs e métricas.
Como algumas relações envolvem requisição e resposta ou operações nos dois sentidos,
as setas foram omitidas. As cores funcionam como principal referência visual para
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
3. **Consulta síncrona.** No modo EKS, o navegador acessa um Application Load
   Balancer (ALB), criado pelo Ingress, que encaminha `/` ao frontend nginx e `/api`
   e `/health` à API Flask. Os dois `Services` são `ClusterIP`, portanto somente o
   Ingress publica o sistema externamente. A configuração Terraform também mantém o
   ALB/ASG legado, mesmo quando sua capacidade é zerada, porque esse ALB depende de
   `create_network`, não de `create_eks`. A API de leitura Lambda + API Gateway
   continua provisionada como compatibilidade e alternativa. No modo padrão da
   `develop`, o dashboard é servido pelo website S3 e a API pode ser atendida pelo
   ALB/EC2 ou pela API Gateway/Lambda, conforme o comando de operação utilizado.
4. **Persistência.** As consultas da API usam o usuário de leitura e as views `v_*`.
   O feedback de hipóteses é uma escrita controlada pela função `SECURITY DEFINER`
   `gold.submit_hypothesis_feedback`. Workers, loader e migrations usam credenciais
   de execução próprias do serviço, mas as tasks ECS compartilham a URL mestre e a
   task role configurada para o fluxo. A porta 5432 é privada e liberada somente
   pelos *security groups* previstos.
5. **Operação.** Amazon Elastic Container Registry (ECR), Identity and Access
   Management (IAM), Secrets Manager, CloudWatch, Simple Notification Service (SNS)
   e Terraform formam o plano transversal de imagens, identidade, segredos,
   observabilidade e infraestrutura como código. Kustomize é usado na modalidade EKS.

### 1.3 Componentes e justificativas

| Componente / nó | Responsabilidade e artefatos implantados | Justificativa técnica |
|---|---|---|
| **Amazon API Gateway + Lambda authorizer** | Expõe `POST /v1/events` e `POST /v1/changes`, integra diretamente com o SQS e valida o token Bearer pelo hash armazenado no Secrets Manager. | A integração direta reduz componentes intermediários e latência na borda. O authorizer centraliza a autenticação, usa cache de cinco minutos e falha de forma fechada quando o segredo não pode ser validado. |
| **Amazon SQS e DLQs** | Mantém filas independentes para eventos e mudanças, ambas com política de redrive para DLQ após cinco tentativas. | Desacopla recepção e processamento, absorve rajadas e preserva mensagens problemáticas para diagnóstico e reprocessamento sem bloquear toda a ingestão. |
| **Amazon ECS Fargate** | Executa os serviços `event_worker`, `merge_worker`, `processing` e `simulator`, além da task avulsa `loader`. | O pipeline assíncrono já recebe estado desejado, reinicialização e isolamento por task sem administrar servidores. Ele permanece no Fargate porque os consumidores precisam de IAM por task para acessar SQS, S3 e outros serviços AWS. |
| **Amazon EKS Auto Mode** | Na modalidade EKS, orquestra o caminho síncrono no namespace `argus`, reunindo os Deployments do frontend e do backend, Services, Ingress, Horizontal Pod Autoscalers (HPAs), Pod Disruption Budgets (PDBs) e o Job `argus-db-migrate`. | Substitui o contêiner iniciado manualmente pelo `user_data` do ASG por reconciliação contínua, reposição de pods, escalonamento e *rolling update*. O Auto Mode fornece compute, rede e controlador de ALB gerenciados, compatíveis com as restrições de IAM do Learner Lab. |
| **Ingress + Application Load Balancer** | Na modalidade EKS, o Ingress cria um ALB que encaminha `/` para `argus-frontend` e `/api` e `/health` para `argus-backend`, registrando diretamente os IPs dos pods. O Terraform também mantém o ALB legado do ASG quando `create_network = true`. | A origem única elimina o CORS entre dashboard e API no modo EKS. O ALB legado continua provisionado como compatibilidade, mesmo quando o ASG é zerado. |
| **Frontend** | No modo EKS, o `Deployment argus-frontend` serve o export estático do Next.js em nginx, com 2 réplicas mínimas, HPA até 4, sondas, PDB e atualização gradual. No modo padrão, o export é servido pelo website S3. | O nginx no EKS permite compartilhar a origem com a API. O S3 continua sendo a hospedagem da configuração padrão da `develop`. |
| **API de leitura** | A API de leitura é provisionada como Lambda Flask atrás de API Gateway e também pode ser executada como Flask + gunicorn em EC2/ASG. Na modalidade EKS, o `Deployment argus-backend` executa a mesma API na porta 5000, com 2 a 6 pods, HPA por CPU, probes, PDB e `preStop`. | Lambda/API Gateway e EC2/ASG permanecem como compatibilidade e alternativa. O EKS oferece reposição de pods e *rolling update* quando ativado. |
| **Migration** | No modo EKS, o `Job argus-db-migrate` usa a imagem `processing`. A configuração ECS mantém também uma task avulsa de migration para o modo EC2. | Migration é execução finita, portanto um Job representa melhor seu ciclo de vida no Kubernetes. A task ECS permanece disponível para a implantação anterior. |
| **Amazon RDS PostgreSQL 16** | Mantém as camadas `bronze`, `silver`, `gold`, `etl`, `detect`, o relógio `sim.now()` e as views `v_*`, com um DB subnet group que abrange as duas zonas de disponibilidade (AZs) e permite habilitar o modo Multi-AZ. | O modelo relacional preserva transações, constraints, MERGE por LSN e consultas analíticas, enquanto a instância privada e o usuário de leitura com menor privilégio reduzem a exposição. No laboratório, mantivemos o Multi-AZ desligado por custo, mas em produção ele deve ser habilitado. |
| **VPC, sub-redes, Network Address Translation (NAT) e Internet Gateway** | Quando `create_network = true`, mantém EKS, Fargate, ASG e RDS nas sub-redes privadas, enquanto ALBs, NAT e, se habilitado, o bastion ficam nas públicas. | A topologia em duas zonas reduz o domínio de falha e impede a entrada direta da internet nos workloads e no banco. As tags `kubernetes.io/role/*` ajudam o EKS a identificar onde criar o ALB e os nós. |
| **Bastion Host** | É um componente opcional, criado somente quando `bastion_key_name` é preenchido. Quando habilitado, permite SSH e acesso administrativo controlado aos recursos privados. | Mantém um caminho administrativo sem expor o RDS diretamente. O bastion não faz parte obrigatória de toda implantação. |
| **Amazon Simple Storage Service (S3)** | O bucket `origem` armazena os Parquets e o manifesto usados na carga inicial. Buckets separados recebem os access logs do ALB. O website S3 continua hospedando o frontend no modo padrão. | O S3 oferece alta durabilidade para objetos imutáveis e evidências operacionais. No modo EKS, o dashboard é servido pela imagem nginx. O recurso S3 continua declarado para manter a implantação anterior disponível. |
| **Amazon ECR** | Armazena seis imagens: `backend`, `frontend`, `worker`, `simulator`, `processing` e `loader`, publicadas com tag derivada do SHA. | A versão explícita torna o deploy rastreável e permite rollback sem a ambiguidade de `latest`. Backend e frontend são publicados para `amd64` e `arm64`, pois os nós EKS e o Fargate usam arquiteturas diferentes. |
| **CloudWatch + SNS** | Mantém alarmes e logs dos componentes AWS. O SNS envia notificações quando `alarm_email` está preenchido e a assinatura foi confirmada. Os VPC Flow Logs são enviados para S3 por padrão, embora o destino CloudWatch possa ser configurado. Os pods EKS não possuem coleta centralizada de logs e métricas por padrão. | A observabilidade cobre principalmente filas, ECS, RDS, ALB e infraestrutura Terraform. O ambiente ainda depende de uma configuração adicional para acompanhar o EKS de forma centralizada. |
| **IAM + Secrets Manager + Secret do Kubernetes** | O IAM define os papéis de acesso e o Secrets Manager protege credenciais e hashes. O comando `make k8s-secret` cria o Secret `argus-backend` no cluster sem versionar esse recurso Kubernetes. Alguns valores relacionados ao EKS aparecem em outputs sensíveis e continuam no Terraform state. | IRSA e Pod Identity são bloqueados no Learner Lab. Por isso, os workloads EKS não chamam APIs AWS e os workers continuam usando IAM por task no Fargate. |
| **Terraform + Kustomize** | O Terraform provisiona a infraestrutura na AWS, enquanto a base Kustomize descreve os objetos comuns e os overlays `aws` e `kind` adaptam entrada, imagens, réplicas e configuração para cada ambiente. | Essa combinação mantém a infraestrutura e a orquestração reproduzíveis, revisáveis e portáveis, mas o modo EKS depende de `create_eks = true` e de aplicação separada dos manifests. |

### 1.4 Como o EKS altera o caminho síncrono

Na arquitetura v4, a API de leitura era executada em instâncias EC2 de um Auto Scaling Group,
de leitura, com cada instância iniciando o contêiner pelo `user_data` e recebendo
tráfego do Application Load Balancer. A solução funcionava, mas a recuperação
dependia da substituição de uma instância inteira e cada atualização da aplicação
exigia um novo ciclo do ASG.

Na modalidade EKS, levamos o frontend e o backend para o EKS Auto Mode e passamos a
contar com reposição automática de pods, atualização gradual, HPA e PDB, além de
publicar o dashboard e a API pelo mesmo Ingress e pelo mesmo ALB. Com isso, essa
modalidade do caminho síncrono se recupera mais rapidamente quando um contêiner falha.

O EC2 não é removido do Terraform. Quando `create_eks = true`, a capacidade do ASG
deve ser configurada manualmente como zero (`asg_min_size = 0` e
`asg_desired_capacity = 0`) para que ele não execute simultaneamente com o cluster.
Quando `create_eks = false`, o ASG permanece como o caminho síncrono da implantação
e recebe tráfego pelo ALB. O card separado no diagrama representa a alternativa EC2,
não uma garantia de que ela esteja inativa em todo ambiente.

As principais mudanças entre as duas versões foram estas:

| Elemento da v4 | Arquitetura final | Estado |
|---|---|---|
| API de leitura em contêiner iniciado por `user_data` no ASG/EC2 | `Deployment argus-backend` no EKS | Continua sendo o modo padrão quando `create_eks = false`. É substituído pelo EKS quando `create_eks = true` e o ASG é zerado |
| Dashboard estático no website S3 | `Deployment argus-frontend` com nginx no EKS | Continua no modo padrão. No EKS, é servido pelo nginx para compartilhar a origem com a API |
| Migration como task avulsa do ECS | `Job argus-db-migrate` | A task ECS continua disponível. O Job é usado na modalidade EKS |

A escolha por duas plataformas foi intencional, já que o EKS atende às necessidades
do frontend e da API de leitura, enquanto o Fargate continua adequado para os workers
e para as tasks de processamento, que já são desacoplados pelo SQS e precisam de IAM
por task para acessar outros serviços da AWS.

No modo EKS, `min = 0` e `desired = 0` representam a configuração necessária para
não manter instâncias do ASG em execução durante a operação normal. No modo padrão
da `develop`, o exemplo de configuração usa duas instâncias no ASG. A escolha do
modo depende de `create_eks` e dos valores de capacidade definidos no Terraform.


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

