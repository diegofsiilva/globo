# Kubernetes — caminho síncrono do Argus

O cluster orquestra **dashboard, API de leitura e os Jobs de banco** (migration
e login de leitura). O caminho
assíncrono — workers de SQS, `processing`, `simulator` e `loader` — continua no
**ECS Fargate**, sem nenhuma alteração.

Isso é escolha de plataforma por característica de carga, não migração pela
metade. As razões estão em [`infra/eks.tf`](../infra/eks.tf) e no artefato
[`conteineres-final.md`](../../../artefatos/conteineres-final.md); em resumo:

| Caminho | Onde roda | Por quê |
|---|---|---|
| Síncrono (dashboard + API) | **EKS Auto Mode** | Substitui o ASG, que subia o contêiner à mão pelo `user_data` e levava ~300s para repor uma instância. Ganha rolling update sem queda, reposição em segundos e escala por métrica. |
| Assíncrono (ingestão, ETL, simulação) | **ECS Fargate** | Já entrega estado desejado, rolling deploy e health check — e **IAM por task**, que este cluster não consegue oferecer: o Learner Lab bloqueia IRSA e Pod Identity. |

Nenhum pod deste cluster fala com a AWS. O backend não tem `boto3` (removido de
propósito, ver `backend/pyproject.toml`) e o frontend é nginx servindo arquivo
estático. É por isso que os nós usam o `LabEksNodeRole` mínimo, sem SQS nem S3.

## Estrutura

```
k8s/
├── base/        Deployments, Services, HPA, PDB, Ingress, ConfigMap
├── migrate/     Jobs de migration e de login de leitura, à parte (ver abaixo)
└── overlays/
    ├── aws/     IngressClass do ALB e anotações
    └── kind/    Postgres no cluster, ingress-nginx, imagens :dev
```

As imagens entram por placeholder (`IMAGE_BACKEND`, `IMAGE_FRONTEND`,
`IMAGE_PROCESSING`), nunca escritas por extenso: o nome do repositório vem de
`local.name` no Terraform e a conta muda a cada sessão do laboratório. No
overlay `aws`, `make k8s-apply` troca cada um pela referência completa lida de
`terraform output ecr_repository_urls`; no `kind`, o transformer `images:` do
kustomize aponta para as imagens `:dev` locais.

Os `Job`s ficam **fora** da base de propósito: `spec.template` de um Job é
imutável, então incluí-los faria todo `make k8s-apply` com tag nova falhar com
`field is immutable`. `make k8s-migrate` faz `delete` antes do `apply`.

São dois Jobs porque `migrate.py aplicar` **não cria** o login `argus_api`:
`criar-leitor` é subcomando à parte. `argus-db-migrate` aplica o schema;
`argus-db-reader` cria (ou atualiza) o login, e só pode rodar depois, porque o
`GRANT argus_reader` depende do papel que a migration 001 cria. O alvo aplica
um de cada vez, filtrando o YAML renderizado por `-l app.kubernetes.io/name`,
e espera o primeiro completar. Num banco novo, só o primeiro Job deixa o
backend em `0/1` com `PoolTimeout` e, por baixo, `password authentication
failed for user "argus_api"` — foi o que aconteceu no lab limpo de 18/09.

## A decisão central: uma origem só

Um único Ingress serve os dois serviços:

```
/        → argus-frontend  (nginx com o export estático do Next)
/api     → argus-backend   (Flask; o blueprint já vive em /api/v1)
/health  → argus-backend   (conveniência de smoke test)
```

O frontend é construído com `NEXT_PUBLIC_API_URL=/`. O cliente faz
`fetch(`${API_URL.replace(/\/$/, "")}${path}`)` e `path` já começa com `/api/v1`
(`frontend/src/lib/api/client.ts:26,85`), então a chamada vira **relativa**.

Três consequências:

1. O navegador nunca emite preflight — **o CORS deixa de ser parâmetro
   operacional**. Até a Sprint 3 o dashboard vinha do S3 e a API do ALB: duas
   origens e uma lista de permitidos para manter em dia.
2. A imagem do frontend **deixa de depender do endereço do ambiente**. A mesma
   tag roda no `kind` e no EKS — o que importa aqui, onde o hostname do ALB muda
   a cada sessão do lab.
3. Não há rewrite de caminho. O prefixo chega intacto ao Flask.

Não pode ser `NEXT_PUBLIC_API_URL=""`: a linha 61 do `client.ts` rejeita string
vazia de propósito.

## Local, sem AWS nenhuma

Pré-requisitos: `kubectl` e `kind` (`brew install kubectl kind`). O `kubectl` é
exigido também pelo `make check`, que passou a incluir `k8s-validate`.

```bash
make kind-up                     # cluster, ingress-nginx, metrics-server
make k8s-images kind-load        # constrói e carrega backend, frontend e processing
                                 # (processing é a imagem do Job de migration)
make k8s-apply   K8S_OVERLAY=kind
make k8s-migrate K8S_OVERLAY=kind

# saída esperada: dashboard e API na mesma origem
open http://localhost:8080/
curl -s http://localhost:8080/api/v1/clock
```

O overlay `kind` usa **uma réplica** por Deployment e `AUTH_REQUIRED=0`. O
segredo vem de `secret.env` (copiado de `secret.env.example`, gitignored) — são
credenciais de um banco descartável que vive dentro do cluster.

`make kind-down` destrói tudo.

> **Recursos.** Um nó só rodando control plane, ingress-nginx, metrics-server,
> Postgres e a aplicação pede folga de CPU. Em Docker Desktop ou Colima, menos
> de 4 vCPU faz o próprio API server começar a dar `TLS handshake timeout` — o
> sintoma aparece como "o cluster caiu", e é só falta de CPU.

## AWS

```bash
# 0. O RDS costuma estar parado; ele é pré-requisito do /health/ready.
aws rds start-db-instance --db-instance-identifier argus-events-dev --profile g4
aws rds wait db-instance-available --db-instance-identifier argus-events-dev --profile g4

# 1. Cluster (create_eks = true no terraform.tfvars). Leva 10 a 15 minutos.
make tf-apply
make k8s-kubeconfig
make k8s-bootstrap      # IngressClass do ALB

# 2. Imagens, segredo, migrations, aplicação
make k8s-push           # backend e frontend multi-arquitetura
make k8s-secret
make k8s-migrate        # dois Jobs, em sequência: schema e login argus_api
make k8s-apply

# 3. Verificação
make k8s-status
make k8s-url            # http://<hostname do ALB>
```

O `metrics-server` **não vem** com o Auto Mode: um cluster recém-criado nasce
com `kube-system` vazio e sem o APIService `v1beta1.metrics.k8s.io`, e o HPA
fica em `<unknown>/60%` com `ScalingActive=False` — foi assim no lab limpo de
18/09. Ele é o add-on `aws_eks_addon.metrics_server` declarado em
[`infra/eks.tf`](../infra/eks.tf), instalado pelo `make tf-apply` junto com o
cluster; `cpu: 0%/60%` aparece uns dois minutos depois. No `kind` é o
`kind-up` que o instala.

### Multi-arquitetura

As node pools padrão do Auto Mode são **amd64**; as máquinas do time e o Fargate
são **arm64**. `make k8s-push` publica as duas arquiteturas numa lista de
manifestos. Publicar só arm64 coloca o pod em `CrashLoopBackOff` com
`exec format error` — a mesma falha que já mordeu o time no ASG.

Por isso `docker buildx build --push`, e não `docker build` + `docker push`: uma
lista de manifestos só existe no registry, e o `push` empurraria apenas a
arquitetura carregada no daemon local.

### Segredos

Sem IRSA e sem Pod Identity, o pod não lê o Secrets Manager sozinho.
`make k8s-secret` lê os outputs do Terraform e canaliza direto para o `kubectl` —
o valor **nunca toca o disco**, nem o repositório, nem o `tfstate`.

São cinco chaves, e duas delas são URLs de banco **diferentes**:

| Chave | Usuário | Quem consome |
|---|---|---|
| `DATABASE_URL` | `argus_api` (só lê as views `v_*`) | Deployment do backend |
| `DATABASE_URL_MASTER` | mestre | **Jobs `argus-db-migrate` e `argus-db-reader`** |
| `DB_READER_PASSWORD` | — | Job `argus-db-reader`, que cria o login de leitura com esta senha |
| `USER_ID_HASH_SALT` | — | Deployment do backend |
| `DASHBOARD_TOKEN_SHA256` | — | Deployment do backend |

Confundir as duas primeiras falha com `permission denied for schema` no meio da
migration, deixando o banco parcialmente migrado.

> Variável vinda de `secretKeyRef` **não recarrega** em pod que já está de pé.
> Depois de `make auth-rotate`, rode `make k8s-secret` — ele termina com
> `rollout restart`.

## Resiliência — o que dá para demonstrar

**As três sondas atacam problemas diferentes**, e trocá-las de lugar tem
consequência concreta:

| Sonda | Alvo | Se estivesse trocada |
|---|---|---|
| `startupProbe` | `/health/live` | Sem ela, a liveness contaria falha durante o boot e reiniciaria o pod em laço |
| `livenessProbe` | `/health/live` (não toca no banco) | Em `/health/ready`, uma queda do RDS **mataria todos os pods ao mesmo tempo** |
| `readinessProbe` | `/health/ready` (consulta o banco) | Em `/health/live`, o pod receberia tráfego sem banco e responderia 500 |

```bash
# 1. Autocura
kubectl -n argus delete pod -l app.kubernetes.io/name=argus-backend
kubectl -n argus get pods -w      # reagendado em segundos, contra ~300s do ASG

# 2. Deploy sem downtime, sob carga (usa o k6 que já existe)
ARGUS_API_URL=$(make -s k8s-url) ./tests/carga/executar_testes.sh rnf01 &
kubectl -n argus rollout restart deployment/argus-backend
kubectl -n argus rollout status  deployment/argus-backend
# esperado: réplicas Ready nunca abaixo do mínimo, e 0.00% de erro no k6

# 3. HPA sob carga
kubectl -n argus get hpa -w
```

`maxUnavailable: 0` mantém a capacidade durante o deploy; o `preStop: sleep 10`
cobre a propagação do desregistro no ALB, sem o qual cada rolling update produz
um punhado de 502.

## Custo

O cluster cobra por hora existindo, somado ao ALB. Ao fim de cada sessão:

```bash
make k8s-scale-zero   # sem pod pendente, o Karpenter consolida os nós até zero
make k8s-delete       # remove o namespace e, com ele, o ALB
```

Para derrubar o cluster inteiro: `create_eks = false` no `terraform.tfvars` e
`make tf-apply`. ECS, RDS, ALB e ASG não referenciam nada dele e continuam de pé.
