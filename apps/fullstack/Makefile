# Comandos do projeto Argus (v3: RDS PostgreSQL, CDC e camadas bronze/silver/gold).
#
#   make            lista os alvos disponiveis
#   make check      roda tudo que a CI deveria rodar
#   make deploy     publica a API de leitura
#
# Endpoints, contas e senhas vem do .env (veja .env.example). Nenhum valor real
# e escrito aqui — este arquivo e versionado.

SHELL := /bin/bash
.DEFAULT_GOAL := help

# Carrega o .env quando existir, sem quebrar quando nao existir.
ifneq (,$(wildcard .env))
include .env
export
endif

COMMON     := common
AUTHORIZER := authorizer
WORKER     := worker
SIMULATOR  := simulator
PROCESSING := processing
LOADER     := loader
BACKEND    := backend
AGENTE     := agente
INFRA      := infra
TOOLS      := tools
FRONTEND   := frontend
POSTMAN    := ../../artefatos/postman
OBSERVABILITY := observability
TESTES_CARGA := tests/carga
OBSERVABILITY_COMPOSE := docker compose -p carga -f $(OBSERVABILITY)/docker-compose.yml

# A API de hipóteses faz parte da API de leitura. O mock continua disponível
# para desenvolvimento visual explícito, mas nunca é o padrão de um build.
HYPOTHESES_SOURCE ?= api
NEXT_BUILD_ARGS ?=

# Pasta com os CSVs de evento exportados do BI.
EVENTS_SRC ?= $(HOME)/Downloads/Events

# Parquet gerado por tools/etl_dump.py a partir do dump.
PARQUET_DIR ?= ../../data/parquet

# PostgreSQL local para migrations e testes. Porta 55432 e nao 5432 para nao
# colidir com um Postgres que ja esteja instalado na maquina.
PG_CONTAINER ?= argus-pg
PG_PORT      ?= 55432
PG_URL       := postgresql://argus:argus@localhost:$(PG_PORT)/argus
PG_TEST_URL  := postgresql://argus:argus@localhost:$(PG_PORT)/argus_test

# Portas do `make dev`. Variaveis, e nao numeros fixos nas receitas, porque no
# macOS o AirPlay Receiver escuta em 5000 e responde 403 no lugar da API -- o
# sintoma parece "a API subiu mas o dashboard nao autentica". `make dev
# API_PORT=5001` resolve sem tocar em arquivo nenhum.
API_PORT ?= 5000
WEB_PORT ?= 3000

# Token da tela de acesso no ambiente LOCAL. A API local sobe com
# AUTH_REQUIRED=0 e ignora o valor; a tela do dashboard so exige o FORMATO de
# 64 hexadecimais (lib/api/session.ts). Nao e segredo: e o que qualquer clone
# usa, e nunca vale contra a API publicada.
DEV_TOKEN := 0000000000000000000000000000000000000000000000000000000000000000

# `uv run` monta o ambiente sozinho a partir do pyproject de cada app.
UV := uv run --quiet

# As imagens de container.
#
# As quatro do pipeline (worker, simulator, processing, loader) constroem com
# contexto em apps/fullstack/ -- e nao na pasta de cada app -- porque todas
# dependem de common/.
#
# `backend` entrou quando a API de leitura saiu da Lambda e passou a rodar como
# container: primeiro nas instancias EC2 da Sprint 3 (caminho removido na
# Sprint 4), hoje como Deployment no cluster Kubernetes (k8s/). Ele NAO depende
# de common/, entao constroi com contexto so em backend/, que e muito menor.
#
# `frontend` entrou na Sprint 4, quando o dashboard passou a ser servido por um
# nginx dentro do cluster em vez de pelo website do S3. Tambem nao depende de
# common/, entao constroi com contexto so em frontend/.
IMAGES := worker simulator processing loader backend frontend

# Contexto de build por imagem. Ver acima por que backend e frontend diferem.
CONTEXTO = $(if $(filter backend frontend,$(1)),$(1),.)

# As imagens que o cluster Kubernetes executa (k8s/) precisam de amd64 E arm64.
#
# As node pools padrao do EKS Auto Mode sao amd64, enquanto o Fargate do caminho
# assincrono e as maquinas do time sao arm64 (Apple Silicon). Publicar so arm64
# colocaria o pod em CrashLoopBackOff com `exec format error` -- a mesma falha
# que ja mordeu o time na Sprint 3, quando a API rodava em EC2. As tres imagens
# que rodam SO no Fargate seguem arm64, que custa ~20% menos e dispensa emulacao
# no build.
#
# `processing` entrou nesta lista em 21/09/2026. Sao TRES as imagens que o
# cluster executa, e nao duas: alem do backend e do frontend, o `Job` de
# migration usa a imagem de processing (ver k8s/migrate/job-db-migrate.yaml).
# Publicada so em arm64, ela nunca poderia ter rodado nos nos amd64 do Auto
# Mode; no `kind` passava despercebido porque a maquina do dev e amd64. Quem
# guarda essa invariante agora e tools/verifica_manifests.py.
#
# A escolha da plataforma por imagem e feita no `push`, em shell: o nome da
# imagem la e variavel de SHELL (vem do laco), e uma funcao de make nao alcanca.
IMAGES_MULTIARCH := backend frontend processing

# A tag que as task definitions referenciam. NUNCA `latest`.
#
# Com `latest`, a task definition nao muda quando a imagem muda: o Terraform ve
# a mesma string, nao propoe nada, e o servico segue rodando o digest antigo. Foi
# assim que os tres servicos passaram a executar builds diferentes entre si.
#
# `-dirty` quando ha alteracao nao commitada: uma imagem construida a partir da
# arvore suja nao corresponde a nenhum commit, e a tag precisa dizer isso em vez
# de mentir que corresponde.
GIT_SHA := $(shell git rev-parse --short=12 HEAD)$(shell git diff --quiet || echo -dirty)
IMAGE_TAG ?= $(GIT_SHA)

# O Terraform le variavel por TF_VAR_*; `export` aqui vale para todos os alvos.
export TF_VAR_worker_image_tag = $(IMAGE_TAG)

.PHONY: help
help: ## Lista os alvos
	@echo "Argus — alvos disponiveis:"
	@echo
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo
	@echo "Variaveis: EVENTS_SRC=$(EVENTS_SRC)  PARQUET_DIR=$(PARQUET_DIR)"
	@if [ ! -f .env ]; then \
	  echo; echo "  Aviso: .env ausente. Copie de .env.example e preencha"; \
	  echo "  (os alvos de operacao precisam dele)."; \
	fi

# --------------------------------------------------------------------------- #
# Ambiente
# --------------------------------------------------------------------------- #

.PHONY: install
install: ## Instala as dependencias de todos os apps Python
	cd $(TOOLS) && uv sync --all-groups
	cd $(WORKER) && uv sync --all-groups
	cd $(SIMULATOR) && uv sync --all-groups
	cd $(PROCESSING) && uv sync --all-groups
	cd $(LOADER) && uv sync --all-groups
	cd $(BACKEND) && uv sync --extra dev
	cd $(AGENTE) && uv sync --all-groups

.PHONY: env
env: ## Cria o .env a partir dos outputs do Terraform
	@test -f .env && { echo ".env ja existe — apague antes se quiser regerar."; exit 1; } || true
	@echo "Lendo os endpoints do Terraform..."
	@# ARGUS_API_URL e o HTTP API da Lambda de leitura (`read_api_url`): o
	@# caminho de contingencia, que sempre existe no estado. O endereco publico
	@# do cluster vem do Ingress e nao passa pelo Terraform -- `make k8s-url`.
	@{ \
	  echo "ARGUS_API_URL=$$(cd $(INFRA) && terraform output -raw read_api_url 2>/dev/null)"; \
	  echo "ARGUS_INGEST_URL=$$(cd $(INFRA) && terraform output -raw ingest_url 2>/dev/null)"; \
	  echo "ARGUS_CHANGES_URL=$$(cd $(INFRA) && terraform output -raw changes_url 2>/dev/null)"; \
	  echo "HYPOTHESES_SOURCE=api"; \
	  echo "AWS_PROFILE=$${AWS_PROFILE:-default}"; \
	  echo "AWS_REGION=$${AWS_REGION:-us-east-1}"; \
	  echo "ARGUS_READ_TOKEN="; \
	  echo "ARGUS_INGEST_TOKEN="; \
	  echo '# DATABASE_URL: monte com "make db-url" (a senha nao passa por arquivo)'; \
	} > .env
	@echo ".env criado (esta no .gitignore)."
	@echo "Tokens ficam vazios de proposito -- preencha com 'make auth-show-ingest'"
	@echo "(so o de ingestao e recuperavel; o de leitura precisa de 'make auth-rotate')."

# --------------------------------------------------------------------------- #
# Banco
# --------------------------------------------------------------------------- #

.PHONY: db-local
db-local: ## Sobe um PostgreSQL 16 local e aplica as migrations
	@docker rm -f $(PG_CONTAINER) >/dev/null 2>&1 || true
	docker run -d --name $(PG_CONTAINER) \
	  -e POSTGRES_USER=argus -e POSTGRES_PASSWORD=argus -e POSTGRES_DB=argus \
	  -p $(PG_PORT):5432 postgres:16 >/dev/null
	@# A espera e por uma conexao TCP, e nao por `pg_isready` no socket unix:
	@# durante o initdb a imagem sobe um servidor TEMPORARIO que responde no
	@# socket e depois e derrubado. Quem esperasse por ele conectaria cedo demais
	@# e levaria "terminating connection due to administrator command" no meio da
	@# primeira migration. O servidor definitivo e o unico que escuta em TCP.
	@echo -n "esperando o banco subir"
	@for i in $$(seq 1 60); do \
	  docker exec $(PG_CONTAINER) psql -h 127.0.0.1 -U argus -d argus -qc \
	    "SELECT 1" >/dev/null 2>&1 && break; \
	  echo -n "."; sleep 1; \
	done; echo
	@docker exec $(PG_CONTAINER) psql -h 127.0.0.1 -U argus -d argus -qc \
	  "SELECT 1" >/dev/null || { echo "o banco nao subiu"; exit 1; }
	@docker exec $(PG_CONTAINER) psql -U argus -d postgres -qc \
	  "CREATE DATABASE argus_test" >/dev/null
	@$(MAKE) --no-print-directory migrate DATABASE_URL=$(PG_URL)
	@echo
	@echo "  banco:  $(PG_URL)"
	@echo "  testes: $(PG_TEST_URL)"

.PHONY: db-stop
db-stop: ## Derruba o PostgreSQL local
	docker rm -f $(PG_CONTAINER) >/dev/null 2>&1 || true

# `db-local` recria o container do zero (`docker rm -f`), e com ele vai embora
# o que `dev-seed` levou minutos para carregar. `db-ensure` e o que `make dev`
# chama: cria so quando nao existe, religa quando esta parado (reboot da
# maquina) e, em qualquer caso, aplica as migrations pendentes -- que e a parte
# idempotente por construcao (tools/migrate.py registra o que ja rodou).
#
# Receita em linhas separadas de proposito: a primeira e a ultima contem
# $(MAKE) e por isso EXECUTAM sob `make -n`; as do meio (docker start, espera)
# tem efeito colateral e ficam fora delas para que o dry-run continue seco.
.PHONY: db-ensure
db-ensure: ## Garante o PostgreSQL local no ar e migrado, sem recriar o que ja existe
	@docker container inspect $(PG_CONTAINER) >/dev/null 2>&1 || $(MAKE) --no-print-directory db-local
	@docker start $(PG_CONTAINER) >/dev/null
	@for i in $$(seq 1 60); do \
	  docker exec $(PG_CONTAINER) psql -h 127.0.0.1 -U argus -d argus -qc "SELECT 1" >/dev/null 2>&1 && break; \
	  sleep 1; \
	done
	@docker exec $(PG_CONTAINER) psql -h 127.0.0.1 -U argus -d argus -qc "SELECT 1" >/dev/null 2>&1 \
	  || { echo "o container $(PG_CONTAINER) existe mas nao responde; 'make db-local' recria do zero"; exit 1; }
	@$(MAKE) --no-print-directory migrate DATABASE_URL=$(PG_URL)

.PHONY: db-psql
db-psql: ## Abre um psql no banco local
	docker exec -it $(PG_CONTAINER) psql -U argus -d argus

.PHONY: migrate
migrate: ## Aplica as migrations pendentes (usa DATABASE_URL)
	@$(call require_env,DATABASE_URL)
	cd $(TOOLS) && $(UV) python migrate.py aplicar

.PHONY: migrate-status
migrate-status: ## Mostra quais migrations ja rodaram (usa DATABASE_URL)
	@$(call require_env,DATABASE_URL)
	cd $(TOOLS) && $(UV) python migrate.py status

# Os dois alvos abaixo rodam a MESMA ferramenta pela task `migration`, dentro da
# VPC. Sao o caminho para o RDS publicado desde que ele voltou a ser privado: da
# maquina de quem trabalha nao ha rota ate a porta 5432, e nem deve haver.
.PHONY: migrate-aws
migrate-aws: ## Aplica as migrations pendentes no RDS, pela VPC
	@$(call require_env,AWS_PROFILE)
	@cd $(INFRA) && terraform output -raw migration_run_command | bash
	@echo
	@echo "Acompanhe: make logs SERVICO=processing"

.PHONY: migrate-status-aws
migrate-status-aws: ## Lista as migrations aplicadas no RDS, pela VPC
	@$(call require_env,AWS_PROFILE)
	@cd $(INFRA) && terraform output -raw migration_status_command | bash
	@echo
	@echo "Acompanhe: make logs SERVICO=processing"

.PHONY: db-reader-aws
db-reader-aws: ## Cria/atualiza o usuario de leitura no RDS, pela VPC
	@$(call require_env,AWS_PROFILE)
	@cd $(INFRA) && terraform output -raw db_reader_run_command | bash
	@echo
	@echo "Acompanhe: make logs SERVICO=processing"

.PHONY: db-reader
db-reader: ## Cria o usuario de leitura que a Lambda usa
	@$(call require_env,DATABASE_URL)
	@$(call require_env,DB_READER_PASSWORD)
	@echo "A senha precisa ser a MESMA de read_api_db_password no terraform.tfvars."
	cd $(TOOLS) && $(UV) python migrate.py criar-leitor

.PHONY: db-url
db-url: ## Imprime como montar a DATABASE_URL do banco publicado
	@cd $(INFRA) && terraform output -raw database_url_hint

.PHONY: gen-ddl
gen-ddl: ## Regera a migration 004 a partir do schema do dump
	cd $(TOOLS) && $(UV) python gen_ddl.py --parquet ../$(PARQUET_DIR)

# --------------------------------------------------------------------------- #
# Qualidade
# --------------------------------------------------------------------------- #

.PHONY: test
test: test-worker test-simulator test-processing test-backend test-authorizer test-frontend test-observabilidade test-hypothesis-batch test-agente ## Roda as suites que tem teste

.PHONY: test-hypothesis-batch
test-hypothesis-batch: ## Valida o lote CDC sem usar AWS ou banco
	cd $(TOOLS) && $(UV) python -m unittest discover -s tests -p test_hypothesis_batch.py

.PHONY: test-observabilidade
test-observabilidade: ## Valida scripts, Compose e dashboards sem acessar AWS nem subir containers
	bash -n $(TESTES_CARGA)/executar_testes.sh
	@command -v docker >/dev/null 2>&1 \
		&& $(OBSERVABILITY_COMPOSE) config --quiet \
		|| echo "  compose pulado: Docker ausente."
	@for painel in $(OBSERVABILITY)/grafana/dashboards/*.json; do \
		python3 -m json.tool "$$painel" >/dev/null || exit 1; \
	done

.PHONY: test-authorizer
test-authorizer: ## Testes do Lambda authorizer (Bearer, audiencias, rotacao)
	@# `handler.py` cria o cliente do Secrets Manager no import, e o botocore so
	@# aceita a regiao por AWS_DEFAULT_REGION -- AWS_REGION, que e o que o .env
	@# define, nao basta. Sem isso a coleta do pytest quebra com NoRegionError
	@# numa maquina sem a variavel no shell. Nenhuma chamada sai daqui: o cliente
	@# so precisa de uma regiao para ser construido.
	cd $(AUTHORIZER) && AWS_DEFAULT_REGION=$${AWS_DEFAULT_REGION:-$${AWS_REGION:-us-east-1}} uv run --quiet --group dev pytest

# TEST_DATABASE_URL aponta para o banco de teste local por padrao. Os testes que
# precisam de banco sao PULADOS quando ele nao existe, em vez de quebrarem —
# assim `make test` numa maquina sem docker ainda valida models, keys e changes.
.PHONY: test-worker
test-worker: ## Testes dos workers de ingestao
	cd $(WORKER) && TEST_DATABASE_URL=$${TEST_DATABASE_URL:-$(PG_TEST_URL)} $(UV) pytest

.PHONY: test-backend
test-backend: ## Testes da API de leitura
	@# O backend declara pytest e ruff em [project.optional-dependencies].dev,
	@# e nao em [dependency-groups].dev como os outros apps. `uv run` nao
	@# instala extras sozinho: sem `--extra dev`, num clone limpo o alvo
	@# morre com "Failed to spawn: pytest".
	cd $(BACKEND) && TEST_DATABASE_URL=$${TEST_DATABASE_URL:-$(PG_TEST_URL)} $(UV) --extra dev pytest

.PHONY: test-simulator
test-simulator: ## Testes do relogio e do emissor do simulador
	cd $(SIMULATOR) && $(UV) pytest

.PHONY: test-processing
test-processing: ## Testes do ETL incremental (watermarks, workers)
	cd $(PROCESSING) && TEST_DATABASE_URL=$${TEST_DATABASE_URL:-$(PG_TEST_URL)} $(UV) pytest

# O piloto do agente nao toca banco, AWS nem rede: o modelo entra por dublê de
# roteiro. O alvo roda em qualquer maquina, e e por isso que ele esta no `test`.
.PHONY: test-agente
test-agente: ## Testes do piloto de hipoteses com IA (ciclo, tetos e validador)
	cd $(AGENTE) && $(UV) pytest


.PHONY: test-frontend
test-frontend: ## Testes de contratos e componentes do dashboard
	cd $(FRONTEND) && npm test

# Mesma regra dos testes Python que dependem de banco: sem a dependencia, o
# alvo PULA em vez de quebrar. `make check` numa maquina sem docker ou sem o
# Chromium do Playwright continua validando lint, tipos, unitarios e Terraform,
# em vez de falhar por infraestrutura ausente e ensinar o time a ignorar o
# portao.
# Recipe de UMA linha logica so, de proposito: cada linha de recipe roda no seu
# proprio shell, entao um `exit 0` numa linha de guarda encerraria apenas
# aquela linha e o make seguiria para a proxima -- rodando exatamente o que a
# guarda queria evitar.
.PHONY: test-frontend-e2e
test-frontend-e2e: ## Teste integrado dashboard -> Flask -> PostgreSQL local
	@set -e; \
	if ! docker exec $(PG_CONTAINER) psql -U argus -d argus_test -qc "SELECT 1" >/dev/null 2>&1; then \
	  echo "  pulado: PostgreSQL local ausente (rode 'make -C apps/fullstack db-local')."; \
	  exit 0; \
	fi; \
	if ! (cd $(FRONTEND) && npx playwright install --dry-run chromium >/dev/null 2>&1); then \
	  echo "  pulado: Chromium do Playwright ausente (rode 'npx playwright install chromium')."; \
	  exit 0; \
	fi; \
	$(MAKE) --no-print-directory migrate DATABASE_URL=$(PG_TEST_URL); \
	docker exec -i $(PG_CONTAINER) psql -v ON_ERROR_STOP=1 -U argus -d argus_test \
	  < $(FRONTEND)/tests/e2e/fixture.sql; \
	cd $(FRONTEND) && \
	  NEXT_PUBLIC_API_URL="http://127.0.0.1:5100" \
	  NEXT_PUBLIC_HYPOTHESES_SOURCE="api" \
	  npm run build -- --webpack; \
	npm run test:e2e

.PHONY: lint
lint: ## Verifica estilo sem alterar arquivos
	cd $(TOOLS) && $(UV) ruff check . && $(UV) ruff format --check .
	cd $(COMMON) && uv run --quiet --with ruff ruff check src
	cd $(WORKER) && $(UV) ruff check src tests && $(UV) ruff format --check src tests
	cd $(SIMULATOR) && $(UV) ruff check src
	cd $(PROCESSING) && $(UV) ruff check src tests && $(UV) ruff format --check src tests
	cd $(LOADER) && $(UV) ruff check src
	cd $(BACKEND) && $(UV) --extra dev ruff check src tests
	cd $(AGENTE) && $(UV) ruff check src tests && $(UV) ruff format --check src tests
	cd $(AUTHORIZER) && uv run --quiet --with ruff ruff check handler.py tests
	cd $(FRONTEND) && npm run lint
	cd $(INFRA) && terraform fmt -check -recursive

.PHONY: fmt
fmt: ## Formata o codigo e o Terraform
	@# `ruff check --fix` sai com erro quando resta algo que ele nao conserta
	@# sozinho. Aqui isso nao deve interromper a formatacao — quem barra e o
	@# alvo `lint`, que e o portao de qualidade.
	cd $(TOOLS) && ($(UV) ruff check --fix . || true) && $(UV) ruff format .
	cd $(WORKER) && ($(UV) ruff check --fix src tests || true) && $(UV) ruff format src tests
	cd $(SIMULATOR) && ($(UV) ruff check --fix src || true) && $(UV) ruff format src
	cd $(PROCESSING) && ($(UV) ruff check --fix src tests || true) && $(UV) ruff format src tests
	cd $(LOADER) && ($(UV) ruff check --fix src || true) && $(UV) ruff format src
	cd $(BACKEND) && ($(UV) --extra dev ruff check --fix src tests || true) && $(UV) --extra dev ruff format src tests
	cd $(AGENTE) && ($(UV) ruff check --fix src tests || true) && $(UV) ruff format src tests
	cd $(AUTHORIZER) && uv run --quiet --with ruff ruff format handler.py tests
	cd $(INFRA) && terraform fmt -recursive

.PHONY: check
check: lint test frontend-build-check test-frontend-e2e tf-validate tf-test k8s-validate ## Tudo que a CI deveria rodar

# O build do dashboard faz parte do portao, e nao so o lint.
#
# O `next build` roda o TypeScript e a geracao estatica das sete rotas. Um erro
# de tipo num Server Component ou uma rota que deixou de exportar passa pelo
# eslint e so aparece aqui -- ou, sem este alvo, no deploy.
#
# A URL e um placeholder: o objetivo e compilar, nao falar com a API. O build
# falha de proposito sem `NEXT_PUBLIC_API_URL` (ver frontend/AGENTS.md, regra 1),
# entao alguma URL precisa existir.
.PHONY: frontend-build-check
frontend-build-check: ## Compila o dashboard com URL de placeholder (portao de CI)
	cd $(FRONTEND) && \
	  NEXT_PUBLIC_API_URL="https://api.invalido.local" \
	  NEXT_PUBLIC_HYPOTHESES_SOURCE="mock" \
	  npm run build

# --------------------------------------------------------------------------- #
# Desenvolvimento
# --------------------------------------------------------------------------- #

.PHONY: api
api: ## Sobe a API de leitura local contra o banco local (porta API_PORT)
	cd $(BACKEND) && DATABASE_URL=$${DATABASE_URL:-$(PG_URL)} PORT=$(API_PORT) $(UV) python lambda_handler.py

# `dev` e o caminho de UM comando: banco, API e dashboard no mesmo terminal, e
# Ctrl-C derruba os tres. A orquestracao (subir em paralelo, esperar a API
# responder antes do dashboard, matar a ARVORE de processos na saida) vive em
# scripts/dev.sh, que so encadeia alvos deste Makefile -- nenhum passo e
# reproduzido la. Nao usa `make -j2 api frontend-dev` porque o -j nao espera a
# API antes de subir o Next, nao imprime URL nem token no fim, e ao morrer
# deixa python e node orfaos presos nas portas.
#
# O banco e SEMPRE o local: `dev` passa DATABASE_URL explicitamente, para que
# um .env com a URL do RDS nao faca a API local apontar para a nuvem em
# silencio. Quem quer a API publicada usa `frontend-dev` com ARGUS_API_URL.
#
# Sem $(MAKE) nesta linha, de proposito: o GNU Make executa de verdade qualquer
# linha de receita que o contenha, mesmo sob `make -n` -- e o dry-run subiria
# tudo. O script chama `make` pelo PATH.
.PHONY: dev
dev: ## Sobe banco local, API e dashboard juntos; Ctrl-C derruba tudo
	@API_PORT=$(API_PORT) WEB_PORT=$(WEB_PORT) \
	  PG_CONTAINER=$(PG_CONTAINER) PG_URL=$(PG_URL) DEV_TOKEN=$(DEV_TOKEN) \
	  DEV_API_URL="$(DEV_API_URL)" scripts/dev.sh

# Amostra para as telas nao abrirem vazias. O unico dado real e o do parceiro
# (4 GB, nao redistribuivel -- AGENTS.md regra 9), que nao vem no clone: quem
# tem o dump gera o Parquet uma vez (`make parquet`) e este alvo o carrega no
# banco local, reconstroi silver e gold e posiciona o relogio virtual no ultimo
# evento -- toda view filtra `available_at <= sim.now()`, e com o relogio no
# inicio do dump as telas continuariam vazias mesmo com o banco cheio.
#
# `make replay` NAO serve aqui: ele reenvia os seis eventos de exemplo a API de
# ingestao PUBLICADA (API Gateway -> SQS -> worker), que nao existe localmente.
#
# Condicional de make, e nao `if` de shell: a guarda e a carga precisam ficar
# em linhas separadas (uma so linha com $(MAKE) executaria o psql sob -n), e
# um `exit 0` na linha da guarda nao impediria as seguintes de rodar.
.PHONY: dev-seed
dev-seed: ## Carrega a amostra do parceiro no banco local (precisa de ../../data/parquet)
ifeq (,$(wildcard $(PARQUET_DIR)/*.parquet))
	@echo "sem amostra: $(PARQUET_DIR) nao existe neste clone, entao o banco segue vazio."
	@echo "  O dado e do parceiro (4 GB, nao redistribuivel). Quem tem o dump gera o Parquet"
	@echo "  com 'make parquet' e roda 'make dev-seed' de novo. 'make replay' nao substitui"
	@echo "  isto: ele fala com a API de ingestao publicada, que nao existe localmente."
else
	@$(MAKE) --no-print-directory load-local DATABASE_URL=$(PG_URL)
	@echo "reconstruindo silver e gold a partir da bronze..."
	@docker exec $(PG_CONTAINER) psql -U argus -d argus -qc "SELECT * FROM gold.rebuild_tudo();"
	@docker exec $(PG_CONTAINER) psql -U argus -d argus -qc \
	  "SELECT sim.set_clock(COALESCE((SELECT max(ts) FROM silver.session_event), sim.now()));"
	@echo "amostra carregada; relogio virtual posicionado no ultimo evento."
endif

# --------------------------------------------------------------------------- #
# Piloto de hipoteses com IA (experimental, fora do motor deterministico)
# --------------------------------------------------------------------------- #

# AGENTE_CASOS aceita um arquivo ou um diretorio de casos.
AGENTE_CASOS ?= $(AGENTE)/fixtures
AGENTE_SAIDA ?= $(AGENTE)/saidas/lote

.PHONY: agente-ensaio
agente-ensaio: ## Roda o lote do piloto com o dublê de roteiro, sem rede nem modelo
	cd $(AGENTE) && $(UV) agentectl --modelo roteiro --roteiro fixtures/roteiros \
	  lote fixtures --saida saidas/lote-ensaio

.PHONY: agente-lote
agente-lote: ## Roda o lote do piloto no Ollama (precisa das chaves OLLAMA_* no .env)
	@test -n "$$OLLAMA_URL" || { echo "defina OLLAMA_URL e OLLAMA_MODEL no .env"; exit 1; }
	cd $(AGENTE) && $(UV) agentectl lote ../$(AGENTE_CASOS) --saida ../$(AGENTE_SAIDA)

.PHONY: agente-recorte-real
agente-recorte-real: ## Reconstroi um recorte real da bronze (PostgreSQL local) para o piloto
	@test -n "$$DATABASE_URL" || { echo "defina DATABASE_URL (make db-url)"; exit 1; }
	psql "$$DATABASE_URL" -v ON_ERROR_STOP=1 \
	  -v entidade='$(or $(AGENTE_ENTIDADE),br1|playback.video.globo.com)' \
	  -v janela_inicio='$(or $(AGENTE_JANELA_INICIO),2026-08-18 00:00+00)' \
	  -v janela_fim='$(or $(AGENTE_JANELA_FIM),2026-08-31 00:00+00)' \
	  -v presente='$(or $(AGENTE_PRESENTE),2026-08-21 08:00+00)' \
	  -f $(AGENTE)/scripts/reconstruir_recorte_real.sql

.PHONY: agente-investigar-banco
agente-investigar-banco: ## Investiga um checkpoint real do PostgreSQL local (CHECKPOINT=, ENTIDADE=)
	@test -n "$$DATABASE_URL" -a -n "$(CHECKPOINT)" -a -n "$(ENTIDADE)" || { echo "defina DATABASE_URL, CHECKPOINT e ENTIDADE"; exit 1; }
	cd $(AGENTE) && $(UV) agentectl investigar-banco --checkpoint $(CHECKPOINT) --entidade "$(ENTIDADE)" --lookback $(or $(LOOKBACK),360)

.PHONY: agente-checar
agente-checar: ## Confirma que o Ollama configurado no .env responde
	cd $(AGENTE) && $(UV) agentectl checar-modelo

.PHONY: docs
docs: ## Abre a documentacao Swagger da API publicada
	@$(call require_env,ARGUS_API_URL)
	@echo "Abrindo a Swagger UI..."
	@open "$(ARGUS_API_URL)/docs" 2>/dev/null || echo "Acesse: $$ARGUS_API_URL/docs"

.PHONY: openapi
openapi: ## Salva a especificacao OpenAPI em backend/openapi.json
	@$(call require_env,ARGUS_API_URL)
	curl -s "$(ARGUS_API_URL)/openapi.json" -o $(BACKEND)/openapi.json
	@echo "gravado em $(BACKEND)/openapi.json"

.PHONY: events-json
events-json: ## Converte os CSVs do BI em JSON canonico (fixtures)
	cd $(TOOLS) && $(UV) python events_csv_to_json.py --src "$(EVENTS_SRC)" --out ../$(WORKER)/tests/fixtures

.PHONY: parquet
parquet: ## Converte o dump MySQL em Parquet (demora ~5 min)
	cd $(TOOLS) && $(UV) python etl_dump.py --dump ../../../argus_dump.sql --out ../$(PARQUET_DIR)

# --------------------------------------------------------------------------- #
# Imagens
# --------------------------------------------------------------------------- #

# ARM64 no build local: a Lambda e arm64 e as tasks Fargate sao arm64. As
# imagens que o cluster executa (IMAGES_MULTIARCH) ganham tambem amd64 no
# `push` -- ver o comentario no topo do arquivo.
.PHONY: images
images: $(addprefix image-,$(IMAGES)) ## Constroi as imagens (ARM64)

# Build-args de quem tem configuracao COMPILADA para dentro do artefato. O Next
# resolve `NEXT_PUBLIC_*` em tempo de build e congela o valor no bundle: passar a
# variavel no ambiente do contêiner nao tem efeito nenhum.
#
# Sem esta linha, o `ARG NEXT_PUBLIC_HYPOTHESES_SOURCE=mock` do Dockerfile
# vencia, e a imagem do dashboard ia para o cluster com a tela de Hipoteses
# servida por dado simulado -- enquanto o caminho antigo, do S3, usava `api`
# (ver `frontend-build`). O E2E-05 pega isso.
BUILD_ARGS_frontend := --build-arg NEXT_PUBLIC_HYPOTHESES_SOURCE=$(HYPOTHESES_SOURCE)

.PHONY: $(addprefix image-,$(IMAGES))
$(addprefix image-,$(IMAGES)): image-%:
	@# Build local: uma arquitetura so, a da propria maquina. O multi-arquitetura
	@# custa o dobro do tempo e so faz falta ao publicar -- ver `push`.
	docker build -f $*/Dockerfile -t argus-$*:dev \
	  --build-arg GIT_SHA=$(GIT_SHA) $(BUILD_ARGS_$*) $(call CONTEXTO,$*)

.PHONY: image-tag
image-tag: ## Mostra a tag de imagem deste commit
	@echo "$(IMAGE_TAG)"

# --------------------------------------------------------------------------- #
# Infraestrutura
# --------------------------------------------------------------------------- #

.PHONY: tf-init
tf-init: ## Inicializa o Terraform
	cd $(INFRA) && terraform init

.PHONY: tf-validate
tf-validate: ## Valida a configuracao sem tocar na AWS
	cd $(INFRA) && terraform validate

.PHONY: tf-test
tf-test: ## Testa a rede com provider mockado, sem tocar na AWS
# `validate` confirma sintaxe, tipos e referencias. Nao confirma que a
# COMBINACAO de variaveis produz uma rede valida -- CIDR de sub-rede fora da
# VPC, ou task privada pedindo IP publico, passam por ele. Isto pega.
#
# Roda offline: nao precisa de sessao do Learner Lab, que vence em horas.
	cd $(INFRA) && terraform test

.PHONY: tf-plan
tf-plan: lambda-build ## Mostra o que mudaria na AWS (somente leitura)
	@$(call require_env,AWS_PROFILE)
	cd $(INFRA) && terraform plan

.PHONY: tf-apply
tf-apply: lambda-build ## Aplica as mudancas na AWS
	@$(call require_env,AWS_PROFILE)
	cd $(INFRA) && terraform apply

.PHONY: tf-output
tf-output: ## Mostra os endpoints e nomes de recurso
	@$(call require_env,AWS_PROFILE)
	cd $(INFRA) && terraform output

.PHONY: tf-destroy
tf-destroy: ## Remove TODA a infraestrutura
	@echo "Isto apaga o BANCO com as 33 tabelas, as filas e os servicos."
	@echo "O bucket de origem tem versionamento, mas tambem vai."
	@read -p "Digite 'destruir' para confirmar: " r; [ "$$r" = "destruir" ] || { echo "cancelado."; exit 1; }
	@$(call require_env,AWS_PROFILE)
	cd $(INFRA) && terraform destroy

.PHONY: lambda-build
lambda-build: ## Empacota a API de leitura e o authorizer para a Lambda
	cd $(BACKEND) && ./scripts/build_lambda.sh
	cd $(AUTHORIZER) && ./scripts/build_lambda.sh

.PHONY: lambda-hash
lambda-hash: lambda-build ## Imprime o hash local dos zips (compare com o CodeSha256 publicado)
	@echo "commit:     $(GIT_SHA)"
	@echo "read-api:   $$(openssl dgst -sha256 -binary $(BACKEND)/dist/telemetry-read-api.zip | openssl base64)"
	@echo "authorizer: $$(openssl dgst -sha256 -binary $(AUTHORIZER)/dist/argus-authorizer.zip | openssl base64)"
	@echo
	@echo "Publicado na AWS:"
	@$(call require_env,AWS_PROFILE)
	@cluster=$$(cd $(INFRA) && terraform output -raw ecs_cluster_name); \
	 for fn in read-api authorizer; do \
	   printf "  %-11s %s\n" "$$fn:" \
	     "$$(aws lambda get-function-configuration --function-name "$$cluster-$$fn" \
	          --query CodeSha256 --output text --profile $$AWS_PROFILE 2>/dev/null || echo '(ausente)')"; \
	 done

.PHONY: deploy
deploy: test-backend lambda-build ## Testa, empacota e publica a API de leitura
	@$(call require_env,AWS_PROFILE)
	cd $(INFRA) && terraform apply -auto-approve
	@$(MAKE) --no-print-directory smoke

.PHONY: push
push: ## Publica as imagens no ECR com a tag do commit
	@$(call require_env,AWS_PROFILE)
	@case "$(IMAGE_TAG)" in *-dirty) \
	  echo "erro: a arvore tem alteracao nao commitada ($(IMAGE_TAG))."; \
	  echo "      Publicar assim gera uma imagem que nao corresponde a commit"; \
	  echo "      nenhum, e o rollback deixa de ter para onde voltar."; \
	  exit 1;; esac
	@echo "publicando com a tag $(IMAGE_TAG)"
	@# `docker buildx build --push` e nao `docker build` + `docker push`: uma
	@# imagem multi-arquitetura e uma LISTA de manifestos, que so existe no
	@# registry. O `docker push` empurraria apenas a arquitetura carregada no
	@# daemon local, e o pod amd64 do EKS falharia com `exec format error`.
	@# A tag vem do Makefile, e a URL do repositorio vem do `terraform output`.
	@#
	@# Nao use `docker_push_commands` aqui. `terraform output` le do STATE, e nao
	@# da configuracao: enquanto o apply que introduziu a tag por SHA nao rodar,
	@# aquele output ainda descreve `:latest`. Publicar por ele deixaria o ECR sem
	@# a tag que as task definitions novas referenciam, e o apply seguinte
	@# derrubaria os servicos em ImagePullBackOff -- com a causa aparecendo como
	@# "imagem nao encontrada", longe da linha que a originou.
	@#
	@# `ecr_repository_urls` nao tem esse problema: a URL de um repositorio nao
	@# muda, entao o valor em state e sempre o correto.
	@$(call require_env,AWS_PROFILE)
	@set -e; \
	registry=$$(cd $(INFRA) && terraform output -json ecr_repository_urls \
	  | python3 -c "import json,sys; print(json.load(sys.stdin)['worker'].split('/')[0])"); \
	aws ecr get-login-password --region $${AWS_REGION:-us-east-1} --profile $$AWS_PROFILE \
	  | docker login --username AWS --password-stdin "$$registry"; \
	urls=$$(cd $(INFRA) && terraform output -json ecr_repository_urls); \
	for nome in $(IMAGES); do \
	  url=$$(printf '%s' "$$urls" | python3 -c "import json,sys; print(json.load(sys.stdin)['$$nome'])"); \
	  echo; echo "--- $$nome"; \
	  contexto="."; \
	  case " backend frontend " in *" $$nome "*) contexto="$$nome";; esac; \
	  plataformas="linux/arm64"; \
	  case " $(IMAGES_MULTIARCH) " in *" $$nome "*) plataformas="linux/amd64,linux/arm64";; esac; \
	  echo "    plataformas: $$plataformas"; \
	  extra=""; \
	  case "$$nome" in frontend) extra="$(BUILD_ARGS_frontend)";; esac; \
	  docker buildx build --platform "$$plataformas" -f $$nome/Dockerfile \
	    --build-arg GIT_SHA=$(GIT_SHA) $$extra \
	    -t "$$url:$(IMAGE_TAG)" -t "$$url:latest" --push "$$contexto"; \
	done
	@echo
	@echo "publicadas com a tag $(IMAGE_TAG). Agora rode: make tf-apply"

# `push` publica; ELE NAO troca a task definition. Quem troca e o `tf-apply`,
# porque a tag do commit entrou na task definition -- e por isso que o servico
# passa a rodar o digest novo sem ninguem forcar deploy a mao.
.PHONY: rollout
rollout: push tf-apply ## Publica as imagens e aplica as novas task definitions
	@$(MAKE) --no-print-directory digests

.PHONY: digests
digests: ## Confere que cada servico roda o digest da tag publicada
	@$(call require_env,AWS_PROFILE)
	@cluster=$$(cd $(INFRA) && terraform output -raw ecs_cluster_name); \
	fail=0; \
	for servico in event-worker merge-worker processing simulator; do \
	  td=$$(aws ecs describe-services --cluster "$$cluster" \
	         --services "$$cluster-$$servico" --profile $$AWS_PROFILE \
	         --query 'services[0].taskDefinition' --output text 2>/dev/null); \
	  [ "$$td" = "None" ] && continue; \
	  img=$$(aws ecs describe-task-definition --task-definition "$$td" \
	          --profile $$AWS_PROFILE \
	          --query 'taskDefinition.containerDefinitions[0].image' --output text); \
	  tag=$${img##*:}; \
	  if [ "$$tag" = "$(IMAGE_TAG)" ]; then st="ok   "; else st="ATRAS"; fail=1; fi; \
	  printf "  %s %-14s %s\n" "$$st" "$$servico" "$$tag"; \
	done; \
	[ $$fail -eq 0 ] || echo "  esperado: $(IMAGE_TAG)"; \
	exit $$fail

# --------------------------------------------------------------------------- #
# Autenticacao (RNF09)
# --------------------------------------------------------------------------- #

# Gera os dois tokens, grava os HASHES no Secrets Manager e imprime os valores
# em claro UMA vez. Depois disso nao ha como recupera-los: o que a AWS guarda e
# o SHA-256, e o unico caminho de volta e gerar tokens novos.
#
# Os valores nao passam por arquivo nem por argumento de linha de comando --
# argumento aparece no `ps` de qualquer processo da maquina e fica no historico
# do shell.
.PHONY: auth-rotate
auth-rotate: ## Gera e publica tokens Bearer novos (invalida os antigos)
	@$(call require_env,AWS_PROFILE)
	@echo "Isto INVALIDA os tokens atuais. O dashboard vai pedir o token de novo,"
	@echo "e o simulador precisa ser reiniciado para pegar o valor novo."
	@# Os dois segredos so existem depois do apply que os cria, e `terraform
	@# output` le do state. Sem esta checagem, a mensagem seria "Output not
	@# found", que nao diz o que fazer.
	@cd $(INFRA) && terraform output -raw auth_tokens_secret >/dev/null 2>&1 || { \
	  echo "erro: os segredos ainda nao existem na AWS."; \
	  echo "      Rode 'make tf-apply' antes -- e o apply que os cria."; \
	  exit 1; }
	@read -p "Digite 'rotacionar' para confirmar: " r; [ "$$r" = "rotacionar" ] || { echo "cancelado."; exit 1; }
	@set -euo pipefail; \
	 region="$${AWS_REGION:-us-east-1}"; \
	 hashes_id=$$(cd $(INFRA) && terraform output -raw auth_tokens_secret); \
	 ingest_id=$$(cd $(INFRA) && terraform output -raw ingest_token_secret); \
	 read_api_id=$$(cd $(INFRA) && terraform output -raw read_api_id); \
	 ingest_api_id=$$(cd $(INFRA) && terraform output -raw ingest_api_id); \
	 echo "Validando credenciais e acesso aos segredos..."; \
	 aws secretsmanager describe-secret --profile "$$AWS_PROFILE" --region "$$region" \
	   --secret-id "$$hashes_id" >/dev/null; \
	 aws secretsmanager describe-secret --profile "$$AWS_PROFILE" --region "$$region" \
	   --secret-id "$$ingest_id" >/dev/null; \
	 dash=$$(openssl rand -hex 32); ing=$$(openssl rand -hex 32); \
	 dash_h=$$(printf '%s' "$$dash" | openssl dgst -sha256 -r | cut -d' ' -f1); \
	 ing_h=$$(printf '%s' "$$ing" | openssl dgst -sha256 -r | cut -d' ' -f1); \
	 printf '%s' "$$ing" | aws secretsmanager put-secret-value \
	   --profile "$$AWS_PROFILE" --region "$$region" --secret-id "$$ingest_id" \
	   --secret-string file:///dev/stdin >/dev/null; \
	 printf '{"dashboard":"%s","ingest":"%s"}' "$$dash_h" "$$ing_h" \
	   | aws secretsmanager put-secret-value --profile "$$AWS_PROFILE" --region "$$region" \
	       --secret-id "$$hashes_id" --secret-string file:///dev/stdin >/dev/null; \
	 hashes_publicados=$$(aws secretsmanager get-secret-value \
	   --profile "$$AWS_PROFILE" --region "$$region" --secret-id "$$hashes_id" \
	   --query SecretString --output text); \
	 printf '%s' "$$hashes_publicados" \
	   | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d == {"dashboard": sys.argv[1], "ingest": sys.argv[2]}' \
	       "$$dash_h" "$$ing_h"; \
	 ingest_publicado=$$(aws secretsmanager get-secret-value \
	   --profile "$$AWS_PROFILE" --region "$$region" --secret-id "$$ingest_id" \
	   --query SecretString --output text); \
	 [ "$$ingest_publicado" = "$$ing" ] || { echo "erro: verificacao do token de ingestao falhou." >&2; exit 1; }; \
	 cache_falhou=0; \
	 for api_id in "$$read_api_id" "$$ingest_api_id"; do \
	   if ! aws apigatewayv2 reset-authorizers-cache --profile "$$AWS_PROFILE" \
	     --region "$$region" --api-id "$$api_id" --stage-name '$$default'; then \
	     cache_falhou=1; \
	   fi; \
	 done; \
	 echo; \
	 echo "  Token de LEITURA  (cole somente os 64 caracteres, sem 'Bearer '):"; \
	 echo "    $$dash"; \
	 echo; \
	 echo "  Token de INGESTAO (export ARGUS_INGEST_TOKEN=...):"; \
	 echo "    $$ing"; \
	 echo; \
	 echo "  Guarde-os agora. A AWS so tem o hash do token de leitura."; \
	 if [ $$cache_falhou -ne 0 ]; then \
	   echo "  AVISO: tokens publicados, mas o cache nao foi limpo por completo." >&2; \
	   echo "         O token antigo pode continuar valido por ate 5 minutos." >&2; \
	   exit 1; \
	 fi; \
	 echo "  Rotacao concluida: o token novo ja pode ser usado."

.PHONY: auth-show-ingest
auth-show-ingest: ## Imprime o token de ingestao (o unico recuperavel)
	@$(call require_env,AWS_PROFILE)
	@aws secretsmanager get-secret-value --profile $$AWS_PROFILE \
	  --secret-id "$$(cd $(INFRA) && terraform output -raw ingest_token_secret)" \
	  --query SecretString --output text

# --------------------------------------------------------------------------- #
# Carga inicial
# --------------------------------------------------------------------------- #

.PHONY: origem-sync
origem-sync: ## Sobe o dump e o Parquet para o bucket de origem
	@$(call require_env,AWS_PROFILE)
	@bucket=$$(cd $(INFRA) && terraform output -raw origem_bucket); \
	aws s3 sync $(PARQUET_DIR)/ "s3://$$bucket/parquet/" --profile $$AWS_PROFILE; \
	echo "subindo o dump (4 GB, demora)..."; \
	aws s3 cp ../../argus_dump.sql "s3://$$bucket/dump/" --profile $$AWS_PROFILE

.PHONY: load
load: ## Dispara a carga inicial das 33 tabelas no RDS
	@$(call require_env,AWS_PROFILE)
	@echo "Disparando a task de carga (20 a 30 min para 68,7 M linhas)..."
	@cd $(INFRA) && terraform output -raw loader_run_command | bash

.PHONY: load-local
load-local: ## Carrega os Parquet no banco LOCAL (util para desenvolver)
	cd $(LOADER) && DATABASE_URL=$${DATABASE_URL:-$(PG_URL)} \
	  $(UV) python -m argus_loader --local ../$(PARQUET_DIR)

.PHONY: etl
etl: ## Reconstroi silver e gold a partir da bronze (recompute completo, idempotente)
	@$(call require_env,DATABASE_URL)
	@psql "$$DATABASE_URL" -c "SELECT * FROM gold.rebuild_tudo();"

.PHONY: etl-incremental
etl-incremental: ## Roda manualmente UM ciclo do ETL incremental (bronze->silver e silver->gold)
	@$(call require_env,DATABASE_URL)
	@psql "$$DATABASE_URL" -c "SELECT * FROM etl.executar_bronze_silver();"
	@psql "$$DATABASE_URL" -c "SELECT * FROM etl.executar_silver_gold();"

# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #

.PHONY: frontend-install
frontend-install: ## Instala as dependencias do dashboard
	cd $(FRONTEND) && npm ci

# Diz QUAL versao esta publicada, em /build-info.json.
#
# Sem isso, ao ver um comportamento estranho na tela publicada nao ha como saber
# se ela corresponde ao codigo que se esta lendo -- e a resposta padrao vira
# "publica de novo e ve se muda", que gasta uma sessao de laboratorio.
#
# Nao entra endpoint nem id de conta: e um arquivo publico, servido a qualquer
# visitante da distribuicao.
.PHONY: frontend-build-info
frontend-build-info: ## Grava frontend/public/build-info.json com commit e data
	@printf '{\n  "commit": "%s",\n  "built_at": "%s",\n  "version": "%s"\n}\n' \
	  "$(GIT_SHA)" "$$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
	  "$$(cd $(FRONTEND) && node -p "require('./package.json').version")" \
	  > $(FRONTEND)/public/build-info.json
	@echo "build-info.json: $(GIT_SHA)"

# A URL da API entra no bundle em tempo de build e NUNCA fica escrita no codigo
# (ver .env.example). Sem ela o build falha de proposito: um bundle apontando
# para o proprio dominio devolveria o HTML da pagina no lugar do JSON, e o erro
# so apareceria no navegador do usuario.
.PHONY: frontend-build
frontend-build: frontend-build-info ## Gera o site estatico do dashboard
	@$(call require_env,ARGUS_API_URL)
	cd $(FRONTEND) && \
	  NEXT_PUBLIC_API_URL="$(ARGUS_API_URL)" \
	  NEXT_PUBLIC_HYPOTHESES_SOURCE="$(HYPOTHESES_SOURCE)" \
	  npm run build -- $(NEXT_BUILD_ARGS)

.PHONY: frontend-deploy
frontend-deploy: frontend-build ## Publica o dashboard no website S3
	@$(call require_env,AWS_PROFILE)
	aws s3 sync $(FRONTEND)/out/ \
	  "s3://$$(cd $(INFRA) && terraform output -raw frontend_bucket)/" --delete
	@echo
	@echo "Dashboard no ar: $$(cd $(INFRA) && terraform output -raw frontend_url)"

.PHONY: frontend-dev
frontend-dev: ## Sobe o dashboard local contra a API de ARGUS_API_URL (porta WEB_PORT)
	@$(call require_env,ARGUS_API_URL)
	cd $(FRONTEND) && \
	  NEXT_PUBLIC_API_URL="$(ARGUS_API_URL)" \
	  NEXT_PUBLIC_HYPOTHESES_SOURCE="$(HYPOTHESES_SOURCE)" \
	  npm run dev -- --port $(WEB_PORT)

# --------------------------------------------------------------------------- #
# Testes de API (Postman)
# --------------------------------------------------------------------------- #

# Os tokens entram como `secret`, e nao `default`: o Postman mascara o valor na
# interface e o omite ao exportar a colecao. O arquivo continua gitignored --
# `secret` protege a tela e o compartilhamento acidental, nao o disco.
.PHONY: postman-env
postman-env: ## Gera o environment do Postman a partir do .env
	@$(call require_env,ARGUS_API_URL)
	@$(call require_env,ARGUS_INGEST_URL)
	@$(call require_env,ARGUS_READ_TOKEN)
	@$(call require_env,ARGUS_INGEST_TOKEN)
	@printf '%s\n' \
	  '{' \
	  '  "name": "Argus — lab (gerado, nao versionado)",' \
	  '  "values": [' \
	  '    { "key": "read_url", "value": "$(ARGUS_API_URL)", "type": "default", "enabled": true },' \
	  '    { "key": "ingest_url", "value": "$(ARGUS_INGEST_URL)", "type": "default", "enabled": true },' \
	  '    { "key": "changes_url", "value": "$(ARGUS_CHANGES_URL)", "type": "default", "enabled": true },' \
	  '    { "key": "read_token", "value": "$(ARGUS_READ_TOKEN)", "type": "secret", "enabled": true },' \
	  '    { "key": "ingest_token", "value": "$(ARGUS_INGEST_TOKEN)", "type": "secret", "enabled": true }' \
	  '  ],' \
	  '  "_postman_variable_scope": "environment"' \
	  '}' > $(POSTMAN)/environment.json
	@echo "$(POSTMAN)/environment.json gerado (esta no .gitignore)"

.PHONY: postman
postman: postman-env ## Roda a colecao Postman contra as APIs publicadas
	npx --yes newman@6 run $(POSTMAN)/argus.postman_collection.json \
	  -e $(POSTMAN)/environment.json --delay-request 1500

# O resumo vai para o repositorio como evidencia; o JSON completo NAO, porque
# carrega os cabecalhos de cada requisicao -- inclusive o Authorization. O
# `jq` abaixo extrai so as contagens e o commit.
.PHONY: postman-evidencia
postman-evidencia: postman-env ## Roda a colecao e versiona um resumo sanitizado
	@mkdir -p $(POSTMAN)/evidencias
	@tmp=$$(mktemp); \
	npx --yes newman@6 run $(POSTMAN)/argus.postman_collection.json \
	  -e $(POSTMAN)/environment.json --delay-request 1500 \
	  --reporters cli,json --reporter-json-export "$$tmp"; \
	status=$$?; \
	jq --arg commit "$(GIT_SHA)" --arg data "$$(date -u +%Y-%m-%dT%H:%M:%SZ)" '{ \
	  commit: $$commit, executado_em_utc: $$data, ambiente: "AWS (lab)", \
	  colecao: .collection.info.name, \
	  requisicoes: .run.stats.requests, \
	  assertions: .run.stats.assertions, \
	  duracao_ms: .run.timings.completed - .run.timings.started, \
	  falhas: [.run.failures[]? | {teste: .error.test, motivo: .error.message}] \
	}' "$$tmp" > $(POSTMAN)/evidencias/newman-resumo.json; \
	rm -f "$$tmp"; \
	echo; echo "resumo em $(POSTMAN)/evidencias/newman-resumo.json"; \
	exit $$status

# --------------------------------------------------------------------------- #
# Operacao
# --------------------------------------------------------------------------- #

.PHONY: smoke
smoke: ## Verifica a API publicada: autenticacao, status, latencia e tamanho
	@$(call require_env,ARGUS_API_URL)
	@$(call require_env,ARGUS_READ_TOKEN)
	@echo "Testando $$ARGUS_API_URL"
	@fail=0; \
	auth="Authorization: Bearer $$ARGUS_READ_TOKEN"; \
	origin=$$(cd $(INFRA) && terraform output -raw frontend_url); \
	origin=$${origin%/}; \
	headers=$$(mktemp); \
	trap 'rm -f "$$headers"' EXIT; \
	check() { \
	  code=$$(curl -s -o /dev/null -w '%{http_code}' "$$@"); \
	  echo "$$code"; \
	}; \
	echo; echo "  --- CORS do dashboard"; \
	c=$$(curl -s -o /dev/null -D "$$headers" -w '%{http_code}' -X OPTIONS \
	  -H "Origin: $$origin" -H "Access-Control-Request-Method: GET" \
	  -H "Access-Control-Request-Headers: authorization" \
	  "$(ARGUS_API_URL)/api/v1/clock"); \
	if [ "$$c" = "200" ] || [ "$$c" = "204" ]; then st="ok   "; else st="FALHA"; fail=1; fi; \
	printf "  %s %3s  preflight OPTIONS   (esperado 200/204)\n" "$$st" "$$c"; \
	allow_origin=$$(awk 'tolower($$0) ~ /^access-control-allow-origin: */ {sub(/^[^:]+: */, ""); gsub(/\r/, ""); print}' "$$headers" | tail -1); \
	if [ "$$allow_origin" = "$$origin" ]; then st="ok   "; else st="FALHA"; fail=1; fi; \
	printf "  %s      origem do dashboard permitida\n" "$$st"; \
	allow_headers=$$(awk -F': *' 'tolower($$1) == "access-control-allow-headers" {gsub(/\r/, "", $$2); print tolower($$2)}' "$$headers" | tail -1 | tr -d ' '); \
	case ",$$allow_headers," in *,authorization,*) st="ok   ";; *) st="FALHA"; fail=1;; esac; \
	printf "  %s      header Authorization permitido\n" "$$st"; \
	echo; echo "  --- autenticacao (RNF09)"; \
	c=$$(check "$(ARGUS_API_URL)/api/v1/sources"); \
	if [ "$$c" = "401" ]; then st="ok   "; else st="FALHA"; fail=1; fi; \
	printf "  %s %3s  sem token           (esperado 401)\n" "$$st" "$$c"; \
	c=$$(check -H "Authorization: Bearer token-invalido" "$(ARGUS_API_URL)/api/v1/sources"); \
	if [ "$$c" = "403" ]; then st="ok   "; else st="FALHA"; fail=1; fi; \
	printf "  %s %3s  token invalido      (esperado 403)\n" "$$st" "$$c"; \
	c=$$(check "$(ARGUS_API_URL)/health/live"); \
	if [ "$$c" = "200" ]; then st="ok   "; else st="FALHA"; fail=1; fi; \
	printf "  %s %3s  /health/live publico (esperado 200)\n" "$$st" "$$c"; \
	echo; echo "  --- rotas autenticadas (RNF02: teto de 5s)"; \
	for path in \
	  "/health/ready" \
	  "/openapi.json" \
	  "/api/v1/clock" \
	  "/api/v1/sources" \
	  "/api/v1/signals" \
	  "/api/v1/series?limit=10" \
	  "/api/v1/series/facets" \
	  "/api/v1/incidents?limit=5" \
	  "/api/v1/events?limit=1" \
	  "/api/v1/changes" \
	  "/api/v1/timeline" \
	  "/api/v1/facets?field=event_name"; do \
	  read -r code t size < <(curl -s -o /dev/null -H "$$auth" \
	    -w '%{http_code} %{time_total} %{size_download}\n' "$(ARGUS_API_URL)$$path"); \
	  st="ok   "; \
	  [ "$$code" = "200" ] || { st="FALHA"; fail=1; }; \
	  awk -v t="$$t" 'BEGIN{exit !(t > 5)}' && { st="LENTO"; fail=1; }; \
	  printf "  %s %3s %6.2fs %7s  %s\n" "$$st" "$$code" "$$t" \
	    "$$(echo $$size | awk '{printf "%.0fKB", $$1/1024}')" "$$path"; \
	done; \
	exit $$fail

.PHONY: replay
replay: ## Reenvia os eventos de exemplo para a API de ingestao
	@$(call require_env,ARGUS_INGEST_URL)
	@$(call require_env,ARGUS_INGEST_TOKEN)
	cd $(TOOLS) && $(UV) python replay_events.py --url "$(ARGUS_INGEST_URL)" --src "$(EVENTS_SRC)"

# BATCH_FILE deve ser absoluto e apontar para fora do repositorio.
# O envio e separado da preparacao para permitir
# revisar as 52 mudancas antes de colocá-las na fila.
.PHONY: hypothesis-batch-prepare hypothesis-batch-send hypothesis-batch-verify
.PHONY: hypothesis-agent-case
hypothesis-agent-case: ## Repete um caso sintético do agente (AGENT_CASE=degradacao_sintetica)
	@case_name="$${AGENT_CASE:-degradacao_sintetica}"; \
	cd $(TOOLS) && $(UV) python agente_hipoteses_caso.py \
	  --case "../$(AGENTE)/fixtures/sinteticos/$${case_name}.json"

.PHONY: hypothesis-agent-db
hypothesis-agent-db: ## Consulta fatos reais de um checkpoint (CHECKPOINT_ID=... ENTITY=... AGENT_QUERIES=...)
	@$(call require_env,DATABASE_URL)
	@test -n "$(CHECKPOINT_ID)" -a -n "$(ENTITY)" || { echo "CHECKPOINT_ID e ENTITY obrigatórios"; exit 1; }
	@cd $(TOOLS) && $(UV) python agente_hipoteses_db.py \
	  --checkpoint-id "$(CHECKPOINT_ID)" --entity "$(ENTITY)" \
	  $(if $(AGENT_QUERIES),--queries "$(AGENT_QUERIES)")

hypothesis-batch-prepare: ## Prepara lote CDC (BATCH_FILE=/caminho/fora/do/repo.json)
	@$(call require_env,DATABASE_URL)
	@test -n "$(BATCH_FILE)" || { echo "defina BATCH_FILE" >&2; exit 1; }
	cd $(TOOLS) && $(UV) python hypothesis_batch.py prepare --output "$(BATCH_FILE)"

hypothesis-batch-send: ## Envia lote CDC preparado uma vez (BATCH_FILE=...)
	@$(call require_env,ARGUS_CHANGES_URL)
	@$(call require_env,ARGUS_INGEST_TOKEN)
	@test -n "$(BATCH_FILE)" || { echo "defina BATCH_FILE" >&2; exit 1; }
	cd $(TOOLS) && $(UV) python hypothesis_batch.py send --input "$(BATCH_FILE)"

hypothesis-batch-verify: ## Mostra Bronze, Silver, Gold e hipotese do lote
	@$(call require_env,DATABASE_URL)
	@test -n "$(BATCH_FILE)" || { echo "defina BATCH_FILE" >&2; exit 1; }
	cd $(TOOLS) && $(UV) python hypothesis_batch.py verify --input "$(BATCH_FILE)"

.PHONY: observabilidade-up
observabilidade-up: ## Sobe Prometheus e Grafana locais (dashboards de resiliencia RNF04/05/11 e de carga RNF01/02/03)
	@command -v docker >/dev/null || { echo "erro: docker nao encontrado no PATH."; exit 1; }
	@# So o perfil selecionado vai pro container -- nunca o arquivo inteiro, que pode ter
	@# outros perfis (ex. default) sem relacao com este dashboard. `mktemp` (nao
	@# um nome fixo) evita reaproveitar permissao de um arquivo antigo. Sem o
	@# perfil, Prometheus e o dashboard k6 continuam disponiveis; apenas as
	@# consultas CloudWatch ficam sem autenticacao.
	@set -eu; \
	perfil="$${AWS_PROFILE:-g4}"; \
	creds_tmp=$$(mktemp); \
	trap 'rm -f "$$creds_tmp"' EXIT; \
	if [ -f "$(HOME)/.aws/credentials" ]; then \
		awk -v perfil="$$perfil" '\
		  $$0 == "[" perfil "]" {f=1; print "[g4]"; next} \
		  /^\[/ {f=0} f' "$(HOME)/.aws/credentials" > "$$creds_tmp"; \
	fi; \
	if [ -s "$$creds_tmp" ]; then \
		echo "CloudWatch: credencial temporaria do perfil $$perfil habilitada."; \
	else \
		echo "Aviso: perfil $$perfil ausente; seguindo somente com Prometheus/k6."; \
	fi; \
	AWS_CREDS_FILE="$$creds_tmp" $(OBSERVABILITY_COMPOSE) up -d
	@echo "Prometheus: http://localhost:9090"
	@echo "Grafana:    http://localhost:3001 (dashboards 'RNF04/05/11 - Resiliencia Argus' e 'Argus — Testes de Carga (RNF01/02/03)'), acessivel so pela propria maquina."

.PHONY: observabilidade-down
observabilidade-down: ## Derruba Prometheus e Grafana locais (preserva os volumes; 'down -v' manual apaga o historico)
	$(OBSERVABILITY_COMPOSE) down

.PHONY: observabilidade-check
observabilidade-check: ## Valida Prometheus, Grafana e os dois datasources (Prometheus e CloudWatch)
	@set -euo pipefail; \
	aguardar() { \
		nome="$$1"; url="$$2"; \
		for _ in $$(seq 1 30); do \
			curl -fsS "$$url" >/dev/null 2>&1 && return 0; \
			sleep 1; \
		done; \
		echo "FALHA: $$nome nao ficou pronto em 30 segundos ($$url)."; \
		return 1; \
	}; \
	aguardar Prometheus http://localhost:9090/-/ready; \
	aguardar Grafana http://localhost:3001/api/health; \
	auth="$${GRAFANA_USER:-admin}:$${GRAFANA_PASSWORD:-admin}"; \
	uid=$$(curl -fsS -u "$$auth" \
		http://localhost:3001/api/datasources/name/Prometheus | jq -r '.uid'); \
	[ "$$uid" = "prometheus" ] || { \
		echo "FALHA: datasource Prometheus usa uid=$$uid; esperado prometheus."; \
		exit 1; \
	}; \
	series=$$(curl -fsSG -u "$$auth" \
		http://localhost:3001/api/datasources/proxy/uid/prometheus/api/v1/query \
		--data-urlencode 'query=up{job="prometheus"}' | \
		jq -r '.data.result | length'); \
	[ "$$series" -gt 0 ] || { \
		echo "FALHA: Grafana nao recebeu series do Prometheus."; \
		exit 1; \
	}; \
	cw_uid=$$(curl -fsS -u "$$auth" \
		http://localhost:3001/api/datasources/name/CloudWatch | jq -r '.uid'); \
	[ "$$cw_uid" = "cloudwatch-g4" ] || { \
		echo "FALHA: datasource CloudWatch usa uid=$$cw_uid; esperado cloudwatch-g4."; \
		exit 1; \
	}; \
	echo "OK: Prometheus e CloudWatch integrados ao Grafana (series prometheus=$$series)."

.PHONY: teste-performance
teste-performance: ## Executa a suite k6 (CENARIO=todos; COM_GRAFANA=1 habilita metricas)
	$(TESTES_CARGA)/executar_testes.sh "$${CENARIO:-todos}" \
		$(if $(filter 1 sim true,$(COM_GRAFANA)),--com-grafana,)

.PHONY: teste-carga-ui
teste-carga-ui: ## Carga sobre as telas do dashboard em 3 niveis (5, 25 e 100 usuarios)
	$(TESTES_CARGA)/executar_testes.sh carga-ui \
		$(if $(filter 1 sim true,$(COM_GRAFANA)),--com-grafana,)

.PHONY: teste-carga-ui-ec2
teste-carga-ui-ec2: ## Mesma carga das telas, gerada de uma EC2 descartavel dentro da VPC
	@$(call require_env,AWS_PROFILE)
	$(TESTES_CARGA)/gerador_ec2.sh carga-ui

.PHONY: teste-lote-drenagem
teste-lote-drenagem: ## Injeta 1 lote logico de 150 mil eventos (nao mede sozinho a drenagem)
	K6_QUANTIDADE_LOTES=1 $(TESTES_CARGA)/executar_testes.sh rnf01-lote \
		$(if $(filter 1 sim true,$(COM_GRAFANA)),--com-grafana,)

.PHONY: teste-lotes-acumulados
teste-lotes-acumulados: ## Injeta 2-4 lotes logicos (LOTES=2); use com o event-worker parado
	@lotes=$${LOTES:-2}; \
	case "$$lotes" in 2|3|4) ;; *) echo "LOTES deve ser 2, 3 ou 4"; exit 2;; esac; \
	K6_QUANTIDADE_LOTES="$$lotes" $(TESTES_CARGA)/executar_testes.sh rnf01-acumulo \
		$(if $(filter 1 sim true,$(COM_GRAFANA)),--com-grafana,)

# Carga sustentada para os testes de RNF01 (1.000 ev/min) e RNF03 (2.000
# ev/min com os workers escalados). `--rate` e por SEGUNDO, dai a divisao.
.PHONY: carga
carga: ## Carga sustentada de ingestao (EVENTOS_POR_MINUTO=1000 MINUTOS=5)
	@$(call require_env,ARGUS_INGEST_URL)
	@$(call require_env,ARGUS_INGEST_TOKEN)
	@epm=$${EVENTOS_POR_MINUTO:-1000}; mins=$${MINUTOS:-5}; \
	total=$$((epm * mins)); \
	echo "$$epm ev/min por $$mins min = $$total eventos"; \
	cd $(TOOLS) && $(UV) python replay_events.py \
	  --url "$(ARGUS_INGEST_URL)" --src "$(EVENTS_SRC)" \
	  --repeat $$((total / 6 + 1)) --rate $$(($$epm / 60))

# Carga sustentada contra /v1/changes (CDC), nao /v1/events -- e o fluxo do
# pivot v3 que a Sprint de NFR pede testar (10 mil eventos/min). Mesmo script
# serve de gerador de trafego de fundo nos cenarios de resiliencia (fila
# cheia, timeout), que escalam o merge-worker por fora enquanto isto roda.
.PHONY: carga-changes
carga-changes: ## Carga K6 contra /v1/changes (EVENTOS_POR_MINUTO=10000 MINUTOS=5)
	@command -v k6 >/dev/null || { \
	  echo "erro: k6 nao encontrado no PATH."; \
	  echo "      Instale a partir de https://k6.io/docs/get-started/installation/"; \
	  exit 1; \
	}
	@$(call require_env,ARGUS_CHANGES_URL)
	@$(call require_env,ARGUS_INGEST_TOKEN)
	cd $(TOOLS)/loadtest && k6 run \
	  -e ARGUS_CHANGES_URL="$(ARGUS_CHANGES_URL)" \
	  -e ARGUS_INGEST_TOKEN="$(ARGUS_INGEST_TOKEN)" \
	  -e EVENTOS_POR_MINUTO=$${EVENTOS_POR_MINUTO:-10000} \
	  -e MINUTOS=$${MINUTOS:-5} \
	  changes_load.js

# --------------------------------------------------------------------------- #
# Cenarios de resiliencia (RNF04, RNF05) -- ver /projeto/plano-teste-resiliencia.md
# (fora do repo). Ao contrario de carga-changes, os tres primeiros mexem em
# infraestrutura de verdade (terraform apply / aws ecs) e exigem credencial
# AWS valida -- so o resiliencia-evento-invalido fala so HTTP.
# --------------------------------------------------------------------------- #

.PHONY: resiliencia-evento-invalido
resiliencia-evento-invalido: ## RNF04: eventos invalidos misturados a validos (REPETICOES=3)
	@command -v k6 >/dev/null || { \
	  echo "erro: k6 nao encontrado no PATH."; \
	  exit 1; \
	}
	@$(call require_env,ARGUS_CHANGES_URL)
	@$(call require_env,ARGUS_INGEST_TOKEN)
	cd $(TOOLS)/loadtest && k6 run \
	  -e ARGUS_CHANGES_URL="$(ARGUS_CHANGES_URL)" \
	  -e ARGUS_INGEST_TOKEN="$(ARGUS_INGEST_TOKEN)" \
	  -e REPETICOES=$${REPETICOES:-3} \
	  eventos_invalidos.js
	@echo "Agora rode: make dlq   (confere FailureReason)"
	@echo "        e:  make count (confere que os validos do mesmo lote sobreviveram)"

.PHONY: resiliencia-fila-cheia
resiliencia-fila-cheia: ## RNF05a "fila cheia": desliga o merge-worker, sustenta carga, religa e observa a drenagem
	@command -v k6 >/dev/null || { echo "erro: k6 nao encontrado no PATH."; exit 1; }
	@$(call require_env,ARGUS_CHANGES_URL)
	@$(call require_env,ARGUS_INGEST_TOKEN)
	@$(call require_env,AWS_PROFILE)
	@echo "1/4: escalando merge-worker para 0 (terraform vai pedir confirmacao)"
	cd $(INFRA) && terraform apply -var="worker_desired_count=0"
	@echo "2/4: carga sustentada com o worker desligado ($${EVENTOS_POR_MINUTO:-10000} ev/min por $${MINUTOS:-10} min)"
	cd $(TOOLS)/loadtest && k6 run \
	  -e ARGUS_CHANGES_URL="$(ARGUS_CHANGES_URL)" \
	  -e ARGUS_INGEST_TOKEN="$(ARGUS_INGEST_TOKEN)" \
	  -e EVENTOS_POR_MINUTO=$${EVENTOS_POR_MINUTO:-10000} \
	  -e MINUTOS=$${MINUTOS:-10} \
	  changes_load.js
	@echo "3/4: religando o merge-worker (terraform vai pedir confirmacao)"
	cd $(INFRA) && terraform apply -var="worker_desired_count=$${WORKER_DESIRED_COUNT:-1}"
	@echo "4/4: aguardando a fila 'changes' drenar"
	@fila=$$(cd $(INFRA) && terraform output -raw changes_queue_url); \
	while true; do \
	  n=$$(aws sqs get-queue-attributes --profile "$(AWS_PROFILE)" --region "$${AWS_REGION:-us-east-1}" \
	    --queue-url "$$fila" --attribute-names ApproximateNumberOfMessages \
	    --query 'Attributes.ApproximateNumberOfMessages' --output text); \
	  echo "  mensagens visiveis na fila changes: $$n"; \
	  [ "$$n" = "0" ] && break; \
	  sleep 15; \
	done
	@echo "Fila drenada. Reconcilie com 'make count' e confira 'make dlq' (deve continuar vazia -- so entram la evento invalido, nao backlog)."

.PHONY: resiliencia-timeout
# NUNCA chame `$(MAKE)` (nem `resiliencia-evento-invalido`) de dentro deste
# alvo, nem em linha separada nem continuada com `\`. O GNU Make executa de
# verdade QUALQUER linha de receita que contenha `$(MAKE)` mesmo sob `make -n`
# -- inclusive o resto da mesma linha continuada, aws incluso. Ja aconteceu
# aqui: um `make -n` desta suite chegou a chamar `aws ecs stop-task` de
# verdade (so nao teve efeito porque a credencial estava expirada). Por isso
# o k6 e chamado direto abaixo, nao via `carga-changes`.
.PHONY: resiliencia-timeout
resiliencia-timeout: ## RNF05b "timeout": derruba uma task do merge-worker no meio do processamento
	@command -v k6 >/dev/null || { echo "erro: k6 nao encontrado no PATH."; exit 1; }
	@$(call require_env,ARGUS_CHANGES_URL)
	@$(call require_env,ARGUS_INGEST_TOKEN)
	@$(call require_env,AWS_PROFILE)
	@cluster=$$(cd $(INFRA) && terraform output -raw ecs_cluster_name); \
	servico=$$(cd $(INFRA) && terraform output -json ecs_service_names | python3 -c "import json,sys; print(json.load(sys.stdin)['merge-worker'])"); \
	echo "1/3: disparando carga em segundo plano ($${MINUTOS:-3} min)"; \
	( cd $(TOOLS)/loadtest && k6 run \
	    -e ARGUS_CHANGES_URL="$(ARGUS_CHANGES_URL)" \
	    -e ARGUS_INGEST_TOKEN="$(ARGUS_INGEST_TOKEN)" \
	    -e EVENTOS_POR_MINUTO=$${EVENTOS_POR_MINUTO:-10000} \
	    -e MINUTOS=$${MINUTOS:-3} \
	    changes_load.js ) & \
	carga_pid=$$!; \
	sleep 15; \
	task=$$(aws ecs list-tasks --profile "$(AWS_PROFILE)" --region "$${AWS_REGION:-us-east-1}" \
	  --cluster "$$cluster" --service-name "$$servico" --query 'taskArns[0]' --output text); \
	echo "2/3: derrubando a task $$task no meio do processamento"; \
	aws ecs stop-task --profile "$(AWS_PROFILE)" --region "$${AWS_REGION:-us-east-1}" \
	  --cluster "$$cluster" --task "$$task" --reason "teste de resiliencia RNF05b (timeout)"; \
	echo "3/3: aguardando a carga terminar..."; \
	wait $$carga_pid; \
	echo "Carga concluida. Confira RunningTaskCount do merge-worker (deve voltar sozinho) e rode make count."

# Profundidade (nao exigido pelo minimo do artefato): fila cheia e evento
# invalido ao mesmo tempo, pra garantir que os dois mecanismos (backlog e DLQ)
# nao interferem um no outro -- ver secao 6.3 do plano de teste. Mesma regra
# do alvo acima: k6 chamado direto, nunca via `$(MAKE)`.
.PHONY: resiliencia-concorrente
resiliencia-concorrente: ## Profundidade: fila cheia + evento invalido ao mesmo tempo
	@command -v k6 >/dev/null || { echo "erro: k6 nao encontrado no PATH."; exit 1; }
	@$(call require_env,ARGUS_CHANGES_URL)
	@$(call require_env,ARGUS_INGEST_TOKEN)
	@$(call require_env,AWS_PROFILE)
	@echo "1/3: escalando merge-worker para 0 (terraform vai pedir confirmacao)"
	cd $(INFRA) && terraform apply -var="worker_desired_count=0"
	@echo "2/3: carga normal + eventos invalidos ao mesmo tempo, worker desligado"
	@( cd $(TOOLS)/loadtest && k6 run \
	     -e ARGUS_CHANGES_URL="$(ARGUS_CHANGES_URL)" \
	     -e ARGUS_INGEST_TOKEN="$(ARGUS_INGEST_TOKEN)" \
	     -e EVENTOS_POR_MINUTO=$${EVENTOS_POR_MINUTO:-10000} \
	     -e MINUTOS=$${MINUTOS:-5} \
	     changes_load.js ) & \
	carga_pid=$$!; \
	( cd $(TOOLS)/loadtest && k6 run \
	     -e ARGUS_CHANGES_URL="$(ARGUS_CHANGES_URL)" \
	     -e ARGUS_INGEST_TOKEN="$(ARGUS_INGEST_TOKEN)" \
	     -e REPETICOES=$${REPETICOES:-3} \
	     eventos_invalidos.js ) & \
	invalidos_pid=$$!; \
	wait $$carga_pid $$invalidos_pid
	@echo "3/3: religando o merge-worker (terraform vai pedir confirmacao)"
	cd $(INFRA) && terraform apply -var="worker_desired_count=$${WORKER_DESIRED_COUNT:-1}"
	@echo "Confira 'make dlq' logo apos religar: o invalido nao deve ficar preso atras do backlog normal."

# Profundidade: confere que os watermarks do ETL (015_etl_incremental.sql)
# nunca regrediram -- e o bug real documentado em plano-argus-v3.md secao 12.
# So faz sentido rodar depois de algum dos cenarios acima ja ter passado dado
# pelo ETL.
.PHONY: resiliencia-watermark-check
resiliencia-watermark-check: ## Profundidade: confere que os watermarks do ETL nunca regrediram
	@$(call require_env,DATABASE_URL)
	psql "$(DATABASE_URL)" -f $(TOOLS)/loadtest/watermark_check.sql

# Avancado (fora do minimo do artefato): aciona o redrive NATIVO do SQS --
# 5 tentativas -> changes-dlq SEM FailureReason -- em vez da quarentena
# explicita do worker (que e o caminho comum, ja coberto por
# resiliencia-evento-invalido e sempre acontece na 1a tentativa). Exige o RDS
# genuinamente inacessivel para os workers por ~15 min (5 x
# changes_visibility_timeout_seconds=180s); autorizado explicitamente pelo
# usuario em 2026-09-01 para este ambiente de Learner Lab individual -- ver
# plano-teste-resiliencia.md secao 6.2.
#
# SEGURANCA: a regra do security group e restaurada num `trap ... EXIT`, que
# roda mesmo se o alvo for interrompido (Ctrl+C) ou falhar no meio -- nunca
# deveria deixar o RDS inacessivel para o resto do sistema além da janela do
# teste. Se o "acesso restaurado" no final NAO aparecer, rode a mesma
# `authorize-security-group-ingress` na mao antes de continuar qualquer outra
# coisa no ambiente.
.PHONY: resiliencia-dlq-fronteira
resiliencia-dlq-fronteira: ## Avancado: redrive nativo do SQS via ~15-20min de RDS inacessivel aos workers
	@command -v k6 >/dev/null || { echo "erro: k6 nao encontrado no PATH."; exit 1; }
	@$(call require_env,ARGUS_CHANGES_URL)
	@$(call require_env,ARGUS_INGEST_TOKEN)
	@$(call require_env,AWS_PROFILE)
	@nome=$$(cd $(INFRA) && terraform output -raw ecs_cluster_name); \
	regiao="$${AWS_REGION:-us-east-1}"; \
	rds_sg=$$(aws ec2 describe-security-groups --profile "$(AWS_PROFILE)" --region "$$regiao" \
	  --filters "Name=group-name,Values=$${nome}-rds" --query 'SecurityGroups[0].GroupId' --output text); \
	worker_sg=$$(aws ec2 describe-security-groups --profile "$(AWS_PROFILE)" --region "$$regiao" \
	  --filters "Name=group-name,Values=$${nome}-tasks" --query 'SecurityGroups[0].GroupId' --output text); \
	if [ "$$rds_sg" = "None" ] || [ -z "$$rds_sg" ] || [ "$$worker_sg" = "None" ] || [ -z "$$worker_sg" ]; then \
	  echo "erro: nao encontrei os security groups (rds_sg=$$rds_sg worker_sg=$$worker_sg)"; exit 1; \
	fi; \
	echo "RDS SG: $$rds_sg | worker SG: $$worker_sg"; \
	trap 'echo; echo "restaurando acesso do worker ao RDS..."; \
	  aws ec2 authorize-security-group-ingress --profile "$(AWS_PROFILE)" --region "'"$$regiao"'" \
	    --group-id "'"$$rds_sg"'" --protocol tcp --port 5432 --source-group "'"$$worker_sg"'" >/dev/null 2>&1 \
	    && echo "acesso restaurado." \
	    || echo "AVISO: a regra pode ja existir (ok) ou a restauracao falhou de verdade -- confira com: aws ec2 describe-security-groups --group-ids '"$$rds_sg"' --profile $(AWS_PROFILE)"' EXIT; \
	echo "1/4: revogando o acesso do worker ao RDS (porta 5432)"; \
	aws ec2 revoke-security-group-ingress --profile "$(AWS_PROFILE)" --region "$$regiao" \
	  --group-id "$$rds_sg" --protocol tcp --port 5432 --source-group "$$worker_sg"; \
	echo "2/4: enviando trafego minimo (vai falhar 5x e cair na changes-dlq sem FailureReason)"; \
	( cd $(TOOLS)/loadtest && k6 run \
	    -e ARGUS_CHANGES_URL="$(ARGUS_CHANGES_URL)" \
	    -e ARGUS_INGEST_TOKEN="$(ARGUS_INGEST_TOKEN)" \
	    -e EVENTOS_POR_MINUTO=20 -e MINUTOS=0.1 \
	    changes_load.js ) >/dev/null; \
	echo "3/4: aguardando ate 20 min pela 5a tentativa (visibility timeout de 180s x5)"; \
	fila_dlq=$$(cd $(INFRA) && terraform output -raw changes_dlq_url); \
	limite=$$(( $$(date +%s) + 1200 )); \
	while true; do \
	  n=$$(aws sqs get-queue-attributes --profile "$(AWS_PROFILE)" --region "$$regiao" \
	    --queue-url "$$fila_dlq" --attribute-names ApproximateNumberOfMessages \
	    --query 'Attributes.ApproximateNumberOfMessages' --output text); \
	  echo "  mensagens na changes-dlq: $$n"; \
	  [ "$$n" != "0" ] && break; \
	  [ $$(date +%s) -ge $$limite ] && { echo "timeout de 20 min sem a mensagem cair na DLQ -- confira 'make logs SERVICO=worker'"; break; }; \
	  sleep 30; \
	done; \
	echo "4/4: FailureReason deve estar AUSENTE aqui (prova de que foi o SQS, nao o worker, quem quarentenou):"; \
	aws sqs receive-message --profile "$(AWS_PROFILE)" --region "$$regiao" \
	  --queue-url "$$fila_dlq" --message-attribute-names All --max-number-of-messages 1 \
	  --query 'Messages[0].{motivo:MessageAttributes.FailureReason.StringValue,corpo:Body}' --output json

.PHONY: logs
logs: ## Acompanha os logs de um servico (SERVICO=worker|simulator|processing|loader)
	@$(call require_env,AWS_PROFILE)
	@aws logs tail "/ecs/$$(cd $(INFRA) && terraform output -raw ecs_cluster_name)/$${SERVICO:-worker}" --follow

.PHONY: logs-api
logs-api: ## Acompanha os logs da API de leitura
	@$(call require_env,AWS_PROFILE)
	aws logs tail "/aws/lambda/$$(cd $(INFRA) && terraform output -raw ecs_cluster_name)-read-api" --follow

.PHONY: dlq
dlq: ## Mostra o que esta nas filas de rejeitados
	@$(call require_env,AWS_PROFILE)
	@for fila in dlq_url changes_dlq_url; do \
	  echo "--- $$fila"; \
	  aws sqs receive-message \
	    --queue-url "$$(cd $(INFRA) && terraform output -raw $$fila)" \
	    --message-attribute-names All --max-number-of-messages 10 \
	    --query 'Messages[].{motivo:MessageAttributes.FailureReason.StringValue,corpo:Body}' \
	    --output json; \
	done

.PHONY: count
count: ## Conta as linhas carregadas por camada
	@$(call require_env,DATABASE_URL)
	@psql "$$DATABASE_URL" -c " \
	  SELECT 'bronze.change_log' AS tabela, count(*) FROM bronze.change_log \
	  UNION ALL SELECT 'bronze.event', count(*) FROM bronze.event \
	  UNION ALL SELECT 'silver.signal_point', count(*) FROM silver.signal_point \
	  UNION ALL SELECT 'gold.feature_bucket', count(*) FROM gold.feature_bucket \
	  ORDER BY 1;"

.PHONY: sim-on
sim-on: ## Liga o simulador (so depois da carga inicial)
	cd $(INFRA) && terraform apply -var="simulator_desired_count=1"

.PHONY: sim-off
sim-off: ## Desliga o simulador
	cd $(INFRA) && terraform apply -var="simulator_desired_count=0"

.PHONY: pause
pause: ## Desliga todos os servicos sem destruir nada (economiza credito)
	cd $(INFRA) && terraform apply \
	  -var="worker_desired_count=0" \
	  -var="simulator_desired_count=0" \
	  -var="processing_desired_count=0"

.PHONY: resume
resume: ## Religa os workers e o processamento
	cd $(INFRA) && terraform apply \
	  -var="worker_desired_count=1" \
	  -var="processing_desired_count=1"

# --------------------------------------------------------------------------- #
# Kubernetes
# --------------------------------------------------------------------------- #
#
# O cluster orquestra o caminho SINCRONO (dashboard + API de leitura). O caminho
# assincrono -- workers de SQS, processing, simulator, loader -- continua no ECS
# Fargate, sem nenhuma alteracao: la o Fargate ja entrega estado desejado,
# rolling deploy e health check, e o IAM por task e melhor do que um cluster
# consegue oferecer neste lab, onde IRSA e Pod Identity estao bloqueados.
#
# Fluxo tipico na AWS:
#
#   make tf-apply          # cria o cluster (create_eks = true no tfvars)
#   make k8s-kubeconfig    # aponta o kubectl para ele
#   make k8s-bootstrap     # IngressClass do ALB
#   make k8s-push          # publica backend e frontend multi-arquitetura
#   make k8s-secret        # monta o Secret a partir dos outputs do Terraform
#   make k8s-migrate       # aplica as migrations
#   make k8s-apply         # sobe a aplicacao
#   make k8s-url           # imprime o endereco publico
#
# Fluxo local, sem AWS nenhuma:
#
#   make kind-up k8s-images kind-load
#   make k8s-apply   K8S_OVERLAY=kind
#   make k8s-migrate K8S_OVERLAY=kind

KUBECTL       ?= kubectl
K8S           := k8s
K8S_OVERLAY   ?= aws
K8S_NAMESPACE ?= argus
KIND_CLUSTER  ?= argus

# Versoes fixadas, e nao `latest`, pela mesma razao que as imagens do ECR sao
# fixadas por digest: `latest` faz o ambiente local de hoje diferir do de amanha
# sem que nenhum arquivo do repositorio tenha mudado.
#
# O repositorio do ingress-nginx e `kubernetes/`, e NAO `kubernetes-sigs/` --
# o segundo existe, mas nao serve o manifesto de deploy e responde 404.
INGRESS_NGINX_VERSAO ?= controller-v1.13.3
METRICS_SERVER_VERSAO ?= v0.8.0

# As tres imagens que o cluster EXECUTA: backend e frontend servem trafego, e
# `processing` e a imagem dos Jobs de `k8s-migrate` (ela embarca db/migrations/
# e tools/migrate.py). Ficar sem ela aqui fazia o Job de migration terminar em
# ImagePullBackOff num ECR de lab recem-criado, porque so `make push` a publicava.
K8S_IMAGES := backend frontend processing

# O que o cluster LOCAL precisa ter carregado: hoje o mesmo conjunto. A lista
# existe separada porque escreve-la a mao foi o que fez `make kind-load` falhar
# com "image not present locally" depois de um `k8s-images` que nunca construiu
# a de `processing`.
K8S_IMAGES_LOCAIS := $(K8S_IMAGES)

.PHONY: eks-roles
eks-roles: ## Mostra os ARNs dos papeis LabEks* desta sessao do lab
	@$(call require_env,AWS_PROFILE)
	@# O prefixo do nome muda a cada sessao. O eks.tf os descobre sozinho por
	@# regex; este alvo existe para o caso de iam:ListRoles ser negado, quando
	@# os ARNs precisam ser colados em eks_*_role_arn no terraform.tfvars.
	@aws iam list-roles --profile $$AWS_PROFILE \
	  --query "Roles[?contains(RoleName,'LabEks')].[RoleName,Arn]" --output text

.PHONY: k8s-kubeconfig
k8s-kubeconfig: ## Aponta o kubectl para o cluster EKS deste stack
	@$(call require_env,AWS_PROFILE)
	@set -e; \
	nome=$$(cd $(INFRA) && terraform output -raw eks_cluster_name); \
	if [ -z "$$nome" ]; then \
	  echo "erro: nenhum cluster EKS no state."; \
	  echo "      Ligue create_eks = true no terraform.tfvars e rode 'make tf-apply'."; \
	  exit 1; \
	fi; \
	aws eks update-kubeconfig --name "$$nome" \
	  --region $${AWS_REGION:-us-east-1} --profile $$AWS_PROFILE

.PHONY: k8s-bootstrap
k8s-bootstrap: ## Instala o que o cluster precisa antes da aplicacao
	@# O metrics-server NAO vem com o Auto Mode: um cluster recem-criado nasce
	@# com kube-system vazio e o HPA fica em `<unknown>/60%` (lab de 18/09).
	@# Ele e o add-on aws_eks_addon.metrics_server de infra/eks.tf, instalado
	@# pelo `tf-apply` junto com o cluster; aqui so falta a IngressClass do
	@# controlador de ALB. No kind o metrics-server entra pelo `kind-up`.
	$(KUBECTL) apply -f $(K8S)/overlays/aws/ingressclass.yaml
	@echo
	@$(KUBECTL) get ingressclass

.PHONY: k8s-images
k8s-images: $(addprefix image-,$(K8S_IMAGES_LOCAIS)) ## Constroi as imagens do cluster para uso local

.PHONY: k8s-push
k8s-push: ## Publica backend, frontend e processing multi-arquitetura no ECR
	@# Atalho para quem mexeu so no cluster. `make push` publica as seis
	@# imagens; este alvo publica as tres que o cluster executa.
	@$(MAKE) --no-print-directory push IMAGES="$(K8S_IMAGES)"

.PHONY: k8s-secret
k8s-secret: ## Monta o Secret do backend a partir dos outputs do Terraform
	@$(call require_env,AWS_PROFILE)
	@# Os valores viajam por PIPE e nunca tocam o disco.
	@#
	@# Sem IRSA e sem Pod Identity (o Learner Lab nega iam:CreateRole e
	@# iam:CreateOpenIDConnectProvider), o pod nao consegue ler o Secrets
	@# Manager sozinho. As alternativas seriam o provider `kubernetes` no
	@# Terraform, que gravaria o segredo no tfstate local, ou um arquivo .env,
	@# que gravaria em disco. Esta e a unica das tres que mantem a regra de
	@# nenhum segredo fora da memoria do shell.
	@set -e; \
	cd $(INFRA); \
	url_api=$$(terraform output -raw eks_backend_database_url); \
	url_mestre=$$(terraform output -raw eks_master_database_url); \
	senha_leitor=$$(terraform output -raw eks_read_api_db_password); \
	salt=$$(terraform output -raw eks_user_id_hash_salt); \
	segredo=$$(terraform output -raw auth_tokens_secret); \
	hash=$$(aws secretsmanager get-secret-value --secret-id "$$segredo" \
	  --profile $$AWS_PROFILE --region $${AWS_REGION:-us-east-1} \
	  --query SecretString --output text \
	  | python3 -c "import json,sys; print(json.load(sys.stdin)['dashboard'])"); \
	cd ..; \
	$(KUBECTL) create namespace $(K8S_NAMESPACE) --dry-run=client -o yaml | $(KUBECTL) apply -f -; \
	$(KUBECTL) create secret generic argus-backend -n $(K8S_NAMESPACE) \
	  --from-literal=DATABASE_URL="$$url_api" \
	  --from-literal=DATABASE_URL_MASTER="$$url_mestre" \
	  --from-literal=DB_READER_PASSWORD="$$senha_leitor" \
	  --from-literal=USER_ID_HASH_SALT="$$salt" \
	  --from-literal=DASHBOARD_TOKEN_SHA256="$$hash" \
	  --dry-run=client -o yaml | $(KUBECTL) apply -f -
	@echo
	@# Variavel de ambiente vinda de secretKeyRef NAO e recarregada em pod que
	@# ja esta de pe. Sem este restart, o token novo de `make auth-rotate` seria
	@# rejeitado ate o proximo deploy -- e a causa apareceria como 401 sem
	@# explicacao.
	@# Distinguir os dois casos importa: antes do primeiro `k8s-apply` o
	@# Deployment ainda nao existe e o silencio e correto; depois, um erro aqui
	@# e RBAC negado ou contexto de kubectl errado -- e engoli-lo devolveria o
	@# 401 sem explicacao que este alvo existe para evitar.
	@if $(KUBECTL) -n $(K8S_NAMESPACE) get deployment argus-backend >/dev/null 2>&1; then \
	  $(KUBECTL) -n $(K8S_NAMESPACE) rollout restart deployment/argus-backend; \
	else \
	  echo "  (backend ainda nao aplicado; o Secret sera lido no primeiro k8s-apply)"; \
	fi
	@echo "Secret argus-backend atualizado (5 chaves)."

# Renderiza um diretorio de kustomize e aplica, trocando os placeholders de
# imagem pela referencia completa do ECR desta sessao do lab.
#
# Por que substituicao em pipe, e nao o transformer `images:` do kustomize no
# overlay `aws`: a referencia depende da CONTA, que muda a cada sessao do
# Learner Lab. Grava-la no arquivo versionado a deixaria errada no dia seguinte.
# No overlay `kind` nao ha esse problema -- la as imagens sao locais e o
# transformer nativo resolve, sem pipe.
#
# $(1) = diretorio do kustomize
# $(2) = flags extras do `kubectl apply` (opcional; `k8s_roda_job` passa -l)
define k8s_aplica_aws
	set -e; \
	urls=$$(cd $(INFRA) && terraform output -json ecr_repository_urls); \
	ref() { printf '%s' "$$urls" | python3 -c "import json,sys; print(json.load(sys.stdin)['$$1'])"; }; \
	$(KUBECTL) kustomize $(1) \
	  | sed "s|IMAGE_BACKEND|$$(ref backend):$(IMAGE_TAG)|g; \
	         s|IMAGE_FRONTEND|$$(ref frontend):$(IMAGE_TAG)|g; \
	         s|IMAGE_PROCESSING|$$(ref processing):$(IMAGE_TAG)|g" \
	  | $(KUBECTL) apply -f - $(2)
endef

.PHONY: k8s-apply
k8s-apply: ## Aplica o overlay no cluster corrente (K8S_OVERLAY=aws|kind)
	@set -e; \
	if [ "$(K8S_OVERLAY)" = "aws" ]; then \
	  $(call k8s_aplica_aws,$(K8S)/overlays/aws); \
	else \
	  $(KUBECTL) apply -k $(K8S)/overlays/$(K8S_OVERLAY); \
	fi

# Roda um dos Jobs de k8s/migrate/ ate o fim e mostra o rabo do log.
#
# Os dois Jobs vivem no mesmo kustomization, mas NAO podem subir juntos: o de
# leitor faz `GRANT argus_reader`, e esse papel nasce na migration 001. Num
# banco novo, aplicar os dois de uma vez e uma corrida que o leitor perde. O
# `-l` do kubectl filtra o YAML renderizado pelo label do Job, e e isso que
# permite aplicar um de cada vez a partir de um unico diretorio.
#
# delete antes do apply porque `spec.template` de Job e imutavel: sem isso,
# rodar de novo com uma tag nova falha com "field is immutable".
#
# $(1) = nome do Job (argus-db-migrate | argus-db-reader)
define k8s_roda_job
	set -e; \
	$(KUBECTL) delete job $(1) -n $(K8S_NAMESPACE) --ignore-not-found; \
	if [ "$(K8S_OVERLAY)" = "aws" ]; then \
	  $(call k8s_aplica_aws,$(K8S)/migrate,-l app.kubernetes.io/name=$(1)); \
	else \
	  $(KUBECTL) apply -k $(K8S)/overlays/$(K8S_OVERLAY)/migrate \
	    -l app.kubernetes.io/name=$(1); \
	fi; \
	$(KUBECTL) wait --for=condition=complete job/$(1) \
	  -n $(K8S_NAMESPACE) --timeout=600s; \
	$(KUBECTL) logs job/$(1) -n $(K8S_NAMESPACE) --tail=20
endef

.PHONY: k8s-migrate
k8s-migrate: ## Aplica as migrations e cria o login de leitura (dois Jobs, em sequencia)
	@# Primeiro o schema, depois o login: `migrate.py aplicar` NAO cria
	@# `argus_api` -- `criar-leitor` e subcomando a parte. So com o primeiro
	@# Job, num banco novo o backend fica 0/1 com PoolTimeout e, por baixo,
	@# "password authentication failed for user argus_api" (lab de 18/09).
	@$(call k8s_roda_job,argus-db-migrate)
	@$(call k8s_roda_job,argus-db-reader)

.PHONY: k8s-rollout
k8s-rollout: ## Publica as imagens e espera o rollout terminar
	@# Em receita, e nao como pre-requisitos: o make nao garante ordem entre
	@# pre-requisitos sob `-j`, e aplicar antes de publicar deixa os pods em
	@# ImagePullBackOff apontando para uma tag que ainda nao existe.
	$(MAKE) --no-print-directory k8s-push
	$(MAKE) --no-print-directory k8s-apply
	$(KUBECTL) -n $(K8S_NAMESPACE) rollout status deployment/argus-backend --timeout=300s
	$(KUBECTL) -n $(K8S_NAMESPACE) rollout status deployment/argus-frontend --timeout=300s

.PHONY: k8s-status
k8s-status: ## Pods, HPA, PDB e Ingress numa tela so
	@$(KUBECTL) -n $(K8S_NAMESPACE) get pods -o wide
	@echo; $(KUBECTL) -n $(K8S_NAMESPACE) get hpa
	@echo; $(KUBECTL) -n $(K8S_NAMESPACE) get pdb
	@echo; $(KUBECTL) -n $(K8S_NAMESPACE) get ingress

.PHONY: k8s-url
k8s-url: ## Imprime o endereco publico do Ingress
	@set -e; \
	host=$$($(KUBECTL) -n $(K8S_NAMESPACE) get ingress argus \
	  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null); \
	if [ -z "$$host" ]; then \
	  host=$$($(KUBECTL) -n $(K8S_NAMESPACE) get ingress argus \
	    -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null); \
	fi; \
	if [ -z "$$host" ]; then \
	  echo "erro: o Ingress ainda nao tem endereco." >&2; \
	  echo "      Na AWS o ALB leva 2 a 4 minutos para nascer." >&2; \
	  exit 1; \
	fi; \
	echo "http://$$host"

.PHONY: k8s-logs
k8s-logs: ## Segue o log de um Deployment (APP=backend|frontend)
	$(KUBECTL) -n $(K8S_NAMESPACE) logs -f deployment/argus-$(or $(APP),backend) --tail=100

.PHONY: k8s-scale-zero
k8s-scale-zero: ## Zera os Deployments para economizar credito do lab
	@# Sem pod da aplicacao o Karpenter do Auto Mode consolida os nos em poucos
	@# minutos -- mas nao ate zero: os pods do metrics-server (add-on em
	@# infra/eks.tf) ficam em kube-system e seguram um no pequeno. O ALB
	@# continua de pe -- para remove-lo tambem, use `make k8s-delete`. E o
	@# equivalente do `make pause` para o cluster.
	$(KUBECTL) -n $(K8S_NAMESPACE) scale deployment --all --replicas=0
	@$(KUBECTL) -n $(K8S_NAMESPACE) get deploy

.PHONY: k8s-delete
k8s-delete: ## Remove a aplicacao do cluster, sem destruir o cluster
	@# Remover o namespace leva o Ingress junto, e com ele o ALB -- que e a
	@# parte que cobra por hora parada.
	$(KUBECTL) delete namespace $(K8S_NAMESPACE) --ignore-not-found

.PHONY: k8s-validate
k8s-validate: ## Renderiza todos os overlays sem tocar em cluster nenhum
	@command -v $(KUBECTL) >/dev/null 2>&1 || { \
	  echo "erro: $(KUBECTL) nao encontrado no PATH."; \
	  echo "      Instale com 'brew install kubectl' -- ele e pre-requisito do"; \
	  echo "      'make check' desde que os manifestos entraram (ver k8s/README.md)."; \
	  exit 1; \
	}
	@set -e; \
	for alvo in base migrate overlays/aws overlays/kind overlays/kind/migrate; do \
	  printf '  %-24s ' "$$alvo"; \
	  $(KUBECTL) kustomize $(K8S)/$$alvo > /dev/null; \
	  echo "ok"; \
	done
	@# O kustomize so responde "este YAML e valido". As invariantes que ele nao
	@# alcanca -- ordem das regras do Ingress, arquitetura das imagens e as chaves
	@# do Secret -- ficam no verificador, que tambem nao toca em cluster nenhum.
	@python3 $(TOOLS)/verifica_manifests.py \
	  --k8s $(K8S) --makefile Makefile --kubectl $(KUBECTL)

# --------------------------------------------------------------------------- #
# Kubernetes local (kind)
# --------------------------------------------------------------------------- #

.PHONY: kind-up
kind-up: ## Cria o cluster local com ingress-nginx, metrics-server e Postgres
	@set -e; \
	if ! kind get clusters 2>/dev/null | grep -qx "$(KIND_CLUSTER)"; then \
	  kind create cluster --config $(K8S)/overlays/kind/kind-cluster.yaml; \
	fi
	@# O ingress-nginx, e nao um `kubectl port-forward`, de proposito: o
	@# port-forward exigiria duas portas (uma por servico) e, com isso, um
	@# bundle com NEXT_PUBLIC_API_URL absoluto -- o dev testaria um artefato
	@# DIFERENTE do que vai para a AWS, e a decisao de origem unica nunca seria
	@# exercitada localmente.
	$(KUBECTL) apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/$(INGRESS_NGINX_VERSAO)/deploy/static/provider/kind/deploy.yaml
	@# `rollout status` e nao `wait --for=condition=ready pod`: o wait falha com
	@# "no matching resources found" quando roda antes de o Deployment criar o
	@# primeiro pod, e o apply acima retorna sem esperar por isso.
	$(KUBECTL) -n ingress-nginx rollout status deployment/ingress-nginx-controller --timeout=300s
	@# Nenhum cluster traz metrics-server sozinho -- nem o kind nem o EKS Auto
	@# Mode (la ele e o add-on de infra/eks.tf). Sem ele o HPA fica em
	@# `<unknown>/60%` e nao escala nada. O --kubelet-insecure-tls e
	@# obrigatorio: os certificados de kubelet do kind sao autoassinados.
	$(KUBECTL) apply -f https://github.com/kubernetes-sigs/metrics-server/releases/download/$(METRICS_SERVER_VERSAO)/components.yaml
	$(KUBECTL) -n kube-system patch deployment metrics-server --type=json \
	  -p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
	$(KUBECTL) -n kube-system rollout status deployment/metrics-server --timeout=180s
	@echo
	@echo "cluster local pronto. Agora: make k8s-images kind-load"

.PHONY: kind-load
kind-load: ## Carrega as imagens locais no no do kind
	@# O kind nao enxerga o daemon do Docker da maquina: a imagem precisa ser
	@# copiada para dentro do no. Por isso imagePullPolicy: IfNotPresent.
	kind load docker-image \
	  $(addsuffix :dev,$(addprefix argus-,$(K8S_IMAGES_LOCAIS))) \
	  --name $(KIND_CLUSTER)

.PHONY: kind-down
kind-down: ## Destroi o cluster local
	kind delete cluster --name $(KIND_CLUSTER)

# --------------------------------------------------------------------------- #
# Limpeza
# --------------------------------------------------------------------------- #

.PHONY: clean
clean: ## Remove artefatos de build e caches
	rm -rf $(BACKEND)/dist $(BACKEND)/openapi.json
	find . -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name '.pytest_cache' -prune -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name '.ruff_cache' -prune -exec rm -rf {} + 2>/dev/null || true

# --------------------------------------------------------------------------- #
# Auxiliar
# --------------------------------------------------------------------------- #

# Falha com mensagem util quando uma variavel obrigatoria nao esta definida, em
# vez de deixar o comando rodar com string vazia e errar de forma obscura.
define require_env
	if [ -z "$${$(1)}" ]; then \
	  echo "erro: $(1) nao definida."; \
	  echo "      Preencha o .env (veja .env.example) ou rode 'make env'."; \
	  exit 1; \
	fi
endef
