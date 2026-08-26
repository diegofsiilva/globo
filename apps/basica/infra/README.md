# Infra — Argus v3

Terraform de dois fluxos de ingestão sobre um banco relacional:

```
App de TV  ──> API Gateway (ingestão) ──> SQS ──> ECS (event worker) ─┐
                                                                      ├──> RDS PostgreSQL ──> Lambda ──> Dashboard
Simulador  ──> API Gateway (mudanças) ──> SQS ──> ECS (merge worker) ─┘
```

> **Aplicado e validado** na AWS Academy Learner Lab (profile `g4`, us-east-1).
> Ver [§ AWS Academy](#aws-academy--learner-lab) para as adaptações que esse
> ambiente exige — elas não são poucas.

O desenho e os porquês estão em [`artefatos/arquitetura.md`](../../artefatos/arquitetura.md)
e na [arquitetura do Argus v3](../../artefatos/arquitetura-inicial.md).

---

## Antes do primeiro apply

### 1. Escolher a conta

O Terraform usa as credenciais padrão do ambiente. Confira **antes** de aplicar:

```bash
export AWS_PROFILE=g4
export AWS_REGION=us-east-1
aws sts get-caller-identity --profile g4
aws ec2 describe-vpcs --profile g4 --max-results 5
```

> **O id da conta do Learner Lab muda a cada sessão nova.** O `existing_role_arn`
> do `terraform.tfvars` carrega esse id: se ele estiver de uma sessão anterior, o
> apply falha (ou, pior, o state passa a descrever uma conta que já não existe).
> Confira e atualize antes de todo apply em conta nova.

Todo comando `aws` deste projeto leva `--profile g4`. Sem ele a CLI cai no
profile default, que é outra conta. O Terraform não tem a opção `--profile`:
ele lê `AWS_PROFILE`, por isso os dois `export` acima também são obrigatórios
antes de `plan` e `apply`.

### 2. Estado remoto (recomendado)

Sem backend remoto, o `terraform.tfstate` fica no disco de quem aplicou: mais
ninguém consegue rodar `apply`, e se a máquina morrer o Terraform perde a
referência de tudo que criou. Veja `backend.tf.example`.

No Learner Lab isso tem um agravante próprio: quando a conta é recriada, o state
antigo continua descrevendo recursos de uma conta morta. O `plan` fica coerente
consigo mesmo e completamente descolado da realidade.

### 3. Variáveis

```bash
cp terraform.tfvars.example terraform.tfvars
```

Os campos que exigem decisão são o `existing_role_arn` (acima), a senha do banco
e o `db_allowed_cidr` — o IP de onde você vai rodar `make migrate`.

---

## Deploy

O ECR nasce vazio, então **a ordem importa**: se você aplicar tudo de uma vez, os
services ECS ficam em crash loop até a primeira imagem existir. Não quebra nada,
mas assusta.

```bash
# 1. cria a infra sem os services
terraform init
terraform apply -var="worker_desired_count=0" -var="processing_desired_count=0"

# 2. publica as quatro imagens (a sequência sai pronta do output)
terraform output -raw docker_push_commands | bash

# 3. aplica as migrations e cria o usuário de leitura
terraform output -raw database_url_hint     # mostra como montar a URL
cd ../.. && make -C basica migrate
DB_READER_PASSWORD=<a mesma do tfvars> make -C basica db-reader

# 4. carga inicial das 33 tabelas (20 a 30 min)
make -C basica origem-sync
make -C basica load

# 5. liga os services
cd basica/infra && terraform apply
```

São **quatro** imagens, não uma:

| Imagem | Serviço |
|---|---|
| `worker` | merge worker **e** event worker — a mesma imagem, `command` diferente |
| `simulator` | relógio virtual e emissor de mudanças |
| `processing` | ETL incremental (bronze->silver e silver->gold); detector e canário seguem no-op |
| `loader` | carga inicial, task one-shot |

O build tem contexto em `apps/basica/` e não na pasta de cada app, porque todas
dependem de `common/`, que fica fora delas:

```bash
docker build --platform linux/arm64 -f worker/Dockerfile -t argus-worker:dev .
```

### Validar

```bash
URL=$(terraform output -raw ingest_url)
python ../tools/replay_events.py --url "$URL" --src ~/Downloads/Events

make -C .. count                                    # linhas por camada
aws logs tail "$(terraform output -json log_groups | jq -r .worker)" --follow --profile g4
```

### Deploys seguintes

Prefira a tag pelo SHA do commit a `latest` — `latest` torna impossível saber o
que está rodando e impede rollback:

```bash
TAG="sha-$(git rev-parse --short HEAD)"
terraform apply -var="worker_image_tag=$TAG"
```

Os services usam `deployment_circuit_breaker` com rollback: imagem quebrada volta
sozinha para a versão anterior.

---

## Operação

### O relógio virtual

O simulador anda um relógio próprio (`sim.clock`), e é ele que define o "agora"
de todo o sistema. Duas consequências práticas:

```bash
# quantas horas virtuais o pipeline está atrás da origem
psql "$DATABASE_URL" -c "SELECT sim.now(), speed FROM sim.v_clock"

# desligar o simulador congela o presente onde ele parou
make -C .. sim-off
```

Deixe o simulador desligado até a carga inicial terminar: simular mudança sobre
tabela vazia não produz nada.

### Ver o que está nas DLQs

São duas — eventos e mudanças:

```bash
make -C .. dlq
```

O atributo `FailureReason` diz por que a mensagem foi recusada e o corpo é o
payload original, intacto.

### Reprocessar uma DLQ

Depois de corrigir a causa, no console do SQS: DLQ → **Start DLQ redrive**. A
policy `redrive_allow_policy` já autoriza o caminho de volta para a fila
principal. Como a escrita é idempotente (o MERGE só sobrescreve quando o `_lsn`
que chega é maior que o corrente), reprocessar não duplica nem regride.

### Entrar no container

```bash
CLUSTER=$(terraform output -raw ecs_cluster_name)
aws ecs execute-command --cluster "$CLUSTER" --profile g4 \
  --task "$(aws ecs list-tasks --cluster "$CLUSTER" --profile g4 \
             --query 'taskArns[0]' --output text)" \
  --container merge-worker --interactive --command /bin/bash
```

### Métricas

Namespace `Argus/Ingestion`, dimensão `Service`:

| Métrica | O que significa |
|---|---|
| `ItemsReceived` | itens que chegaram da fila (evento ou mudança) |
| `ItemsWritten` | linhas efetivamente gravadas |
| `ItemsQuarantined` | itens desviados para a DLQ |
| `ItemsDeduplicated` | duplicatas colapsadas — é a taxa de reentrega do SQS |
| `ChangesMerged` | mudanças aplicadas na tabela corrente pelo MERGE |
| `EventsUnknownType` | `event_name` que o worker ainda não conhece |
| `EventsIncomplete` | evento válido, mas sem campos recomendados |
| `WriteFailed` | itens que o banco recusou após os retries |
| `LagSimSeconds` | atraso do pipeline em tempo **virtual** |
| `SourcesSilent` | fontes que pararam de reportar |
| `CycleLatency` | tempo de **processamento** do ciclo, em ms |
| `PollWait` | quanto o long polling ficou bloqueado esperando, em ms |

`CycleLatency` e `PollWait` são separadas de propósito: o long polling bloqueia
até 20s esperando mensagem, e somar essa espera ociosa ao tempo de trabalho faria
a métrica reportar "13s de latência" quando o processamento real levou 400 ms.

`LagSimSeconds` é medida em tempo virtual e não em tempo de parede. Com
`simulator_speed = 60`, um minuto de relógio de parede são sessenta minutos
virtuais — um atraso de 30 s de parede é meia hora de atraso para quem olha o
dashboard. O merge worker publica a medida ao menos uma vez por minuto mesmo
com a fila vazia; repouso legítimo não vira ausência de dados no alarme.

`EventsUnknownType` subindo é o sinal de que o app começou a mandar um evento
novo — o dado já está sendo salvo, mas vale adicionar o tipo em
`worker/src/argus_worker/models.py` para ganhar validação.

### Alarmes

Onze, no tópico SNS (sem `alarm_email` preenchido, o tópico existe e ninguém é
avisado):

| Alarme | Dispara quando |
|---|---|
| `dlq_not_empty`, `changes_dlq_not_empty` | qualquer mensagem numa DLQ |
| `queue_backlog`, `changes_backlog` | fila acumulando além do limite |
| `servico_down` | um service ECS com menos tasks que o esperado |
| `api_5xx` | a API de leitura devolvendo erro |
| `rds_storage`, `rds_cpu`, `rds_conexoes` | o banco em aperto |
| `lag_sim` | o pipeline atrás demais em tempo virtual |
| `fonte_silenciosa` | fontes que pararam de reportar |

---

## Custo estimado (us-east-1)

| Item | Estimativa |
|---|---|
| RDS `db.t3.medium` + 100 GB gp3, 24/7 | ~US$ 62 |
| Fargate: 4 services de 0.25 vCPU / 0.5 GB ARM, 24/7 | ~US$ 36 |
| API Gateway HTTP API (duas APIs) | ~US$ 2 |
| SQS (duas filas) | ~US$ 0 (1 M req/mês no free tier) |
| S3 (origem versionado + site) | ~US$ 2 |
| CloudWatch Logs + 11 alarmes | ~US$ 4 |
| **Total** | **~US$ 106/mês** |

O RDS é o item dominante e é 24/7 por natureza — ele guarda o resultado da carga
inicial, então desligá-lo não é a mesma coisa que desligar um worker.

Para economizar crédito do lab, `make pause` zera os `desired_count` dos services
e deixa o banco de pé; só `terraform destroy` derruba tudo, **inclusive a carga**.

O item que **não** está aqui e seria o maior de todos é o NAT Gateway (~US$ 32/mês
+ tráfego). Ele é evitado por `assign_public_ip = true`.

---

## AWS Academy — Learner Lab

Três coisas do laboratório quebram um Terraform escrito para conta normal. As
três estão resolvidas por variável, sem bifurcar o código:

**1. `iam:CreateRole` é negado.** O ambiente obriga a usar a `LabRole` pronta.

```hcl
create_iam_roles  = false
existing_role_arn = "arn:aws:iam::<conta>:role/LabRole"
```

A `LabRole` confia em `apigateway.amazonaws.com`, `ecs-tasks.amazonaws.com` e
`lambda.amazonaws.com`, os três de que este stack precisa. Mas ela é **muito**
mais permissiva do que o necessário: numa conta normal deixe
`create_iam_roles = true` e cada componente ganha permissão mínima.

**2. O Secrets Manager é imprevisível no lab.** A senha do RDS pode vir do
`tfvars` em vez do Secrets Manager:

```hcl
db_password_from_secrets_manager = false
db_password                      = "..."
```

Isso só é aceitável porque `terraform.tfvars` está no `.gitignore`. Numa conta
normal, deixe `true` — a senha nasce aleatória e nunca toca o disco.

**3. Nem toda classe de instância é ofertável.** Antes do primeiro apply em conta
nova, confirme:

```bash
aws rds describe-orderable-db-instance-options --profile g4 \
  --engine postgres --engine-version 16 \
  --query 'OrderableDBInstanceOptions[].DBInstanceClass' --output text
```

**Credenciais expiram.** A sessão do laboratório vence em algumas horas. Quando
vence, a AWS anexa uma policy `voc-cancel-cred` que **nega tudo** — os comandos
falham com `AccessDenied ... explicit deny`, e não com `ExpiredToken`, o que
confunde. `sts get-caller-identity` continua respondendo mesmo assim. Reinicie o
lab e atualize o profile `g4`.

**Crédito é limitado.** Para pausar sem destruir nada:

```bash
make -C .. pause      # zera os services, mantém o banco e a carga
make -C .. resume
terraform destroy     # remove tudo, inclusive as 68,7 M linhas
```

Com os workers parados, as APIs continuam aceitando e as filas retêm por 4 dias
— voltar retoma o consumo de onde parou.

---

## Rede: pública vs privada

O padrão é **subnet pública com IP público e security group sem regra de
entrada**. As tasks alcançam as APIs da AWS pela internet, mas ninguém alcança as
tasks — não há porta aberta.

O RDS é a exceção: com `db_publicly_accessible = true` ele aceita conexão do
CIDR de `db_allowed_cidr` (o seu IP em /32), que é o que permite rodar
`make migrate` e inspecionar o banco sem bastion. Se você trocar de rede, o IP
muda e o acesso para até você atualizar a variável.

Para exigência de subnet privada, `assign_public_ip = false` exige uma destas:

- **NAT Gateway** — simples, ~US$ 32/mês + tráfego.
- **VPC endpoints** — sem NAT, mas precisa de *todos* estes, senão a task nem
  baixa a imagem e o service entra em crash loop:
  - Gateway (grátis): `s3`
  - Interface (~US$ 7/mês cada por AZ): `sqs`, `ecr.api`, `ecr.dkr`, `logs`,
    `secretsmanager`

---

## Destruir

```bash
make -C .. tf-destroy    # pede confirmação por escrito
```

Isso apaga o banco com as 33 tabelas. O bucket de origem tem versionamento, mas
também vai. Recarregar custa os 20–30 min da carga inicial mais o `origem-sync`.

Em `environment = "prod"` o RDS tem `deletion_protection` ligada: o destroy falha
de propósito. Para remover mesmo, mude para `false`, aplique, e só então destrua.

---

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `rds.tf` | instância PostgreSQL 16, subnet group, parameter group e segredo da senha |
| `s3_origem.tf` | bucket versionado com o dump e os Parquet da carga inicial |
| `sqs.tf` | fila de eventos, DLQ, redrive e policy restringindo o publisher à API |
| `sqs_changes.tf` | fila de mudanças, DLQ e policy |
| `apigateway.tf` | HTTP API de ingestão, integração direta `SQS-SendMessage` |
| `apigateway_changes.tf` | HTTP API de mudanças, mesma integração |
| `ecs.tf` | cluster, security group, log groups e os dois workers |
| `ecs_simulator.tf` | service do simulador |
| `ecs_processing.tf` | service de processamento |
| `ecs_loader.tf` | task definition one-shot da carga inicial |
| `ecr.tf` | um repositório por imagem, com lifecycle policy |
| `api_read.tf` | Lambda da API de leitura e o HTTP API na frente dela |
| `frontend_s3.tf` | bucket do dashboard, com website hosting |
| `iam.tf` | execution role e task role, separadas |
| `observability.tf` | SNS e os 11 alarmes |
| `locals.tf` | lookup da VPC/subnets default e a lista de imagens |
| `outputs.tf` | endpoints, nomes de recurso e comandos prontos (push, carga) |
