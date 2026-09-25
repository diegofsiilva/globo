# Inteli - Instituto de Tecnologia e Liderança

<p align="center">
  <img src="assets/inteli-logo.png" alt="Inteli" width="260"/>
  &nbsp;&nbsp;&nbsp;&nbsp;
  <img src="assets/grupoglobo.png" alt="Grupo Globo" width="260"/>
</p>

## G04 - Vale a Pena Ver de Novo

**Sistema distribuído de telemetria para diagnóstico de degradação de streaming**

Turma T15 · 2026-2A · Parceiro: **Grupo Globo**

### Integrantes

- [Christian Gandra](https://www.linkedin.com/in/christian-gandra/)
- [Diego Figueiredo](https://www.linkedin.com/in/diegofigueiredos/)
- [Gabriel Bartmanovicz](https://www.linkedin.com/in/gabriel-bartmanovicz/)
- [Livia Saboia Tavares](https://www.linkedin.com/in/livia-saboia-tavares/)
- [Lorenzo Ferrari Aggio](https://www.linkedin.com/in/lorenzo-ferrari-aggio/)
- [Luiz Gustavo](https://www.linkedin.com/in/luiz-gustavo-0b33b62b7/)
- [Nicole Riedla](https://www.linkedin.com/in/nicoleriedla/)
- [Vinicius Cadena](https://github.com/ViniCadena1405)

---

## Descrição do projeto

**Argus, sistema distribuído de telemetria para diagnóstico de degradação de streaming.** A cadeia de entrega do Globoplay (player, CDN, backend, identidade, catálogo) é monitorada em silos: cada área tem seu próprio painel e vocabulário de métricas, o que faz com que a triagem de um incidente consuma mais tempo para descobrir *quem* conserta do que para de fato consertar, e degradações que não geram erro (buffer alto, tempo de início ruim) sequer acendem os alertas atuais. A solução é um sistema distribuído de telemetria com API única de ingestão, normalização dos eventos sob vocabulário comum, pipeline assíncrono de alta escala e camada de consulta que devolve uma linha do tempo única do incidente com o recorte afetado explícito, permitindo identificar a causa provável em minutos e sem depender de um especialista por componente; o sistema ingere os seis eventos do MVP (`request`, `screen_view`, `session`, `video_view`, `vitals` e `error`) e ainda aceita tipos novos sem alteração de código, porque o parque de TVs atualiza devagar e um schema estrito viraria perda de dados em massa.

---

## Arquitetura

A arquitetura possui **dois fluxos de ingestão** independentes que desembocam no mesmo banco, e um fluxo de leitura sobre ele, servido por um cluster Kubernetes.

O primeiro fluxo é o de **eventos de sessão**: o que o app de TV emite (`request`, `screen_view`, `session`, `video_view`, `vitals`, `error`). O segundo é o de **mudanças (CDC)**: as 33 tabelas de telemetria do parceiro não chegam como evento, chegam como *linha que mudou*, e é isso que o simulador reproduz.

```
App de TV ──> API Gateway ──> SQS ──> ECS Fargate ─┐
             (ingestão)                (event      │
                                        worker)    │
                                                   ├──> RDS PostgreSQL ──> EKS Auto Mode ──> ALB interno
Simulador ──> API Gateway ──> SQS ──> ECS Fargate ─┘   bronze/silver/gold   (Deployments     (Ingress:
 (ECS)       (mudanças)                (merge                                backend Flask e   / dashboard,
                                        worker)                              frontend nginx)   /api leitura)

Navegador ──HTTPS──> API Gateway ──> Lambda de entrada ──> ALB interno
                                           │
                                           └── falha do ALB ──> API Lambda / S3 privado
```

Dentro do banco o dado atravessa quatro camadas, cada uma com um trabalho só:

| Camada | O que guarda | Por que existe |
|--------|--------------|----------------|
| `bronze` | `change_log` (append-only) + uma tabela *corrente* por tabela de origem, e `event` para o grain de sessão | O log é a fonte de verdade; a corrente é o MERGE dele. Dá para reconstruir a corrente do zero a partir do log |
| `silver` | sinais, sessões e `analysis_fact_version` | Canonicaliza tempo e conserva versões imutáveis por LSN |
| `gold` | features, qualidade, hipóteses e evidências | Produtos de leitura e resultados explicáveis do motor |
| `detect` | runs, claims, cursor, baseline e anomalias | Coordena e executa o detector causal por checkpoint |

| Componente | Responsabilidade | Serviço AWS |
|------------|------------------|-------------|
| Rede | VPC própria com sub-redes pública e privada em duas AZs; os serviços rodam sem IP público e saem pelo NAT | VPC, NAT Gateway, Flow Logs |
| API de ingestão | Recebe os eventos de sessão e publica na fila por integração direta, sem Lambda no caminho | API Gateway (HTTP API) |
| API de mudanças | Recebe os *change events* do simulador, mesma integração direta | API Gateway (HTTP API) |
| Filas | Absorvem picos e garantem a entrega; payload inválido vai para a DLQ com o motivo | SQS + DLQ (duas filas) |
| Event worker | Consome a fila de eventos, valida e grava em `bronze.event` | ECS Fargate (ARM64) |
| Merge worker | Grava o change event em `bronze.change_log` e faz o MERGE na tabela corrente, na **mesma transação** | ECS Fargate (ARM64) |
| Simulador | Anda um relógio virtual e reemite as mudanças das tabelas como se estivessem acontecendo agora | ECS Fargate (ARM64) |
| Banco de dados | 33 tabelas de origem (68,7 M linhas), 6 delas particionadas por dia | RDS PostgreSQL 16 |
| Carga inicial | Sobe as 33 tabelas a partir de Parquet, via `COPY FROM STDIN` | ECS Fargate (task one-shot) |
| API de leitura | Filtros cumulativos, agregações, paginação por cursor e redação de dado pessoal | EKS Auto Mode (`Deployment argus-backend`, Flask + gunicorn, 2 a 6 pods por HPA) |
| Dashboard | Visualização e investigação de incidentes | EKS Auto Mode (`Deployment argus-frontend`, nginx com o export estático do Next.js) |
| Entrada pública | API Gateway HTTPS recebe `/`, `/api` e `/health`; Lambda encaminha ao ALB interno do Ingress | API Gateway + Lambda + ALB interno |
| Migrations e login de leitura | `Job argus-db-migrate` aplica as 33 migrations; depois, `Job argus-db-reader` cria ou atualiza o usuário de leitura. Ambos usam a imagem `processing` | EKS (dois Jobs sequenciais) |
| Contingência | Na falha do ALB, a entrada tenta a API de leitura Lambda e serve o export estático de um bucket S3 privado | AWS Lambda + API Gateway + S3 |

### O relógio virtual

O dataset do parceiro é um **dump do passado**. Um dashboard "ao vivo" sobre ele mostraria uma tela vazia, porque nada tem a data de hoje. Por isso o sistema tem um presente próprio: `sim.now()`.

Toda linha carrega um `available_at`, que é o instante em que a informação *ficaria disponível na vida real*, contando a latência da fonte (a NPAW entrega com 28 h de atraso; o Prometheus, com 1 min). E **toda** view `v_*` filtra `available_at <= sim.now()`.

Isso não é um filtro de conveniência: é a barreira que impede vazamento de futuro. O usuário de leitura do banco (`argus_reader`) só tem `SELECT` nas views, nunca nas tabelas, então nem a API nem o detector conseguem enxergar um dado antes da hora em que ele existiria.

Escolhas de projeto, modelo de dados, garantias de entrega, custo e pendências estão detalhados na [arquitetura final](artefatos/arquitetura-final.md), na [arquitetura inicial do Argus v3](artefatos/arquitetura-inicial.md), no [plano da v3](artefatos/plano-argus-v3.md) e no [README de infraestrutura](apps/fullstack/infra/README.md).

### Estado atual (Sprint 4): conteinerização e Kubernetes

Na Sprint 4 o caminho síncrono passou a rodar num cluster **Amazon EKS Auto Mode**, criado pelo Terraform dentro da VPC do projeto (`create_eks = true`) e descrito pelos manifestos de [`apps/fullstack/k8s`](apps/fullstack/k8s). O namespace `argus` reúne dois Deployments (`argus-backend`, a API Flask + gunicorn, e `argus-frontend`, o nginx com o export estático do Next.js), cada um com Service, HorizontalPodAutoscaler e PodDisruptionBudget; um ConfigMap; um Ingress que provisiona o Application Load Balancer e encaminha `/` ao dashboard e `/api` e `/health` à API; e dois Jobs sequenciais com a imagem `processing`: `argus-db-migrate` aplica as migrations e `argus-db-reader` cria ou atualiza o login de leitura. O Auto Mode cria e remove os nós EC2 conforme os pods pendentes, e os overlays `aws` e `kind` executam o mesmo conjunto de manifestos na AWS e num cluster local.

A ingestão não mudou de plataforma: API Gateway → SQS → ECS Fargate (merge worker, event worker, simulador, processamento e a task de carga) continua gravando no RDS PostgreSQL 16, porque esses serviços precisam de IAM por task para falar com SQS e S3, e o Learner Lab bloqueia IRSA e Pod Identity no EKS. O caminho de leitura em EC2 da Sprint 3 (Auto Scaling Group com Application Load Balancer próprio) foi removido. Na correção de 25/09, o acesso público passa por API Gateway HTTPS e Lambda, que usam o ALB **interno** como origem principal e a API de leitura Lambda/S3 privado como contingência automática. Esta configuração ainda exige implantação e ensaio na AWS; as evidências anteriores descrevem o estado observado antes da correção. O [plano de correção](artefatos/plano-correcao-develop.md) registra as etapas e pendências. Diagrama, justificativas, plano de recuperação de falhas e evidências estão em [`artefatos/arquitetura-final.md`](artefatos/arquitetura-final.md); as decisões de conteinerização e orquestração, em [`artefatos/conteineres-final.md`](artefatos/conteineres-final.md).

### Histórico: arquitetura v4 da Sprint 3

A arquitetura v4, desenvolvida na Sprint 3, acrescentou a VPC dedicada com sub-redes públicas e privadas em duas zonas de disponibilidade, NAT Gateway, bastion host, Flow Logs, a opção de RDS Multi-AZ e uma API de leitura em instâncias EC2 sob Auto Scaling Group atrás de um Application Load Balancer, com CloudFront no desenho. A rede, o bastion e os Flow Logs permanecem; o caminho EC2 foi substituído pelo cluster na Sprint 4. O diagrama e a documentação dessa etapa estão em [`artefatos/infraestrutura-integracao.md`](artefatos/infraestrutura-integracao.md), que separa o desenho da Sprint 3 do que foi efetivamente provisionado na conta do Learner Lab. O estado das Sprints 1 e 2, com o modelo de dados e o relatório de testes iniciais, está em [`artefatos/mvp-inicial.md`](artefatos/mvp-inicial.md).

---

## Estrutura de pastas

```text
g04/
├── README.md
├── .gitignore
├── apps/
│   └── fullstack/          # aplicação, infraestrutura e comandos de execução
│       ├── authorizer/     # autorização das APIs por token Bearer
│       ├── backend/        # API de leitura (Flask)
│       ├── common/         # código compartilhado pelos serviços Python
│       ├── db/migrations/  # as 33 migrations do banco
│       ├── frontend/       # dashboard (Next.js)
│       ├── infra/          # Terraform da AWS
│       ├── k8s/            # manifestos Kubernetes (base, migrate, overlays aws e kind)
│       ├── loader/         # carga inicial
│       ├── notebooks/      # análise exploratória
│       ├── observability/  # Prometheus e Grafana locais
│       ├── processing/     # ETL, detector e motor de hipóteses
│       ├── simulator/      # relógio virtual e emissor de mudanças
│       ├── tests/carga/    # scripts K6 de carga, escalabilidade e resiliência
│       ├── tools/          # migrations, DDL, ETL do dump, replay e loadtest
│       ├── worker/         # merge worker e event worker
│       └── Makefile        # comandos do projeto
├── artefatos/              # documentação e evidências das sprints
├── slides/                 # apresentações das sprints
└── assets/                 # logos do Inteli e do parceiro
```

| Pasta / Arquivo | Conteúdo |
|-----------------|----------|
| `/apps` | Aplicações do projeto, organizadas em subpastas |
| `/apps/fullstack` | Aplicação Argus completa: serviços, dashboard, infraestrutura e ferramentas |
| `/apps/fullstack/authorizer` | Autorização das APIs por token Bearer |
| `/apps/fullstack/db/migrations` | As 33 migrations que constroem o banco, aplicadas em ordem por `tools/migrate.py` |
| `/apps/fullstack/backend` | API de leitura em Flask com arquitetura hexagonal, servida por contêiner no cluster Kubernetes |
| `/apps/fullstack/worker` | Os dois workers de ingestão (`merge` e `event`), que consomem o SQS e gravam na bronze |
| `/apps/fullstack/simulator` | Relógio virtual e emissor de mudanças, que reproduz o dump como se fosse hoje |
| `/apps/fullstack/loader` | Carga inicial das 33 tabelas, de Parquet para o PostgreSQL |
| `/apps/fullstack/processing` | ETL, checkpoints, canário, detector e motor determinístico das 11 famílias de hipótese |
| `/apps/fullstack/common` | O que os quatro serviços compartilham: conexão, métricas e ciclo de vida |
| `/apps/fullstack/frontend` | Dashboard em Next.js, export estático servido por nginx no cluster |
| `/apps/fullstack/infra` | Terraform de toda a infraestrutura AWS, incluindo o cluster EKS (`eks.tf`) |
| `/apps/fullstack/k8s` | Manifestos Kubernetes do caminho síncrono: `base` (Deployments, Services, HPA, PDB, Ingress, ConfigMap), `migrate` (Job) e overlays `aws` e `kind` |
| `/apps/fullstack/tools` | Migrations (`migrate.py`), geração do DDL, ETL do dump, conversão dos CSVs, replay de eventos, lote de hipóteses, validação dos manifestos e scripts K6 de ingestão (`loadtest`) |
| `/apps/fullstack/notebooks` | Análise exploratória do dataset do parceiro |
| `/apps/fullstack/observability` | Configuração local de Prometheus e Grafana para acompanhar os testes |
| `/apps/fullstack/tests/carga` | Scripts K6 dos testes de carga (RNF01 a RNF03), escalabilidade e resiliência, com `executar_testes.sh` e README próprio |
| `/apps/fullstack/AGENTS.md`, `CLAUDE.md` | Convenções do app para assistentes de código; algumas subpastas têm os seus |
| `/artefatos` | Documentação das sprints: negócio, UX, requisitos, modelagem, arquitetura, hipóteses, testes, infraestrutura e conteinerização (índice na seção [Documentação](#documentação)) |
| `/artefatos/assets` | Imagens e diagramas usados nos artefatos |
| `/artefatos/evidencias` | Saídas brutas dos testes unitários, de integração, de carga e do cluster citadas pelos artefatos |
| `/artefatos/postman` | Coleção Postman de teste das duas APIs + evidências `evidencias/newman-*.json` |
| `/assets` | Logos usados neste README |
| `/slides` | Apresentações das sprints: Sprint 1 em PDF, Sprints 2 e 3 em PPTX |
| `/apps/fullstack/Makefile` | Comandos do projeto; `make -C apps/fullstack` lista os alvos |
| `/apps/fullstack/.env.example` | Chaves de configuração; os valores ficam em `/apps/fullstack/.env`, fora do repositório |
| `README.md` | Este arquivo |
| `.gitignore` | Arquivos e pastas ignorados pelo controle de versão, entre eles o dump do parceiro, a pasta local `data/` e o `terraform.tfvars` |

---

## Execução local

### Pré-requisitos

- Python 3.12 ou superior
- [uv](https://docs.astral.sh/uv/), que monta os ambientes a partir do `pyproject.toml` de cada app
- Node.js 20+ (para o dashboard)
- Docker (para o PostgreSQL local e para construir as imagens dos serviços)
- GNU Make e Bash (para os comandos do `Makefile`; no Windows, use WSL com essas ferramentas e integração com o Docker)

Para a implantação na AWS, também são necessários Terraform 1.x, AWS CLI e
credenciais do Learner Lab no profile `g4` (`aws sts get-caller-identity --profile g4`
deve responder). A execução local abaixo não depende de credenciais AWS.

Quem prefere não instalar nada na máquina usa o devcontainer em
[`apps/fullstack/.devcontainer`](apps/fullstack/.devcontainer), que já traz Python 3.12,
uv, Node 20, Docker e make: no VS Code, **Dev Containers: Open Folder in Container…**
apontando para a pasta `apps/fullstack`. Ele não pode ficar na raiz porque a raiz do
repositório é fixa — e por isso o Codespaces, que só procura `.devcontainer` na raiz,
não o encontra. Com `apps/fullstack` aberto como pasta do workspace,
[`apps/fullstack/.vscode`](apps/fullstack/.vscode) traz a task padrão de build
**Argus: subir tudo** (`make dev`) e as configurações **Run and Debug → Backend Flask**
e **Dashboard (Next dev)**.

### Passos

O caminho principal são três passos: clonar, `make dev` e abrir o dashboard.

```bash
# 1. clonar o repositório
git clone https://git.inteli.edu.br/graduacao/2026-2a/t15/g04.git
cd g04

# 2. subir tudo no mesmo terminal: PostgreSQL local já migrado, API de leitura
#    e dashboard. Ctrl-C derruba os três.
make -C apps/fullstack dev

# 3. abrir http://localhost:3000 e colar, na tela de acesso, o token local de
#    64 zeros — o próprio `make dev` imprime URL e token quando os dois respondem.
```

`make dev` instala o que falta (`uv` monta os ambientes Python na primeira execução;
`npm ci` roda se `frontend/node_modules` não existir), reaproveita o container
`argus-pg` quando ele já existe (só aplica as migrations pendentes) e imprime, ao
final, a URL do dashboard e o token. As portas são variáveis:
`make -C apps/fullstack dev API_PORT=5001` quando a 5000 estiver ocupada (no macOS, o
AirPlay Receiver escuta nela) e `WEB_PORT=3001` para o dashboard.

No ambiente local a API sobe com `AUTH_REQUIRED=0` e ignora o token; a tela de acesso
do dashboard só exige o **formato** de 64 caracteres hexadecimais, daí os 64 zeros:
`0000000000000000000000000000000000000000000000000000000000000000`. Para usar a API
publicada, gere o `.env` com `make -C apps/fullstack env` após a implantação na AWS e
use o token de leitura desse ambiente.

**O banco nasce vazio.** O dataset é do parceiro (4 GB, não redistribuível) e não vem
no clone; as telas abrem, mas sem dados. Quem tem o dump gera o Parquet uma vez
(`make -C apps/fullstack parquet`) e carrega a amostra com
`make -C apps/fullstack dev-seed`, que roda a carga local, reconstrói silver e gold e
posiciona o relógio virtual no último evento. Sem a pasta `data/parquet`, `dev-seed`
apenas avisa. `make replay` não substitui isso: ele reenvia os seis eventos de exemplo
à API de **ingestão publicada** (API Gateway → SQS → worker), que não existe no
ambiente local.

#### Passo a passo, um serviço por terminal

Os mesmos passos que o `make dev` encadeia, para quem quer cada serviço num terminal:

```bash
# instalar as dependências dos serviços e do dashboard
make -C apps/fullstack install
make -C apps/fullstack frontend-install

# subir um PostgreSQL 16 local e aplicar as migrations
make -C apps/fullstack db-local

# rodar a suíte de testes
make -C apps/fullstack test

# subir a API de leitura local e manter este terminal aberto
make -C apps/fullstack api DATABASE_URL=postgresql://argus:argus@localhost:55432/argus

# em outro terminal, a partir da raiz do repositório, subir o dashboard
make -C apps/fullstack frontend-dev ARGUS_API_URL=http://localhost:5000
```

O `db-local` sobe o container `argus-pg` na porta **55432** (e não 5432, para não colidir com um PostgreSQL já instalado na máquina), cria os bancos `argus` e `argus_test` e aplica as migrations — sempre do zero. `make -C apps/fullstack db-ensure` é a versão idempotente que o `make dev` usa: reaproveita o container existente e só aplica o que falta. `make -C apps/fullstack db-stop` derruba, `make -C apps/fullstack db-psql` abre um `psql` dentro dele.

| Serviço | Porta local | Como subir |
|---------|-------------|------------|
| Tudo (banco + API + dashboard) | 55432 / 5000 / 3000 | `make -C apps/fullstack dev` |
| PostgreSQL local | 55432 | `make -C apps/fullstack db-ensure` (`db-local` recria do zero) |
| API de leitura | 5000 | `make -C apps/fullstack api` |
| Dashboard | 3000 | `make -C apps/fullstack frontend-dev ARGUS_API_URL=http://localhost:5000` |

O backend também possui scripts de desenvolvimento que preparam o ambiente Python,
sem `make`. Com o banco local já iniciado:

```bash
# Linux/macOS
DATABASE_URL=postgresql://argus:argus@localhost:55432/argus sh apps/fullstack/backend/scripts/dev.sh
```

```powershell
# Windows (PowerShell)
$env:DATABASE_URL = "postgresql://argus:argus@localhost:55432/argus"
& ./apps/fullstack/backend/scripts/dev.ps1
```

Os scripts criam o `.venv`, instalam as dependências e executam `run.py`. Para apenas
instalar, testar e analisar o código, não é necessário gerar o `.env` nem possuir
credenciais AWS.

Os workers não são executados localmente contra a fila real: use `make -C apps/fullstack images` para construir as quatro imagens e `make -C apps/fullstack replay` para reenviar os eventos de exemplo à API de ingestão publicada.

### Sem credenciais AWS

Os testes usam um SQS falso (moto) mas um PostgreSQL **de verdade**, porque a parte difícil deste sistema é o SQL: o MERGE idempotente, o keyset de paginação, a barreira do `available_at`. Um dublê que respondesse "ok" a tudo isso testaria apenas o dublê.

Com `make -C apps/fullstack db-local` no ar, `test` e `lint` funcionam sem nenhuma configuração de nuvem; sem ele, os testes que precisam de banco são **pulados** em vez de quebrarem. Os alvos que acessam a AWS ou as APIs publicadas (`deploy`, `smoke`, `postman`) precisam da configuração correspondente. `api` e `frontend-dev` aceitam os valores locais mostrados acima.

> **Nenhuma URL de API ou identificador de conta é versionado.** Os valores vêm do `terraform output` e ficam em `apps/fullstack/.env`, que está no `.gitignore`; o mesmo vale para o environment do Postman (`artefatos/postman/environment.example.json`). As três APIs exigem `Authorization: Bearer` (RNF09); os tokens saem de `make -C apps/fullstack auth-rotate` e nunca entram no repositório, nem no bundle do dashboard.

Outros alvos úteis, todos com o prefixo `make -C apps/fullstack`: `lint`, `check`, `smoke`, `dlq`, `pause` e `resume`.

### O sistema inteiro num cluster Kubernetes local

O dashboard e a API também rodam num cluster de verdade na sua máquina, sem nenhuma credencial da AWS. É o mesmo conjunto de manifestos que vai para o EKS — muda só o banco (local em vez de RDS) e a classe do Ingress.

```bash
# pré-requisitos adicionais: kubectl e kind (brew install kubectl kind)
make -C apps/fullstack kind-up                      # cluster, ingress-nginx, metrics-server
make -C apps/fullstack k8s-images kind-load         # constrói e carrega as imagens
make -C apps/fullstack k8s-apply   K8S_OVERLAY=kind
make -C apps/fullstack k8s-migrate K8S_OVERLAY=kind

# dashboard e API na MESMA origem, sem CORS
open http://localhost:8080/
curl -s http://localhost:8080/api/v1/clock
```

`make -C apps/fullstack kind-down` destrói tudo. O runbook completo, incluindo o caminho na AWS, está em [`apps/fullstack/k8s/README.md`](apps/fullstack/k8s/README.md).

> **Recursos.** Um nó rodando control plane, ingress-nginx, metrics-server, PostgreSQL e a aplicação pede folga de CPU. Com menos de 4 vCPU na VM do Docker, o próprio API server começa a responder `TLS handshake timeout` — o sintoma parece "o cluster caiu", e é só falta de CPU.

---

## Execução na AWS

Toda a infraestrutura é provisionada por Terraform em [`apps/fullstack/infra`](apps/fullstack/infra), que documenta o passo a passo completo, as adaptações do AWS Academy Learner Lab e o custo estimado. O caminho síncrono é aplicado por `kubectl` e `kustomize` a partir de [`apps/fullstack/k8s`](apps/fullstack/k8s), cujo README é o runbook do cluster. Além do Terraform 1.x e da AWS CLI, esse caminho exige `kubectl` e Docker com `buildx`, porque as imagens do EKS são publicadas em duas arquiteturas (os nós do Auto Mode são amd64; as máquinas do time e o Fargate, arm64).

A rede é gerenciada pelo projeto: as tarefas, os nós do cluster e o banco vivem em **sub-redes privadas**, sem endereço público, e alcançam os serviços da AWS por um **NAT Gateway**. O tráfego da VPC é registrado em Flow Logs. O desenho, as justificativas e as evidências de aplicação estão em [`artefatos/infraestrutura-integracao.md`](artefatos/infraestrutura-integracao.md) e em [`artefatos/arquitetura-final.md`](artefatos/arquitetura-final.md); `create_network = false` devolve o stack à VPC padrão da conta e dispensa o custo do NAT (e, com isso, o cluster, que exige a rede dedicada).

O ambiente de entrega é o **AWS Academy Learner Lab**, que impõe concessões a um Terraform escrito para conta normal, todas resolvidas por variável no `terraform.tfvars` (que está no `.gitignore` porque carrega o id da conta e pode carregar a senha do banco): `iam:CreateRole` é negado, então os componentes usam a `LabRole` pronta (`create_iam_roles = false` e `existing_role_arn`); a senha do RDS pode vir do tfvars em vez do Secrets Manager; e a SCP da organização impede o provider de reler um bucket S3 recém-criado, por isso os buckets de logs são criados fora do Terraform e apenas referenciados por nome. O detalhe de cada uma, e o que muda numa conta normal, está em [`apps/fullstack/infra/README.md` § AWS Academy](apps/fullstack/infra/README.md#aws-academy--learner-lab).

| Recurso | Configuração |
|---------|--------------|
| VPC | `10.0.0.0/16`, duas sub-redes públicas e duas privadas em AZs distintas, Internet Gateway, NAT Gateway, gateway endpoint de S3 e Flow Logs |
| API Gateway (ingestão) | HTTP API com integração direta `SQS-SendMessage` |
| API Gateway (mudanças) | HTTP API com integração direta `SQS-SendMessage`, fila separada |
| SQS | Duas filas (`events` e `changes`), cada uma com DLQ e redrive de 5 tentativas |
| ECR | Um repositório por imagem (`worker`, `simulator`, `processing`, `loader`, `backend`, `frontend`), com lifecycle policy; a tag é o SHA do commit |
| ECS Fargate | Quatro serviços ARM64 do caminho assíncrono (merge worker, event worker, simulador, processamento) e tasks one-shot (carga e migration) |
| RDS PostgreSQL 16 | `db.t3.medium`, 100 GB gp3, 33 tabelas de origem, 6 particionadas por dia |
| S3 (origem) | Bucket versionado com o dump e os Parquet que alimentam a carga inicial |
| EKS (Auto Mode) | Cluster na VPC do projeto (`create_eks = true`) que orquestra o caminho síncrono: dashboard, API de leitura e os Jobs de migrations e login de leitura, atrás do ALB provisionado pelo Ingress; os nós usam o papel mínimo `LabEksNodeRole` |
| Bastion | Host de acesso administrativo ao RDS, que é privado |
| Lambda + API Gateway | Entrada HTTPS com comutação automática e API de leitura de contingência; os pacotes são gerados por `make lambda-build` |
| S3 (site) | Bucket privado com o export estático usado quando o Ingress falha |
| CloudWatch | Namespace `Argus/Ingestion` com alarmes de fila, banco e atraso do relógio virtual |

### Passos de implantação

Credenciais primeiro: [`artefatos/mvp-inicial.md` §6.2](artefatos/mvp-inicial.md#62-conectar-o-terraform-ao-aws-academy-learner-lab)
mostra como pegar as credenciais do AWS Academy Learner Lab em **AWS Details →
AWS CLI**, gravá-las num profile e preencher o `terraform.tfvars`.

> **O id da conta do Learner Lab muda a cada sessão nova.** Antes do apply, confira com `aws sts get-caller-identity --profile g4 --query Account --output text` e atualize o `existing_role_arn` do `terraform.tfvars`. E **todo** comando `aws` deste projeto leva `--profile g4`: sem ele a CLI usa o profile default, que é outra conta. O Terraform não tem `--profile`: exporte `AWS_PROFILE=g4` e `AWS_REGION=us-east-1` antes de `plan` e `apply`.

```bash
# 1. empacota a Lambda de compatibilidade: o Terraform precisa do zip já no plan
make -C apps/fullstack install
make -C apps/fullstack lambda-build

# 2. cria a infraestrutura sem os serviços (o ECR nasce vazio) e com o cluster
#    (create_eks = true no terraform.tfvars; o EKS leva 10 a 15 minutos)
cd apps/fullstack/infra
cp terraform.tfvars.example terraform.tfvars   # e preencha
terraform init
terraform apply -var="worker_desired_count=0" -var="processing_desired_count=0" -var="simulator_desired_count=0"

# 3. publica as seis imagens no ECR, com a tag do commit
cd ../../.. && make -C apps/fullstack push

# 4. gera os tokens Bearer (imprime UMA vez) e monta o segredo do cluster
make -C apps/fullstack auth-rotate          # até aqui as APIs respondem 403 de propósito
make -C apps/fullstack k8s-kubeconfig       # aponta o kubectl para o cluster
make -C apps/fullstack k8s-bootstrap        # classe de Ingress do ALB
make -C apps/fullstack k8s-secret           # lê os outputs do Terraform; nada toca o disco

# 5. aplica as 33 migrations e cria o usuário de leitura, por dois Jobs em sequência
make -C apps/fullstack k8s-migrate

# 6. carga inicial: sobe o Parquet e dispara a task (20 a 30 min, 68,7 M linhas)
make -C apps/fullstack parquet              # só na primeira vez: dump MySQL -> Parquet
make -C apps/fullstack origem-sync
make -C apps/fullstack load

# 7. liga os workers e, depois que a carga terminar, o simulador
cd apps/fullstack/infra && terraform apply
cd ../../.. && make -C apps/fullstack sim-on

# 8. publica o export de contingência, sobe a aplicação e registra o ALB interno
make -C apps/fullstack frontend-deploy
make -C apps/fullstack k8s-apply
make -C apps/fullstack k8s-edge-register
make -C apps/fullstack k8s-url              # HTTPS: dashboard em / e API em /api
make -C apps/fullstack env                  # .env com as URLs, para smoke, postman e replay
```

O simulador fica desligado até a carga terminar de propósito: simular mudança sobre tabela vazia não produz nada útil. Se o RDS estiver parado (é o que guarda a carga entre sessões), religue-o antes do passo 4 com `aws rds start-db-instance --db-instance-identifier argus-events-dev --profile g4`. Sem o cluster, `migrate-aws` e `db-reader-aws` fazem o trabalho do passo 5 por uma task ECS dentro da VPC.

Nos deploys seguintes, `make -C apps/fullstack push` seguido de `make -C apps/fullstack tf-apply` atualiza o caminho assíncrono (a tag é o SHA do commit, e o rollback é apontar o SHA anterior); `k8s-push`, `k8s-migrate` (quando houver migration nova) e `k8s-apply` atualizam o cluster com rolling update, sem queda. Depois de um `auth-rotate`, repita `k8s-secret`: ele termina com `rollout restart`, porque variável de `secretKeyRef` não recarrega em pod que já está de pé. `make -C apps/fullstack deploy` continua publicando a Lambda de compatibilidade.

Verificação:

```bash
make -C apps/fullstack k8s-status # pods, HPA, PDB e Ingress do cluster
make -C apps/fullstack smoke      # confere as rotas da API publicada
make -C apps/fullstack postman    # roda a coleção Postman contra as APIs
make -C apps/fullstack count      # conta as linhas carregadas por camada
make -C apps/fullstack dlq        # mostra o que foi rejeitado, com o motivo
make -C apps/fullstack logs SERVICO=worker    # worker|simulator|processing|loader
```

Para economizar crédito do lab, `pause` e `resume` desligam e religam os serviços do Fargate sem destruir nada, e o RDS continua de pé, que é o que guarda o trabalho da carga. O cluster cobra por hora existindo, somado ao ALB: `k8s-scale-zero` consolida os nós até zero e `k8s-delete` remove o namespace e, com ele, o ALB; `create_eks = false` seguido de `tf-apply` derruba o cluster inteiro sem tocar no resto.

---

## Documentação

Os artefatos em [`artefatos/`](artefatos) estão agrupados pela sprint em que foram entregues; vários foram revisados nas sprints seguintes.

| Sprint | Artefato | Descrição |
|--------|----------|-----------|
| 1 | [Entendimento do negócio](artefatos/entendimento_negocio.md) | Matriz de Oceano Azul, análise de riscos e oportunidades, Value Proposition Canvas, análise financeira e ODS |
| 1 | [Entendimento de UX](artefatos/entendimento_ux.md) | Personas, user stories, wireframes, protótipo de alta fidelidade e avaliação heurística |
| 1 | [Requisitos](artefatos/requisitos.md) | Requisitos funcionais e não funcionais (ISO 25010) com planos de teste |
| 1 | [MVP inicial](artefatos/mvp-inicial.md) | O que foi implantado no MVP, modelo de dados, conexão do Terraform ao Learner Lab e relatório de testes |
| 2 | [Arquitetura inicial (Argus v3)](artefatos/arquitetura-inicial.md) | Diagrama de implantação, nós, justificativa de arquitetura, schemas do banco, ETL incremental e plano de deploy |
| 2 | [Plano da v3](artefatos/plano-argus-v3.md) | Por que a arquitetura mudou para RDS + CDC + bronze/silver/gold, schemas, Terraform, carga inicial, serviços, ordem de execução, riscos e ETL incremental |
| 2 | [Correlação de dados](artefatos/correlacao_dados.md) | Correlação de dados para geração de hipóteses: invariantes temporais, tipos de correlação, features explicáveis, score, cobertura e confiança, padrões por família |
| 2 | [Geração de hipóteses](artefatos/hipoteses.md) | Arquitetura do motor de hipóteses: conceitos temporais, responsabilidade de cada camada, catálogo inicial, proteções contra falsos positivos, score explicável e persistência no PostgreSQL |
| 2 | [Back-end](artefatos/backend.md) | Organização do código da API de leitura, endpoints e itens da especificação atendidos |
| 2 | [Interface gráfica](artefatos/frontend.md) | Implementação do frontend, resultados dos testes de entradas e matrizes de rastreabilidade |
| 2 | [Revisão estrutural do frontend](artefatos/revisao-estrutura-frontend.md) | Revisão Standards/Spec, organização Next.js e evidências da refatoração |
| 3 | [Infraestrutura e integração](artefatos/infraestrutura-integracao.md) | Arquitetura v4, diagrama em nuvem, componentes, plano de deploy, alta disponibilidade e rollback, vídeos de infraestrutura e integração front-end/back-end e riscos conhecidos |
| 3 | [Modelagem](artefatos/modelagem.md) | Diagrama de classes UML (unificado + quatro recortes) e descrição textual do modelo de domínio |
| 3 | [Testes de carga iniciais](artefatos/testes-carga-inicial.md) | Requisitos não funcionais e planos de teste revisados, resultados de desempenho e resiliência e visualização dos indicadores de observabilidade |
| 4 | [Arquitetura final](artefatos/arquitetura-final.md) | Diagrama de implantação com EKS Auto Mode e ECS Fargate, componentes e justificativas, inventário de contêineres, Docker e Kubernetes, plano de recuperação de falhas e evidências de validação |
| 4 | [Conteinerização e orquestração](artefatos/conteineres-final.md) | Arquitetura distribuída, imagens Docker, por que o Kubernetes cobre só o caminho síncrono, tabela de decisões e mecanismos de resiliência |
| 4 | [Testes funcionais](artefatos/testes-funcionais.md) | Testes unitários, de integração, do UC03 com análise de valor-limite e de carga, com cobertura de requisitos e evidências em `artefatos/evidencias` |
| 4 | [Teste de hipótese por ingestão CDC](artefatos/teste-hipoteses-ingestao.md) | Roteiro que leva um lote de `POST /v1/changes` até `gold.hypothesis` (bronze → silver → checkpoint → detector), com a execução no lab de 23/09/2026 e a visualização no dashboard |

Os READMEs de cada parte da aplicação complementam os artefatos:

| Documento | Descrição |
|-----------|-----------|
| [Frontend](apps/fullstack/frontend/README.md) | Rotas, estrutura App Router, fontes de dados e comandos de validação |
| [API de leitura](apps/fullstack/backend/README.md) | Rotas, filtros, estratégias de consulta e variáveis de configuração |
| [Infraestrutura](apps/fullstack/infra/README.md) | Deploy, operação, DLQ, métricas, rede, Flow Logs e AWS Academy |
| [Kubernetes](apps/fullstack/k8s/README.md) | Runbook do cluster: manifestos, overlays, segredos, resiliência, custo e desligamento |
| [Testes de carga](apps/fullstack/tests/carga/README.md) | Como executar os scripts K6 de carga, escalabilidade e resiliência |

A API também se documenta em tempo de execução: `GET /docs` serve a Swagger UI e `GET /openapi.json` a especificação OpenAPI 3.1.

---

## Padrões de contribuição

- **Fluxo de branches:** branch de tema → `develop` → `main`. Nunca commitar direto em `main`.
- **Commits:** Conventional Commits em português, no imperativo, distribuídos ao longo da sprint.
- **Documentação de código:** docstrings (PEP 257) em Python e JSDoc em JavaScript. Todo módulo tem cabeçalho descritivo e toda função documenta parâmetros, retorno e comportamento.
- **Qualidade:** `make -C apps/fullstack check` roda o que a CI deveria rodar: `ruff`, `terraform fmt`/`validate` e as duas suítes de testes.
- **Tags:** uma tag `SPRINTN` por entrega (`SPRINT4` para esta), sem hífen, criada na data de entrega da sprint, como pede o enunciado. As tags anteriores variaram na grafia (`SPRINT-1`, `SPRINT-2`, `Sprint-3`) e foram mantidas como estão.

---

## Licença

<p>
  <img style="height:22px!important;margin-left:3px;vertical-align:text-bottom;" src="https://mirrors.creativecommons.org/presskit/icons/cc.svg?ref=chooser-v1" alt="Creative Commons">
  <img style="height:22px!important;margin-left:3px;vertical-align:text-bottom;" src="https://mirrors.creativecommons.org/presskit/icons/by.svg?ref=chooser-v1" alt="Attribution">
</p>

<p xmlns:cc="http://creativecommons.org/ns#" xmlns:dct="http://purl.org/dc/terms/">
  <a property="dct:title" rel="cc:attributionURL" href="https://git.inteli.edu.br/graduacao/2026-2a/t15/g04">Aplicação Escalável em Sistemas Distribuídos - Globo</a>
  by
  <a rel="cc:attributionURL dct:creator" property="cc:attributionName" href="https://www.inteli.edu.br/">Inteli</a>,
  Christian Vinícius Gandra dos Santos,
  Diego Figueiredo Silva,
  Gabriel Willian Bartmanovicz,
  Lívia Sabóia Tavares,
  Lorenzo Ferrari Aggio,
  Luiz Gustavo Borges Oliveira,
  Nicole Riedla Paiva Neves e
  Vinícius de Castro Cadena
  is licensed under
  <a href="https://creativecommons.org/licenses/by/4.0/?ref=chooser-v1" target="_blank" rel="license noopener noreferrer" style="display:inline-block;">Attribution 4.0 International</a>.
</p>
