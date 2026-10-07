# Conteinerização e orquestração

&emsp; Este artefato descreve a aplicação Linceu do ponto de vista da arquitetura distribuída, da conteinerização, da orquestração e dos mecanismos de resiliência frente a falhas. O ponto central é uma decisão de projeto: onde o Kubernetes entra no sistema. O texto sustenta cada afirmação com evidência colhida em cluster real.

&emsp; A conclusão, adiantada, é a seguinte. O Kubernetes orquestra o caminho síncrono, formado pelo dashboard, pela API de leitura e pela aplicação das migrations. O ECS Fargate permanece responsável pelo caminho assíncrono, formado pela ingestão por SQS, pelo ETL, pela simulação e pela carga inicial. Cada carga executa na plataforma que resolve o problema dela, e a seção 3 explica por que levar tudo para o cluster seria neutro em um caso e uma regressão de segurança no outro.

---

## 1. Componentes e onde executam

&emsp; A aplicação é formada por seis imagens Docker, publicadas em seis repositórios no ECR. Três delas executam no cluster Kubernetes e as outras três, somadas ao simulador e ao loader, executam no ECS Fargate. O quadro abaixo resume cada componente e a plataforma que o orquestra.

| Componente | Plataforma | Orquestração |
|---|---|---|
| Dashboard | EKS | Imagem nginx servida por um `Deployment`, com sondas, HPA e PDB |
| API de leitura | EKS | `Deployment` com sondas, HPA, PDB e entrada pelo Ingress |
| Migrations | EKS | `Job` do Kubernetes, com a mesma imagem e o mesmo comando do processamento |
| Workers de ingestão (`merge`, `event`) | ECS Fargate | Serviços com estado desejado declarativo |
| ETL e motor de hipóteses (`processing`) | ECS Fargate | Serviço com estado desejado declarativo |
| Simulador e carga inicial (`simulator`, `loader`) | ECS Fargate | Serviço e task avulsa |

&emsp; A leitura pública chega pelo ALB que o EKS Auto Mode provisiona a partir do Ingress (`k8s/overlays/aws/ingress-patch.yaml`). Com o cluster desligado, a contingência é a Lambda `read_api_url` servindo o website do S3.

---

## 2. Arquitetura distribuída

&emsp; O Linceu tem dois caminhos independentes, acoplados apenas pelo banco. O caminho assíncrono recebe eventos e mudanças por API Gateway, enfileira no SQS e grava no PostgreSQL pelas camadas bronze, silver e gold. O caminho síncrono lê desse mesmo banco e serve o dashboard. Os dois escalam por razões diferentes, e essa diferença justifica plataformas diferentes.

| Caminho | Gatilho de escala | O que resolve a elasticidade |
|---|---|---|
| Assíncrono | Profundidade da fila | A própria fila: o SQS absorve a rajada e o consumidor drena no seu ritmo |
| Síncrono | Requisições por segundo, com latência percebida pelo usuário | A orquestração do cluster, que repõe e escala réplicas em segundos |

### 2.1 Componentes no cluster

| Objeto | Imagem | Papel |
|---|---|---|
| `Deployment argus-frontend` | `argus-events-dev-frontend` (nginx + export estático) | Serve o dashboard |
| `Deployment argus-backend` | `argus-events-dev-backend` (Flask + gunicorn) | API de leitura, porta 5000 |
| `Job argus-db-migrate` | `argus-events-dev-processing` | Aplica as 33 migrations e termina |
| `Job argus-db-reader` | `argus-events-dev-processing` | Cria ou atualiza o login somente-leitura `argus_api` que o backend usa (`migrate.py criar-leitor`); `make k8s-migrate` o executa depois do `Job` de migrations, porque o `GRANT` depende do papel criado na migration 001 |
| `Ingress argus` | Não aplicável | Entrada única: `/` para o dashboard, `/api` e `/health` para a API |
| `HorizontalPodAutoscaler argus-backend` | Não aplicável | 2 a 6 réplicas da API, a 60% de CPU (`backend-hpa.yaml`) |
| `HorizontalPodAutoscaler argus-frontend` | Não aplicável | 2 a 4 réplicas do dashboard, a 70% de CPU (`frontend-hpa.yaml`) |
| `PodDisruptionBudget argus-backend` e `argus-frontend` | Não aplicável | `minAvailable: 1` em cada um: impede que uma consolidação de nó retire todas as réplicas |

### 2.2 Os componentes fora do cluster em execução

&emsp; Os quatro componentes que executam no Fargate permanecem em operação, e a prova está em comandos que qualquer integrante do grupo pode repetir com o perfil `g4`. Os alvos do `Makefile` exigem `AWS_PROFILE`, e o alvo `count` exige `DATABASE_URL`.

```bash
aws ecs list-tasks --cluster argus-events-dev --desired-status RUNNING --profile g4
# saída esperada: uma task RUNNING por serviço (merge_worker, event_worker, processing)
make -C apps/fullstack logs SERVICO=worker      # também simulator | processing | loader
make -C apps/fullstack count                    # linhas em bronze, silver e gold: o loader e o worker gravaram
make -C apps/fullstack dlq                       # filas de rejeitados; vazias, o worker está drenando
make -C apps/fullstack k8s-status                # pods, HPA, PDB e Ingress do lado do cluster
```

&emsp; A tabela a seguir fecha o inventário. Para cada imagem, ela traz o repositório no ECR (`${name_prefix}-${environment}-<imagem>`, criados por `for_each` em `infra/ecr.tf`), onde executa, com quantas réplicas, para quais arquiteturas é publicada e qual sonda a acompanha. Os valores vêm dos `Dockerfile`, do `Makefile` (`IMAGES` e `IMAGES_MULTIARCH`), de `infra/variables.tf` e de `k8s/base/`.

| Imagem | Registro ECR | Onde executa | Réplicas | Plataformas | Sonda |
|---|---|---|---|---|---|
| `worker` | `argus-events-dev-worker` | ECS Fargate: serviços `merge_worker` e `event_worker` | 1 task cada (`worker_desired_count`) | `arm64` (`worker_cpu_architecture = "ARM64"`) | `HEALTHCHECK` por arquivo de batimento |
| `simulator` | `argus-events-dev-simulator` | ECS Fargate: serviço `simulator` | 0 ou 1 (`simulator_desired_count`; dois relógios virtuais disputariam o mesmo `sim.clock`) | `arm64` | `HEALTHCHECK` por arquivo de batimento |
| `processing` | `argus-events-dev-processing` | ECS Fargate: serviço `processing` (ETL e motor de hipóteses); EKS: `Job argus-db-migrate` e `Job argus-db-reader` | 1 task (`processing_desired_count`); cada `Job` executa uma vez, com `backoffLimit: 2` | `arm64` + `amd64` | `HEALTHCHECK` por arquivo de batimento; no `Job`, a conclusão em `1/1` é a sonda |
| `loader` | `argus-events-dev-loader` | ECS Fargate: task avulsa disparada por `make load` | 0 em repouso; uma task enquanto carrega | `arm64` | Carga finita, sem sonda contínua |
| `backend` | `argus-events-dev-backend` | EKS: `Deployment argus-backend` | 2, com HPA de 2 a 6 | `arm64` + `amd64` | `HEALTHCHECK` em `/health/live`; sondas de partida e de vida em `/health/live`, de prontidão em `/health/ready` |
| `frontend` | `argus-events-dev-frontend` | EKS: `Deployment argus-frontend` | 2, com HPA de 2 a 4 | `arm64` + `amd64` | `HEALTHCHECK` em `/healthz`; as três sondas em `/healthz` |

---

## 3. Por que o Kubernetes não cobre todo o sistema

&emsp; A pergunta que orientou o desenho foi onde o Kubernetes conserta um problema real, e a resposta é diferente em cada caminho.

&emsp; No caminho assíncrono, o Kubernetes não acrescenta capacidade. O ECS Fargate já entrega estado desejado declarativo, verificação de saúde, implantação gradual e escala automática. Mover os workers para o cluster seria trocar de ferramenta sem ganho, e em um ponto seria uma perda de segurança. O AWS Academy Learner Lab nega `iam:CreateRole`, `iam:AttachRolePolicy` e `iam:CreateOpenIDConnectProvider`, o que torna IRSA e EKS Pod Identity indisponíveis. Os workers precisam de acesso ao SQS; para conceder essa credencial no cluster seria preciso dar permissão ampla ao nó inteiro, trocando o papel granular por task por um papel compartilhado por todos os pods daquele nó.

&emsp; No caminho síncrono, o Kubernetes resolve problemas concretos. A API de leitura executava em cada instância de um Auto Scaling Group, iniciada pelo `user_data`, de forma equivalente ao comando abaixo:

```bash
dnf install docker  →  docker pull  →  docker run -p 5000:5000
```

&emsp; Isso é orquestração de contêiner feita à mão em uma máquina virtual. Não havia implantação gradual, porque publicar uma versão nova significava substituir instâncias. Não havia reposição do contêiner por saúde, apenas o target group derrubando a instância inteira. O `health_check_grace_period` de 300 segundos existia para cobrir o tempo de boot, instalação e download da imagem.

&emsp; Havia ainda um efeito de desenho. Como o dashboard vinha do S3 e a API vinha do balanceador, eram duas origens, com uma lista de CORS para manter em dia e uma URL de API compilada dentro do bundle. Um Ingress único elimina as duas coisas de uma vez, como descreve a seção 4.

### 3.1 Principais decisões

&emsp; A tabela reúne as decisões de plataforma com a justificativa e a forma de reverter cada uma. O detalhamento das restrições de IAM que fundamentam a primeira decisão está na seção 7.

| Decisão | Justificativa | Como reverter |
|---|---|---|
| Kubernetes apenas no caminho síncrono | Cada carga fica na plataforma que resolve o problema dela | Escrever `Deployment` para os workers; a imagem já serve |
| EKS em Auto Mode | O controlador por Helm exigiria IRSA, indisponível no laboratório | `compute_config.enabled = false` e um node group clássico |
| Cluster na VPC do Linceu | O RDS é privado e só é alcançável de dentro da VPC | `create_eks = false` |
| Nós com o papel `LabEksNodeRole` mínimo | Menor privilégio: nenhum pod do cluster fala com a AWS | Trocar `node_role_arn` |
| Ingress único com origem única | Elimina o CORS e desacopla a imagem do ambiente | Separar em dois `Ingress` |
| Sonda de vida em `/health/live` | Uma consulta ao banco mataria todos os pods em uma queda do RDS | Trocar o `path` da sonda |
| Sem limite de CPU nos contêineres | A cota de CPU provoca estrangulamento em rajada | Acrescentar `limits.cpu` |
| Escala por CPU | Métrica nativa de `metrics.k8s.io`, sem adaptador externo | KEDA, ou adaptador de métricas externas |
| Imagens multi-arquitetura para `backend`, `frontend` e `processing` | As node pools padrão do Auto Mode são `amd64` | Node pool customizada `arm64` |
| Segredo montado por `kubectl` a partir do Terraform | O valor não toca disco, repositório nem estado | Operador de segredos externos, quando houver IRSA |

---

## 4. Uma origem só

&emsp; Um único `Ingress` atende os dois serviços:

```
/        →  argus-frontend  (nginx com o export estático do Next)
/api     →  argus-backend   (Flask; o blueprint vive em /api/v1)
/health  →  argus-backend   (conveniência de verificação)
```

&emsp; A imagem do dashboard é construída com `NEXT_PUBLIC_API_URL=/`. O cliente monta a requisição como `fetch(`${API_URL.replace(/\/$/, "")}${path}`)`, e `path` já começa com `/api/v1`, então a chamada sai relativa. O valor não pode ser string vazia: o cliente o rejeita de propósito, para que uma configuração faltando falhe de forma visível em vez de gerar requisições para a própria página.

&emsp; O ganho é maior do que parece. O navegador deixa de emitir a requisição de verificação prévia, e o CORS deixa de ser um parâmetro operacional. A imagem deixa de depender do endereço do ambiente, de modo que a mesma tag executa no cluster local e no EKS, o que importa em um laboratório onde o endereço do balanceador muda a cada sessão. E não há reescrita de caminho, pois o prefixo chega intacto ao Flask.

&emsp; A ordem das regras no `Ingress` é relevante. O controlador as emite na ordem declarada; com `/` antes de `/api`, ele casaria tudo e a API nunca receberia requisição.

---

## 5. Resiliência frente a falhas

### 5.1 Três sondas, três problemas distintos

&emsp; As três sondas têm alvos diferentes porque cada uma protege de um problema diferente. Trocá-las de lugar tem consequência concreta, como mostra a tabela.

| Sonda | Alvo | O que aconteceria se estivesse trocada |
|---|---|---|
| `startupProbe` | `/health/live` | Sem ela, a sonda de vida contaria falha durante o boot e reiniciaria o pod em laço |
| `livenessProbe` | `/health/live`, que não consulta o banco | Em `/health/ready`, uma indisponibilidade do RDS reiniciaria todos os pods ao mesmo tempo, transformando falha de banco em falha de aplicação |
| `readinessProbe` | `/health/ready`, que consulta o banco | Em `/health/live`, o pod receberia tráfego sem banco e responderia erro 500 ao usuário |

&emsp; Essa separação foi observada em operação. Com o banco de pé, mas sem as migrations aplicadas, o registro do contêiner mostrou exatamente o comportamento projetado:

```
route "/health/live"   status 200   ← a sonda de vida passa: o processo está sadio
route "/health/ready"  status 503   ← a de prontidão falha: relation "silver.v_session_event" does not exist
```

&emsp; O pod ficou fora do balanceamento, sem reinício, até o `Job` de migrations concluir, quando voltou sozinho.

### 5.2 Implantação sem queda

&emsp; A combinação de `maxUnavailable: 0` com `maxSurge: 1` garante que o pod novo esteja pronto antes de o antigo sair. O `preStop` de 10 segundos cobre a propagação do descadastramento no balanceador; sem ele, cada implantação produz um punhado de erros 502.

&emsp; A medição foi feita no cluster kind local, com um nó, usando k6 a 5 VUs contra `/api/v1/clock` e `/api/v1/hypotheses` pelo Ingress durante 150 segundos que cobriram um `rollout restart`, um deploy com tag de imagem inexistente e um `rollout undo`.

```
# saída registrada em evidencias/resiliencia-kind-02-rollout-e-undo.txt
rollout restart   : pod novo Ready antes de o antigo sair; rollout status concluído em 60,3 s
                    (inclui o preStop de 10 s e o término gracioso do gunicorn)
deploy defeituoso : set image ...:nao-existe -> pod novo em ImagePullBackOff após 17,1 s,
                    pods antigos seguiram Ready, Ingress respondendo 200, rollout status não conclui
rollout undo      : imagem anterior restaurada, rollout status concluído em 3,0 s
k6 nos 150 s      : 5394 requisições, 5389 respostas 200, 5 falhas (0,09%)
```

&emsp; As cinco falhas foram timeouts de 5 segundos no mesmo instante, durante o `ContainerCreating` do pod novo, com o pod antigo ainda `Ready` e único endpoint do Service. Elas são sintoma de saturação da máquina virtual local, e não de troca de endpoint: o `ContainerCreating` levou 10 segundos e o pod só ficou `Ready` 28 segundos depois de criado. Da entrada do pod novo até o fim do ensaio, inclusive na saída do antigo, no deploy defeituoso e no `undo`, não houve falhas. Durante o ensaio o HPA subiu o Deployment de uma para duas réplicas, porque a CPU passou de 60% da `request` de 100m sob a carga, que é o comportamento esperado e não altera a leitura. No EKS essa medição ainda não foi repetida.

### 5.3 Autocura

&emsp; A autocura foi medida pela remoção forçada de um pod da API, cronometrada até a condição `Ready`, no cluster kind local, com k6 a 5 VUs contra `/api/v1/clock` e `/api/v1/hypotheses` pelo Ingress durante toda a troca.

```
# saída registrada em evidencias/resiliencia-kind-01-autocura.txt
1 réplica (padrão do overlay kind): novo pod Ready 8,3 s após o delete
   k6: 2470 requisições, 2116 respostas 200, 354 falhas (503, 14,3%) na janela sem pod
2 réplicas (um dos dois pods removido): novo pod Ready 6,2 s após o delete
   k6: 2262 requisições, 2262 respostas 200, 0 falhas
```

&emsp; Os dois números medem coisas diferentes. O tempo de reposição é do Kubernetes e fica em segundos nos dois casos. A interrupção percebida pelo usuário depende de haver outra réplica `Ready` no momento da falha, que é a condição da meta descrita em `arquitetura-final.md` §3.1.1 e o motivo de a base usar duas réplicas. Com uma réplica só, os 8 segundos sem pod viram 503 no Ingress.

&emsp; Para efeito de comparação, o Auto Scaling Group levava até 300 segundos para repor uma instância, o valor do `health_check_grace_period`, dimensionado para cobrir boot, `dnf install` e `docker pull`. São duas ordens de grandeza de diferença, e vêm do mesmo fato: o Kubernetes reagenda um processo, enquanto o grupo de instâncias precisa construir uma máquina.

### 5.4 Interrupção voluntária

&emsp; O `PodDisruptionBudget` com `minAvailable: 1` tem papel operacional. O Auto Mode consolida nós de forma agressiva para reduzir custo, e esvazia o nó escolhido sem cerimônia. Sem esse objeto, ele pode retirar todas as réplicas da API ao mesmo tempo durante uma operação que deveria ser invisível.

### 5.5 Escala automática e a métrica de CPU

&emsp; O HPA escala por CPU e depende da API `metrics.k8s.io`, servida pelo `metrics-server`. A premissa de que o EKS Auto Mode já traria essa métrica não se confirmou no cluster do laboratório: nas rodadas de carga os dois HPAs ficaram em `cpu: <unknown>` durante os 36 minutos do ensaio, com o evento `FailedGetResourceMetric ... the server could not find the requested resource (get pods.metrics.k8s.io)`, e o `APIService v1beta1.metrics.k8s.io` não existia no cluster ([`evidencias/carga-kubernetes.txt`](evidencias/carga-kubernetes.txt), linhas 17–23). As réplicas ficaram no mínimo de duas, e a rodada de saturação registrou dois reinícios por pod do backend com o HPA sem poder reagir.

&emsp; A correção é declarativa: o add-on `metrics-server` é declarado como `aws_eks_addon` em `infra/eks.tf`, de modo que o cluster nasce com a métrica. No ambiente local o `kind-up` já instala o `metrics-server` v0.8.0, razão pela qual o HPA do kind reporta CPU ([`evidencias/testes-kubernetes.txt`](evidencias/testes-kubernetes.txt) mostra `cpu: 20%/60%` e `117%/70%`).

---

## 6. Conteinerização

### 6.1 As seis imagens

| Imagem | Base | Padrão |
|---|---|---|
| `worker`, `simulator`, `processing` | `uv` + `python:3.12-slim` | Multi-estágio, usuário sem privilégio uid 10001, `HEALTHCHECK` por arquivo de batimento |
| `loader` | `uv` + `python:3.12-slim` | Mesmo padrão, sem `HEALTHCHECK`, porque a carga é finita e uma sonda marcaria o encerramento normal como falha |
| `backend` | `uv` + `python:3.12-slim` | Multi-estágio, usuário sem privilégio, `HEALTHCHECK` em `/health/live` |
| `frontend` | `node:20` + `nginx:1.27-alpine` | Multi-estágio, usuário sem privilégio uid 101, `HEALTHCHECK` em `/healthz` |

&emsp; Todas as bases são fixadas por resumo criptográfico (`@sha256:`), e não por tag, porque uma tag pode passar a apontar para outra imagem sem que arquivo nenhum do repositório mude. Cada contexto de build tem o seu próprio `.dockerignore`: o de `apps/fullstack/` cobre os quatro serviços que compartilham `common/`, enquanto `backend/` e `frontend/` têm os seus, porque constroem a partir da própria pasta.

&emsp; Os contêineres executam com `readOnlyRootFilesystem: true`, `allowPrivilegeEscalation: false` e todas as capacidades descartadas. O `nginx.conf` do dashboard aponta o arquivo de processo e os diretórios temporários para `/tmp` para tornar isso possível, pois um nginx que não consegue gravar o próprio `pid` não chega a escutar na porta.

### 6.2 Multi-arquitetura

&emsp; As node pools padrão do Auto Mode são `amd64`, enquanto as máquinas do time e o Fargate são `arm64`. As três imagens que executam no cluster (`backend`, `frontend` e `processing`, esta pelo `Job` de migrations, que cai em nós `amd64`) são publicadas para as duas arquiteturas, em uma lista de manifestos, pela variável `IMAGES_MULTIARCH := backend frontend processing` do `Makefile`. As outras três (`worker`, `simulator` e `loader`) seguem só em `arm64`, porque só executam no Fargate. Publicar apenas `arm64` coloca o pod em `CrashLoopBackOff` com `exec format error`.

&emsp; Por isso a publicação usa `docker buildx build --push`, e não `docker build` seguido de `docker push`. Uma lista de manifestos só existe no registro, e o `push` empurraria apenas a arquitetura carregada no daemon local.

---

## 7. Restrições do AWS Academy Learner Lab

&emsp; As restrições abaixo foram verificadas por simulação de política na conta do laboratório, e não presumidas.

| Ação | Resultado | Consequência no desenho |
|---|---|---|
| `eks:CreateCluster`, `eks:CreateNodegroup` | Permitido | O cluster pode ser criado pelo Terraform |
| `iam:PassRole` sobre `LabEksClusterRole` e `LabEksNodeRole` | Permitido | Os papéis do laboratório podem ser usados |
| `iam:ListRoles` | Permitido | Os papéis são descobertos por expressão regular, sem fixar o prefixo de sessão |
| `iam:CreateRole`, `iam:AttachRolePolicy` | Negado | Nenhum papel novo; os do laboratório são reusados |
| `iam:CreateOpenIDConnectProvider` | Negado | IRSA indisponível |
| `eks-auth:AssumeRoleForPodIdentity` | Negado | Pod Identity indisponível |

&emsp; As duas últimas linhas fundamentam a primeira decisão da seção 3.1. Em uma conta comum, os workers no cluster receberiam um papel por conta de serviço, e a discussão seria outra.

&emsp; O nome dos papéis carrega um prefixo que muda a cada sessão do laboratório, e a própria conta é rotacionada. Nada é fixado: o Terraform descobre os papéis por expressão regular, e o endereço do registro entra por substituição no momento da aplicação, lido do estado.

### 7.1 Por que o EKS é viável no Learner Lab

&emsp; A ideia de que o EKS não funciona no Learner Lab decorre dos fluxos padrão de criação, e não de uma indisponibilidade do serviço. Tanto o `eksctl create cluster` quanto o fluxo usual do console tentam criar o papel do cluster e, em seguida, criar o provedor OpenID Connect para usar IRSA com o AWS Load Balancer Controller. Essas etapas dependem de `iam:CreateRole` e `iam:CreateOpenIDConnectProvider`, ações negadas pelo laboratório.

&emsp; A investigação do grupo identificou que a conta do laboratório já disponibiliza os papéis `LabEksClusterRole` e `LabEksNodeRole`. O arquivo `infra/eks.tf` não fixa os nomes, pois o prefixo da sessão muda a cada laboratório. Em vez disso, ele consulta os papéis por expressão regular e usa os ARNs encontrados no cluster e nos nós, por meio das permissões já liberadas de `iam:ListRoles` e `iam:PassRole`.

&emsp; O segundo desvio é o EKS Auto Mode. Com o balanceamento elástico habilitado no cluster, a própria AWS provisiona o ALB a partir do `Ingress` usando o papel do cluster. Não é necessário instalar o AWS Load Balancer Controller por Helm, criar uma conta de serviço com IRSA ou conceder permissões adicionais aos nós. Como o caminho síncrono não acessa SQS, S3 nem Secrets Manager diretamente, o `LabEksNodeRole` mínimo permanece suficiente e preserva o princípio do menor privilégio.

&emsp; Essa combinação foi validada no ambiente do grupo: o `terraform apply` criou o cluster em aproximadamente 12 minutos, sem qualquer negação de permissão. Portanto, a restrição do Learner Lab impede o caminho convencional de instalação, mas permite um cluster EKS Auto Mode quando os papéis preexistentes são reutilizados e o ALB é delegado ao serviço gerenciado.

---

## 8. Como executar

&emsp; O runbook completo está em [`apps/fullstack/k8s/README.md`](../apps/fullstack/k8s/README.md).

&emsp; Para executar localmente, sem Kubernetes:

```bash
make -C apps/fullstack dev    # scripts/dev.sh: PostgreSQL local já migrado, API em :5000 e dashboard em :3000; Ctrl-C derruba os três
# ou só a API em contêiner, com um PostgreSQL próprio em 127.0.0.1:55433 (sobe vazio; o
# comentário do compose.yaml traz o comando de migration):
docker compose -f apps/fullstack/backend/compose.yaml up --build
```

&emsp; O `apps/fullstack/.devcontainer/` traz Python 3.12, uv, Node 20 e Docker prontos para o `make dev`: no VS Code, use "Dev Containers: Open Folder in Container..." apontando para `apps/fullstack`. O Codespaces não o encontra, porque só procura `.devcontainer` na raiz do repositório.

&emsp; Para executar localmente em Kubernetes, sem credencial da AWS:

```bash
# o overlay kind lê o Secret de secret.env, que é gitignored: sem esta cópia,
# kind, k8s-apply e k8s-validate falham com "env source files: [secret.env]"
cp apps/fullstack/k8s/overlays/kind/secret.env.example apps/fullstack/k8s/overlays/kind/secret.env
make -C apps/fullstack kind-up
make -C apps/fullstack k8s-images kind-load
make -C apps/fullstack k8s-apply   K8S_OVERLAY=kind
make -C apps/fullstack k8s-migrate K8S_OVERLAY=kind
# saída esperada: dashboard em http://localhost:8080/ e API em /api/v1/clock,
# na mesma origem
```

&emsp; Para executar na AWS:

```bash
export AWS_PROFILE=g4                      # os alvos da AWS abortam sem ele (require_env)
aws rds start-db-instance --db-instance-identifier argus-events-dev --profile g4
make -C apps/fullstack tf-apply            # create_eks = true no terraform.tfvars
make -C apps/fullstack k8s-kubeconfig k8s-bootstrap
make -C apps/fullstack k8s-push k8s-secret k8s-migrate k8s-apply
make -C apps/fullstack k8s-url
```

&emsp; O `k8s-push` publica as três imagens que o cluster executa (`backend`, `frontend` e `processing`, a dos dois `Job`s de `k8s-migrate`), multi-arquitetura, conforme a seção 6.2. O `k8s-migrate` executa os dois `Job`s em sequência: primeiro as migrations, depois o login de leitura `argus_api`.

&emsp; O alvo `make check` inclui `k8s-validate`, que renderiza as cinco kustomizations (`base`, `migrate`, `overlays/aws`, `overlays/kind` e `overlays/kind/migrate`; saída em [`evidencias/k8s-validate.txt`](evidencias/k8s-validate.txt)) sem tocar em cluster nenhum e, em seguida, executa o verificador `verifica_manifests.py` para as invariantes que o kustomize não alcança: ordem das regras do Ingress, arquitetura das imagens e chaves do Secret. Ele é o portão que impede um erro de YAML de chegar à entrega, e tem a mesma pré-condição do runbook local: sem o `secret.env` copiado do `secret.env.example`, a renderização de `overlays/kind` falha, e com ela o `make check`.

---

## 9. Custo e desligamento

&emsp; O cluster cobra por hora existindo, somado ao balanceador. Ao fim de cada sessão de trabalho:

```bash
make -C apps/fullstack k8s-scale-zero   # sem pod pendente, os nós são consolidados até zero
make -C apps/fullstack k8s-delete       # remove o namespace e, com ele, o balanceador
```

&emsp; Para derrubar o cluster inteiro, use `create_eks = false` e `make tf-apply`. O ECS e o RDS não referenciam nada dele e continuam de pé. O ALB é criado pelo Auto Mode a partir do Ingress, e por isso o `k8s-delete` vem antes: é ele que o remove. Com o cluster desligado, a leitura fica com a Lambda `read_api_url` e o website do S3.

---

## 10. Vídeo

&emsp; O vídeo percorre os três itens avaliados, na ordem da rubrica. A tabela serve de índice: a primeira coluna dá o instante, a segunda diz o que aparece na tela e a terceira aponta a seção deste artefato que aquele trecho sustenta.

&emsp; Link: [Vídeo no Drive](https://drive.google.com/file/d/19DgDxN_cqHcZNQNFGKcaMAjAmcMVvx5W/view?usp=sharing)

| Tempo | O que o vídeo mostra | Evidência na tela |
|---|---|---|
| 0:00–0:35 | Apresentação do objetivo e visão geral da arquitetura | Introdução falada aos fluxos de ingestão e leitura |
| 0:35–1:40 | Código em contêiner: Dockerfiles do backend e do frontend, build em estágios, usuário sem privilégio e health check | Dockerfile do backend com `@sha256`, `USER argus` UID 10001 e `HEALTHCHECK`; Dockerfile do frontend e arquivos de deployment |
| 1:40–2:30 | Kubernetes no EKS: contexto do cluster, nó e configuração do Deployment | `kubectl get nodes` com nó `Ready`; YAML do backend com `replicas: 2` |
| 2:30–3:15 | Pods do backend e do frontend em execução e chamadas à aplicação | `kubectl get pods -o wide` com dois pods de cada serviço, todos `Running` e `1/1`; logs com respostas HTTP 200 |
| 3:15–4:07 | Resiliência: atualização controlada do backend e explicação das sondas | `kubectl rollout restart` e `kubectl rollout status`; pods novos iniciam, pods antigos terminam e o rollout conclui |
| 4:07–5:14 | Processamento assíncrono com workers, ECS Fargate e SQS | Dockerfile de worker; explicação de como a fila absorve picos e os consumidores processam eventos |
| 5:14–5:50 | Build local da imagem Docker do backend | `docker build -t argus-backend:demo ...` e saída de build concluído |
| 5:50–6:18 | Execução local do backend e do PostgreSQL em contêineres separados | `docker ps` mostra os dois contêineres saudáveis; backend acessível pela porta 5000 |
| 6:18–6:54 | Verificação de saúde e chamada à API | `/health/live` e `/health/ready` retornam `200`; `/api/v1/clock` retorna JSON |
| 6:54–6:58 | Encerramento | Conclusão da demonstração |

---

## 11. Evidências

&emsp; As saídas brutas dos ensaios ficam em [`evidencias/`](evidencias/), com URLs e identificadores de conta substituídos. Cada arquivo diz a data, o ambiente e o comando que o produziu.

| Arquivo | O que registra | Sustenta |
|---|---|---|
| [`evidencias/carga-kubernetes.txt`](evidencias/carga-kubernetes.txt) | Rodadas A (5, 25 e 100 usuários) e B (200, 450 e 900) de carga contra o Ingress do EKS real: cluster Auto Mode 1.33, nós `amd64`, estado final dos objetos e o diagnóstico do HPA sem métrica | 2.1, 5.5, 6.2 |
| [`evidencias/carga-kubernetes/`](evidencias/carga-kubernetes/) | Os arquivos de cada rodada: `rodada-{a,b}-saida-k6.txt`, `-summary-k6.json`, `-resultado.json` e `-instancia.log` | 5.5 |
| [`evidencias/testes-kubernetes.txt`](evidencias/testes-kubernetes.txt) | TI-01 e a suíte e2e (12 testes, todos aprovados) contra o caminho orquestrado no cluster kind local, pela origem única do Ingress | 4, 5.1 |
| [`evidencias/k8s-validate.txt`](evidencias/k8s-validate.txt) | `make k8s-validate` renderizando as cinco kustomizations sem tocar em cluster | 8 |
| [`evidencias/resiliencia-kind-01-autocura.txt`](evidencias/resiliencia-kind-01-autocura.txt), [`resiliencia-kind-02-rollout-e-undo.txt`](evidencias/resiliencia-kind-02-rollout-e-undo.txt), [`resiliencia-kind-03-perda-do-banco.txt`](evidencias/resiliencia-kind-03-perda-do-banco.txt) e [`resiliencia-kind/`](evidencias/resiliencia-kind/) | Ensaios no kind local: autocura (`kubectl delete pod`), implantação sob carga (`rollout restart` com k6, deploy defeituoso e `rollout undo`) e queda do Postgres, com saída bruta, timestamps e os scripts k6 que os reproduzem; são as medições de 5.2 e 5.3 | 5.2, 5.3 |

---

## Apêndice A: Mapa de arquivos

| Arquivo | Papel |
|---|---|
| `apps/fullstack/infra/eks.tf` | Cluster Auto Mode, descoberta dos papéis do laboratório, entradas de acesso |
| `apps/fullstack/infra/vpc.tf` | Etiquetas `kubernetes.io/role/*`, sem as quais o balanceador não é provisionado |
| `apps/fullstack/infra/rds.tf` | Regra que autoriza os pods a alcançar o banco |
| `apps/fullstack/k8s/base/` | `Deployment`, `Service`, `HPA`, `PDB`, `Ingress` e `ConfigMap` |
| `apps/fullstack/k8s/migrate/` | `Job`s de banco, aplicados à parte porque o modelo de um `Job` é imutável |
| `apps/fullstack/k8s/migrate/job-db-migrate.yaml` | `Job argus-db-migrate`: aplica as migrations |
| `apps/fullstack/k8s/migrate/job-db-reader.yaml` | `Job argus-db-reader`: cria o login somente-leitura `argus_api`; executa depois do anterior, por `make k8s-migrate` |
| `apps/fullstack/k8s/overlays/kind/secret.env.example` | Modelo do `secret.env` (gitignored) que o overlay kind exige |
| `apps/fullstack/k8s/overlays/aws/` | Classe de Ingress do balanceador e anotações |
| `apps/fullstack/k8s/overlays/kind/` | Banco local, ingress-nginx, uma réplica por carga |
| `apps/fullstack/frontend/Dockerfile` | Imagem do dashboard |
| `apps/fullstack/frontend/nginx.conf` | Servidor do export estático, preparado para raiz somente-leitura |
| `apps/fullstack/Makefile` | Alvos `k8s-*`, `kind-*` e `dev`; `IMAGES`, `IMAGES_MULTIARCH` e `K8S_IMAGES` |
| `artefatos/evidencias/` | Saídas brutas dos ensaios (seção 11) |
