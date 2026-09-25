# AGENTS.md — infraestrutura

Terraform de toda a AWS: dois fluxos de ingestão, um banco, uma Lambda de
leitura e o bucket do dashboard. Passo a passo completo, custo estimado e as
adaptações do Learner Lab estão no `README.md` deste diretório.

## Regras

1. **Confira a conta antes de todo `plan` ou `apply`.** O id da conta do AWS
   Academy Learner Lab muda a cada sessão nova, e ele está dentro do
   `existing_role_arn` do `terraform.tfvars`. Se estiver de uma sessão anterior,
   o apply falha ou, pior, o state passa a descrever uma conta que já não
   existe.
   ```bash
   export AWS_PROFILE=g4 AWS_REGION=us-east-1
   aws sts get-caller-identity --profile g4 --query Account --output text
   ```
2. **O Terraform não aceita `--profile`.** Ele lê `AWS_PROFILE` do ambiente. Os
   dois `export` acima são obrigatórios; sem eles a CLI cai no profile default,
   que é outra conta.
3. **Não rode `apply`, `destroy`, `make deploy`, `make load` ou `make push` por
   iniciativa própria.** São ações irreversíveis sobre infraestrutura viva.
   `make tf-destroy` apaga o banco com as 33 tabelas carregadas (20 a 30 min de
   recarga); o alvo pede confirmação digitada por esse motivo.

   Mudar `create_network` num stack já aplicado tem o mesmo peso, nos dois
   sentidos: a AWS não move uma instância RDS entre VPCs, então o `apply`
   **recria o banco**. Leia "Ligar a rede dedicada num stack que já existe" no
   `README.md` antes.
4. **`*.tfvars` e `*.tfstate` são gitignored; `.terraform.lock.hcl` é
   versionado** de propósito: é o que garante a mesma versão de provider para
   todo mundo. Só o `*.tfvars.example` entra no repositório, e sem valores.
5. **O Terraform não cria schema.** Ele provisiona a instância e para; o DDL vem
   de `tools/migrate.py`. Separar as duas coisas é o que permite iterar o schema
   sem `apply`, que numa sessão de laboratório é a diferença entre trinta
   segundos e cinco minutos por tentativa.
6. **`terraform fmt` e `terraform validate` fazem parte do `make check`.** Rode
   `make -C .. tf-init` uma vez antes.
7. **O `plan` depende do zip da Lambda.** `make -C .. tf-plan` e `tf-apply` já
   chamam `lambda-build` antes; não pule esse passo ao rodar `terraform` direto.

## Organização

Um arquivo por recurso, sem módulos: `vpc.tf`, `vpc_logs.tf`, `bastion.tf`,
`eks.tf`, `rds.tf`, `sqs.tf` / `sqs_changes.tf`, `apigateway.tf` /
`apigateway_changes.tf`, `ecs.tf` e os `ecs_*.tf` por serviço, `api_read.tf`,
`frontend_s3.tf`, `s3_origem.tf`, `ecr.tf`, `iam.tf`, `observability.tf`, mais
`variables.tf`, `outputs.tf`, `locals.tf`, `providers.tf` e `versions.tf`.

Caminho EC2 (ASG+ALB) da Sprint 3 removido na Sprint 4; a leitura pública vem
do Ingress do EKS (ver `../k8s/README.md`) e, como contingência, da Lambda
`read_api_url`. Não recrie `asg.tf`/`alb.tf`: o ALB do cluster nasce do
Ingress, fora do estado do Terraform.

A rede toda passa por três valores de `locals.tf`: `vpc_id`, `subnet_ids` e
`public_subnet_ids`. Os arquivos que consomem rede leem esses locals e não sabem
de onde vieram; é por isso que trocar a VPC default pela VPC dedicada de `vpc.tf`
não toca em nenhum deles. **Não referencie `aws_vpc.main` ou `aws_subnet.private`
direto** fora de `vpc.tf` e `vpc_logs.tf`: isso quebraria o caminho
`create_network = false`.

`rede.tftest.hcl` testa essa camada com provider mockado, sem tocar a AWS
(`make -C .. tf-test`, já dentro do `make check`). Toda mudança em `vpc.tf` ou
nas variáveis de rede passa por ele. O `validate` confirma sintaxe e referências, mas
não confirma que a combinação de variáveis produz uma rede válida.

## Operação pelo Makefile

```bash
make -C .. tf-plan       # somente leitura
make -C .. tf-output     # endpoints e nomes de recurso
make -C .. smoke         # bate nas rotas da API publicada
make -C .. dlq           # o que foi rejeitado, com o motivo
make -C .. logs SERVICO=worker    # worker|simulator|processing|loader
make -C .. pause         # zera os desired_count sem destruir nada
make -C .. resume
```

`pause` existe para economizar crédito do lab: derruba os serviços e mantém o
RDS de pé, que é o que guarda o trabalho da carga inicial.

O simulador fica desligado (`simulator_desired_count=0`) até a carga terminar,
simular mudança sobre tabela vazia não produz nada.
