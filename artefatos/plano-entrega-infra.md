# Plano de entrega — Infraestrutura AWS provisionada

Plano de implantação da camada de infraestrutura exigida pela entrega: rede
virtual gerenciada, bastion host, escalonamento automático com balanceamento de
carga e banco de dados gerenciado — com o roteiro de evidências de console que
comprova cada cláusula.

Este documento é o contrato escrito da mudança. Registra o que entra, por que
entra e em que ordem — antes de qualquer código.

> **Estado, atualizado em 8 de setembro de 2026.** O critério (a) foi implementado
> em `infra/vpc.tf` e verificado na AWS; o (d) já era atendido. Os critérios (b) e
> (c) seguem planejados, com o desenho fechado nas seções 4 e 5 deste documento. As
> evidências de aplicação, as decisões consolidadas e as duas restrições do Learner
> Lab que se confirmaram estão em
> [`infraestrutura-integracao.md`](infraestrutura-integracao.md).

---

## 1. O entregável e o estado atual

### 1.1 As quatro cláusulas

&emsp; A entrega pede a apresentação da infraestrutura provisionada, com evidências
no console da AWS de instâncias ativas, autoescalonamento, balanceamento, segurança
e observabilidade, e é avaliada em quatro critérios de peso 1.0 cada:

| # | Critério |
|---|---|
| (a) | Gerenciamento do ambiente virtual de rede utilizando AWS VPC, incluindo observabilidade com logs distribuídos, a estrutura de redes com sub-rede pública e privada, com acesso à Internet para os hosts privados via NAT Gateway |
| (b) | Bastion Host com regras seguras de acesso |
| (c) | Auto Scaling Group de AWS EC2 com política de escalonamento e Application Load Balancer utilizando AWS ELB |
| (d) | Banco de dados com AWS RDS |

### 1.2 Estado verificado

&emsp; Uma busca por recursos de rede e de computação EC2 no diretório `infra/`
retorna vazio. Não existe `aws_vpc`, `aws_subnet`, `aws_internet_gateway`,
`aws_nat_gateway`, `aws_route_table`, `aws_eip`, `aws_flow_log`, `aws_instance`,
`aws_autoscaling_group`, `aws_launch_template`, `aws_lb` nem `aws_lb_target_group`.
O que existe é um único `data "aws_vpc" "default"` em `infra/locals.tf`: o stack
**consome** a rede padrão da conta, sem gerenciá-la.

| Critério | Estado | O que falta |
|---|---|---|
| (a) | **Atende** | Implementado em `infra/vpc.tf` e verificado na AWS. Ver [`infraestrutura-integracao.md`](infraestrutura-integracao.md) §5 |
| (b) | **Não atende** | Nenhuma instância EC2 no stack |
| (c) | **Não atende** | Nenhum ASG, nenhum balanceador |
| (d) | **Atende** | Apenas o roteiro de evidências |

&emsp; A observabilidade exigida em (a) está **parcialmente** atendida: existe um
log group por serviço, log de acesso das duas APIs e log JSON correlacionado por
`X-Request-Id`. O que falta é a camada de **rede**, que são os VPC Flow Logs.

### 1.3 A causa da distância

&emsp; A rubrica pressupõe uma arquitetura de três camadas sobre EC2: instâncias
atrás de um balanceador, escalando por política, acessadas administrativamente por
um bastion, com o banco atrás. O Argus v3 foi construído em outro estilo —
API Gateway, SQS, ECS Fargate, Lambda e site estático em S3 —, no qual **não existe
uma única instância EC2 nem um balanceador**.

&emsp; O critério (d) coincide porque o projeto já usa RDS. Os critérios (b) e (c)
não são ajuste de configuração: são uma camada de computação nova, que precisa ser
acrescentada ao lado da existente. Esse é o volume real do trabalho.

&emsp; A boa notícia é que os quatro critérios formam **uma arquitetura só**, e não
quatro tarefas soltas: o balanceador de (c) vive nas sub-redes públicas de (a), as
instâncias de (c) e o banco de (d) vivem nas privadas, e o bastion de (b) é o que dá
acesso administrativo a elas. Por isso (a) vem primeiro — os outros três dependem
da estrutura que ele cria.

---

## 2. Desenho alvo

```
VPC  10.0.0.0/16   (DNS hostnames e DNS support habilitados)
│
├── Internet Gateway
│
├── Tabela de rota PÚBLICA          0.0.0.0/0 → IGW
│   ├── sub-rede pública  10.0.0.0/24   us-east-1a
│   │      ├── NAT Gateway + EIP                        ← critério (a)
│   │      ├── Bastion Host  (t3.micro)                 ← critério (b)
│   │      └── Application Load Balancer                ← critério (c)
│   └── sub-rede pública  10.0.1.0/24   us-east-1b
│          └── Application Load Balancer (segunda AZ)
│
├── Tabela de rota PRIVADA          0.0.0.0/0 → NAT Gateway
│   ├── sub-rede privada  10.0.10.0/24  us-east-1a
│   └── sub-rede privada  10.0.11.0/24  us-east-1b
│          ├── Auto Scaling Group de EC2 (min 2, max 4) ← critério (c)
│          ├── tarefas ECS Fargate  (assign_public_ip = false)
│          ├── Lambda da API de leitura
│          └── RDS PostgreSQL  (db_subnet_group)        ← critério (d)
│
├── Gateway endpoint S3  → tabela de rota privada  (grátis)
│
└── Flow Logs (traffic_type = ALL)  → S3 ou CloudWatch Logs   ← critério (a)
```

&emsp; **O que não muda.** As tarefas Fargate continuam sem nenhuma regra de entrada
no grupo de segurança, e o RDS continua privado, aceitando conexão apenas dos grupos
de segurança autorizados. A mudança acrescenta camadas; não afrouxa nenhuma
existente.

### 2.1 Conceitos usados neste documento

&emsp; Os termos abaixo aparecem em todo o plano e são definidos aqui uma vez.

- **VPC** (*Virtual Private Cloud*): rede virtual isolada dentro da AWS, com faixa
  de endereços própria. Toda conta recebe uma VPC padrão pronta; gerenciar a
  própria significa declará-la como recurso.
- **CIDR**: notação que descreve uma faixa de endereços IP. `10.0.0.0/16` são os
  65.536 endereços entre `10.0.0.0` e `10.0.255.255`.
- **AZ** (*Availability Zone*, zona de disponibilidade): datacenter fisicamente
  separado dentro de uma região. Distribuir recursos entre AZs é o que permite
  sobreviver à queda de uma delas.
- **Sub-rede pública / privada**: a diferença não está na sub-rede em si, e sim na
  **tabela de rota** associada a ela. Pública é a que roteia `0.0.0.0/0` para o
  Internet Gateway; privada, a que roteia para o NAT Gateway.
- **Internet Gateway (IGW)**: componente que liga a VPC à internet, nos dois
  sentidos, para máquinas que tenham IP público.
- **NAT Gateway**: serviço gerenciado que permite a uma máquina **sem** IP público
  iniciar conexões para fora. O retorno volta, mas ninguém de fora consegue iniciar
  conexão para dentro. É o mecanismo que a cláusula (a) exige.
- **EIP** (*Elastic IP*): endereço IP público fixo. O NAT Gateway precisa de um.
- **Tabela de rota**: lista que diz, para cada destino, por onde sair.
- **VPC Flow Logs**: registro de todo fluxo de rede aceito ou rejeitado nas
  interfaces da VPC. É a observabilidade da camada de rede.
- **Gateway endpoint**: porta de entrada privada para S3 e DynamoDB, criada dentro
  da VPC. É **gratuito** e retira esse tráfego de cima do NAT.
- **Bastion host**: instância intermediária, e único ponto de entrada administrativo
  para máquinas que não têm endereço público.
- **ASG** (*Auto Scaling Group*): conjunto de instâncias EC2 que a AWS mantém no
  tamanho definido, criando e destruindo máquinas conforme uma política.
- **ALB** (*Application Load Balancer*): balanceador de camada 7, que distribui
  requisições HTTP entre as instâncias saudáveis de um *target group*.
- **Target tracking**: política de escalonamento que persegue um valor-alvo de uma
  métrica — por exemplo, manter a CPU média em 60% — ajustando o número de
  instâncias sozinha.

---

## 3. Critério (a) — VPC, sub-redes, NAT e Flow Logs

### 3.1 Novo: `infra/vpc.tf`

| Recurso | Qtd | Propósito |
|---|---:|---|
| `aws_vpc` | 1 | A rede gerenciada. Núcleo da cláusula |
| `aws_subnet` | 4 | Duas públicas e duas privadas, uma por AZ |
| `aws_internet_gateway` | 1 | Saída das públicas |
| `aws_eip` | 1 | IP fixo do NAT |
| `aws_nat_gateway` | 1 | Saída dos hosts privados |
| `aws_route_table` | 2 | Uma pública, uma privada |
| `aws_route_table_association` | 4 | Liga cada sub-rede à sua tabela |
| `aws_vpc_endpoint` (gateway, `s3`) | 1 | Tráfego do `loader` fora do NAT. Grátis |
| `aws_flow_log` | 1 | Observabilidade de rede |
| `aws_cloudwatch_log_group` ou bucket | 1 | Destino dos flow logs, com retenção |

&emsp; **Um NAT, não dois.** Em produção o correto é um NAT por AZ, com uma tabela de
rota privada por AZ: com um só, a queda daquela zona derruba a saída das duas. Para
a entrega, um único NAT demonstra o mecanismo por metade do custo. A limitação deve
ser **declarada na apresentação**, não escondida — é uma decisão de custo consciente,
do mesmo tipo já registrado na tabela 4.9 de
[`arquitetura-inicial.md`](arquitetura-inicial.md).

### 3.2 Modificado

&emsp; O desenho atual concentra toda a rede em dois valores de `infra/locals.tf`,
`local.vpc_id` e `local.subnet_ids`, consumidos por `ecs.tf`, `ecs_processing.tf`,
`ecs_simulator.tf`, `ecs_loader.tf`, `ecs_migration.tf`, `api_read.tf` e `rds.tf`.
**Essa indireção é o que torna a mudança pequena**: os sete arquivos consumidores
não são tocados.

| Arquivo | Mudança |
|---|---|
| `locals.tf` | `vpc_id` e `subnet_ids` passam a referenciar os recursos novos; o `data` da VPC padrão vira caminho alternativo sob `var.create_vpc` |
| `variables.tf` | Entram `create_vpc`, `vpc_cidr`, `azs`; `assign_public_ip` passa a `false` por padrão |
| `rds.tf` | `aws_db_subnet_group` passa a apontar para as sub-redes privadas |
| `README.md` | Reescrita da seção "Rede: pública vs privada", hoje descrevendo o oposto |

### 3.3 A armadilha do Learner Lab: papel dos Flow Logs

&emsp; Flow Logs entregues ao **CloudWatch Logs** exigem um papel IAM que confie no
serviço `vpc-flow-logs.amazonaws.com`. A seção "AWS Academy" do `infra/README.md`
registra que a `LabRole` confia em `apigateway.amazonaws.com`,
`ecs-tasks.amazonaws.com` e `lambda.amazonaws.com` — **e o serviço de flow logs não
está na lista**. Com `create_iam_roles = false`, obrigatório no laboratório, o
`apply` pode falhar por confiança negada.

&emsp; **Contorno, e provavelmente a escolha melhor:** entregar os flow logs em um
bucket **S3**. Esse destino usa política de bucket em vez de papel IAM, elimina a
dependência da `LabRole` e ainda custa menos por GB. A evidência da cláusula
funciona igual.

&emsp; Confirmar antes de decidir:

```bash
aws iam get-role --role-name LabRole \
  --query 'Role.AssumeRolePolicyDocument' --output json
```

### 3.4 Impacto no RDS

&emsp; **A AWS não permite mover uma instância RDS entre VPCs.** Um subnet group só
pode conter sub-redes da mesma VPC da instância. Criar VPC própria, portanto,
**obriga a recriar o banco**, hoje com as 33 tabelas carregadas.

| Caminho | Como | Preserva o dado | Tempo |
|---|---|---|---|
| **A. Snapshot e restauração** | Snapshot manual, depois `aws_db_instance` com `snapshot_identifier` apontando para o novo subnet group | Sim | ~20 a 40 min |
| **B. Recriar e recarregar** | Deixar o Terraform recriar vazio, então `make migrate-aws` e `make load` | Não, mas reconstrói | ~15 a 30 min |

&emsp; Para o laboratório, **B é o recomendado**: `make load` já existe e é exercitado
a cada recriação da conta do Learner Lab, então é o percurso mais testado do projeto.
A é preferível se houver dado produzido pelo simulador que não seja reproduzível pela
carga inicial. Em qualquer caso, um snapshot manual antes do `apply` é barato e evita
uma sessão perdida.

---

## 4. Critério (b) — Bastion Host

### 4.1 Desenho

&emsp; Uma instância `t3.micro` na sub-rede **pública**, com um grupo de segurança
próprio. O que torna o desenho um bastion não é a instância, e sim as regras dos
**outros** grupos de segurança passarem a referenciar o grupo dele:

| Recurso | Regra |
|---|---|
| SG do bastion | Entrada: SSH apenas do CIDR nomeado do time. Saída: 22 e 5432 para dentro da VPC |
| SG do RDS | Acrescenta entrada 5432 vinda do **SG do bastion** |
| SG das instâncias do ASG | Entrada 22 vinda do **SG do bastion**, e 8000 vinda do SG do ALB |

&emsp; Referenciar grupo de segurança em vez de CIDR é o mesmo princípio já aplicado
em `infra/rds.tf`: sub-rede muda e IP muda, mas a identidade do grupo não.

### 4.2 O que são "regras seguras de acesso"

&emsp; A cláusula admite duas leituras, e elas não se excluem:

- **SSM Session Manager** — acesso pelo agente da AWS, com **nenhuma regra de
  entrada** e a porta 22 fechada. É a resposta mais defensável tecnicamente: não há
  superfície de ataque para força bruta, e todo acesso fica registrado no CloudTrail.
  Exige um instance profile com a política `AmazonSSMManagedInstanceCore`; no Learner
  Lab, verificar se o `LabInstanceProfile` já a traz.
- **SSH restrito a CIDR nomeado**, com par de chaves. Mais imediatamente visível para
  quem avalia, e menos seguro.

&emsp; **Recomendação: implementar os dois.** SSM habilitado como mecanismo
preferencial, e o grupo de segurança com a porta 22 aberta somente ao CIDR do time —
nunca `0.0.0.0/0`, que é exatamente o antipadrão que a cláusula testa. A tela do
grupo de segurança vira a evidência.

### 4.3 Relação com a task `migration`

&emsp; O projeto já resolveu o acesso administrativo ao banco sem bastion: a task
avulsa `migration` roda dentro da VPC e aplica as migrations, decisão registrada na
seção 4.7 de `arquitetura-inicial.md` como substituta do acesso por CIDR do
desenvolvedor. O bastion **não a substitui** — ele acrescenta acesso interativo, para
inspeção `psql` ad-hoc e para alcançar as instâncias do ASG, que a task não faz. Vale
dizer isso na apresentação: o bastion não é retrabalho, é outro caso de uso.

---

## 5. Critério (c) — Auto Scaling Group e Application Load Balancer

### 5.1 O encaixe: a aplicação já existe

&emsp; O `backend/pyproject.toml` declara **Flask**, **gunicorn** e `apig-wsgi`. Ou
seja: a API de leitura é uma aplicação WSGI comum, e o `apig-wsgi` é apenas o
adaptador que a faz caber em Lambda. **O gunicorn já é dependência declarada.**

&emsp; A mesma aplicação, sem alteração de código, roda numa instância EC2 servida
por gunicorn atrás de um ALB. Isso é o que separa este plano de criar uma aplicação
descartável só para satisfazer a rubrica: o critério (c) é atendido com o código que
já está em produção, e a evidência de console mostra a API real do projeto.

### 5.2 Recursos novos: `infra/ec2_api.tf`

| Recurso | Propósito |
|---|---|
| `aws_launch_template` | AMI, tipo de instância, instance profile e `user_data` |
| `aws_autoscaling_group` | `min_size = 2`, `max_size = 4`, espalhado nas duas sub-redes privadas |
| `aws_autoscaling_policy` | Política de target tracking |
| `aws_lb` | ALB nas duas sub-redes públicas |
| `aws_lb_target_group` | Alvo do ALB, com health check |
| `aws_lb_listener` | Porta 80 ou 443 → target group |
| `aws_security_group` × 2 | Um do ALB, um das instâncias |

&emsp; **Distribuição da aplicação.** O `build_lambda.sh` hoje gera um zip para
Lambda. Para o EC2, o caminho mais curto é publicar o mesmo artefato no bucket
`origem`, que já existe, e ter o `user_data` baixando-o, instalando as dependências
e subindo o gunicorn como unidade `systemd`. As credenciais do banco vêm do Secrets
Manager pelo instance profile, como já fazem as tarefas Fargate.

### 5.3 Política de escalonamento e health check

&emsp; **Target tracking em `ASGAverageCPUUtilization`, alvo de 60%.** É a política
mais simples de demonstrar ao vivo: uma carga sintética contra o ALB sobe a CPU, o
grupo cresce, e o console mostra a atividade de escalonamento. A alternativa,
`ALBRequestCountPerTarget`, é tecnicamente mais adequada para uma API — reage a
demanda e não a sintoma — e vale citar na apresentação como o que se usaria em
produção.

&emsp; O health check do target group aponta para **`GET /health/live`**, rota que já
existe e já é pública, sem authorizer. O `health_check_type` do ASG deve ser `"ELB"`,
e não `"EC2"`: assim uma instância que responde a ping mas cuja aplicação morreu é
substituída, e não mantida de pé indefinidamente.

### 5.4 Manter ou aposentar a Lambda

&emsp; Duas opções, e a escolha muda o risco da apresentação:

| Opção | Consequência |
|---|---|
| **Manter as duas** | A Lambda continua servindo o API Gateway; o ALB é o caminho novo. Nada quebra durante a demonstração. Custa a duplicidade de dois caminhos para a mesma API |
| **Migrar de vez** | Arquitetura mais limpa, um caminho só. Mas mexe no que já funciona, na véspera da entrega |

&emsp; **Recomendação: manter as duas durante a entrega**, e registrar a duplicidade
como dívida explícita. A decisão 4 da tabela 4.9 de `arquitetura-inicial.md` — Lambda
para leitura, por custo ocioso próximo de zero — continua válida e deve ser citada
como o motivo pelo qual, fora da exigência da rubrica, o ALB não seria a escolha.

---

## 6. Critério (d) — Banco de dados com AWS RDS

&emsp; **Já atende.** O `infra/rds.tf` provisiona uma instância PostgreSQL com
`publicly_accessible = false`, criptografia em repouso, senha no Secrets Manager,
grupo de segurança sem regra de entrada padrão e acesso liberado apenas ao grupo das
tarefas. As migrations são aplicadas pela task `migration` dentro da VPC.

&emsp; O que falta é **evidência**, não implementação — ver a seção 8. Vale destacar
na apresentação três pontos que vão além do mínimo da cláusula: o banco é privado,
a senha nunca aparece em variável de ambiente, e a aplicação conecta com um usuário
`argus_reader` que só tem `SELECT` nas views `v_*`.

&emsp; O único item da cláusula que hoje está desligado por custo é `db_multi_az`,
registrado como ponto único de falha na decisão 1 da tabela 4.9. Ligá-lo dobra o
custo do RDS; a recomendação é mantê-lo desligado e **declarar a limitação**.

---

## 7. Ordem de execução

&emsp; A ordem separa **criar** de **mudar-se**, para que uma falha não derrube o
ambiente que está no ar.

1. **Snapshot manual do RDS.** Rede de segurança, independente do caminho escolhido.
2. **Escrever `vpc.tf`** com os recursos da seção 3.1, sem alterar `locals.tf`.
3. **`terraform apply`.** Cria VPC, sub-redes, IGW, NAT, rotas e flow logs. Nada se
   move: o stack continua rodando na VPC padrão.
4. **Verificar o NAT isoladamente**, antes de depender dele: subir uma tarefa avulsa
   na sub-rede privada e confirmar que ela alcança o SQS.
5. **Apontar `locals.tf`** para a rede nova e definir `assign_public_ip = false`.
6. **`terraform apply`.** Recria o RDS, move tarefas e Lambda para as privadas.
7. **`make migrate-aws` e `make load`.**
8. **Bastion** (critério b). Depende apenas da sub-rede pública do passo 3.
9. **Publicar o artefato da API** no bucket `origem` e escrever `ec2_api.tf`.
10. **`terraform apply`.** Sobe ALB, ASG e política.
11. **Validar o escalonamento** com carga sintética contra o ALB.
12. **Capturar as evidências** da seção 8.

&emsp; O passo 4 é o que separa um problema de rede de um problema de aplicação. Sem
ele, uma tarefa em crash loop no passo 6 tem duas causas possíveis e nenhuma pista —
e a `variables.tf` atual já documenta o sintoma: sem rota de saída, a tarefa não
baixa a imagem do ECR e o serviço nem chega a subir.

---

## 8. Roteiro de evidências para o console

&emsp; O enunciado pede evidências no console. Cada cláusula precisa de uma tela que
a comprove, e a tabela abaixo é o roteiro de captura.

| Cláusula | Tela do console | O que precisa aparecer |
|---|---|---|
| (a) VPC gerenciada | VPC → Your VPCs | A VPC com o CIDR `10.0.0.0/16` e as tags do projeto |
| (a) Pública e privada | VPC → Subnets | Quatro sub-redes, duas com *auto-assign public IP* habilitado e duas sem |
| (a) NAT | VPC → Route Tables | Uma tabela com destino `0.0.0.0/0` → IGW; outra `0.0.0.0/0` → NAT Gateway |
| (a) Logs de rede | CloudWatch Logs Insights, ou o bucket dos flow logs | Registros `ACCEPT` e `REJECT` com origem, destino e porta |
| (b) Bastion | EC2 → Instances, e o SG do bastion | Instância na sub-rede pública; regra de entrada 22 **restrita a CIDR**, nunca `0.0.0.0/0` |
| (b) Acesso seguro | Systems Manager → Session Manager | Sessão aberta na instância sem uso de chave SSH |
| (c) Instâncias ativas | EC2 → Auto Scaling Groups → Instance management | Duas ou mais instâncias `InService`, em AZs diferentes |
| (c) Autoescalonamento | ASG → Activity history | Registro de *Launching a new EC2 instance* após a carga sintética |
| (c) Política | ASG → Automatic scaling | A política de target tracking com o alvo de 60% |
| (c) Balanceamento | EC2 → Target Groups → Targets | Todos os alvos `healthy`, respondendo em `/health/live` |
| (d) RDS | RDS → Databases → Connectivity & security | `Publicly accessible: No`, o subnet group privado e o SG |
| (d) Segurança | RDS → Configuration | Criptografia em repouso habilitada |

&emsp; A evidência mais forte de todo o conjunto é a combinação de duas telas do
critério (a) com uma do (c): uma tarefa ou instância comprovadamente **sem** IP
público que ainda assim consome da fila e responde ao balanceador só pode estar
saindo pelo NAT.

---

## 9. Custo

| Item | US$/mês |
|---|---:|
| NAT Gateway, 1 unidade, US$ 0,045/hora | ~33 |
| Application Load Balancer, US$ 0,0225/hora | ~16 + LCU |
| ASG, 2× `t3.micro` | ~15 |
| Bastion, 1× `t3.micro` | ~7,6 |
| Volumes EBS `gp3` das três instâncias | ~2 |
| VPC, sub-redes, IGW, tabelas de rota, EIP em uso | 0 |
| Gateway endpoint S3 | 0 |
| Flow Logs | centavos a poucos dólares no volume do laboratório |
| **Acréscimo total** | **~US$ 74** |

&emsp; Sobre os ~US$ 106/mês estimados no `infra/README.md` para o stack de
laboratório, o acréscimo é de aproximadamente **70%**. Todos os itens cobram por hora
existindo, em uso ou não.

&emsp; **Recomendação operacional:** provisionar próximo à apresentação, capturar as
evidências da seção 8, e derrubar ALB, ASG, bastion e NAT logo depois. O `make pause`
existente zera os serviços do ECS, mas **não** remove esses quatro — eles precisam de
`terraform destroy` seletivo ou de uma variável que os condicione.

---

## 10. Riscos

| Risco | Probabilidade | Mitigação |
|---|---|---|
| Recriação do RDS perde as 33 tabelas | Alta, por desenho | Snapshot manual antes do passo 3; `make load` reconstrói |
| `LabRole` não confia em `vpc-flow-logs.amazonaws.com` | **Confirmado** | Resolvido: flow logs em S3, que dispensa papel IAM (§3.3) |
| SCP nega `s3:GetBucketObjectLockConfiguration`, quebrando todo `aws_s3_bucket` | **Confirmado**, não previsto | Variável `flow_logs_bucket_name` aceita bucket criado fora do Terraform |
| `LabInstanceProfile` sem `AmazonSSMManagedInstanceCore` | Média | Cair para SSH com CIDR restrito, mantendo a regra segura |
| Tarefas em crash loop por falta de rota | Média | Passo 4 valida o NAT antes de qualquer serviço depender dele |
| Limite de Elastic IPs da conta atingido | Baixa | O padrão da região são 5; liberar EIPs órfãos antes do `apply` |
| `user_data` do ASG falha e os alvos ficam `unhealthy` | Média | Validar o `user_data` numa instância avulsa antes de colocá-lo no launch template |
| NAT e ALB em AZ única são ponto de falha | Certa, por decisão | Declarar a limitação na apresentação |
| Crédito do laboratório consumido pelos recursos ociosos | Alta | Provisionar próximo à apresentação e destruir depois |

---

## 11. Argumentação: as escolhas e o que mais vale a pena

&emsp; Esta seção sustenta as decisões do plano e registra os acréscimos de alto
retorno que **não** são exigidos pela rubrica, mas que se apoiam na mesma
infraestrutura. O critério de seleção foi duplo: cada item precisa fechar uma lacuna
já reconhecida na documentação do projeto ou mitigar um risco já mapeado em
[`entendimento_negocio.md`](entendimento_negocio.md), e custar pouco.

### 11.1 Base de comparação de custo

&emsp; A tabela de dimensionamento de produção da seção 4.4 de
`entendimento_negocio.md` estima **US$ 5.310/mês** para o cenário base (rollout de
40%, ~1,44 bilhão de eventos por mês). Esse número foi calculado sobre **DynamoDB**,
que era o armazenamento da sprint anterior. A persistência atual é PostgreSQL em RDS,
conforme a seção 4.2 de `arquitetura-inicial.md` e a nota 1.1.5 de
[`modelagem.md`](modelagem.md).

&emsp; Refazendo a conta com RDS — instância da ordem de `db.r6g.2xlarge` em Multi-AZ,
com 1,5 a 2 TB em retenção de 30 dias — a conta cai para aproximadamente
**US$ 3.950/mês**. Esse valor é uma estimativa própria, ainda não validada por teste
de carga, e serve apenas como denominador para as porcentagens desta seção.

> **Pendência.** A seção 4.4 de `entendimento_negocio.md`, e a seção 2.1.1, que
> justifica a escolha do DynamoDB como forma de descartar o risco de desempenho de
> escrita, continuam descrevendo a arquitetura anterior. Isso afeta os números de
> custo operacional das seções 4.4 a 4.7 e o cálculo de ROI. A correção é independente
> deste plano, mas deve ser feita antes da próxima entrega econômica.

### 11.2 Por que NAT Gateway, e o que ele não resolve

&emsp; O NAT Gateway é exigido pela cláusula (a) e é o padrão da indústria para dar
saída a hosts privados. Ele resolve **defesa em profundidade no ingresso**: hoje o
único controle que impede alguém de alcançar as tarefas é o grupo de segurança sem
regra de entrada. Com sub-rede privada, some também a rota — dois controles
independentes em vez de um.

&emsp; É importante, porém, ser preciso sobre o que ele **não** entrega, porque a
intuição engana: o NAT **não protege a saída**. A regra `tasks_https` de `infra/ecs.tf`
libera 443 para `0.0.0.0/0`, e com NAT ela continua idêntica. Do ponto de vista de
exfiltração de dado a partir de um contêiner comprometido, IP público e NAT são
equivalentes.

&emsp; Quem fecha essa lacuna é o **VPC endpoint**, que aceita uma *política de
endpoint* restringindo o acesso a recursos nomeados — a fila e o segredo específicos
deste stack, e nada além. Os dois não se excluem: o desenho maduro usa **NAT para a
saída geral e endpoints para os serviços da AWS**, e o gateway endpoint de S3, que é
gratuito, já está previsto na seção 3.1 justamente por isso.

&emsp; Esse risco cresceu com a migração para PostgreSQL. Um contêiner comprometido
hoje tem IP público, saída irrestrita e a senha do banco vinda do Secrets Manager —
caminho direto para extração. Com DynamoDB o acesso era por IAM, sem credencial
estática dentro do contêiner. Acrescentar os cinco endpoints de interface (`sqs`,
`ecr.api`, `ecr.dkr`, `logs`, `secretsmanager`) custaria ~US$ 83/mês e é a evolução
natural depois da entrega — **não** um substituto do NAT.

### 11.3 Estado remoto do Terraform

&emsp; O `terraform.tfstate` fica no disco de quem aplicou. Não há bloco `backend` em
`infra/versions.tf`, embora o `infra/backend.tf.example` já esteja escrito e a seção 2
do `infra/README.md` recomende a mudança. Consequências: apenas quem aplicou consegue
aplicar de novo; se a máquina for perdida, o Terraform perde a referência de tudo; e o
estado guarda a senha do RDS em texto claro. Este último ponto está contido — o
`.gitignore` cobre `apps/basica/infra/*.tfstate` e nenhum arquivo de estado está
versionado.

&emsp; Com uma entrega em que várias pessoas vão aplicar infraestrutura, isso deixa de
ser dívida e vira impedimento. Desde a versão 1.10 do Terraform o backend S3 tem
bloqueio nativo por `use_lockfile = true`, o que dispensa a tabela DynamoDB que o
`backend.tf.example` ainda instrui a criar:

```hcl
terraform {
  backend "s3" {
    bucket       = "argus-tfstate-<conta>"
    key          = "ingestao-eventos/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
```

&emsp; Exige elevar `required_version` de `>= 1.9` para `>= 1.10`. Custo: um bucket S3
versionado, **~US$ 0/mês**.

### 11.4 Acréscimos sem custo relevante

| Item | Lacuna que fecha | Custo |
|---|---|---:|
| **CloudFront no dashboard** | O dashboard é servido por endpoint de website S3, **só HTTP**, e recebe um token Bearer — violação de RNF09 registrada em `infra/frontend_s3.tf` e na decisão 7 da tabela 4.9. Com *Origin Access Control*, o bucket volta a ser privado e o tráfego passa a HTTPS. A camada gratuita cobre 1 TB e 10 M de requisições | US$ 0–5 |
| **Cognito** | A autenticação usa dois tokens compartilhados por audiência; a decisão 5 já registra que "token identifica serviço, não pessoa". Um user pool traz identidade individual, MFA, revogação e **trilha de auditoria de quem acessou dado pessoal**. Camada gratuita: 50 mil usuários ativos | US$ 0 |
| **Budgets e Cost Anomaly Detection** | O risco R13 está mapeado com mitigação em prosa e nenhum controle técnico. Dois orçamentos e a detecção de anomalias são gratuitos | US$ 0 |
| **Painel do CloudWatch** | Há 16 alarmes em `infra/observability.tf` e nenhuma tela onde alguém olhe o estado geral. Responde à ressalva da seção 1.3 de `entendimento_negocio.md`: a plataforma "cria um sistema que passa a precisar ele próprio de monitoração". Os três primeiros painéis são gratuitos | US$ 0 |
| **Alarme em canal de chat** | O SNS entrega por e-mail; durante um evento ao vivo o plantão não lê e-mail. Uma Lambda inscrita no tópico publicando em webhook muda a utilidade dos 16 alarmes sem alterar nenhum | ~US$ 0 |
| **EventBridge Scheduler** | Único componente do diagrama da seção 2 de `arquitetura-inicial.md` marcado como "planejado e não provisionado" | ~US$ 0,01 |

### 11.5 Acréscimos de custo baixo

&emsp; **Athena e Glue sobre Parquet no S3** — ~US$ 5 a 15/mês, e provavelmente
negativo no líquido. *Tiering* é a separação do armazenamento em camadas por
frequência de acesso: dado recente fica no banco, onde a consulta é rápida e cara;
dado antigo migra para arquivos no S3, onde é barato e continua consultável pelo
Athena. A infraestrutura já existe pela metade — há bucket de origem versionado e um
`loader` que lê Parquet, formato colunar em que a consulta lê apenas as colunas que
cita. Falta o caminho inverso. Ganhos: o RF14, comparação entre períodos, deixa de
ser limitado pela retenção do RDS; e o custo do RDS cai, com menos armazenamento,
índices menores e `VACUUM` mais rápido. Ataca R13 e R07 ao mesmo tempo.

&emsp; **Canário sintético do CloudWatch** — ~US$ 10/mês. Os 16 alarmes medem
exclusivamente métricas **internas**: profundidade de fila, DLQ, CPU e conexões do
RDS, `lag_sim`, silêncio de fonte. Nenhum verifica se a API responde **de fora**. Um
roteiro que chama a aplicação a cada cinco minutos detecta indisponibilidade da ponta
antes do usuário e transforma o RNF02 em medição contínua. Depois do critério (c),
o alvo natural do canário passa a ser o próprio ALB.

&emsp; **WAF apenas na API de leitura** — ~US$ 11/mês. Limite de taxa por IP e
proteção do dashboard, sobre ~5 milhões de requisições mensais. **Não aplicar na
ingestão**: sobre 1,44 bilhão de requisições o mesmo serviço custaria ~US$ 864/mês,
sozinho mais caro que todos os itens desta seção somados.

&emsp; **X-Ray com amostragem baixa** — ~US$ 7/mês. Registra o percurso de uma fração
das requisições pelos componentes, medindo quanto tempo cada uma passa em cada um. A
0,1% de 1,44 bilhão são 1,44 milhão de traços. Dá a latência ponta a ponta do
pipeline, hoje apenas inferida de métricas agregadas.

### 11.6 Descartados por custo

| Item | Ganho | Custo | Por que fica de fora |
|---|---|---:|---|
| Réplica de leitura do RDS | Isola as consultas do dashboard do caminho de escrita; ataca R07 | ~US$ 600/mês | Ordem de grandeza acima do critério |
| `db_multi_az` | Elimina o ponto único de falha da decisão 1 | ~US$ 800/mês | Em produção deve ser tratado como obrigatório, não como melhoria opcional |
| WAF na ingestão | Proteção da borda de maior volume | ~US$ 864/mês | Cobrança por requisição sobre 1,44 bi torna inviável |
| OpenSearch, Timestream, RDS Proxy | — | Variável | Nenhum resolve problema existente pelo preço cobrado |

### 11.7 Consolidado dos acréscimos opcionais

| # | Item | US$/mês |
|---|---|---:|
| 1 | CloudFront no dashboard | 0–5 |
| 2 | Cognito | 0 |
| 3 | Budgets e anomalia de custo | 0 |
| 4 | Painel do CloudWatch | 0 |
| 5 | Alarme em canal de chat | ~0 |
| 6 | EventBridge Scheduler | ~0 |
| 7 | Estado remoto do Terraform | ~0 |
| 8 | Athena e Glue | 5–15 |
| 9 | Canário sintético | ~10 |
| 10 | WAF na API de leitura | ~11 |
| 11 | X-Ray amostrado | ~7 |
| 12 | Endpoints de interface (evolução do item 11.2) | ~83 |
| | **Total** | **~118–133** |

&emsp; Sobre a conta de produção estimada de ~US$ 3.950/mês, o conjunto completo
representa cerca de **3,2%**. Excluído o item 12, os onze primeiros somam ~US$ 35 a
50/mês — em torno de **1%** — e o item 8 tende a devolver mais do que os outros dez
custam juntos.

&emsp; **Prioridade sugerida, se houver espaço além da rubrica:** itens 7, 1 e 2. O
estado remoto destrava o trabalho em equipe sobre a infraestrutura durante a própria
entrega; CloudFront e Cognito fecham as duas lacunas de segurança que a documentação
do projeto já admite em aberto, e somam menos de US$ 5/mês.

---

## 12. Pendências de documentação

&emsp; Três documentos descrevem a infraestrutura atual e passam a contradizer esta
mudança quando ela for aplicada. Devem ser revistos junto com o código, e não depois.

| Documento | O que corrigir |
|---|---|
| `arquitetura-inicial.md` | Seção 4.7 e o parágrafo de rede da seção 2, que descrevem a VPC padrão com IP público; decisões 4 e 7 da tabela 4.9; o diagrama de implantação, que passa a ter ALB, ASG e bastion |
| `entendimento_negocio.md` | Seções 4.4 e 2.1.1, ainda dimensionadas sobre DynamoDB (§11.1) |
| `infra/README.md` | Seção "Rede: pública vs privada" e a tabela de custo, que registra o NAT como item deliberadamente evitado |

---

## Referências internas

- `arquitetura-inicial.md` — seções 2 (diagrama), 4.2, 4.7, 4.8 e tabela de decisões 4.9
- `entendimento_negocio.md` — seções 1.3, 1.6, 2.1 (riscos R07 e R13), 2.1.1 e 4.4
- `requisitos.md` — RNF01, RNF02, RNF09, RNF10; RF14
- `modelagem.md` — seção 1.1.5, nota sobre a migração do armazenamento
- `apps/basica/infra/README.md` — seções "Estado remoto", "Rede: pública vs privada",
  "AWS Academy" e "Segurança e lacunas conhecidas"
