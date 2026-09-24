# Conteinerização e orquestração

&emsp; Este artefato descreve a aplicação Argus sob o recorte da Sprint 4: arquitetura
distribuída, conteinerização, orquestração e mecanismos de resiliência frente a falhas.
Ele documenta uma decisão específica: **onde** o Kubernetes entra no sistema. O texto
sustenta com a evidência colhida em cluster de verdade.

&emsp; A conclusão, adiantada: o Kubernetes orquestra o **caminho síncrono** (dashboard,
API de leitura e a aplicação de migrations); o **ECS Fargate continua intocado** no
caminho assíncrono (ingestão por SQS, ETL, simulação e carga inicial). Isso não é
migração pela metade. É escolha de plataforma por característica de carga, e a seção 3
explica por que levar tudo para o cluster seria lateral num caso e
regressão de segurança no outro.

---

## 1. O que muda nesta sprint

&emsp; O projeto já chegou à Sprint 4 quase todo conteinerizado: cinco imagens Docker,
cinco repositórios no ECR e seis cargas em ECS Fargate. O que não existia era
orquestração por Kubernetes, e havia um ponto do sistema onde contêiner era executado
sem orquestrador nenhum.

| Componente | Antes (Sprint 3) | Agora (Sprint 4) |
|---|---|---|
| Dashboard | Export estático no website do S3 | Imagem nginx, `Deployment` no EKS |
| API de leitura | Contêiner iniciado à mão pelo `user_data` de instâncias EC2 num Auto Scaling Group | `Deployment` no EKS, com sondas, HPA, PDB e Ingress |
| Migrations | Task avulsa do ECS | `Job` do Kubernetes, mesma imagem e mesmo comando |
| Workers de ingestão (`merge`, `event`) | ECS Fargate | **ECS Fargate, sem alteração** |
| ETL e motor de hipóteses (`processing`) | ECS Fargate | **ECS Fargate, sem alteração** |
| Simulador e carga inicial (`simulator`, `loader`) | ECS Fargate | **ECS Fargate, sem alteração** |

&emsp; O Auto Scaling Group não foi destruído: foi zerado (`asg_min_size = 0`,
`asg_desired_capacity = 0`). O `launch template`, o target group e as políticas de
escala continuam no estado do Terraform, de modo que voltar atrás é trocar dois valores
no `terraform.tfvars`, e não refazer o provisionamento.

&emsp; Essa reversibilidade cumpriu o seu papel durante a sprint e agora sai de cena: esta
sprint remove o caminho EC2 da Sprint 3
(`infra/asg.tf`, `alb.tf` e `asg_observability.tf`). A leitura pública passa a vir só do
ALB que o Ingress do EKS provisiona; a contingência, com o cluster desligado, é a Lambda
`read_api_url` com o website do S3 (decisão 13 da seção 3.1).

---

## 2. Arquitetura distribuída

&emsp; O Argus tem dois caminhos independentes, acoplados apenas pelo banco. O caminho
**assíncrono** recebe eventos e mudanças por API Gateway, enfileira no SQS e grava no
PostgreSQL pelas camadas bronze, silver e gold. O caminho **síncrono** lê desse mesmo
banco e serve o dashboard. Os dois escalam por razões diferentes, e é essa diferença
que justifica plataformas diferentes.

| Caminho | Gatilho de escala | O que já resolve a elasticidade |
|---|---|---|
| Assíncrono | Profundidade da fila | A própria fila: o SQS absorve a rajada e o consumidor drena no seu ritmo |
| Síncrono | Requisições por segundo, com latência percebida pelo usuário | Nada, antes desta sprint; o ASG levava minutos para repor uma instância |

### 2.1 Componentes no cluster

| Objeto | Imagem | Papel |
|---|---|---|
| `Deployment argus-frontend` | `argus-events-dev-frontend` (nginx + export estático) | Serve o dashboard |
| `Deployment argus-backend` | `argus-events-dev-backend` (Flask + gunicorn) | API de leitura, porta 5000 |
| `Job argus-db-migrate` | `argus-events-dev-processing` | Aplica as 33 migrations e termina |
| `Ingress argus` | Não aplicável | Entrada única: `/` para o dashboard, `/api` e `/health` para a API |
| `HorizontalPodAutoscaler argus-backend` | Não aplicável | 2 a 6 réplicas da API, a 60% de CPU (`backend-hpa.yaml`) |
| `HorizontalPodAutoscaler argus-frontend` | Não aplicável | 2 a 4 réplicas do dashboard, a 70% de CPU (`frontend-hpa.yaml`) |
| `PodDisruptionBudget argus-backend` e `argus-frontend` | Não aplicável | `minAvailable: 1` em cada um: impede que uma consolidação de nó tire todas as réplicas |

### 2.2 Os componentes fora do cluster em execução

&emsp; O vídeo cobre o que roda no Kubernetes. Os quatro componentes que ficaram no
Fargate continuam em execução, e a prova está em comandos que qualquer integrante do
grupo pode repetir com o perfil `g4` (os alvos do `Makefile` exigem `AWS_PROFILE`; o
`count` exige `DATABASE_URL`):

```bash
aws ecs list-tasks --cluster argus-events-dev --desired-status RUNNING --profile g4
# saída esperada: uma task RUNNING por serviço (merge_worker, event_worker, processing)
make -C apps/fullstack logs SERVICO=worker      # também simulator | processing | loader
make -C apps/fullstack count                    # linhas em bronze, silver e gold: o loader e o worker gravaram
make -C apps/fullstack dlq                      # filas de rejeitados; vazias, o worker está drenando
make -C apps/fullstack k8s-status               # pods, HPA, PDB e Ingress do lado do cluster
```

&emsp; A tabela abaixo fecha o inventário: cada imagem, o seu repositório no ECR
(`${name_prefix}-${environment}-<imagem>`, criados por `for_each` em `infra/ecr.tf`),
onde ela executa, com quantas réplicas, para quais arquiteturas é publicada e qual
sonda a vigia. Os valores vêm dos `Dockerfile`, do `Makefile` (`IMAGES` e
`IMAGES_MULTIARCH`), de `infra/variables.tf` e de `k8s/base/`.

| Imagem | Registro ECR | Onde roda | Réplicas | Plataformas | Sonda |
|---|---|---|---|---|---|
| `worker` | `argus-events-dev-worker` | ECS Fargate: serviços `merge_worker` e `event_worker` | 1 task cada (`worker_desired_count`) | `arm64` (`worker_cpu_architecture = "ARM64"`) | `HEALTHCHECK` por arquivo de batimento |
| `simulator` | `argus-events-dev-simulator` | ECS Fargate: serviço `simulator` | 0 ou 1 (`simulator_desired_count`; dois relógios virtuais brigariam pelo mesmo `sim.clock`) | `arm64` | `HEALTHCHECK` por arquivo de batimento |
| `processing` | `argus-events-dev-processing` | ECS Fargate: serviço `processing` (ETL e motor de hipóteses); EKS: `Job argus-db-migrate` | 1 task (`processing_desired_count`); o `Job` roda uma vez, com `backoffLimit: 2` | `arm64` + `amd64` | `HEALTHCHECK` por arquivo de batimento; no `Job`, a conclusão em `1/1` é a sonda |
| `loader` | `argus-events-dev-loader` | ECS Fargate: task avulsa disparada por `make load` | 0 em repouso; uma task enquanto carrega | `arm64` | Nenhuma, de propósito: a carga termina |
| `backend` | `argus-events-dev-backend` | EKS: `Deployment argus-backend` | 2, com HPA de 2 a 6 | `arm64` + `amd64` | `HEALTHCHECK` em `/health/live`; sondas de partida e de vida em `/health/live`, de prontidão em `/health/ready` |
| `frontend` | `argus-events-dev-frontend` | EKS: `Deployment argus-frontend` | 2, com HPA de 2 a 4 | `arm64` + `amd64` | `HEALTHCHECK` em `/healthz`; as três sondas em `/healthz` |

---

## 3. A decisão: por que o Kubernetes não cobre tudo

&emsp; A pergunta que orientou o desenho não foi "como levar a aplicação para o
Kubernetes", e sim "onde o Kubernetes conserta um problema real".

**No caminho assíncrono, ele não conserta nada.** O ECS Fargate já entrega estado
desejado declarativo, verificação de saúde, implantação gradual e escala automática.
Mover os workers para lá do cluster seria trocar de ferramenta sem trocar de
capacidade e, num ponto, seria piorar: o AWS Academy Learner Lab nega
`iam:CreateRole`, `iam:AttachRolePolicy` e `iam:CreateOpenIDConnectProvider`, o que
torna **IRSA e EKS Pod Identity impossíveis**. Os workers precisam de SQS; para lhes dar
credencial no cluster seria preciso conceder permissão ampla ao nó inteiro, trocando o
papel por task, granular, por um papel compartilhado por todos os pods daquele nó.

**No caminho síncrono, ele conserta bastante.** Até a Sprint 3 a API rodava assim, no
`infra/templates/user_data.sh.tftpl` de cada instância do ASG:

```bash
dnf install docker  →  docker pull  →  docker run -p 5000:5000
```

&emsp; Isso é orquestração de contêiner feita à mão numa máquina virtual. Não há
implantação gradual: publicar uma versão nova significa substituir instâncias. Não há
reposição do contêiner por saúde, apenas o target group derrubando a instância inteira.
E o `health_check_grace_period = 300s` existe justamente para cobrir o tempo de boot,
instalação e download da imagem.

&emsp; Há ainda um efeito de desenho: como o dashboard vinha do S3 e a API do
balanceador, eram **duas origens**, com lista de CORS para manter em dia e uma URL de
API compilada dentro do bundle. Um Ingress único elimina as duas coisas de uma vez
(seção 4).

### 3.1 Tabela de decisões

| # | Decisão | Alternativa descartada | Atributo de qualidade | Falha prevista e mitigação | Custo | Como reverter |
|---|---|---|---|---|---|---|
| 1 | Kubernetes só no caminho síncrono | Levar `merge`, `event` e `processing` também | Adequação: cada carga na plataforma que resolve o problema dela | Duas plataformas a operar; mitigado por observabilidade comum no CloudWatch | Não aplicável | Escrever `Deployment` para os workers; a imagem já serve |
| 2 | EKS em **Auto Mode** | Cluster com node group gerenciado + AWS Load Balancer Controller por Helm | Viabilidade: o controlador por Helm exige IRSA, bloqueado no lab | Sobretaxa de gerenciamento por hora de nó | Sobretaxa do Auto Mode | `compute_config.enabled = false` e um node group clássico |
| 3 | Cluster na VPC do Argus, não na default | Reusar o cluster de laboratório já existente | Segurança: o RDS é privado e só é alcançável de dentro da VPC | Depende de `create_network = true` | Não aplicável | `create_eks = false` |
| 4 | Nós com o papel `LabEksNodeRole` mínimo | `LabRole`, que traz SQS, S3 e Secrets Manager | Menor privilégio | Nenhuma: nenhum pod deste cluster fala com a AWS | Não aplicável | Trocar `node_role_arn` |
| 5 | ASG zerado, não destruído | Remover `asg.tf` e `alb.tf` | Reversibilidade durante a sprint | Recurso ocioso no estado | Nenhum, com capacidade zero | Dois valores no `terraform.tfvars` |
| 6 | Ingress único com origem única | Um `Service` do tipo `LoadBalancer` por aplicação | Simplicidade: elimina CORS e desacopla a imagem do ambiente | Uma regra de roteamento errada afeta os dois serviços | Um balanceador em vez de dois | Separar em dois `Ingress` |
| 7 | Sonda de vida em `/health/live` | `/health/ready`, que consulta o banco | Disponibilidade | Uma queda do RDS mataria **todos** os pods ao mesmo tempo | Não aplicável | Trocar o `path` da sonda |
| 8 | Sem limite de CPU nos contêineres | `limits.cpu` declarado | Latência previsível | Cota CFS provoca estrangulamento em rajada, invisível nas métricas usuais | Nó pode precisar ser maior | Acrescentar `limits.cpu` |
| 9 | Escala por CPU | Requisições por alvo, como fazia o ASG | Métrica nativa de `metrics.k8s.io`, sem adaptador externo; no EKS do laboratório ela exige o add-on `metrics-server` (5.5) | A métrica não é a mesma do ASG; a comparação entre plataformas precisa dizer isso. Sem o `metrics-server` o HPA fica em `<unknown>`, como aconteceu em 21/09 | Não aplicável | KEDA, ou o adaptador de métricas externas |
| 10 | Imagens multi-arquitetura para as três que rodam no cluster (`backend`, `frontend` e `processing`) | Somente `arm64`, como as três que só rodam no Fargate | Compatibilidade: as node pools padrão do Auto Mode são `amd64` | `CrashLoopBackOff` com `exec format error` | ~2 min a mais no build | Node pool customizada `arm64` |
| 11 | `topologySpreadConstraints` com `ScheduleAnyway` | `DoNotSchedule` | Velocidade de implantação | Distribuição entre zonas deixa de ser garantida | Não aplicável | Trocar para `DoNotSchedule` quando houver nó quente |
| 12 | Segredo montado por `kubectl` a partir do Terraform | Provider `kubernetes` no Terraform, ou arquivo `.env` | Segurança: o valor não toca disco, repositório nem estado | Exige `rollout restart` após rotação; automatizado no alvo do Makefile | Não aplicável | Operador de segredos externos, se houver IRSA |
| 13 | Remover o caminho EC2 da Sprint 3 (`asg.tf`, `alb.tf`, `asg_observability.tf`), substituindo a decisão 5 | Manter o ASG zerado no estado | Simplicidade e custo: o Auto Mode cria o ALB pelo Ingress; dois balanceadores custavam em dobro e confundiam qual era a origem pública | A volta atrás deixa de ser dois valores no `tfvars`; a contingência passa a ser a Lambda `read_api_url` com o website do S3 | Nenhum: um balanceador a menos | Reverter a branch `refactor/remove-caminho-ec2-sprint3` |

---

## 4. Uma origem só

&emsp; Um único `Ingress` atende os dois serviços:

```
/        →  argus-frontend  (nginx com o export estático do Next)
/api     →  argus-backend   (Flask; o blueprint já vive em /api/v1)
/health  →  argus-backend   (conveniência de verificação)
```

&emsp; A imagem do dashboard é construída com `NEXT_PUBLIC_API_URL=/`. O cliente monta a
requisição como `fetch(`${API_URL.replace(/\/$/, "")}${path}`)`, e `path` já começa com
`/api/v1`, então a chamada sai **relativa**. Não pode ser string vazia: o cliente a
rejeita de propósito, para que uma configuração faltando falhe alto em vez de gerar
requisições para a própria página.

&emsp; O ganho é maior do que parece:

1. O navegador nunca emite requisição de verificação prévia, e **o CORS deixa de ser
   parâmetro operacional**.
2. A imagem **deixa de depender do endereço do ambiente**. A mesma tag roda no cluster
   local e no EKS, o que importa num laboratório onde o endereço do balanceador muda a
   cada sessão.
3. Não há reescrita de caminho: o prefixo chega intacto ao Flask.

&emsp; A ordem das regras no `Ingress` não é cosmética. O controlador as emite na ordem
declarada; com `/` antes de `/api`, ele casaria tudo e a API nunca receberia requisição.

---

## 5. Resiliência frente a falhas

### 5.1 Três sondas, três problemas distintos

&emsp; Trocá-las de lugar tem consequência concreta, e é por isso que elas não são
intercambiáveis:

| Sonda | Alvo | O que aconteceria se estivesse trocada |
|---|---|---|
| `startupProbe` | `/health/live` | Sem ela, a sonda de vida contaria falha durante o boot e reiniciaria o pod em laço |
| `livenessProbe` | `/health/live`, que não toca no banco | Em `/health/ready`, uma indisponibilidade do RDS **mataria todos os pods ao mesmo tempo**, transformando falha de banco em falha de aplicação |
| `readinessProbe` | `/health/ready`, que consulta o banco | Em `/health/live`, o pod receberia tráfego sem banco e responderia erro 500 ao usuário |

&emsp; Essa separação foi observada em operação. Com o banco de pé mas sem as migrations
aplicadas, o registro do contêiner mostrou exatamente o comportamento projetado:

```
route "/health/live"   status 200   ← a sonda de vida passa: o processo está sadio
route "/health/ready"  status 503   ← a de prontidão falha: relation "silver.v_session_event" does not exist
```

&emsp; O pod ficou fora do balanceamento, **sem ser reiniciado**, até o `Job` de
migrations concluir, quando voltou sozinho.

### 5.2 Implantação sem queda

&emsp; `maxUnavailable: 0` com `maxSurge: 1` garante que o pod novo esteja pronto antes
de o antigo sair. O `preStop` de 10 segundos cobre a propagação do descadastramento no
balanceador; sem ele, cada implantação produz um punhado de erros 502.

&emsp; Medição feita durante um `rollout restart`, com requisições a cada 200 ms contra
`/api/v1/clock` pelo Ingress:

```
# saída esperada: nenhuma falha
RESULTADO: 547 respostas 200, 0 falhas
```

&emsp; *Os números acima são a saída esperada do ensaio, não uma medição. A medição, com
`rollout restart` sob carga do k6 no cluster kind, será gravada em
`evidencias/resiliencia-kind-*.txt` e
substituirá este bloco.*

### 5.3 Autocura

&emsp; Remoção forçada de um pod da API, cronometrada até a condição `Ready`:

```
# saída esperada: recuperação em poucos segundos
recuperado em 4s
```

&emsp; *Também aqui o valor é a saída esperada; a medição do `kubectl delete pod` e da
queda do Postgres no kind entra em `evidencias/resiliencia-kind-*.txt`.*

&emsp; O ASG levava até **300 segundos** para repor uma instância, o valor do
`health_check_grace_period`, dimensionado para cobrir boot, `dnf install` e `docker
pull`. São duas ordens de grandeza de diferença, e vêm do mesmo fato: o Kubernetes
reagenda um processo, enquanto o ASG precisa construir uma máquina.

### 5.4 Interrupção voluntária

&emsp; O `PodDisruptionBudget` com `minAvailable: 1` não é decoração. O Auto Mode
consolida nós de forma agressiva para reduzir custo, e esvazia o nó escolhido sem
cerimônia. Sem esse objeto, ele pode tirar todas as réplicas da API ao mesmo tempo
durante uma operação que deveria ser invisível.

### 5.5 Escala automática: a métrica não veio de graça

&emsp; O HPA escala por CPU (decisão 9) e depende da API `metrics.k8s.io`, servida pelo
`metrics-server`. A premissa de que o EKS Auto Mode já a traria, registrada no alvo
`k8s-bootstrap` do `Makefile`, **não se confirmou no cluster do laboratório**: nas
rodadas de carga de 21/09 os dois HPAs ficaram em `cpu: <unknown>` durante os 36 minutos
do ensaio, com o evento `FailedGetResourceMetric ... the server could not find the
requested resource (get pods.metrics.k8s.io)`, e o `APIService v1beta1.metrics.k8s.io`
não existia no cluster
([`evidencias/carga-kubernetes.txt`](evidencias/carga-kubernetes.txt), linhas 17–23).
As réplicas ficaram no mínimo de 2, e a rodada B, de saturação, registrou dois reinícios
por pod do backend com o HPA sem poder reagir.

&emsp; A correção é declarativa: a partir desta sprint o add-on `metrics-server` é
declarado como `aws_eks_addon` em `infra/eks.tf`, de
modo que o cluster nasce com a métrica. No ambiente local o `kind-up` já instalava o
`metrics-server` v0.8.0, razão pela qual o HPA do kind reporta CPU
([`evidencias/testes-kubernetes.txt`](evidencias/testes-kubernetes.txt) mostra
`cpu: 20%/60%` e `117%/70%`).

---

## 6. Conteinerização

### 6.1 As seis imagens

| Imagem | Base | Padrão |
|---|---|---|
| `worker`, `simulator`, `processing` | `uv` + `python:3.12-slim` | Multi-estágio, usuário sem privilégio uid 10001, `HEALTHCHECK` por arquivo de batimento |
| `loader` | `uv` + `python:3.12-slim` | Mesmo padrão, **sem `HEALTHCHECK`**, de propósito: a carga é one-shot e termina, e uma sonda marcaria o encerramento normal como falha |
| `backend` | `uv` + `python:3.12-slim` | Multi-estágio, usuário sem privilégio, `HEALTHCHECK` em `/health/live` |
| `frontend` | `node:20` + `nginx:1.27-alpine` | Multi-estágio, usuário sem privilégio uid 101, `HEALTHCHECK` em `/healthz` |

&emsp; Todas as bases são fixadas por resumo criptográfico (`@sha256:`), e não por tag:
uma tag pode passar a apontar para outra imagem sem que arquivo nenhum do repositório
mude. Cada contexto de build tem seu próprio `.dockerignore`, o de `apps/fullstack/`
cobre os quatro serviços que compartilham `common/`; `backend/` e `frontend/` têm os
seus, porque constroem a partir da própria pasta.

&emsp; Os contêineres rodam com `readOnlyRootFilesystem: true`,
`allowPrivilegeEscalation: false` e todas as capacidades descartadas. O `nginx.conf` do
dashboard aponta o arquivo de processo e os diretórios temporários para `/tmp`
justamente para tornar isso possível: um nginx que não consegue gravar o próprio `pid`
nem chega a escutar na porta.

### 6.2 Multi-arquitetura

&emsp; As node pools padrão do Auto Mode são `amd64`; as máquinas do time e o Fargate
são `arm64`. As três imagens que rodam no cluster (`backend`, `frontend` e `processing`,
esta pelo `Job` de migrations, que cai em nós `amd64`) são publicadas para as duas
arquiteturas, numa lista de manifestos: é a variável
`IMAGES_MULTIARCH := backend frontend processing` do `Makefile`. As outras três
(`worker`, `simulator` e `loader`) seguem só em `arm64`, porque só rodam no Fargate.
Publicar só `arm64` coloca o pod em `CrashLoopBackOff` com `exec format error`, a mesma
falha que já apareceu no ASG.

&emsp; Por isso a publicação usa `docker buildx build --push`, e não `docker build`
seguido de `docker push`: uma lista de manifestos só existe no registro, e o `push`
empurraria apenas a arquitetura carregada no daemon local.

---

## 7. Restrições do AWS Academy Learner Lab

&emsp; Verificadas por simulação de política na conta do laboratório, e não assumidas:

| Ação | Resultado | Consequência no desenho |
|---|---|---|
| `eks:CreateCluster`, `eks:CreateNodegroup` | Permitido | O cluster pode ser criado pelo Terraform |
| `iam:PassRole` sobre `LabEksClusterRole` e `LabEksNodeRole` | Permitido | Os papéis do laboratório podem ser usados |
| `iam:ListRoles` | Permitido | Os papéis são descobertos por expressão regular, sem fixar o prefixo de sessão |
| `iam:CreateRole`, `iam:AttachRolePolicy` | **Negado** | Nenhum papel novo; os do laboratório são reusados |
| `iam:CreateOpenIDConnectProvider` | **Negado** | **IRSA impossível** |
| `eks-auth:AssumeRoleForPodIdentity` | **Negado** | **Pod Identity impossível** |

&emsp; As duas últimas linhas são o que fundamenta a decisão 1 da seção 3.1. Numa conta
comum, os workers no cluster receberiam um papel por conta de serviço, e a discussão
seria outra.

&emsp; O nome dos papéis carrega um prefixo que muda a cada sessão do laboratório, e a
própria conta rotaciona. Nada é fixado: o Terraform descobre os papéis por expressão
regular e o endereço do registro entra por substituição no momento da aplicação, lido
do estado.

### 7.1 Descoberta: por que o EKS é viável no Learner Lab

&emsp; A afirmação de que o EKS não funciona no Learner Lab decorre dos fluxos padrão
de criação, e não de uma indisponibilidade do serviço. Tanto o `eksctl create cluster`
quanto o fluxo usual do console tentam criar o papel do cluster e, em seguida, criar o
provedor OpenID Connect para usar IRSA com o AWS Load Balancer Controller. Essas etapas
dependem de `iam:CreateRole` e `iam:CreateOpenIDConnectProvider`, ações negadas pelo
laboratório.

&emsp; A investigação, conduzida por integrante do grupo com apoio de IA, identificou
que a conta do laboratório já disponibiliza os papéis `LabEksClusterRole` e
`LabEksNodeRole`. O arquivo `infra/eks.tf` não fixa os nomes, pois o prefixo da sessão
muda a cada laboratório. Em vez disso, consulta os papéis por expressão regular e usa
os ARNs encontrados no cluster e nos nós, por meio das permissões já liberadas de
`iam:ListRoles` e `iam:PassRole`.

&emsp; O segundo desvio é o EKS Auto Mode. Com o balanceamento elástico habilitado no
cluster, a própria AWS provisiona o ALB a partir do `Ingress` usando o papel do cluster.
Não foi necessário instalar o AWS Load Balancer Controller por Helm, criar uma conta de
serviço com IRSA ou conceder permissões adicionais aos nós. Como o caminho síncrono não
acessa SQS, S3 nem Secrets Manager diretamente, o `LabEksNodeRole` mínimo permanece
suficiente e preserva o princípio do menor privilégio.

&emsp; Essa combinação foi validada no ambiente do grupo: o `terraform apply` criou o
cluster em aproximadamente 12 minutos, sem qualquer negação de permissão. Portanto, a
restrição do Learner Lab impede o caminho convencional de instalação, mas não impede um
cluster EKS Auto Mode quando os papéis preexistentes são reutilizados e o ALB é delegado
ao serviço gerenciado.

---

## 8. Como executar

&emsp; O runbook completo está em [`apps/fullstack/k8s/README.md`](../apps/fullstack/k8s/README.md).

**Local, sem credencial da AWS:**

```bash
make -C apps/fullstack kind-up
make -C apps/fullstack k8s-images kind-load
make -C apps/fullstack k8s-apply   K8S_OVERLAY=kind
make -C apps/fullstack k8s-migrate K8S_OVERLAY=kind
# saída esperada: dashboard em http://localhost:8080/ e API em /api/v1/clock,
# na mesma origem
```

**Na AWS:**

```bash
aws rds start-db-instance --db-instance-identifier argus-events-dev --profile g4
make -C apps/fullstack tf-apply            # create_eks = true no terraform.tfvars
make -C apps/fullstack k8s-kubeconfig k8s-bootstrap
make -C apps/fullstack k8s-push k8s-secret k8s-migrate k8s-apply
make -C apps/fullstack k8s-url
```

&emsp; O alvo `make check` passou a incluir `k8s-validate`, que renderiza as cinco
kustomizations (`base`, `migrate`, `overlays/aws`, `overlays/kind` e
`overlays/kind/migrate`; saída em
[`evidencias/k8s-validate.txt`](evidencias/k8s-validate.txt)) sem tocar em cluster
nenhum e, em seguida, roda o verificador `verifica_manifests.py` para as invariantes que
o kustomize não alcança: ordem das regras do Ingress, arquitetura das imagens e chaves
do Secret. É o portão que impede um erro de YAML de chegar à entrega.

---

## 9. Custo e desligamento

&emsp; O cluster cobra por hora existindo, somado ao balanceador. Ao fim de cada sessão
de trabalho:

```bash
make -C apps/fullstack k8s-scale-zero   # sem pod pendente, os nós são consolidados até zero
make -C apps/fullstack k8s-delete       # remove o namespace e, com ele, o balanceador
```

&emsp; Para derrubar o cluster inteiro, `create_eks = false` e `make tf-apply`. ECS e
RDS não referenciam nada dele e continuam de pé; o balanceador e o ASG da Sprint 3, o
mesmo, até a remoção descrita na decisão 13. É, também, a demonstração prática
da decisão 5.

---

## 10. Vídeo

&emsp; O vídeo percorre os três itens avaliados, na ordem da rubrica. A tabela serve de
índice: a primeira coluna dá o instante, a segunda diz o que aparece na tela e a
terceira aponta a seção deste artefato que aquele trecho sustenta.

**Link:** [Vídeo no Drive](https://drive.google.com/file/d/1XFad3iP95uWSyXMZs26mPbUz7NWT7i-4/view?usp=sharing)

| Tempo | O que o vídeo mostra | Evidência na tela |
|---|---|---|
| 0:00–0:30 | Apresentação do grupo e do recorte da sprint | Não aplicável |
| 0:30–1:40 | **Código em contêiner**: os seis `Dockerfile`, o multi-estágio, o usuário sem privilégio e a base fixada por resumo | `USER argus` uid 10001 e `USER nginx` uid 101; `HEALTHCHECK` em cinco das seis imagens, pois o `loader` é one-shot e termina; `@sha256:` nas bases (6.1) |
| 1:40–2:30 | O build multi-arquitetura e a lista de manifestos no ECR | `docker buildx build --platform linux/amd64,linux/arm64`; `docker manifest inspect` listando as duas arquiteturas (6.2) |
| 2:30–3:30 | **Kubernetes**: o cluster no console, os nós e os objetos aplicados | `kubectl get nodes`; `kubectl -n argus get pods,svc,ingress,hpa,pdb` (2.1) |
| 3:30–4:10 | O Ingress de origem única | O dashboard em `/` e o relógio virtual em `/api/v1/clock`, no mesmo endereço, sem CORS (4) |
| 4:10–4:40 | O `Job` de migrations | `kubectl get job` em `1/1`; as migrations aplicadas no registro do contêiner (33 em `db/migrations` na data desta entrega) (2.1) |
| 4:40–5:30 | **Resiliência: autocura**. Remoção de um pod da API | Pod reagendado e `Ready` em segundos, contra os 300 s do ASG (5.3) |
| 5:30–6:30 | **Resiliência: implantação sem queda sob carga** | `rollout restart` com o teste de carga rodando; zero erro no relatório (5.2) |
| 6:30–6:50 | Escala automática | `kubectl get hpa -w` com as réplicas subindo e descendo (3.1, decisão 9). Requer o `metrics-server`, instalado pelo `kind-up` no ambiente local e, a partir desta sprint, pelo add-on no EKS; no cluster do laboratório de 21/09 a métrica ainda não existia (5.5) |
| 6:50–7:00 | Encerramento | Não aplicável |

---

## 11. Evidências

&emsp; As saídas brutas dos ensaios ficam em [`evidencias/`](evidencias/), com URLs e
identificadores de conta substituídos. Cada arquivo diz a data, o ambiente e o comando
que o produziu.

| Arquivo | O que registra | Sustenta |
|---|---|---|
| [`evidencias/carga-kubernetes.txt`](evidencias/carga-kubernetes.txt) | Rodadas A (5, 25 e 100 usuários) e B (200, 450 e 900) de carga contra o Ingress do EKS real, em 21/09: cluster Auto Mode 1.33, nós `amd64`, estado final dos objetos e o diagnóstico do HPA sem métrica | 2.1, 5.5, 6.2 |
| [`evidencias/carga-kubernetes/`](evidencias/carga-kubernetes/) | Os arquivos de cada rodada: `rodada-{a,b}-saida-k6.txt`, `-summary-k6.json`, `-resultado.json` e `-instancia.log` | 5.5 |
| [`evidencias/testes-kubernetes.txt`](evidencias/testes-kubernetes.txt) | TI-01 e a suíte e2e (12 testes, todos aprovados) contra o caminho orquestrado no cluster kind local, em 21/09, pela origem única do Ingress | 4, 5.1 |
| [`evidencias/k8s-validate.txt`](evidencias/k8s-validate.txt) | `make k8s-validate` renderizando as cinco kustomizations sem tocar em cluster | 8 |
| `evidencias/resiliencia-kind-*.txt` | Ensaios de autocura (`kubectl delete pod`), implantação sob carga (`rollout restart` com k6) e queda do Postgres no kind; serão gravados nesta sprint e substituirão as saídas esperadas de 5.2 e 5.3 | 5.2, 5.3 |

---

## Apêndice A: Mapa de arquivos

| Arquivo | Papel |
|---|---|
| `apps/fullstack/infra/eks.tf` | Cluster Auto Mode, descoberta dos papéis do laboratório, entradas de acesso |
| `apps/fullstack/infra/vpc.tf` | Etiquetas `kubernetes.io/role/*`, sem as quais o balanceador não é provisionado |
| `apps/fullstack/infra/rds.tf` | Regra que autoriza os pods a alcançar o banco |
| `apps/fullstack/k8s/base/` | `Deployment`, `Service`, `HPA`, `PDB`, `Ingress` e `ConfigMap` |
| `apps/fullstack/k8s/migrate/` | `Job` de migrations, aplicado à parte porque o modelo de um `Job` é imutável |
| `apps/fullstack/k8s/overlays/aws/` | Classe de Ingress do balanceador e anotações |
| `apps/fullstack/k8s/overlays/kind/` | Banco local, ingress-nginx, uma réplica por carga |
| `apps/fullstack/frontend/Dockerfile` | Imagem do dashboard |
| `apps/fullstack/frontend/nginx.conf` | Servidor do export estático, preparado para raiz somente-leitura |
| `apps/fullstack/Makefile` | Alvos `k8s-*` e `kind-*`; `IMAGES` e `IMAGES_MULTIARCH` |
| `artefatos/evidencias/` | Saídas brutas dos ensaios (seção 11) |
