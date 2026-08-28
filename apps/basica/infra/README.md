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

O desenho e os porquês estão na [arquitetura do Argus v3](../../../artefatos/arquitetura-inicial.md)
e no [plano da v3](../../../artefatos/plano-argus-v3.md).

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

Os campos que exigem decisão são o `existing_role_arn` (acima) e a senha do
banco. `db_allowed_cidr` fica **vazio**: o RDS é privado e o acesso
administrativo passa pela task `migration`, dentro da VPC.

---

## Deploy

**A ordem importa, e não é a intuitiva.** As task definitions referenciam a
imagem pelo SHA do commit; se o `apply` rodar antes do `push`, os serviços
procuram uma tag que ainda não existe no ECR e entram em `ImagePullBackOff` — com
o erro aparecendo como "imagem não encontrada", longe da linha que o causou.

```bash
cd ../..                              # raiz do repositório
export AWS_PROFILE=g4 AWS_REGION=us-east-1
aws sts get-caller-identity --profile g4 --query Account --output text

make -C apps/basica check             # portão de qualidade
make -C apps/basica push              # 1. imagens PRIMEIRO, com a tag do commit
make -C apps/basica tf-plan           # 2. revise
make -C apps/basica tf-apply          #    aplica
make -C apps/basica auth-rotate       # 3. gera os tokens (imprime UMA vez)
make -C apps/basica migrate-status-aws
make -C apps/basica migrate-aws       # 4. migrations pela VPC
make -C apps/basica frontend-deploy   # 5. dashboard + invalidação do CloudFront
make -C apps/basica smoke             # 6. 401/403/200, latência e tamanho
```

**Entre o `tf-apply` e o `auth-rotate` a API responde 403 em tudo.** O segredo
nasce vazio e o authorizer falha fechado — é o comportamento correto, não um
defeito. Faça os dois na mesma sessão.

O `tf-apply` também **desativa o endpoint de website do S3** e torna o bucket
privado. Entre ele e o `frontend-deploy`, o dashboard fica fora do ar.

Numa conta nova, onde o ECR nasce vazio e não há banco, acrescente antes do
passo 3:

```bash
terraform apply -var="worker_desired_count=0" \
                -var="processing_desired_count=0" \
                -var="simulator_desired_count=0"
make -C apps/basica db-url
DB_READER_PASSWORD=<a mesma do tfvars> make -C apps/basica db-reader
make -C apps/basica origem-sync
make -C apps/basica load              # 20 a 30 min, 68,7 M linhas
```

### Conferir o que ficou no ar

```bash
make -C apps/basica digests      # cada serviço roda a tag do commit?
make -C apps/basica lambda-hash  # hash local == CodeSha256 publicado?
cd apps/basica/infra && terraform plan   # tem que dar zero mudanças
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

`make push && make tf-apply`, nessa ordem. A tag sai do commit automaticamente
(`make image-tag` mostra qual é) e `worker_image_tag` recusa `latest` por
validação — com `latest` a task definition não muda quando a imagem muda, o
Terraform não propõe nada, e o serviço segue rodando o digest antigo. Foi assim
que os três serviços passaram a executar builds diferentes entre si sem nada
aparecer no `plan`.

Rollback é apontar o SHA anterior:

```bash
TF_VAR_worker_image_tag=<sha-anterior> make -C ../.. tf-apply
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

O RDS **não é exceção**: ele é privado e aceita conexão apenas do security
group das tasks. Não há regra para CIDR externo.

Até a adequação do RNF09 o banco era público, restrito ao IP de quem estava
trabalhando. A exposição do dado do parceiro dependia de uma linha de `tfvars` e
da rede do momento: trocar de rede quebrava o acesso, e esquecer de reverter
deixava a instância alcançável de fora. Migrations e inspeção agora usam:

```bash
make -C .. migrate-status-aws
make -C .. migrate-aws
```

Para exigência de subnet privada, `assign_public_ip = false` exige uma destas:

- **NAT Gateway** — simples, ~US$ 32/mês + tráfego.
- **VPC endpoints** — sem NAT, mas precisa de *todos* estes, senão a task nem
  baixa a imagem e o service entra em crash loop:
  - Gateway (grátis): `s3`
  - Interface (~US$ 7/mês cada por AZ): `sqs`, `ecr.api`, `ecr.dkr`, `logs`,
    `secretsmanager`

---

## Segurança e lacunas conhecidas

**Superfície de rede.** As tasks ficam em subnet pública com IP público e
security group sem regra de entrada: elas alcançam a AWS pela internet, mas
ninguém alcança as tasks. O RDS é privado e só aceita conexão do security group
das tasks — não há porta aberta para fora da VPC.

**Dado pessoal.** A API de leitura remove identificadores e cabeçalhos sensíveis
na resposta (RNF10). O evento cru fica no banco, com criptografia em repouso, e o
usuário `argus_reader` que a Lambda usa só tem `SELECT` nas views `v_*`.

**Autenticação (RNF09).** As duas HTTP APIs ficam atrás de um Lambda authorizer do
tipo `REQUEST`, com cache de cinco minutos por token. São dois tokens aleatórios
de 256 bits, um por audiência — `dashboard` para leitura, `ingest` para escrita —,
e um não vale no lugar do outro: isso impede que a credencial exposta no navegador
do operador sirva também para injetar evento no pipeline.

O Secrets Manager guarda apenas o **SHA-256** de cada token. O valor em claro
existe no terminal de quem rodou `make auth-rotate`, que o imprime uma única vez, e
— só o de ingestão — num segundo segredo que a task do simulador lê pelo bloco
`secrets` da task definition. Usar `environment` ali exporia o token em qualquer
`aws ecs describe-task-definition`.

```bash
make -C .. auth-rotate        # gera os dois, grava os hashes, imprime uma vez
make -C .. auth-show-ingest   # relê o de ingestao (o de leitura nao e recuperavel)
```

Sem o cabeçalho, o API Gateway responde **401** sem invocar a função; com token
inválido, **403**.

Três rotas ficam públicas: `GET /health/live` (sonda de vida) e `GET /docs` +
`GET /openapi.json`. As duas últimas porque o Swagger UI é aberto por navegação,
que não carrega `Authorization` — protegidas, devolveriam 401 antes de a página
renderizar, e não haveria onde clicar em "Authorize". Elas expõem a forma da API,
nunca dado; toda rota que devolve dado continua exigindo o Bearer.

**Limitação assumida:** o token identifica um *serviço*, não uma pessoa. Não há
como saber qual integrante fez uma consulta, e a resposta a um vazamento é
rotacionar, não revogar um usuário. Identidade individual exigiria Cognito.

**Transporte.** O bucket do dashboard é privado; quem serve é o CloudFront, com
HTTPS obrigatório e Origin Access Control. O endpoint de website do S3, que só
falava HTTP, foi desativado — numa página HTTP qualquer intermediário leria o token
que o operador cola na tela de acesso.

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
