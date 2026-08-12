# Infra — fluxo de ingestão de eventos

Terraform do fluxo `API Gateway → SQS → ECS Fargate → DynamoDB`.

> **Aplicado e validado** na AWS Academy Learner Lab (conta `<conta>`,
> profile `g4`, us-east-1). Ver [§ AWS Academy](#aws-academy--learner-lab) para
> as adaptações que esse ambiente exige.

O desenho e os porquês estão em [`../artefatos/arquitetura_ingestao.md`](../artefatos/arquitetura_ingestao.md).

---

## Antes do primeiro apply

### 1. Escolher a conta

O Terraform usa as credenciais padrão do ambiente. Confira **antes** de aplicar:

```bash
aws sts get-caller-identity
```

> A conta usada durante o desenvolvimento (`619071345960`) tem workload de outros
> projetos (`norya-*`, `remax-*`). Todo recurso aqui é prefixado com
> `argus-events-<ambiente>` e o `plan` confirmou `0 to change, 0 to destroy` —
> mas confirme a conta mesmo assim.

Para usar outra conta/perfil:

```bash
export AWS_PROFILE=argus
# ou
export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=...
```

### 2. Estado remoto (recomendado)

Sem backend remoto, o `terraform.tfstate` fica no disco de quem aplicou: mais
ninguém consegue rodar `apply`, e se a máquina morrer o Terraform perde a
referência de tudo que criou. Veja `backend.tf.example`.

### 3. Variáveis

```bash
cp terraform.tfvars.example terraform.tfvars
```

---

## Deploy

O ECR nasce vazio, então **a ordem importa**: se você aplicar tudo de uma vez, o
service ECS fica em crash loop até a primeira imagem existir. Não quebra nada,
mas assusta.

```bash
# 1. cria a infra sem o service
terraform init
terraform apply -var="worker_desired_count=0"

# 2. publica a imagem
terraform output -raw docker_push_commands   # imprime a sequência pronta

aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin \
      "$(aws sts get-caller-identity --query Account --output text)".dkr.ecr.us-east-1.amazonaws.com

REPO=$(terraform output -raw ecr_repository_url)
docker build --platform linux/arm64 -t "$REPO:latest" ../worker
docker push "$REPO:latest"

# 3. liga o worker
terraform apply -var="worker_desired_count=1"
```

### Validar

```bash
URL=$(terraform output -raw ingest_url)
python ../tools/replay_events.py --url "$URL" --src ~/Downloads/Events

aws dynamodb scan --table-name "$(terraform output -raw table_name)" --select COUNT
aws logs tail "$(terraform output -raw log_group_worker)" --follow
```

### Deploys seguintes

Prefira a tag pelo SHA do commit a `latest` — `latest` torna impossível saber o
que está rodando e impede rollback:

```bash
TAG="sha-$(git rev-parse --short HEAD)"
docker build --platform linux/arm64 -t "$REPO:$TAG" ../worker
docker push "$REPO:$TAG"
terraform apply -var="worker_image_tag=$TAG"
```

O service usa `deployment_circuit_breaker` com rollback: imagem quebrada volta
sozinha para a versão anterior.

---

## Operação

### Ver o que está na DLQ

```bash
aws sqs receive-message --queue-url "$(terraform output -raw dlq_url)" \
  --message-attribute-names All --max-number-of-messages 10
```

O atributo `FailureReason` diz por que o evento foi recusado e o corpo é o
payload original, intacto.

### Reprocessar a DLQ

Depois de corrigir a causa, no console do SQS: DLQ → **Start DLQ redrive**. A
policy `redrive_allow_policy` já autoriza o caminho de volta para a fila
principal. Como a escrita é idempotente, reprocessar não duplica.

### Entrar no container

```bash
aws ecs execute-command --cluster "$(terraform output -raw ecs_cluster_name)" \
  --task "$(aws ecs list-tasks --cluster "$(terraform output -raw ecs_cluster_name)" \
             --query 'taskArns[0]' --output text)" \
  --container worker --interactive --command /bin/bash
```

### Métricas

Namespace `Argus/Ingestion`, dimensão `Service`:

| Métrica | O que significa |
|---|---|
| `EventsReceived` | eventos que chegaram da fila |
| `EventsWritten` | linhas efetivamente gravadas (já sem duplicatas) |
| `EventsQuarantined` | eventos desviados para a DLQ |
| `EventsDeduplicated` | duplicatas colapsadas — é a taxa de reentrega do SQS |
| `EventsUnknownType` | `event_name` que o worker ainda não conhece |
| `EventsIncomplete` | evento válido, mas sem campos recomendados |
| `EventsWriteFailed` | itens que o DynamoDB recusou após os retries |
| `CycleLatency` | tempo de **processamento** do ciclo, em ms (não inclui a espera do polling) |
| `PollWait` | quanto o long polling ficou bloqueado esperando mensagem, em ms |

`CycleLatency` e `PollWait` são separadas de propósito: o long polling bloqueia
até 20s esperando mensagem, e somar essa espera ociosa ao tempo de trabalho faria
a métrica reportar "13s de latência" quando o processamento real levou 400 ms.

`EventsUnknownType` subindo é o sinal de que o app começou a mandar um evento
novo — o dado já está sendo salvo, mas vale adicionar o tipo em
`worker/src/argus_worker/models.py` para ganhar validação.

---

## Custo estimado (us-east-1, ~1 M eventos/mês)

| Item | Estimativa |
|---|---|
| Fargate 0.25 vCPU / 0.5 GB ARM, 24/7 | ~US$ 9 |
| DynamoDB on-demand (escrita + 2 GSI) | ~US$ 4 |
| API Gateway HTTP API | ~US$ 1 |
| SQS | ~US$ 0 (1 M req/mês no free tier) |
| CloudWatch Logs + alarmes | ~US$ 2 |
| **Total** | **~US$ 16/mês** |

Cada GSI multiplica o custo de escrita: uma escrita na tabela vira três (tabela
+ gsi1 + gsi2). Se o volume crescer muito e a GSI2 (histórico por aparelho) não
estiver sendo consultada, removê-la corta ~1/3 do custo de escrita.

O item que **não** está aqui e seria o maior de todos é o NAT Gateway (~US$ 32/mês
+ tráfego). Ele é evitado por `assign_public_ip = true`.

---

## AWS Academy — Learner Lab

Duas coisas do laboratório quebram um Terraform escrito para conta normal. Ambas
estão resolvidas por variável, sem bifurcar o código:

**1. `iam:CreateRole` é negado.** O ambiente obriga a usar a `LabRole` pronta.

```hcl
create_iam_roles  = false
existing_role_arn = "arn:aws:iam::<conta>:role/LabRole"
```

A `LabRole` confia em `apigateway.amazonaws.com` e `ecs-tasks.amazonaws.com`, os
dois de que este fluxo precisa. Mas ela é **muito** mais permissiva do que o
necessário: numa conta normal deixe `create_iam_roles = true` e cada componente
ganha permissão mínima (o worker, por exemplo, só recebe `PutItem` e
`BatchWriteItem` — nem `DeleteItem` ele tem).

**2. A chave KMS gerenciada `aws/dynamodb` não existe** e o laboratório não a
provisiona. O `CreateTable` falha com `KMS validation error ... does not exist`.

```hcl
dynamodb_kms_managed_key = false
```

Isso **não** deixa a tabela sem criptografia: o DynamoDB criptografa em repouso
sempre. A flag só troca a chave *AWS-managed* (visível no KMS, auditável por
CloudTrail, ~US$ 1/mês) pela *AWS-owned* (padrão, gratuita).

**Credenciais expiram.** A sessão do laboratório vence em algumas horas. Se um
comando falhar com `ExpiredToken`, reinicie o lab e atualize o profile `g4`.

**Crédito é limitado.** O Fargate roda 24/7. Para pausar sem destruir nada:

```bash
terraform apply -var="worker_desired_count=0"   # para o worker, mantém a infra
terraform destroy                                # remove tudo
```

Com o worker parado, a API continua aceitando eventos e a fila os retém por 4
dias — voltar para `1` retoma o consumo de onde parou.

---

## Rede: pública vs privada

O padrão é **subnet pública com IP público e security group sem regra de
entrada**. A task alcança as APIs da AWS pela internet, mas ninguém alcança a
task — não há porta aberta.

Para exigência de subnet privada, `assign_public_ip = false` exige uma destas:

- **NAT Gateway** — simples, ~US$ 32/mês + tráfego.
- **VPC endpoints** — sem NAT, mas precisa de *todos* estes, senão a task nem
  baixa a imagem e o service entra em crash loop:
  - Gateway (grátis): `s3`, `dynamodb`
  - Interface (~US$ 7/mês cada por AZ): `sqs`, `ecr.api`, `ecr.dkr`, `logs`

---

## Destruir

```bash
terraform destroy
```

Em `environment = "prod"` a tabela tem `deletion_protection_enabled = true`: o
destroy falha de propósito. Para remover mesmo, mude para `false`, aplique, e só
então destrua.

---

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `dynamodb.tf` | tabela única + GSI1 (tipo/dia, com shard) + GSI2 (aparelho) + TTL |
| `sqs.tf` | fila, DLQ, redrive e policy restringindo o publisher à API |
| `apigateway.tf` | HTTP API com integração direta `SQS-SendMessage` |
| `ecs.tf` | cluster, task definition, service e security group |
| `iam.tf` | execution role e task role, separadas |
| `ecr.tf` | repositório e lifecycle policy |
| `observability.tf` | log groups, SNS e 5 alarmes |
| `locals.tf` | lookup da VPC/subnets default |
