# Infra — Argus v3

Terraform de dois fluxos de ingestão sobre um banco relacional:

```
App de TV  ──> API Gateway (ingestão) ──> SQS ──> ECS (event worker) ─┐
                                                                      ├──> RDS PostgreSQL ──> Lambda ──> Dashboard
Simulador  ──> API Gateway (mudanças) ──> SQS ──> ECS (merge worker) ─┘
```

> **Aplicado e validado** na AWS Academy Learner Lab (profile `g4`, us-east-1).
> Ver [§ AWS Academy](#aws-academy--learner-lab) para as adaptações que esse
> ambiente exige; elas não são poucas.

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
procuram uma tag que ainda não existe no ECR e entram em `ImagePullBackOff`, com
o erro aparecendo como "imagem não encontrada", longe da linha que o causou.

```bash
cd ../..                              # raiz do repositório
export AWS_PROFILE=g4 AWS_REGION=us-east-1
aws sts get-caller-identity --profile g4 --query Account --output text

make -C apps/fullstack check             # portão de qualidade
make -C apps/fullstack push              # 1. imagens PRIMEIRO, com a tag do commit
make -C apps/fullstack tf-plan           # 2. revise
make -C apps/fullstack tf-apply          #    aplica
make -C apps/fullstack auth-rotate       # 3. gera os tokens (imprime UMA vez)
make -C apps/fullstack migrate-status-aws
make -C apps/fullstack migrate-aws       # 4. migrations pela VPC
make -C apps/fullstack frontend-deploy   # 5. dashboard no website S3
make -C apps/fullstack smoke             # 6. 401/403/200, latência e tamanho
```

**Entre o `tf-apply` e o `auth-rotate` a API responde 403 em tudo.** O segredo
nasce vazio e o authorizer falha fechado, que é o comportamento correto e não um
defeito. Faça os dois na mesma sessão.

O `tf-apply` cria o endpoint de website do S3 e libera leitura pública somente
dos objetos do dashboard. Entre o primeiro apply e o `frontend-deploy`, o
endpoint existe, mas ainda não contém o build atual.

Numa conta nova, onde o ECR nasce vazio e não há banco, acrescente antes do
passo 3:

```bash
terraform apply -var="worker_desired_count=0" \
                -var="processing_desired_count=0" \
                -var="simulator_desired_count=0"
make -C apps/fullstack db-url
DB_READER_PASSWORD=<a mesma do tfvars> make -C apps/fullstack db-reader
make -C apps/fullstack origem-sync
make -C apps/fullstack load              # 20 a 30 min, 68,7 M linhas
```

### Conferir o que ficou no ar

```bash
make -C apps/fullstack digests      # cada serviço roda a tag do commit?
make -C apps/fullstack lambda-hash  # hash local == CodeSha256 publicado?
cd apps/fullstack/infra && terraform plan   # tem que dar zero mudanças
```

São **quatro** imagens, não uma:

| Imagem | Serviço |
|---|---|
| `worker` | merge worker **e** event worker — a mesma imagem, `command` diferente |
| `simulator` | relógio virtual e emissor de mudanças |
| `processing` | ETL incremental (bronze->silver e silver->gold); detector e canário seguem no-op |
| `loader` | carga inicial, task one-shot |

O build tem contexto em `apps/fullstack/` e não na pasta de cada app, porque todas
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
validação: com `latest` a task definition não muda quando a imagem muda, o
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

São duas, de eventos e de mudanças:

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
virtuais: um atraso de 30 s de parede é meia hora de atraso para quem olha o
dashboard. O merge worker publica a medida ao menos uma vez por minuto mesmo
com a fila vazia; repouso legítimo não vira ausência de dados no alarme.

`EventsUnknownType` subindo é o sinal de que o app começou a mandar um evento
novo; o dado já está sendo salvo, mas vale adicionar o tipo em
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

O RDS é o item dominante e é 24/7 por natureza, porque guarda o resultado da carga
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
`lambda.amazonaws.com`. Mas ela é **muito** mais permissiva do que o necessário:
numa conta normal deixe `create_iam_roles = true` e cada componente ganha
permissão mínima.

A lista de confiança tem 53 serviços e **`vpc-flow-logs.amazonaws.com` não está
entre eles**, verificado na conta. Por isso `flow_logs_destination` tem `s3`
como padrão: esse destino usa política de bucket em vez de papel IAM. O caminho
do CloudWatch é criado sem erro e simplesmente nunca escreve, que é o pior modo
de falha possível para uma evidência de entrega.

```bash
aws iam get-role --role-name LabRole --profile g4 \
  --query 'Role.AssumeRolePolicyDocument.Statement[].Principal.Service' --output json
```

**2. O Secrets Manager é imprevisível no lab.** A senha do RDS pode vir do
`tfvars` em vez do Secrets Manager:

```hcl
db_password_from_secrets_manager = false
db_password                      = "..."
```

Isso só é aceitável porque `terraform.tfvars` está no `.gitignore`. Numa conta
normal, deixe `true`: a senha nasce aleatória e nunca toca o disco.

**3. Nem toda classe de instância é ofertável.** Antes do primeiro apply em conta
nova, confirme:

```bash
aws rds describe-orderable-db-instance-options --profile g4 \
  --engine postgres --engine-version 16 \
  --query 'OrderableDBInstanceOptions[].DBInstanceClass' --output text
```

**4. A SCP da organização nega `s3:GetBucketObjectLockConfiguration`.** O provider
AWS chama exatamente essa API ao reler qualquer `aws_s3_bucket` recém-criado. O
bucket nasce, o `apply` falha na releitura, e o recurso fica no estado quebrando
todo `plan` seguinte. Apenas essa chamada é negada: `GetBucketPolicy`,
`GetPublicAccessBlock`, `GetBucketEncryption`, `GetBucketLifecycleConfiguration`
e `GetBucketVersioning` passam.

Os buckets desta camada aceitam um nome criado fora do Terraform, e continuam
com política, bloqueio público, criptografia e ciclo de vida gerenciados aqui:

```hcl
flow_logs_bucket_name = "argus-flow-logs-<conta>"
alb_logs_bucket_name  = "argus-alb-logs-<conta>"
```

A restrição atinge igualmente `aws_s3_bucket.origem` e `aws_s3_bucket.frontend`,
que são anteriores a esta entrega e ainda não têm a mesma válvula. O paliativo
para eles é `terraform plan -refresh=false`, já que estão no estado e sem refresh
o provider não os relê.

**Credenciais expiram.** A sessão do laboratório vence em algumas horas. Quando
vence, a AWS anexa uma policy `voc-cancel-cred` que nega tudo, e os comandos
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
Voltar retoma o consumo de onde parou.

---

## Rede: pública vs privada

O padrão é a **VPC dedicada** de `vpc.tf` (`create_network = true`): duas
sub-redes públicas e duas privadas, em duas AZs, com NAT Gateway.

O que separa pública de privada não é nada na sub-rede: é a tabela de rota
associada a ela. A pública roteia `0.0.0.0/0` para o Internet Gateway, que é
simétrico (deixa sair e deixa entrar). A privada roteia para o NAT Gateway, que
é assimétrico: a máquina de dentro inicia conexão para fora e a resposta volta,
mas ninguém de fora consegue iniciar conexão para dentro, porque não existe
caminho de entrada.

| Sub-rede | Quem mora lá |
|---|---|
| Pública | ALB do Ingress do EKS, NAT Gateway, bastion — os únicos com motivo para ter endereço roteável |
| Privada | nós do EKS, tasks Fargate, Lambda de leitura, subnet group do RDS |

Antes desta camada, as tasks rodavam na VPC default com `assign_public_ip =
true`. O único controle que impedia alguém de alcançá-las era o security group
sem regra de entrada. Com sub-rede privada some também a rota: **dois controles
independentes em vez de um**.

As duas chaves andam juntas, e o Terraform recusa a combinação errada já no
`plan`. `create_network = true` com `assign_public_ip = true` põe a task numa
sub-rede sem rota para o IGW, onde o endereço público não serve para nada e o
pull do ECR falha.

Um **gateway endpoint de S3** (grátis) está associado à tabela de rota privada.
Ele tira do NAT os ~200 MB de Parquet que o `loader` lê por carga, e o NAT
cobra por GB trafegado.

**Um NAT, não um por AZ.** A recomendação da AWS para produção é um por zona,
para que a queda de uma não leve junto a saída da outra. Aqui é um só, por custo
(~US$ 32/mês cada). A consequência está assumida: se a AZ do NAT cair, os nós
da outra zona continuam servindo tráfego pelo ALB do Ingress, porque o caminho de
leitura não passa pelo NAT, mas perdem a saída para a internet.

**Trocar de rede recria o banco.** A AWS não move uma instância RDS entre VPCs, e
um subnet group só aceita sub-redes da própria VPC. Tire um snapshot manual antes
de ligar ou desligar `create_network` num ambiente já aplicado.

O RDS **não é exceção** à postura privada: ele aceita conexão apenas dos security
groups autorizados. Não há regra para CIDR externo.

Até a adequação do RNF09 o banco era público, restrito ao IP de quem estava
trabalhando. A exposição do dado do parceiro dependia de uma linha de `tfvars` e
da rede do momento: trocar de rede quebrava o acesso, e esquecer de reverter
deixava a instância alcançável de fora. Migrations e inspeção agora usam:

```bash
make -C .. migrate-status-aws
make -C .. migrate-aws
```

### Caminho EC2 da Sprint 3 (removido na Sprint 4)

Caminho EC2 (ASG+ALB) da Sprint 3 removido na Sprint 4; a leitura pública vem
do Ingress do EKS (ver `../k8s/README.md`) e, como contingência, da Lambda
(`terraform output read_api_url`). `ec2_api.tf.example` continua no repositório
só como exemplo comentado da equivalência com EC2, e não faz parte do estado.

### Saída da sub-rede privada: NAT ou endpoints

Para exigência de subnet privada, `assign_public_ip = false` exige uma destas:

- Gateway (grátis): `s3`, que já existe e é complementar ao NAT
- Interface (~US$ 7/mês cada por AZ): `sqs`, `ecr.api`, `ecr.dkr`, `logs`,
  `secretsmanager`

Cinco interfaces em duas AZs passam de US$ 70/mês contra os ~US$ 32 do NAT.

### Ligar a rede dedicada num stack que já existe

**A AWS não move uma instância RDS entre VPCs.** Um subnet group só pode conter
sub-redes da mesma VPC da instância, então trocar a rede recria o banco, e com ele
as 33 tabelas carregadas.

```bash
# 1. Rede de segurança, antes de qualquer coisa.
aws rds create-db-snapshot \
  --db-instance-identifier argus-events-<env> \
  --db-snapshot-identifier argus-events-<env>-pre-vpc

# 2. Aplique.
make -C .. tf-plan          # confira: a instância RDS aparece como replace
make -C .. tf-apply

# 3. Reconstrua o schema e a carga.
make -C .. migrate-aws
make -C .. load
```

`make load` é o percurso mais testado do projeto, exercitado a cada recriação
da conta do Learner Lab. Se houver dado produzido pelo simulador que a carga
inicial não reproduza, restaure do snapshot em vez de recarregar.

**Valide o NAT antes de depender dele.** Entre criar a rede e mover os serviços,
suba uma task avulsa na sub-rede privada e confirme que ela alcança a AWS. Sem
esse passo, uma task em crash loop tem duas causas possíveis e nenhuma pista: rota
de saída ausente e defeito de aplicação são indistinguíveis pelo sintoma.

### Voltar atrás

As duas chaves andam juntas, e uma não vale sem a outra:

```hcl
create_network   = false   # volta a consumir a VPC default da conta
assign_public_ip = true    # task em sub-rede pública, sem NAT
```

`create_network = false` com `assign_public_ip = false` deixa a task sem rota
nenhuma para o ECR: ela não baixa a imagem e o service entra em crash loop. A
combinação oposta, `create_network = true` com `assign_public_ip = true`, é recusada
no `plan`, porque põe a task numa sub-rede sem rota para o Internet Gateway.

Voltar atrás **também recria o banco**, pelo mesmo motivo da ida. Snapshot antes.

---

## Observabilidade da rede: Flow Logs

Os alarmes de `observability.tf` medem a aplicação: profundidade de fila,
DLQ, CPU do banco, lag do simulador. Nenhum enxerga a rede. Os VPC Flow Logs
preenchem esse buraco: registram todo fluxo `ACCEPT` e `REJECT` nas interfaces
da VPC, com origem, destino, porta e bytes.

Na prática é o que responde, sem instrumentar nada:

- a task **está mesmo saindo pelo NAT**? (`ACCEPT` de um IP `10.0.1x.x` para fora)
- quem está batendo na 5432 e sendo recusado? (`REJECT` para o IP do banco)

`traffic_type = "ALL"`, e não `REJECT`: o rejeitado sozinho conta metade da
história, e é o `ACCEPT` que prova que a máquina privada saiu.

O formato é explícito, e não o padrão, porque o padrão **não traz**
`pkt-srcaddr` e `pkt-dstaddr`, que são o endereço real antes da tradução do NAT. Sem eles
todo tráfego de saída das sub-redes privadas aparece vindo do NAT, e fica
impossível dizer *qual* instância falou com quem.

A agregação está em **60 segundos** em vez dos 600 do padrão. Numa apresentação,
esperar dez minutos pelo primeiro registro é a diferença entre mostrar a
evidência e falar sobre ela. No destino S3 ainda há a latência própria da
entrega, de cerca de cinco minutos, que esse parâmetro não encurta.

**O destino padrão é S3**, pela restrição da `LabRole` descrita na seção AWS
Academy. Numa conta normal, `flow_logs_destination = "cloudwatch"` é melhor: o
Logs Insights consulta os registros com uma linguagem de consulta, sem baixar
arquivo.

Os comandos que fecham a evidência da cláusula sem abrir o console (um mostra as
rotas, com `0.0.0.0/0` para o IGW numa tabela e para o NAT na outra; o outro despeja
os registros de fluxo já capturados):

```bash
VPC=$(terraform output -raw vpc_id)

aws ec2 describe-route-tables --filters Name=vpc-id,Values=$VPC \
  --query 'RouteTables[].{Tabela:Tags[?Key==`Name`]|[0].Value,
            Rotas:Routes[].{Destino:DestinationCidrBlock,IGW:GatewayId,NAT:NatGatewayId}}' \
  --output json

aws ec2 describe-subnets --filters Name=vpc-id,Values=$VPC \
  --query 'Subnets[].{Nome:Tags[?Key==`Name`]|[0].Value,CIDR:CidrBlock,
            AZ:AvailabilityZone,IPPublico:MapPublicIpOnLaunch}' \
  --output table

# Onde ler os fluxos, conforme o destino configurado
terraform output flow_log_destino
aws s3 ls --recursive "$(terraform output -raw flow_log_destino)/" | tail -20
```

---

## Segurança e lacunas conhecidas

**Superfície de rede.** As tasks ficam em sub-rede **privada**, sem endereço
público, e alcançam a AWS pelo NAT Gateway; o security group continua sem regra
de entrada. São dois controles independentes: não há regra que autorize entrada e
não há rota por onde ela chegaria. O RDS é privado e só aceita conexão dos
security groups autorizados; não há porta aberta para fora da VPC.

Com `create_network = false` o desenho volta ao anterior, de sub-rede pública com IP
público, e aí o security group passa a ser o único controle.

**Dado pessoal.** A API de leitura remove identificadores e cabeçalhos sensíveis
na resposta (RNF10). O evento cru fica no banco, com criptografia em repouso, e o
usuário `argus_reader` que a Lambda usa só tem `SELECT` nas views `v_*`.

**Autenticação (RNF09).** As duas HTTP APIs ficam atrás de um Lambda authorizer do
tipo `REQUEST`, com cache de cinco minutos por token no API Gateway. São dois
tokens aleatórios de 256 bits, um por audiência: `dashboard` para leitura e `ingest`
para escrita. Um não vale no lugar do outro, o que impede que a
credencial exposta no navegador do operador sirva também para injetar evento no
pipeline. `auth-rotate` valida as duas publicações e limpa esse cache; por isso o
token novo vale imediatamente. Se apenas a limpeza falhar, os tokens continuam
publicados, o alvo avisa que o antigo pode valer por até cinco minutos e termina
com erro.

O Secrets Manager guarda apenas o **SHA-256** de cada token. O valor em claro
existe no terminal de quem rodou `make auth-rotate`, que o imprime uma única vez, e
e, só no caso do de ingestão, num segundo segredo que a task do simulador lê pelo bloco
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
que não carrega `Authorization`; protegidas, devolveriam 401 antes de a página
renderizar, e não haveria onde clicar em "Authorize". Elas expõem a forma da API,
nunca dado; toda rota que devolve dado continua exigindo o Bearer.

**Limitação assumida:** o token identifica um *serviço*, não uma pessoa. Não há
como saber qual integrante fez uma consulta, e a resposta a um vazamento é
rotacionar, não revogar um usuário. Identidade individual exigiria Cognito.

**Transporte: limitação temporária do Learner Lab.** O papel `voclabs` desta
conta não permite criar Origin Access Control, CloudFront Function nem Response
Headers Policy. Por isso o dashboard voltou ao endpoint de website do S3, que
serve somente HTTP e exige leitura pública dos objetos. A API e os dados
continuam protegidos pelo Bearer, mas uma página carregada por HTTP não protege
o token que o operador cola: um intermediário de rede pode ler ou alterar a
página e capturá-lo. Use apenas em rede confiável e restaure CloudFront antes de
tratar este ambiente como produção.

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
| `observability.tf` | SNS, os 11 alarmes e o painel do CloudWatch |
| `vpc.tf` | VPC dedicada, sub-redes, IGW, NAT, tabelas de rota e gateway endpoint de S3 |
| `vpc_logs.tf` | VPC Flow Logs (S3 ou CloudWatch) e access logs do ALB |
| `bastion.tf` | bastion host e as regras de acesso administrativo |
| `eks.tf` | cluster EKS Auto Mode do caminho síncrono (o ALB nasce do Ingress em `../k8s/`) |
| `locals.tf` | resolução da rede, papéis e a lista de imagens |
| `outputs.tf` | endpoints, nomes de recurso e comandos prontos (push, carga) |
