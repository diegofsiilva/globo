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
WORKER     := worker
SIMULATOR  := simulator
PROCESSING := processing
LOADER     := loader
BACKEND    := backend
INFRA      := infra
TOOLS      := tools
FRONTEND   := frontend
POSTMAN    := ../../artefatos/postman

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

# `uv run` monta o ambiente sozinho a partir do pyproject de cada app.
UV := uv run --quiet

# As quatro imagens de container. O build tem contexto em apps/basica/ (e nao na
# pasta de cada app) porque todas dependem de common/.
IMAGES := worker simulator processing loader

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

.PHONY: env
env: ## Cria o .env a partir dos outputs do Terraform
	@test -f .env && { echo ".env ja existe — apague antes se quiser regerar."; exit 1; } || true
	@echo "Lendo os endpoints do Terraform..."
	@{ \
	  echo "ARGUS_API_URL=$$(cd $(INFRA) && terraform output -raw read_api_url 2>/dev/null)"; \
	  echo "ARGUS_INGEST_URL=$$(cd $(INFRA) && terraform output -raw ingest_url 2>/dev/null)"; \
	  echo "ARGUS_CHANGES_URL=$$(cd $(INFRA) && terraform output -raw changes_url 2>/dev/null)"; \
	  echo "AWS_PROFILE=$${AWS_PROFILE:-g4}"; \
	  echo "AWS_REGION=$${AWS_REGION:-us-east-1}"; \
	  echo '# DATABASE_URL: monte com "make db-url" (a senha nao passa por arquivo)'; \
	} > .env
	@echo ".env criado (esta no .gitignore)."

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

.PHONY: db-psql
db-psql: ## Abre um psql no banco local
	docker exec -it $(PG_CONTAINER) psql -U argus -d argus

.PHONY: migrate
migrate: ## Aplica as migrations pendentes (usa DATABASE_URL)
	@$(call require_env,DATABASE_URL)
	cd $(TOOLS) && $(UV) python migrate.py aplicar

.PHONY: migrate-status
migrate-status: ## Mostra quais migrations ja rodaram
	@$(call require_env,DATABASE_URL)
	cd $(TOOLS) && $(UV) python migrate.py status

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
test: test-worker test-simulator test-backend ## Roda as suites que tem teste

# TEST_DATABASE_URL aponta para o banco de teste local por padrao. Os testes que
# precisam de banco sao PULADOS quando ele nao existe, em vez de quebrarem —
# assim `make test` numa maquina sem docker ainda valida models, keys e changes.
.PHONY: test-worker
test-worker: ## Testes dos workers de ingestao
	cd $(WORKER) && TEST_DATABASE_URL=$${TEST_DATABASE_URL:-$(PG_TEST_URL)} $(UV) pytest

.PHONY: test-backend
test-backend: ## Testes da API de leitura
	cd $(BACKEND) && TEST_DATABASE_URL=$${TEST_DATABASE_URL:-$(PG_TEST_URL)} $(UV) pytest

.PHONY: test-simulator
test-simulator: ## Testes do relogio e do emissor do simulador
	cd $(SIMULATOR) && $(UV) pytest

.PHONY: lint
lint: ## Verifica estilo sem alterar arquivos
	cd $(TOOLS) && $(UV) ruff check . && $(UV) ruff format --check .
	cd $(COMMON) && uv run --quiet --with ruff ruff check src
	cd $(WORKER) && $(UV) ruff check src tests && $(UV) ruff format --check src tests
	cd $(SIMULATOR) && $(UV) ruff check src
	cd $(PROCESSING) && $(UV) ruff check src
	cd $(LOADER) && $(UV) ruff check src
	cd $(BACKEND) && $(UV) ruff check src tests
	cd $(INFRA) && terraform fmt -check -recursive

.PHONY: fmt
fmt: ## Formata o codigo e o Terraform
	@# `ruff check --fix` sai com erro quando resta algo que ele nao conserta
	@# sozinho. Aqui isso nao deve interromper a formatacao — quem barra e o
	@# alvo `lint`, que e o portao de qualidade.
	cd $(TOOLS) && ($(UV) ruff check --fix . || true) && $(UV) ruff format .
	cd $(WORKER) && ($(UV) ruff check --fix src tests || true) && $(UV) ruff format src tests
	cd $(SIMULATOR) && ($(UV) ruff check --fix src || true) && $(UV) ruff format src
	cd $(PROCESSING) && ($(UV) ruff check --fix src || true) && $(UV) ruff format src
	cd $(LOADER) && ($(UV) ruff check --fix src || true) && $(UV) ruff format src
	cd $(BACKEND) && ($(UV) ruff check --fix src tests || true) && $(UV) ruff format src tests
	cd $(INFRA) && terraform fmt -recursive

.PHONY: check
check: lint test tf-validate ## Tudo que a CI deveria rodar

# --------------------------------------------------------------------------- #
# Desenvolvimento
# --------------------------------------------------------------------------- #

.PHONY: api
api: ## Sobe a API de leitura local contra o banco local
	cd $(BACKEND) && DATABASE_URL=$${DATABASE_URL:-$(PG_URL)} $(UV) python lambda_handler.py

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

# O contexto e apps/basica/ (o `.` no fim) e nao a pasta do app: todas as
# imagens dependem de common/, que fica fora da pasta de cada uma.
.PHONY: images
images: $(addprefix image-,$(IMAGES)) ## Constroi as quatro imagens (ARM64)

.PHONY: $(addprefix image-,$(IMAGES))
$(addprefix image-,$(IMAGES)): image-%:
	docker build --platform linux/arm64 -f $*/Dockerfile -t argus-$*:dev .

# --------------------------------------------------------------------------- #
# Infraestrutura
# --------------------------------------------------------------------------- #

.PHONY: tf-init
tf-init: ## Inicializa o Terraform
	cd $(INFRA) && terraform init

.PHONY: tf-validate
tf-validate: ## Valida a configuracao sem tocar na AWS
	cd $(INFRA) && terraform validate

.PHONY: tf-plan
tf-plan: lambda-build ## Mostra o que mudaria na AWS (somente leitura)
	cd $(INFRA) && terraform plan

.PHONY: tf-apply
tf-apply: lambda-build ## Aplica as mudancas na AWS
	cd $(INFRA) && terraform apply

.PHONY: tf-output
tf-output: ## Mostra os endpoints e nomes de recurso
	cd $(INFRA) && terraform output

.PHONY: tf-destroy
tf-destroy: ## Remove TODA a infraestrutura
	@echo "Isto apaga o BANCO com as 33 tabelas, as filas e os servicos."
	@echo "O bucket de origem tem versionamento, mas tambem vai."
	@read -p "Digite 'destruir' para confirmar: " r; [ "$$r" = "destruir" ] || { echo "cancelado."; exit 1; }
	cd $(INFRA) && terraform destroy

.PHONY: lambda-build
lambda-build: ## Empacota a API de leitura para a Lambda
	cd $(BACKEND) && ./scripts/build_lambda.sh

.PHONY: deploy
deploy: test-backend lambda-build ## Testa, empacota e publica a API de leitura
	cd $(INFRA) && terraform apply -auto-approve
	@$(MAKE) --no-print-directory smoke

.PHONY: push
push: ## Publica as imagens no ECR e forca novo deploy
	@$(call require_env,AWS_PROFILE)
	cd $(INFRA) && terraform output -raw docker_push_commands | bash

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
etl: ## Reconstroi silver e gold a partir da bronze
	@$(call require_env,DATABASE_URL)
	@psql "$$DATABASE_URL" -c "SELECT * FROM gold.rebuild_tudo();"

# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #

.PHONY: frontend-install
frontend-install: ## Instala as dependencias do dashboard
	cd $(FRONTEND) && npm ci

# A URL da API entra no bundle em tempo de build e NUNCA fica escrita no codigo
# (ver .env.example). Sem ela o build falha de proposito: um bundle apontando
# para o proprio dominio devolveria o HTML da pagina no lugar do JSON, e o erro
# so apareceria no navegador do usuario.
.PHONY: frontend-build
frontend-build: ## Gera o site estatico do dashboard
	@$(call require_env,ARGUS_API_URL)
	cd $(FRONTEND) && NEXT_PUBLIC_API_URL="$(ARGUS_API_URL)" npm run build

.PHONY: frontend-deploy
frontend-deploy: frontend-build ## Publica o dashboard no bucket S3
	@$(call require_env,AWS_PROFILE)
	aws s3 sync $(FRONTEND)/out/ \
	  "s3://$$(cd $(INFRA) && terraform output -raw frontend_bucket)/" --delete
	@echo
	@echo "Dashboard no ar: $$(cd $(INFRA) && terraform output -raw frontend_url)"

.PHONY: frontend-dev
frontend-dev: ## Sobe o dashboard local contra a API publicada
	@$(call require_env,ARGUS_API_URL)
	cd $(FRONTEND) && NEXT_PUBLIC_API_URL="$(ARGUS_API_URL)" npm run dev

# --------------------------------------------------------------------------- #
# Testes de API (Postman)
# --------------------------------------------------------------------------- #

.PHONY: postman-env
postman-env: ## Gera o environment do Postman a partir do .env
	@$(call require_env,ARGUS_API_URL)
	@$(call require_env,ARGUS_INGEST_URL)
	@printf '%s\n' \
	  '{' \
	  '  "name": "Argus — lab (gerado, nao versionado)",' \
	  '  "values": [' \
	  '    { "key": "read_url", "value": "$(ARGUS_API_URL)", "type": "default", "enabled": true },' \
	  '    { "key": "ingest_url", "value": "$(ARGUS_INGEST_URL)", "type": "default", "enabled": true },' \
	  '    { "key": "changes_url", "value": "$(ARGUS_CHANGES_URL)", "type": "default", "enabled": true }' \
	  '  ],' \
	  '  "_postman_variable_scope": "environment"' \
	  '}' > $(POSTMAN)/environment.json
	@echo "$(POSTMAN)/environment.json gerado (esta no .gitignore)"

.PHONY: postman
postman: postman-env ## Roda a colecao Postman contra as APIs publicadas
	npx --yes newman@6 run $(POSTMAN)/argus.postman_collection.json \
	  -e $(POSTMAN)/environment.json --delay-request 1500

# --------------------------------------------------------------------------- #
# Operacao
# --------------------------------------------------------------------------- #

.PHONY: smoke
smoke: ## Verifica a API publicada de ponta a ponta
	@$(call require_env,ARGUS_API_URL)
	@echo "Testando $$ARGUS_API_URL"
	@fail=0; \
	for path in \
	  "/health/ready" \
	  "/openapi.json" \
	  "/api/v1/clock" \
	  "/api/v1/sources" \
	  "/api/v1/series?limit=10" \
	  "/api/v1/incidents?limit=5" \
	  "/api/v1/events?limit=1" \
	  "/api/v1/facets?field=event_name"; do \
	  code=$$(curl -s -o /dev/null -w '%{http_code}' "$(ARGUS_API_URL)$$path"); \
	  t=$$(curl -s -o /dev/null -w '%{time_total}' "$(ARGUS_API_URL)$$path"); \
	  if [ "$$code" = "200" ]; then st="ok  "; else st="FALHA"; fail=1; fi; \
	  printf "  %s %3s %6.2fs  %s\n" "$$st" "$$code" "$$t" "$$path"; \
	done; \
	exit $$fail

.PHONY: replay
replay: ## Reenvia os eventos de exemplo para a API de ingestao
	@$(call require_env,ARGUS_INGEST_URL)
	cd $(TOOLS) && $(UV) python replay_events.py --url "$(ARGUS_INGEST_URL)" --src "$(EVENTS_SRC)"

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
