# Arquitetura final da aplicação

## 1. Diagrama de implantação

<p align="center"><sub>Figura 1 - Diagrama de implantação da arquitetura final</sub></p>

<div align="center">

![Diagrama de implantação](./assets/arquitetura-implantacao-final.png)

</div>

<p align="center"><sup>Fonte: autoria própria (2026).</sup></p>

O diagrama representa a arquitetura final em uso na Sprint 4. O caminho síncrono é
orquestrado pelo Amazon Elastic Kubernetes Service (EKS) Auto Mode, que provisiona e
remove automaticamente instâncias EC2 gerenciadas. Essas instâncias atuam como
*worker nodes* e hospedam os pods do frontend e do backend. O pipeline assíncrono
permanece no Amazon Elastic Container Service (ECS) Fargate. O Ollama é uma
integração externa e opcional usada somente para refinar a explicação final de uma
hipótese já publicada, sem participar da ingestão, do processamento ou da persistência.

### 1.1 Escopo e leitura do diagrama

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
3. **Consulta síncrona.** O navegador acessa um Application Load
   Balancer (ALB), criado pelo Ingress, que encaminha `/` ao frontend nginx e `/api`
   e `/health` à API Flask. Os dois `Services` são `ClusterIP`, portanto somente o
   Ingress publica o sistema externamente. Os pods são agendados em instâncias EC2
   gerenciadas que o EKS Auto Mode cria como nós quando a capacidade existente não
   comporta a carga. A API de leitura Lambda + API Gateway continua provisionada como
   recurso de compatibilidade, mas o caminho síncrono principal representado no
   diagrama é atendido pelos Deployments `argus-frontend` e `argus-backend` no EKS.
   Quando o frontend usa a API real, a tela solicita automaticamente o refinamento da
   hipótese por `POST /api/v1/hypotheses/{id}/refinement`. Só então o backend envia a
   hipótese e suas evidências ao Ollama remoto por SSH, valida as fontes citadas na
   resposta e devolve a explicação final ao navegador.
4. **Persistência.** As consultas da API usam o usuário de leitura e as views `v_*`.
   O feedback de hipóteses é uma escrita controlada pela função `SECURITY DEFINER`
   `gold.submit_hypothesis_feedback`. Workers, loader e migrations usam credenciais
   de execução próprias do serviço, mas as tasks ECS compartilham a URL mestre e a
   task role configurada para o fluxo. A porta 5432 é privada e liberada somente
   pelos *security groups* previstos.
5. **Operação.** Amazon Elastic Container Registry (ECR), Identity and Access
   Management (IAM), Secrets Manager, CloudWatch, Simple Notification Service (SNS)
   e Terraform formam o plano transversal de imagens, identidade, segredos,
   observabilidade e infraestrutura como código. Kustomize descreve a orquestração
   dos componentes no EKS.

### 1.2 Componentes e justificativas

| Componente / nó | Responsabilidade e artefatos implantados | Justificativa técnica |
|---|---|---|
| **Amazon API Gateway + Lambda authorizer** | Expõe `POST /v1/events` e `POST /v1/changes`, integra diretamente com o SQS e valida o token Bearer pelo hash armazenado no Secrets Manager. | A integração direta reduz componentes intermediários e latência na borda. O authorizer centraliza a autenticação, usa cache de cinco minutos e falha de forma fechada quando o segredo não pode ser validado. |
| **Amazon SQS e DLQs** | Mantém filas independentes para eventos e mudanças, ambas com política de redrive para DLQ após cinco tentativas. | Desacopla recepção e processamento, absorve rajadas e preserva mensagens problemáticas para diagnóstico e reprocessamento sem bloquear toda a ingestão. |
| **Amazon ECS Fargate** | Executa os serviços `event_worker`, `merge_worker`, `processing` e `simulator`, além da task avulsa `loader`. | O pipeline assíncrono já recebe estado desejado, reinicialização e isolamento por task sem administrar servidores. Ele permanece no Fargate porque os consumidores precisam de IAM por task para acessar SQS, S3 e outros serviços AWS. |
| **Amazon EKS Auto Mode** | Orquestra o caminho síncrono no namespace `argus`, provisiona instâncias EC2 gerenciadas como *worker nodes* e reúne os Deployments do frontend e do backend, Services, Ingress, Horizontal Pod Autoscalers (HPAs), Pod Disruption Budgets (PDBs) e o Job `argus-db-migrate`. | Fornece reconciliação contínua, reposição de pods, escalonamento e *rolling update*. Quando faltam recursos para pods pendentes, o Auto Mode cria novos nós EC2 e, quando a capacidade deixa de ser necessária, pode removê-los. Ele também fornece rede e controlador de ALB gerenciados, compatíveis com as restrições de IAM do Learner Lab. |
| **Ingress + Application Load Balancer** | O Ingress cria um ALB que encaminha `/` para `argus-frontend` e `/api` e `/health` para `argus-backend`, registrando diretamente os IPs dos pods. | A origem única elimina o CORS entre dashboard e API, enquanto o registro direto dos IPs evita um salto adicional por `NodePort`. |
| **Frontend** | O `Deployment argus-frontend` serve o export estático do Next.js em nginx, com 2 réplicas mínimas, HPA até 4, sondas, PDB e atualização gradual. | O nginx no EKS permite compartilhar a origem com a API e manter a mesma imagem em diferentes ambientes. |
| **API de leitura** | O `Deployment argus-backend` executa a API Flask + gunicorn na porta 5000, com 2 a 6 pods, HPA por CPU, probes, PDB e `preStop`. Além das consultas determinísticas, expõe `POST /api/v1/hypotheses/{id}/refinement`. A Lambda Flask atrás de API Gateway continua provisionada como recurso de compatibilidade. | O EKS oferece reposição de pods, escala horizontal e *rolling update* para o caminho síncrono principal. |
| **Ollama remoto (opcional)** | Refina a explicação apresentada ao usuário com base exclusiva na hipótese publicada e em suas evidências. O backend abre uma sessão SSH com o servidor externo e executa nele a chamada HTTP ao Ollama; cada afirmação retornada precisa citar uma fonte válida. | Mantém o modelo fora do motor determinístico: ele não cria hipóteses, não altera score ou evidências e não grava dados. Falha de rede, resposta inválida ou fonte inexistente resulta em `503`, sem resposta parcialmente fundamentada. A integração só é ativada quando `OLLAMA_URL` e as variáveis `OLLAMA_SSH_*` são fornecidas; os manifests Kubernetes base ainda não as injetam. |
| **Migration** | O `Job argus-db-migrate` usa a imagem `processing` para aplicar as migrations e criar ou atualizar o usuário de leitura. | Migration é uma execução finita, portanto um Job representa melhor seu ciclo de vida no Kubernetes. |
| **Amazon RDS PostgreSQL 16** | Mantém as camadas `bronze`, `silver`, `gold`, `etl`, `detect`, o relógio `sim.now()` e as views `v_*`, com um DB subnet group que abrange as duas zonas de disponibilidade (AZs) e permite habilitar o modo Multi-AZ. | O modelo relacional preserva transações, constraints, MERGE por LSN e consultas analíticas, enquanto a instância privada e o usuário de leitura com menor privilégio reduzem a exposição. No laboratório, mantivemos o Multi-AZ desligado por custo, mas em produção ele deve ser habilitado. |
| **VPC, sub-redes, Network Address Translation (NAT) e Internet Gateway** | Mantém as instâncias EC2 gerenciadas do EKS, Fargate e RDS nas sub-redes privadas, enquanto ALBs, NAT e, se habilitado, o bastion ficam nas públicas. | A topologia em duas zonas reduz o domínio de falha e impede a entrada direta da internet nos workloads e no banco. As tags `kubernetes.io/role/*` ajudam o EKS a identificar onde criar o ALB e os nós. |
| **Bastion Host** | É um componente opcional, criado somente quando `bastion_key_name` é preenchido. Quando habilitado, permite SSH e acesso administrativo controlado aos recursos privados. | Mantém um caminho administrativo sem expor o RDS diretamente. O bastion não faz parte obrigatória de toda implantação. |
| **Amazon Simple Storage Service (S3)** | O bucket `origem` armazena os Parquets e o manifesto usados na carga inicial. Buckets separados recebem os access logs do ALB e os VPC Flow Logs. | O S3 oferece alta durabilidade para objetos imutáveis e evidências operacionais, enquanto o dashboard do caminho principal é servido pelo nginx no EKS. |
| **Amazon ECR** | Armazena seis imagens: `backend`, `frontend`, `worker`, `simulator`, `processing` e `loader`, publicadas com tag derivada do SHA. | A versão explícita torna o deploy rastreável e permite rollback sem a ambiguidade de `latest`. Backend e frontend são publicados para `amd64` e `arm64`, pois os nós EKS e o Fargate usam arquiteturas diferentes. |
| **CloudWatch + SNS** | Mantém alarmes e logs dos componentes AWS. O SNS envia notificações quando `alarm_email` está preenchido e a assinatura foi confirmada. Os VPC Flow Logs são enviados para S3 por padrão, embora o destino CloudWatch possa ser configurado. Os pods EKS não possuem coleta centralizada de logs e métricas por padrão. | A observabilidade cobre principalmente filas, ECS, RDS, ALB e infraestrutura Terraform. O ambiente ainda depende de uma configuração adicional para acompanhar o EKS de forma centralizada. |
| **IAM + Secrets Manager + Secret do Kubernetes** | O IAM define os papéis de acesso e o Secrets Manager protege credenciais e hashes. O comando `make k8s-secret` cria o Secret `argus-backend` no cluster sem versionar esse recurso Kubernetes. Alguns valores relacionados ao EKS aparecem em outputs sensíveis e continuam no Terraform state. | IRSA e Pod Identity são bloqueados no Learner Lab. Por isso, os workloads EKS não chamam APIs AWS e os workers continuam usando IAM por task no Fargate. |
| **Terraform + Kustomize** | O Terraform provisiona a infraestrutura na AWS, enquanto a base Kustomize descreve os objetos comuns e os overlays `aws` e `kind` adaptam entrada, imagens, réplicas e configuração para cada ambiente. | Essa combinação mantém a infraestrutura e a orquestração reproduzíveis, revisáveis e portáveis. Os manifests são aplicados separadamente depois que o Terraform disponibiliza o cluster. |

### 1.3 Camada de execução no EKS Auto Mode

O frontend e o backend são executados no EKS Auto Mode, com reposição automática
de pods, atualização gradual, HPA e PDB. O dashboard e a API são publicados pelo
mesmo Ingress e pelo mesmo ALB, permitindo compartilhar a origem e recuperar
rapidamente o caminho síncrono quando um contêiner falha.

O Ollama entra somente depois que a API recupera uma hipótese já publicada. O
frontend solicita automaticamente sua explicação refinada, o backend limita o contexto
à hipótese e às evidências disponíveis e valida se todas as afirmações citam fontes
existentes antes de retornar a resposta ao usuário. Assim, a indisponibilidade do
modelo afeta apenas esse refinamento opcional e não interfere no pipeline determinístico.

O EKS Auto Mode não elimina o uso de EC2. Quando o scheduler identifica pods pendentes
e os nós existentes não têm capacidade suficiente, o mecanismo de provisionamento do
Auto Mode cria novas instâncias EC2 gerenciadas para atuarem como *worker nodes*. O
scheduler então aloca os pods nesses nós, e os contêineres e processos da aplicação
são executados dentro dos pods.

A escolha por duas plataformas foi intencional, já que o EKS atende às necessidades
do frontend e da API de leitura, enquanto o Fargate continua adequado para os workers
e para as tasks de processamento, que já são desacoplados pelo SQS e precisam de IAM
por task para acessar outros serviços da AWS.


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

