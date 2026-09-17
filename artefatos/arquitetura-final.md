# Arquitetura final da aplicação

## 1. Diagrama de implantação

![Diagrama de implantação da arquitetura distribuída do Argus]()

**Figura 1 — Diagrama de implantação da arquitetura distribuída do Argus.** A
versão editável está disponível em
[``]().

### 1.1 Componentes e justificativas

| Componente / nó | Responsabilidade e artefatos implantados | Justificativa técnica |
|---|---|---|
| **Amazon API Gateway + Lambda authorizer** | Expõe as rotas HTTP de ingestão (`/events` e `/changes`), integra diretamente com o SQS e valida o token Bearer pelo hash armazenado no Secrets Manager. | A integração direta reduz componentes intermediários e latência na borda. O authorizer centraliza a autenticação e falha de forma fechada quando o segredo não pode ser validado. |
| **Amazon SQS e DLQs** | Desacopla a recepção dos eventos do processamento; mantém filas independentes para eventos e mudanças, com redrive para DLQs. | Absorve picos, permite consumo em lote e evita que falhas transitórias dos workers indisponibilizem a ingestão. As DLQs preservam mensagens rejeitadas para diagnóstico e reprocessamento. |
| **Amazon ECS Fargate** | Executa `event worker`, `merge worker`, `simulator` e `processing`; `loader` e `migration` rodam como tasks avulsas. | Os serviços são empacotados em contêineres e podem ser implantados, reiniciados e dimensionados separadamente. Fargate elimina a gestão direta de servidores para o pipeline assíncrono. |
| **Amazon RDS PostgreSQL 16** | Mantém as camadas `bronze`, `silver`, `gold`, `etl`, `detect` e o relógio `sim.now()`; expõe as views `v_*` para leitura. | Um banco relacional único preserva transações, constraints e consultas analíticas do MVP, reduzindo a complexidade operacional. O acesso privado na porta 5432 e o usuário de leitura com menor privilégio limitam a superfície de exposição. |
| **Application Load Balancer + Auto Scaling Group de EC2** | O ALB recebe consultas do dashboard, verifica `/health/live` e distribui as conexões para instâncias que executam a API Flask com gunicorn. | O ALB fornece endereço estável e retira targets não saudáveis. O ASG mantém capacidade mínima em duas zonas e escala pela quantidade de requisições por target, métrica mais representativa para uma API limitada por espera de banco do que somente CPU. |
| **VPC, sub-redes e gateways** | Separa ALB, NAT e bastion nas sub-redes públicas; workloads e banco permanecem nas sub-redes privadas de duas zonas de disponibilidade. | A separação adiciona defesa em profundidade: workloads não possuem rota direta de entrada pela internet. O NAT fornece saída controlada e o Internet Gateway atende apenas aos recursos públicos. |
| **Bastion Host** | Fornece salto SSH administrativo para os recursos privados a partir de um CIDR autorizado. | Evita abrir SSH nas instâncias da aplicação ou no banco para toda a internet e concentra o acesso operacional em um ponto auditável. |
| **Amazon S3** | O bucket `origem` armazena Parquet e manifesto da carga; o bucket `frontend` publica o export estático do Next.js; o bucket de logs recebe access logs do ALB. | S3 é adequado para objetos imutáveis e publicação estática, tem alta durabilidade e reduz a necessidade de servidores dedicados para arquivos, site e evidências operacionais. |
| **Amazon ECR** | Armazena as quatro imagens (`worker`, `simulator`, `processing` e `loader`) identificadas pelo SHA do commit. | Tags imutáveis tornam o deploy rastreável e permitem rollback para uma versão conhecida, sem a ambiguidade de `latest`. |
| **CloudWatch + SNS** | Centraliza logs, métricas, VPC Flow Logs e alarmes; o SNS encaminha notificações operacionais. | Reúne observabilidade de aplicação, rede e infraestrutura no mesmo plano operacional e permite detectar indisponibilidade, backlog, erro de API e pressão no banco. |
| **IAM + Secrets Manager** | IAM define papéis e políticas; Secrets Manager protege hashes de tokens e credenciais utilizadas pelos serviços. | Separa autorização de infraestrutura dos segredos de runtime. No Learner Lab, a `LabRole` é uma restrição do ambiente e deve ser substituída por papéis de privilégio mínimo em uma conta sem essa limitação. |
| **Kubernetes** |  |  |


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

