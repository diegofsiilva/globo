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
| `Job argus-db-migrate` | `argus-events-dev-processing` | Aplica as 29 migrations e termina |
| `Ingress argus` | Não aplicável | Entrada única: `/` para o dashboard, `/api` para a API |
| `HorizontalPodAutoscaler` | Não aplicável | 2 a 6 réplicas da API, por CPU |
| `PodDisruptionBudget` | Não aplicável | Impede que uma consolidação de nó tire todas as réplicas |

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
| 9 | Escala por CPU | Requisições por alvo, como fazia o ASG | Disponibilidade da métrica sem componente extra | A métrica não é a mesma do ASG; a comparação entre plataformas precisa dizer isso | Não aplicável | KEDA, ou o adaptador de métricas externas |
| 10 | Imagens multi-arquitetura para as duas do cluster | Somente `arm64`, como as quatro do Fargate | Compatibilidade: as node pools padrão do Auto Mode são `amd64` | `CrashLoopBackOff` com `exec format error` | ~2 min a mais no build | Node pool customizada `arm64` |
| 11 | `topologySpreadConstraints` com `ScheduleAnyway` | `DoNotSchedule` | Velocidade de implantação | Distribuição entre zonas deixa de ser garantida | Não aplicável | Trocar para `DoNotSchedule` quando houver nó quente |
| 12 | Segredo montado por `kubectl` a partir do Terraform | Provider `kubernetes` no Terraform, ou arquivo `.env` | Segurança: o valor não toca disco, repositório nem estado | Exige `rollout restart` após rotação; automatizado no alvo do Makefile | Não aplicável | Operador de segredos externos, se houver IRSA |

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

### 5.3 Autocura

&emsp; Remoção forçada de um pod da API, cronometrada até a condição `Ready`:

```
# saída esperada: recuperação em poucos segundos
recuperado em 4s
```

&emsp; O ASG levava até **300 segundos** para repor uma instância, o valor do
`health_check_grace_period`, dimensionado para cobrir boot, `dnf install` e `docker
pull`. São duas ordens de grandeza de diferença, e vêm do mesmo fato: o Kubernetes
reagenda um processo, enquanto o ASG precisa construir uma máquina.

### 5.4 Interrupção voluntária

&emsp; O `PodDisruptionBudget` com `minAvailable: 1` não é decoração. O Auto Mode
consolida nós de forma agressiva para reduzir custo, e esvazia o nó escolhido sem
cerimônia. Sem esse objeto, ele pode tirar todas as réplicas da API ao mesmo tempo
durante uma operação que deveria ser invisível.

---

## 6. Conteinerização

### 6.1 As seis imagens

| Imagem | Base | Padrão |
|---|---|---|
| `worker`, `simulator`, `processing`, `loader` | `uv` + `python:3.12-slim` | Multi-estágio, usuário sem privilégio uid 10001, `HEALTHCHECK` por arquivo de batimento |
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
são `arm64`. As duas imagens do cluster são publicadas para as duas arquiteturas, numa
lista de manifestos. Publicar só `arm64` coloca o pod em `CrashLoopBackOff` com
`exec format error`, a mesma falha que já apareceu no ASG.

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

&emsp; O alvo `make check` passou a incluir `k8s-validate`, que renderiza os seis
conjuntos de manifestos sem tocar em cluster nenhum, e é o portão que impede um erro de
YAML de chegar à entrega.

---

## 9. Custo e desligamento

&emsp; O cluster cobra por hora existindo, somado ao balanceador. Ao fim de cada sessão
de trabalho:

```bash
make -C apps/fullstack k8s-scale-zero   # sem pod pendente, os nós são consolidados até zero
make -C apps/fullstack k8s-delete       # remove o namespace e, com ele, o balanceador
```

&emsp; Para derrubar o cluster inteiro, `create_eks = false` e `make tf-apply`. ECS,
RDS, balanceador e ASG não referenciam nada dele e continuam de pé, o que é, também,
a demonstração prática da decisão 5.

---

## 10. Vídeo

&emsp; O vídeo percorre os três itens avaliados, na ordem da rubrica. A tabela serve de
índice: a primeira coluna dá o instante, a segunda diz o que aparece na tela e a
terceira aponta a seção deste artefato que aquele trecho sustenta.

**Link:** _(a preencher)_

| Tempo | O que o vídeo mostra | Evidência na tela |
|---|---|---|
| 0:00–0:30 | Apresentação do grupo e do recorte da sprint | Não aplicável |
| 0:30–1:40 | **Código em contêiner**: os seis `Dockerfile`, o multi-estágio, o usuário sem privilégio e a base fixada por resumo | `USER argus` uid 10001 e `USER nginx` uid 101; `HEALTHCHECK` em cada imagem; `@sha256:` nas bases (6.1) |
| 1:40–2:30 | O build multi-arquitetura e a lista de manifestos no ECR | `docker buildx build --platform linux/amd64,linux/arm64`; `docker manifest inspect` listando as duas arquiteturas (6.2) |
| 2:30–3:30 | **Kubernetes**: o cluster no console, os nós e os objetos aplicados | `kubectl get nodes`; `kubectl -n argus get pods,svc,ingress,hpa,pdb` (2.1) |
| 3:30–4:10 | O Ingress de origem única | O dashboard em `/` e o relógio virtual em `/api/v1/clock`, no mesmo endereço, sem CORS (4) |
| 4:10–4:40 | O `Job` de migrations | `kubectl get job` em `1/1`; as 29 migrations no registro do contêiner (2.1) |
| 4:40–5:30 | **Resiliência: autocura**. Remoção de um pod da API | Pod reagendado e `Ready` em segundos, contra os 300 s do ASG (5.3) |
| 5:30–6:30 | **Resiliência: implantação sem queda sob carga** | `rollout restart` com o teste de carga rodando; zero erro no relatório (5.2) |
| 6:30–6:50 | Escala automática | `kubectl get hpa -w` com as réplicas subindo e descendo (3.1, decisão 9) |
| 6:50–7:00 | Encerramento | Não aplicável |

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
| `apps/fullstack/Makefile` | Alvos `k8s-*` e `kind-*` |
