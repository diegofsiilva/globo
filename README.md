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

A cadeia de entrega do Globoplay (player, CDN, backend, identidade, catálogo) é monitorada em silos: cada área tem seu próprio painel e vocabulário de métricas, o que faz com que a triagem de um incidente consuma mais tempo para descobrir *quem* conserta do que para de fato consertar. Além disso, degradações que não geram erro (buffer alto, tempo de início ruim) sequer acendem os alertas atuais. A solução é um sistema distribuído de telemetria com API única de ingestão, normalização dos eventos sob vocabulário comum, pipeline assíncrono de alta escala e camada de consulta que devolve uma linha do tempo única do incidente com o recorte afetado explícito, permitindo identificar a causa provável em minutos e sem depender de um especialista por componente.

O sistema ingere os seis eventos do MVP (`request`, `screen_view`, `session`, `video_view`, `vitals` e `error`) e ainda aceita tipos novos sem alteração de código, porque o parque de TVs atualiza devagar e um schema estrito viraria perda de dados em massa.

---

## Arquitetura

São **dois fluxos de ingestão** independentes que desembocam no mesmo banco, e um fluxo de leitura sobre ele.

O primeiro fluxo é o de **eventos de sessão**: o que o app de TV emite (`request`, `screen_view`, `session`, `video_view`, `vitals`, `error`). O segundo é o de **mudanças (CDC)**: as 33 tabelas de telemetria do parceiro não chegam como evento, chegam como *linha que mudou* — e é isso que o simulador reproduz.

```
App de TV ──> API Gateway ──> SQS ──> ECS Fargate ─┐
             (ingestão)                (event      │
                                        worker)    │
                                                   ├──> RDS PostgreSQL ──> Lambda ──> API Gateway ──> Dashboard
Simulador ──> API Gateway ──> SQS ──> ECS Fargate ─┘   bronze/silver/gold   (API de    (leitura)      (Next.js
 (ECS)       (mudanças)                (merge                                leitura)                  estático)
                                        worker)
```

Dentro do banco o dado atravessa quatro camadas, cada uma com um trabalho só:

| Camada | O que guarda | Por que existe |
|--------|--------------|----------------|
| `bronze` | `change_log` (append-only) + uma tabela *corrente* por tabela de origem, e `event` para o grain de sessão | O log é a fonte de verdade; a corrente é o MERGE dele. Dá para reconstruir a corrente do zero a partir do log |
| `silver` | `signal_point`, `signal_bucket`, `session_event` | Canonicaliza vocabulários que não se falam (`epoch_ms`, `ts`, `bts`, `ts_ms`, `hour_ts`, `start_ts`) num par `(ts, valor)` |
| `gold` | `feature_bucket`, `incident_window`, `live_event_window`, `circadian_state` | Traços de 15 min prontos para o dashboard, com hora local, dia da semana e "tem jogo" |
| `detect` | `run`, `anomaly` | Existe e está vazia: o detector é trabalho da próxima sprint, mas o contrato da API já é o final |

| Componente | Responsabilidade | Serviço AWS |
|------------|------------------|-------------|
| API de ingestão | Recebe os eventos de sessão e publica na fila por integração direta, sem Lambda no caminho | API Gateway (HTTP API) |
| API de mudanças | Recebe os *change events* do simulador, mesma integração direta | API Gateway (HTTP API) |
| Filas | Absorvem picos e garantem a entrega; payload inválido vai para a DLQ com o motivo | SQS + DLQ (duas filas) |
| Event worker | Consome a fila de eventos, valida e grava em `bronze.event` | ECS Fargate (ARM64) |
| Merge worker | Grava o change event em `bronze.change_log` e faz o MERGE na tabela corrente, na **mesma transação** | ECS Fargate (ARM64) |
| Simulador | Anda um relógio virtual e reemite as mudanças das tabelas como se estivessem acontecendo agora | ECS Fargate (ARM64) |
| Banco de dados | 33 tabelas de origem (68,7 M linhas), 6 delas particionadas por dia | RDS PostgreSQL 16 |
| Carga inicial | Sobe as 33 tabelas a partir de Parquet, via `COPY FROM STDIN` | ECS Fargate (task one-shot) |
| API de leitura | Filtros cumulativos, agregações, paginação por cursor e redação de dado pessoal | AWS Lambda (Flask) + API Gateway |
| Dashboard | Visualização e investigação de incidentes | S3 (site estático) |

### O relógio virtual

O dataset do parceiro é um **dump do passado**. Um dashboard "ao vivo" sobre ele mostraria uma tela vazia, porque nada tem a data de hoje. Por isso o sistema tem um presente próprio: `sim.now()`.

Toda linha carrega um `available_at` — o instante em que a informação *ficaria disponível na vida real*, contando a latência da fonte (a NPAW entrega com 28 h de atraso; o Prometheus, com 1 min). E **toda** view `v_*` filtra `available_at <= sim.now()`.

Isso não é um filtro de conveniência: é a barreira que impede vazamento de futuro. O usuário de leitura do banco (`argus_reader`) só tem `SELECT` nas views, nunca nas tabelas — então nem a API nem um detector futuro conseguem enxergar um dado antes da hora em que ele existiria.

Escolhas de projeto, modelo de dados, garantias de entrega, custo e pendências estão detalhados em [`artefatos/arquitetura-inicial.md`](artefatos/arquitetura-inicial.md).

> **Estado:** ingestão, leitura e dashboard estão aplicados e validados ponta a ponta em AWS Academy Learner Lab. O que está no ar, o modelo de dados e o relatório de testes estão em [`artefatos/mvp-inicial.md`](artefatos/mvp-inicial.md).

---

## Estrutura de pastas

| Pasta / Arquivo | Conteúdo |
|-----------------|----------|
| `/apps/basica/db/migrations` | As 14 migrations que constroem o banco, aplicadas em ordem por `tools/migrate.py` |
| `/apps/basica/backend` | API de leitura em Flask sobre Lambda, com arquitetura hexagonal |
| `/apps/basica/worker` | Os dois workers de ingestão (`merge` e `event`), que consomem o SQS e gravam na bronze |
| `/apps/basica/simulator` | Relógio virtual e emissor de mudanças, que reproduz o dump como se fosse hoje |
| `/apps/basica/loader` | Carga inicial das 33 tabelas, de Parquet para o PostgreSQL |
| `/apps/basica/processing` | Serviço de processamento; hoje um no-op documentado, futura casa do detector |
| `/apps/basica/common` | O que os quatro serviços compartilham: conexão, métricas e ciclo de vida |
| `/apps/basica/frontend` | Dashboard em Next.js, export estático servido por S3 |
| `/apps/basica/infra` | Terraform de toda a infraestrutura AWS |
| `/apps/basica/tools` | Migrations, geração do DDL, ETL do dump, conversão dos CSVs e replay |
| `/apps/basica/notebooks` | Análise exploratória do dataset do parceiro |
| `/artefatos` | Documentação das sprints: negócio, UX, requisitos, arquitetura e MVP |
| `/artefatos/assets` | Imagens e diagramas usados nos artefatos |
| `/artefatos/postman` | Coleção Postman de teste das duas APIs |
| `/assets` | Logos usados neste README |
| `/apps/basica/Makefile` | Comandos do projeto; `make -C apps/basica` lista os alvos |
| `/apps/basica/.env.example` | Chaves de configuração; os valores ficam em `/apps/basica/.env`, fora do repositório |
| `README.md` | Este arquivo |
| `.gitignore` | Arquivos e pastas ignorados pelo controle de versão |

---

## Execução local

### Pré-requisitos

- Python 3.12 ou superior
- [uv](https://docs.astral.sh/uv/), que monta os ambientes a partir do `pyproject.toml` de cada app
- Node.js 20+ (para o dashboard)
- Docker (para o PostgreSQL local e para construir as imagens dos serviços)
- Terraform 1.x (para a infraestrutura)
- Credenciais AWS configuradas (`aws sts get-caller-identity` deve responder)

Em Codespaces ou VS Code, tudo o que segue funciona sem configuração adicional.

### Passos

```bash
# 1. clonar o repositório
git clone https://git.inteli.edu.br/graduacao/2026-2a/t15/g04.git
cd g04

# 2. instalar as dependências dos apps Python
make -C apps/basica install

# 3. subir um PostgreSQL 16 local e aplicar as 14 migrations
make -C apps/basica db-local

# 4. rodar a suíte de testes (66 do worker + 85 do backend)
make -C apps/basica test

# 5. para usar serviços publicados, gerar as variáveis após o primeiro
#    terraform apply descrito na seção "Execução na AWS"
make -C apps/basica env

# 6. subir a API de leitura local, apontando para o banco local
make -C apps/basica api

# 7. subir o dashboard contra a API publicada
make -C apps/basica frontend-install
make -C apps/basica frontend-dev
```

O `db-local` sobe o container `argus-pg` na porta **55432** (e não 5432, para não colidir com um PostgreSQL já instalado na máquina), cria os bancos `argus` e `argus_test` e aplica as migrations. `make db-stop` derruba, `make db-psql` abre um `psql` dentro dele.

| Serviço | Porta local | Como subir |
|---------|-------------|------------|
| API de leitura | 5000 | `make -C apps/basica api` |
| Dashboard | 3000 | `make -C apps/basica frontend-dev` |

O backend também sobe por um único arquivo, sem `make`:

```bash
python apps/basica/backend/run.py
```

Esse ponto de entrada carrega o ambiente, cria a aplicação Flask e sobe o servidor; na primeira execução ele instala as dependências sozinho. No VS Code, abra `apps/basica/backend` como workspace, vá em **Run and Debug** e execute **Backend Flask** — é o mesmo `run.py`. O Dev Container do serviço está em `apps/basica/backend/.devcontainer`. Para apenas instalar, testar e analisar o código, não é necessário gerar o `.env` nem possuir credenciais AWS.

Os workers não são executados localmente contra a fila real: use `make -C apps/basica images` para construir as quatro imagens e `make -C apps/basica replay` para reenviar os eventos de exemplo à API de ingestão publicada.

### Sem credenciais AWS

Os testes usam um SQS falso (moto) mas um PostgreSQL **de verdade**, porque a parte difícil deste sistema é o SQL — o MERGE idempotente, o keyset de paginação, a barreira do `available_at`. Um dublê que respondesse "ok" a tudo isso testaria apenas o dublê.

Com `make db-local` no ar, `test` e `lint` funcionam sem nenhuma configuração de nuvem; sem ele, os testes que precisam de banco são **pulados** em vez de quebrarem. Só os alvos de operação (`api`, `deploy`, `smoke`, `postman`, `frontend-dev`) precisam do `.env` preenchido.

> **Nenhuma URL de API ou identificador de conta é versionado.** Os valores vêm do `terraform output` e ficam em `apps/basica/.env`, que está no `.gitignore` — o mesmo vale para o environment do Postman (`artefatos/postman/environment.example.json`). Enquanto as APIs não tiverem autenticação, a URL é a única barreira de acesso aos dados.

Outros alvos úteis, todos com o prefixo `make -C apps/basica`: `lint`, `check`, `smoke`, `dlq`, `pause` e `resume`.

---

## Execução na AWS

Toda a infraestrutura é provisionada por Terraform em [`apps/basica/infra`](apps/basica/infra), que documenta o passo a passo completo, as adaptações do AWS Academy Learner Lab e o custo estimado.

| Recurso | Configuração |
|---------|--------------|
| API Gateway (ingestão) | HTTP API com integração direta `SQS-SendMessage` |
| API Gateway (mudanças) | HTTP API com integração direta `SQS-SendMessage`, fila separada |
| SQS | Duas filas (`events` e `changes`), cada uma com DLQ e redrive de 5 tentativas |
| ECS Fargate | Quatro serviços ARM64 (merge worker, event worker, simulador, processamento) e uma task one-shot (carga) |
| RDS PostgreSQL 16 | `db.t3.medium`, 100 GB gp3, 33 tabelas de origem, 6 particionadas por dia |
| S3 (origem) | Bucket versionado com o dump e os Parquet que alimentam a carga inicial |
| Lambda + API Gateway | API de leitura, empacotada por `scripts/build_lambda.sh` |
| S3 (site) | Bucket com website hosting, que serve o export estático do dashboard |
| CloudWatch | Namespace `Argus/Ingestion` com alarmes de fila, banco e atraso do relógio virtual |

### Passos de implantação

Credenciais primeiro: [`artefatos/mvp-inicial.md` §6.2](artefatos/mvp-inicial.md#62-conectar-o-terraform-ao-aws-academy-learner-lab)
mostra como pegar as credenciais do AWS Academy Learner Lab em **AWS Details →
AWS CLI**, gravá-las num profile e preencher o `terraform.tfvars`.

> **O id da conta do Learner Lab muda a cada sessão nova.** Antes do apply, confira com `aws sts get-caller-identity --profile g4 --query Account --output text` e atualize o `existing_role_arn` do `terraform.tfvars`. E **todo** comando `aws` deste projeto leva `--profile g4`: sem ele a CLI usa o profile default, que é outra conta.

```bash
# 1. empacota a API de leitura — o Terraform precisa do zip já no plan
make -C apps/basica install
make -C apps/basica lambda-build

# 2. cria a infraestrutura sem os serviços (o ECR nasce vazio)
cd apps/basica/infra
cp terraform.tfvars.example terraform.tfvars   # e preencha
terraform init
terraform apply -var="worker_desired_count=0" -var="processing_desired_count=0"

# 3. publica as quatro imagens no ECR
cd ../../.. && make -C apps/basica push

# 4. aplica as migrations e cria o usuário de leitura
make -C apps/basica db-url        # mostra como montar a DATABASE_URL
make -C apps/basica migrate
make -C apps/basica db-reader

# 5. carga inicial: sobe o Parquet e dispara a task (20 a 30 min, 68,7 M linhas)
make -C apps/basica parquet       # só na primeira vez: dump MySQL -> Parquet
make -C apps/basica origem-sync
make -C apps/basica load

# 6. liga os workers e, depois que a carga terminar, o simulador
cd apps/basica/infra && terraform apply
cd ../../.. && make -C apps/basica sim-on

# 7. gera o .env a partir dos outputs e publica o dashboard
make -C apps/basica env
make -C apps/basica frontend-install
make -C apps/basica frontend-deploy      # imprime o endereço público do dashboard
```

O simulador fica desligado até a carga terminar de propósito: simular mudança sobre tabela vazia não produz nada útil.

Nos deploys seguintes, `make -C apps/basica deploy` testa, empacota, aplica e roda o smoke num
comando só.

Verificação:

```bash
make -C apps/basica smoke      # confere as rotas da API publicada
make -C apps/basica postman    # roda a coleção Postman contra as APIs
make -C apps/basica count      # conta as linhas carregadas por camada
make -C apps/basica dlq        # mostra o que foi rejeitado, com o motivo
make -C apps/basica logs SERVICO=worker    # worker|simulator|processing|loader
```

Para economizar crédito do lab, `pause` e `resume` desligam e religam os serviços sem destruir nada — o RDS continua de pé, que é o que guarda o trabalho da carga.

---

## Documentação

| Artefato | Descrição |
|----------|-----------|
| [MVP inicial](artefatos/mvp-inicial.md) | O que está implantado, modelo de dados e relatório de testes |
| [Arquitetura do Argus v3](artefatos/arquitetura-inicial.md) | Diagrama de implantação, nós, justificativa de arquitetura, schemas do banco, ETL incremental e plano de deploy |
| [Entendimento do negócio](artefatos/entendimento_negocio.md) | Matriz de Oceano Azul, análise de riscos e oportunidades, Value Proposition Canvas, análise financeira e ODS |
| [Entendimento de UX](artefatos/entendimento_ux.md) | Personas, user stories, wireframes, protótipo de alta fidelidade e avaliação heurística |
| [Requisitos](artefatos/requisitos.md) | Requisitos funcionais e não funcionais (ISO 25010) com planos de teste |
| [Arquitetura](artefatos/arquitetura.md) | Fluxos, modelo de dados, decisões de projeto, segurança, custo e validação |
| [API de leitura](apps/basica/backend/README.md) | Rotas, filtros, estratégias de consulta e variáveis de configuração |
| [Infraestrutura](apps/basica/infra/README.md) | Deploy, operação, DLQ, métricas e AWS Academy |

A API também se documenta em tempo de execução: `GET /docs` serve a Swagger UI e `GET /openapi.json` a especificação OpenAPI 3.1.

---

## Padrões de contribuição

- **Fluxo de branches:** branch de tema → `develop` → `main`. Nunca commitar direto em `main`.
- **Commits:** Conventional Commits em português, no imperativo, distribuídos ao longo da sprint.
- **Documentação de código:** docstrings (PEP 257) em Python e JSDoc em JavaScript. Todo módulo tem cabeçalho descritivo e toda função documenta parâmetros, retorno e comportamento.
- **Qualidade:** `make -C apps/basica check` roda o que a CI deveria rodar: `ruff`, `terraform fmt`/`validate` e as duas suítes de testes.
- **Tags:** uma tag `SPRINTX` por entrega, criada na data de entrega da sprint.

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
