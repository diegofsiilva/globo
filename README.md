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

São dois fluxos independentes ligados por um banco em comum: **ingestão** (aceita na borda, enfileira, valida de forma assíncrona e grava) e **leitura** (consulta, agrega e serve o dashboard).

```
App de TV ──> API Gateway ──> SQS ──> ECS Fargate ──> DynamoDB ──> Lambda ──> API Gateway ──> Dashboard
             (ingestão)       │        (worker)                   (API de     (leitura)      (Next.js
                              ▼                                   leitura)                    estático)
                            SQS DLQ
```

| Camada | Responsabilidade | Serviço AWS |
|--------|------------------|-------------|
| API de ingestão | Recebe os eventos e publica na fila por integração direta, sem Lambda no caminho | API Gateway (HTTP API) |
| Fila de mensagens | Absorve picos e garante a entrega; payload inválido vai para a DLQ com o motivo | SQS + DLQ |
| Worker | Consome a fila por long polling, valida, deduplica e grava em lote | ECS Fargate (ARM64) |
| Banco de dados | Tabela única com GSI1 (tipo + dia, com shard) e GSI2 (aparelho), TTL nativo | DynamoDB |
| API de leitura | Filtros cumulativos, agregações, paginação por cursor e redação de dado pessoal | AWS Lambda (Flask) + API Gateway |
| Dashboard | Visualização e investigação de incidentes | S3 (site estático) |

Escolhas de projeto, modelo de dados, garantias de entrega, custo e pendências estão detalhados em [`artefatos/arquitetura.md`](artefatos/arquitetura.md).

> **Estado:** ingestão, leitura e dashboard estão aplicados e validados ponta a ponta em AWS Academy Learner Lab. O que está no ar, o modelo de dados e o relatório de testes estão em [`artefatos/mvp-inicial.md`](artefatos/mvp-inicial.md).

---

## Estrutura de pastas

| Pasta / Arquivo | Conteúdo |
|-----------------|----------|
| `/apps/basica/backend` | API de leitura em Flask sobre Lambda, com arquitetura hexagonal |
| `/apps/basica/worker` | Worker de ingestão, que consome o SQS e grava no DynamoDB |
| `/apps/basica/frontend` | Dashboard em Next.js, export estático servido por S3 |
| `/apps/basica/infra` | Terraform de toda a infraestrutura AWS |
| `/apps/basica/tools` | Conversão dos CSVs de evento, replay para a API e ETL do dump |
| `/apps/basica/notebooks` | Análise exploratória do dataset do parceiro |
| `/artefatos` | Documentação das sprints: negócio, UX, requisitos, arquitetura e MVP |
| `/artefatos/assets` | Imagens e diagramas usados nos artefatos |
| `/artefatos/postman` | Coleção Postman de teste das duas APIs |
| `/assets` | Logos usados neste README |
| `Makefile` | Comandos do projeto; `make` sozinho lista os alvos |
| `.env.example` | Chaves de configuração; os valores ficam no `.env`, fora do repositório |
| `README.md` | Este arquivo |
| `.gitignore` | Arquivos e pastas ignorados pelo controle de versão |

---

## Execução local

### Pré-requisitos

- Python 3.12 ou superior
- [uv](https://docs.astral.sh/uv/), que monta os ambientes a partir do `pyproject.toml` de cada app
- Node.js 20+ (para o dashboard)
- Docker (para construir a imagem do worker)
- Terraform 1.x (para a infraestrutura)
- Credenciais AWS configuradas (`aws sts get-caller-identity` deve responder)

Em Codespaces ou VS Code, tudo o que segue funciona sem configuração adicional.

### Passos

```bash
# 1. clonar o repositório
git clone https://git.inteli.edu.br/graduacao/2026-2a/t15/g04.git
cd g04

# 2. configurar as variáveis de ambiente
make env                  # lê os endpoints do Terraform e escreve o .env
                          # (só funciona depois do primeiro apply — ver abaixo)

# 3. instalar as dependências dos dois apps Python
make install

# 4. rodar a suíte de testes (58 do worker + 72 do backend)
make test

# 5. subir a API de leitura local, apontando para o DynamoDB
make api

# 6. subir o dashboard contra a API publicada
make frontend-install
make frontend-dev
```

| Serviço | Porta local | Como subir |
|---------|-------------|------------|
| API de leitura | 5000 | `make api` |
| Dashboard | 3000 | `make frontend-dev` |

O backend também sobe por um único arquivo, sem `make`:

```bash
python apps/basica/backend/run.py
```

Esse ponto de entrada carrega o ambiente, cria a aplicação Flask e sobe o servidor; na primeira execução ele instala as dependências sozinho. No VS Code, abra `apps/basica/backend` como workspace, vá em **Run and Debug** e execute **Backend Flask** — é o mesmo `run.py`. O Dev Container do serviço está em `apps/basica/backend/.devcontainer`.

O worker não é executado localmente contra a fila real: use `make worker-image` para construir a imagem e `make replay` para reenviar os eventos de exemplo à API de ingestão publicada.

### Sem credenciais AWS

Os testes rodam contra um DynamoDB falso (moto), então `make test` e `make lint` funcionam sem nenhuma configuração de nuvem. Só os alvos de operação (`api`, `deploy`, `smoke`, `postman`, `frontend-dev`) precisam do `.env` preenchido.

> **Nenhuma URL de API ou identificador de conta é versionado.** Os valores vêm do `terraform output` e ficam no `.env`, que está no `.gitignore` — o mesmo vale para o environment do Postman (`artefatos/postman/environment.example.json`). Enquanto as APIs não tiverem autenticação, a URL é a única barreira de acesso aos dados.

Outros alvos úteis: `make lint`, `make check`, `make smoke` (verifica a API publicada), `make dlq` (mostra os eventos rejeitados com o motivo), `make pause` / `make resume` (desliga e religa o worker sem destruir a infraestrutura).

---

## Execução na AWS

Toda a infraestrutura é provisionada por Terraform em [`apps/basica/infra`](apps/basica/infra), que documenta o passo a passo completo, as adaptações do AWS Academy Learner Lab e o custo estimado (~US$ 14/mês para 1 milhão de eventos/mês).

| Recurso | Configuração |
|---------|--------------|
| API Gateway (ingestão) | HTTP API com integração direta `SQS-SendMessage` |
| SQS | Fila `argus-events-<ambiente>` com DLQ e redrive de 5 tentativas |
| ECS Fargate | 0.25 vCPU / 0.5 GB, ARM64, subnet pública sem regra de entrada |
| DynamoDB | Tabela única `argus-events-<ambiente>`, com GSI1, GSI2 e TTL |
| Lambda + API Gateway | API de leitura, empacotada por `scripts/build_lambda.sh` |
| S3 | Bucket com website hosting, que serve o export estático do dashboard |
| CloudWatch | Namespace `Argus/Ingestion` com 5 alarmes |

### Passos de implantação

Credenciais primeiro: [`artefatos/mvp-inicial.md` §6.2](artefatos/mvp-inicial.md#62-conectar-o-terraform-ao-aws-academy-learner-lab)
mostra como pegar as credenciais do AWS Academy Learner Lab em **AWS Details →
AWS CLI**, gravá-las num profile e preencher o `terraform.tfvars`. Com
`aws sts get-caller-identity` respondendo a conta certa:

```bash
# 1. empacota a API de leitura — o Terraform precisa do zip já no plan
make install
make lambda-build

# 2. cria a infraestrutura sem o worker (o ECR nasce vazio)
cd apps/basica/infra
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform apply -var="worker_desired_count=0"

# 3. publica a imagem do worker no ECR
cd ../../.. && make worker-deploy

# 4. liga o worker
cd apps/basica/infra && terraform apply -var="worker_desired_count=1"

# 5. gera o .env a partir dos outputs e publica o dashboard
cd ../../..
make env
make frontend-install
make frontend-deploy      # imprime o endereço público do dashboard
```

Nos deploys seguintes, `make deploy` testa, empacota, aplica e roda o smoke num
comando só.

Verificação:

```bash
make smoke      # confere as rotas da API publicada
make postman    # roda a coleção Postman contra as duas APIs
make count      # conta os eventos armazenados
make dlq        # mostra os eventos rejeitados, com o motivo
```

Para economizar crédito do lab, `make pause` desliga o worker sem destruir nada e `make resume` religa.

---

## Documentação

| Artefato | Descrição |
|----------|-----------|
| [MVP inicial](artefatos/mvp-inicial.md) | O que está implantado, modelo de dados e relatório de testes |
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
- **Qualidade:** `make check` roda o que a CI deveria rodar: `ruff`, `terraform fmt`/`validate` e as duas suítes de testes.
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
