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

&emsp; Durante a migração, o Auto Scaling Group não foi destruído de imediato: foi zerado
(`asg_min_size = 0`, `asg_desired_capacity = 0`), e o `launch template`, o target group
e as políticas de escala ficaram no estado do Terraform, de modo que voltar atrás era
trocar dois valores no `terraform.tfvars` (decisão 5 da seção 3.1).

&emsp; Essa reversibilidade cumpriu o seu papel e saiu de cena: ao fim da sprint o caminho
EC2 da Sprint 3 foi removido (`infra/asg.tf`, `alb.tf`, `asg_observability.tf` e
`templates/user_data.sh.tftpl`, no commit `ae21485`). A leitura pública passou a vir só
do ALB que o EKS Auto Mode provisiona a partir do Ingress
(`k8s/overlays/aws/ingress-patch.yaml`); a contingência, com o cluster desligado, é a
Lambda `read_api_url` com o website do S3 (decisão 13, que substitui a 5).

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
| `Job argus-db-reader` | `argus-events-dev-processing` | Cria ou atualiza o login somente-leitura `argus_api` que o backend usa (`migrate.py criar-leitor`); `make k8s-migrate` o roda só depois de o `Job` de migrations concluir, porque o `GRANT` depende do papel criado na migration 001 |
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
| `processing` | `argus-events-dev-processing` | ECS Fargate: serviço `processing` (ETL e motor de hipóteses); EKS: `Job argus-db-migrate` e `Job argus-db-reader` | 1 task (`processing_desired_count`); cada `Job` roda uma vez, com `backoffLimit: 2` | `arm64` + `amd64` | `HEALTHCHECK` por arquivo de batimento; no `Job`, a conclusão em `1/1` é a sonda |
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
`infra/templates/user_data.sh.tftpl` de cada instância do ASG (arquivo removido nesta
sprint com o resto do caminho EC2, no commit `ae21485`; só resta o exemplo
`infra/ec2_api.tf.example`):

```bash
dnf install docker  →  docker pull  →  docker run -p 5000:5000
```

&emsp; Isso era orquestração de contêiner feita à mão numa máquina virtual. Não havia
implantação gradual: publicar uma versão nova significava substituir instâncias. Não havia
reposição do contêiner por saúde, apenas o target group derrubando a instância inteira.
E o `health_check_grace_period = 300s` existia justamente para cobrir o tempo de boot,
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
| 5 | ~~ASG zerado, não destruído~~ **Substituída pela decisão 13**; valeu durante a migração | Remover `asg.tf` e `alb.tf` | Reversibilidade durante a sprint | Recurso ocioso no estado | Nenhum, com capacidade zero | Enquanto valeu, dois valores no `terraform.tfvars` |
| 6 | Ingress único com origem única | Um `Service` do tipo `LoadBalancer` por aplicação | Simplicidade: elimina CORS e desacopla a imagem do ambiente | Uma regra de roteamento errada afeta os dois serviços | Um balanceador em vez de dois | Separar em dois `Ingress` |
| 7 | Sonda de vida em `/health/live` | `/health/ready`, que consulta o banco | Disponibilidade | Uma queda do RDS mataria **todos** os pods ao mesmo tempo | Não aplicável | Trocar o `path` da sonda |
| 8 | Sem limite de CPU nos contêineres | `limits.cpu` declarado | Latência previsível | Cota CFS provoca estrangulamento em rajada, invisível nas métricas usuais | Nó pode precisar ser maior | Acrescentar `limits.cpu` |
| 9 | Escala por CPU | Requisições por alvo, como fazia o ASG | Métrica nativa de `metrics.k8s.io`, sem adaptador externo; no EKS do laboratório ela exige o add-on `metrics-server` (5.5) | A métrica não é a mesma do ASG; a comparação entre plataformas precisa dizer isso. Sem o `metrics-server` o HPA fica em `<unknown>`, como aconteceu em 21/09 | Não aplicável | KEDA, ou o adaptador de métricas externas |
| 10 | Imagens multi-arquitetura para as três que rodam no cluster (`backend`, `frontend` e `processing`) | Somente `arm64`, como as três que só rodam no Fargate | Compatibilidade: as node pools padrão do Auto Mode são `amd64` | `CrashLoopBackOff` com `exec format error` | ~2 min a mais no build | Node pool customizada `arm64` |
| 11 | `topologySpreadConstraints` com `ScheduleAnyway` | `DoNotSchedule` | Velocidade de implantação | Distribuição entre zonas deixa de ser garantida | Não aplicável | Trocar para `DoNotSchedule` quando houver nó quente |
| 12 | Segredo montado por `kubectl` a partir do Terraform | Provider `kubernetes` no Terraform, ou arquivo `.env` | Segurança: o valor não toca disco, repositório nem estado | Exige `rollout restart` após rotação; automatizado no alvo do Makefile | Não aplicável | Operador de segredos externos, se houver IRSA |
| 13 | Remover o caminho EC2 da Sprint 3 (`asg.tf`, `alb.tf`, `asg_observability.tf`), substituindo a decisão 5 | Manter o ASG zerado no estado | Simplicidade e custo: o Auto Mode cria o ALB pelo Ingress; dois balanceadores custavam em dobro e confundiam qual era a origem pública | A volta atrás deixa de ser dois valores no `tfvars`; a contingência passa a ser a Lambda `read_api_url` com o website do S3 | Nenhum: um balanceador a menos | Restaurar os três arquivos removidos e reaplicar |

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

&emsp; Medição feita em 24/09 no cluster kind local (um nó, commit `0ff97f4b0130`; não é o
EKS), com k6 a 5 VUs contra `/api/v1/clock` e `/api/v1/hypotheses` pelo Ingress durante
150 s que cobriram um `rollout restart`, um deploy com tag de imagem inexistente e o
`rollout undo`:

```
# saída medida em 24/09 no kind (local) -- ver evidencias/resiliencia-kind-02-rollout-e-undo.txt
rollout restart   : pod novo Ready antes de o antigo sair; rollout status concluído em 60,3 s
                    (inclui o preStop de 10 s e o término gracioso do gunicorn)
deploy defeituoso : set image ...:nao-existe -> pod novo em ImagePullBackOff após 17,1 s,
                    pods antigos seguiram Ready, Ingress respondendo 200, rollout status não conclui
rollout undo      : imagem anterior restaurada, rollout status concluído em 3,0 s
k6 nos 150 s      : 5394 requisições, 5389 respostas 200, 5 falhas (0,09%)
```

&emsp; As 5 falhas foram timeouts de 5 s no mesmo instante (20:45:26), durante o
`ContainerCreating` do pod novo, com o pod antigo ainda `Ready` e único endpoint do
Service: sintoma de saturação da VM local (o `ContainerCreating` levou 10 s e o pod só
ficou `Ready` 28 s depois de criado), não de troca de endpoint. Da entrada do pod novo até
o fim, inclusive na saída do antigo, no deploy defeituoso e no `undo`, foram 0 falhas.
Durante o ensaio o HPA subiu o Deployment de 1 para 2 réplicas, porque a CPU passou de
60% da `request` de 100m sob a carga; é o comportamento esperado e não muda a leitura.
No EKS a medição ainda não foi repetida.

### 5.3 Autocura

&emsp; Remoção forçada de um pod da API, cronometrada até a condição `Ready`. Medido em
24/09 no cluster kind local (um nó, commit `0ff97f4b0130`, imagens construídas desse
mesmo commit; não é o EKS), com k6 a 5 VUs contra `/api/v1/clock` e `/api/v1/hypotheses`
pelo Ingress durante toda a troca:

```
# saída medida em 24/09 no kind (local) -- ver evidencias/resiliencia-kind-01-autocura.txt
1 réplica (padrão do overlay kind): novo pod Ready 8,3 s após o delete
   k6: 2470 requisições, 2116 respostas 200, 354 falhas (503, 14,3%) na janela sem pod
2 réplicas (um dos dois pods removido): novo pod Ready 6,2 s após o delete
   k6: 2262 requisições, 2262 respostas 200, 0 falhas
```

&emsp; Os dois números medem coisas diferentes. O tempo de reposição é do Kubernetes e
fica em segundos nos dois casos; a interrupção percebida pelo usuário depende de haver
**outra réplica `Ready`** no momento da falha, que é a condição da meta de
`arquitetura-final.md` §3.1.1 e o motivo de a base usar duas réplicas. Com uma réplica
só, os 8 segundos sem pod viram 503 no Ingress.

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
`metrics-server`. A premissa de que o EKS Auto Mode já a traria, registrada à época no comentário do alvo
`k8s-bootstrap` do `Makefile` (hoje corrigido: ele diz que o `metrics-server` **não**
vem com o Auto Mode), **não se confirmou no cluster do laboratório**: nas
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

**Local, sem Kubernetes:**

```bash
make -C apps/fullstack dev    # scripts/dev.sh: PostgreSQL local já migrado, API em :5000 e dashboard em :3000; Ctrl-C derruba os três
# ou só a API em contêiner, com um PostgreSQL próprio em 127.0.0.1:55433 (sobe vazio; o
# comentário do compose.yaml traz o comando de migration):
docker compose -f apps/fullstack/backend/compose.yaml up --build
```

&emsp; O `apps/fullstack/.devcontainer/` traz Python 3.12, uv, Node 20 e Docker prontos
para o `make dev`: no VS Code, "Dev Containers: Open Folder in Container..." apontando
para `apps/fullstack`. O Codespaces não o encontra, porque só procura `.devcontainer` na
raiz do repositório, que é fixa.

**Local, sem credencial da AWS:**

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

**Na AWS:**

```bash
export AWS_PROFILE=g4                      # os alvos da AWS abortam sem ele (require_env)
aws rds start-db-instance --db-instance-identifier argus-events-dev --profile g4
make -C apps/fullstack tf-apply            # create_eks = true no terraform.tfvars
make -C apps/fullstack k8s-kubeconfig k8s-bootstrap
make -C apps/fullstack k8s-push k8s-secret k8s-migrate k8s-apply
make -C apps/fullstack frontend-deploy k8s-edge-register
make -C apps/fullstack k8s-url
```

&emsp; O `k8s-push` publica as três imagens que o cluster executa (`backend`, `frontend`
e `processing`, a dos dois `Job`s de `k8s-migrate`), multi-arquitetura, conforme a
seção 6.2. O `k8s-migrate` roda os dois `Job`s em sequência: primeiro as migrations,
depois o login de leitura `argus_api`.

&emsp; O alvo `make check` passou a incluir `k8s-validate`, que renderiza as cinco
kustomizations (`base`, `migrate`, `overlays/aws`, `overlays/kind` e
`overlays/kind/migrate`; saída em
[`evidencias/k8s-validate.txt`](evidencias/k8s-validate.txt)) sem tocar em cluster
nenhum e, em seguida, roda o verificador `verifica_manifests.py` para as invariantes que
o kustomize não alcança: ordem das regras do Ingress, arquitetura das imagens e chaves
do Secret. É o portão que impede um erro de YAML de chegar à entrega. Ele tem a mesma
pré-condição do runbook local: sem o `secret.env` copiado do `secret.env.example`, a
renderização de `overlays/kind` falha, e com ela o `make check`.

---

## 9. Custo e desligamento

&emsp; O cluster cobra por hora existindo, somado ao balanceador. Ao fim de cada sessão
de trabalho:

```bash
make -C apps/fullstack k8s-scale-zero   # sem pod pendente, os nós são consolidados até zero
make -C apps/fullstack k8s-delete       # remove o namespace e, com ele, o balanceador
```

&emsp; Para derrubar o cluster inteiro, `create_eks = false` e `make tf-apply`. ECS e
RDS não referenciam nada dele e continuam de pé. O ALB atual é criado pelo Auto Mode a
partir do Ingress, e por isso o `k8s-delete` vem antes: é ele que o remove; o balanceador e o ASG da Sprint 3 já não
existem desde a remoção descrita na decisão 13, e a leitura, com o cluster desligado,
fica com a Lambda `read_api_url` e o website do S3.

---

## 10. Vídeo

&emsp; O vídeo percorre os três itens avaliados, na ordem da rubrica. A tabela serve de
índice: a primeira coluna dá o instante, a segunda diz o que aparece na tela e a
terceira aponta a seção deste artefato que aquele trecho sustenta.

**Link:** [Vídeo no Drive](https://drive.google.com/file/d/19DgDxN_cqHcZNQNFGKcaMAjAmcMVvx5W/view?usp=sharing)

| Tempo | O que o vídeo mostra | Evidência na tela |
|---|---|---|
| 0:00–0:35 | Apresentação do objetivo e visão geral da arquitetura | Introdução falada aos fluxos de ingestão e leitura |
| 0:35–1:40 | **Código em contêiner:** Dockerfiles do backend e frontend, build em estágios, usuário sem privilégio e health check | Dockerfile do backend com `@sha256`, `USER argus` UID 10001 e `HEALTHCHECK`; Dockerfile do frontend e arquivos de deployment |
| 1:40–2:30 | **Kubernetes no EKS:** contexto do cluster, nó e configuração do Deployment | `kubectl get nodes` com nó `Ready`; YAML do backend com `replicas: 2` |
| 2:30–3:15 | Pods do backend e frontend em execução e chamadas à aplicação | `kubectl get pods -o wide` com dois pods de cada serviço, todos `Running` e `1/1`; logs com respostas HTTP 200 |
| 3:15–4:07 | **Resiliência:** atualização controlada do backend e explicação das sondas | `kubectl rollout restart` e `kubectl rollout status`; pods novos iniciam, pods antigos terminam e o rollout conclui |
| 4:07–5:14 | Processamento assíncrono com workers, ECS/Fargate e SQS | Dockerfile de worker; explicação de como a fila absorve picos e os consumidores processam eventos |
| 5:14–5:50 | Build local da imagem Docker do backend | `docker build -t argus-backend:demo ...` e saída de build concluído |
| 5:50–6:18 | Execução local do backend e do PostgreSQL em contêineres separados | `docker ps` mostra os dois contêineres saudáveis; backend acessível pela porta 5000 |
| 6:18–6:54 | Verificação de saúde e chamada à API | `/health/live` e `/health/ready` retornam `200`; `/api/v1/clock` retorna JSON |
| 6:54–6:58 | Encerramento | Conclusão da demonstração |

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
| [`evidencias/resiliencia-kind-01-autocura.txt`](evidencias/resiliencia-kind-01-autocura.txt), [`resiliencia-kind-02-rollout-e-undo.txt`](evidencias/resiliencia-kind-02-rollout-e-undo.txt), [`resiliencia-kind-03-perda-do-banco.txt`](evidencias/resiliencia-kind-03-perda-do-banco.txt) e [`resiliencia-kind/`](evidencias/resiliencia-kind/) | Ensaios executados em 24/09 no kind local: autocura (`kubectl delete pod`), implantação sob carga (`rollout restart` com k6, deploy defeituoso e `rollout undo`) e queda do Postgres, com saída bruta, timestamps e os scripts k6 que os reproduzem; são as medições de 5.2 e 5.3 | 5.2, 5.3 |

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
| `apps/fullstack/k8s/migrate/job-db-reader.yaml` | `Job argus-db-reader`: cria o login somente-leitura `argus_api`; roda depois do anterior, por `make k8s-migrate` |
| `apps/fullstack/k8s/overlays/kind/secret.env.example` | Modelo do `secret.env` (gitignored) que o overlay kind exige |
| `apps/fullstack/k8s/overlays/aws/` | Classe de Ingress do balanceador e anotações |
| `apps/fullstack/k8s/overlays/kind/` | Banco local, ingress-nginx, uma réplica por carga |
| `apps/fullstack/frontend/Dockerfile` | Imagem do dashboard |
| `apps/fullstack/frontend/nginx.conf` | Servidor do export estático, preparado para raiz somente-leitura |
| `apps/fullstack/Makefile` | Alvos `k8s-*`, `kind-*` e `dev`; `IMAGES`, `IMAGES_MULTIARCH` e `K8S_IMAGES` |
| `artefatos/evidencias/` | Saídas brutas dos ensaios (seção 11) |
