# Comandos do projeto Argus.
#
#   make            lista os alvos disponíveis
#   make test       roda tudo que valida o código
#   make deploy     publica a API de leitura
#
# Endpoints e perfis AWS vêm do .env (veja .env.example). Nenhum valor real de
# URL ou conta é escrito aqui — este arquivo é versionado.

SHELL := /bin/bash
.DEFAULT_GOAL := help

# Carrega o .env quando existir, sem quebrar quando não existir.
ifneq (,$(wildcard .env))
include .env
export
endif

WORKER  := apps/worker
BACKEND := apps/backend
INFRA   := apps/infra
TOOLS   := apps/tools

# Pasta com os CSVs de evento exportados do BI.
EVENTS_SRC ?= $(HOME)/Downloads/Events

# `uv run` monta o ambiente sozinho a partir do pyproject de cada app.
UV := uv run --quiet

.PHONY: help
help: ## Lista os alvos
	@echo "Argus — alvos disponíveis:"
	@echo
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo
	@echo "Variáveis: EVENTS_SRC=$(EVENTS_SRC)"
	@if [ ! -f .env ]; then \
	  echo; echo "  Aviso: .env ausente. Copie de .env.example e preencha"; \
	  echo "  (os alvos de operação precisam dele)."; \
	fi

# --------------------------------------------------------------------------- #
# Ambiente
# --------------------------------------------------------------------------- #

.PHONY: install
install: install-worker install-backend ## Instala as dependências dos dois apps Python

.PHONY: install-worker
install-worker: ## Prepara o ambiente do worker
	cd $(WORKER) && uv sync --all-groups

.PHONY: install-backend
install-backend: ## Prepara o ambiente da API
	cd $(BACKEND) && uv sync --extra dev

.PHONY: env
env: ## Cria o .env a partir dos outputs do Terraform
	@test -f .env && { echo ".env já existe — apague antes se quiser regerar."; exit 1; } || true
	@echo "Lendo os endpoints do Terraform..."
	@{ \
	  echo "ARGUS_API_URL=$$(cd $(INFRA) && terraform output -raw read_api_url 2>/dev/null)"; \
	  echo "ARGUS_INGEST_URL=$$(cd $(INFRA) && terraform output -raw ingest_url 2>/dev/null)"; \
	  echo "AWS_PROFILE=$${AWS_PROFILE:-default}"; \
	  echo "AWS_REGION=$${AWS_REGION:-us-east-1}"; \
	} > .env
	@echo ".env criado (está no .gitignore)."

# --------------------------------------------------------------------------- #
# Qualidade
# --------------------------------------------------------------------------- #

.PHONY: test
test: test-worker test-backend ## Roda as duas suítes

.PHONY: test-worker
test-worker: ## Testes do worker de ingestão
	cd $(WORKER) && $(UV) pytest

.PHONY: test-backend
test-backend: ## Testes da API de leitura
	cd $(BACKEND) && $(UV) pytest

.PHONY: lint
lint: ## Verifica estilo sem alterar arquivos
	cd $(WORKER) && $(UV) ruff check src tests && $(UV) ruff format --check src tests
	cd $(BACKEND) && $(UV) ruff check src tests
	cd $(INFRA) && terraform fmt -check -recursive

.PHONY: fmt
fmt: ## Formata o código e o Terraform
	@# `ruff check --fix` sai com erro quando resta algo que ele não conserta
	@# sozinho. Aqui isso não deve interromper a formatação — quem barra é o
	@# alvo `lint`, que é o portão de qualidade.
	cd $(WORKER) && ($(UV) ruff check --fix src tests || true) && $(UV) ruff format src tests
	cd $(BACKEND) && ($(UV) ruff check --fix src tests || true) && $(UV) ruff format src tests
	cd $(INFRA) && terraform fmt -recursive

.PHONY: check
check: lint test tf-validate ## Tudo que a CI deveria rodar

# --------------------------------------------------------------------------- #
# Desenvolvimento
# --------------------------------------------------------------------------- #

.PHONY: api
api: ## Sobe a API local apontando para o DynamoDB real
	@$(call require_env,AWS_PROFILE)
	cd $(BACKEND) && $(UV) python lambda_handler.py

.PHONY: docs
docs: ## Abre a documentação Swagger da API publicada
	@$(call require_env,ARGUS_API_URL)
	@echo "Abrindo a Swagger UI..."
	@open "$(ARGUS_API_URL)/docs" 2>/dev/null || echo "Acesse: $$ARGUS_API_URL/docs"

.PHONY: openapi
openapi: ## Salva a especificação OpenAPI em apps/backend/openapi.json
	@$(call require_env,ARGUS_API_URL)
	curl -s "$(ARGUS_API_URL)/openapi.json" -o $(BACKEND)/openapi.json
	@echo "gravado em $(BACKEND)/openapi.json"

.PHONY: events-json
events-json: ## Converte os CSVs do BI em JSON canônico (fixtures)
	python3 $(TOOLS)/events_csv_to_json.py --src "$(EVENTS_SRC)" --out $(WORKER)/tests/fixtures

.PHONY: worker-image
worker-image: ## Constrói a imagem do worker (ARM64)
	docker build --platform linux/arm64 -t argus-events-worker:dev $(WORKER)

# --------------------------------------------------------------------------- #
# Infraestrutura
# --------------------------------------------------------------------------- #

.PHONY: tf-init
tf-init: ## Inicializa o Terraform
	cd $(INFRA) && terraform init

.PHONY: tf-validate
tf-validate: ## Valida a configuração sem tocar na AWS
	cd $(INFRA) && terraform validate

.PHONY: tf-plan
tf-plan: lambda-build ## Mostra o que mudaria na AWS (somente leitura)
	cd $(INFRA) && terraform plan

.PHONY: tf-apply
tf-apply: lambda-build ## Aplica as mudanças na AWS
	cd $(INFRA) && terraform apply

.PHONY: tf-output
tf-output: ## Mostra os endpoints e nomes de recurso
	cd $(INFRA) && terraform output

.PHONY: tf-destroy
tf-destroy: ## Remove TODA a infraestrutura
	@echo "Isto apaga a tabela de eventos, as filas e os serviços."
	@read -p "Digite 'destruir' para confirmar: " r; [ "$$r" = "destruir" ] || { echo "cancelado."; exit 1; }
	cd $(INFRA) && terraform destroy

.PHONY: lambda-build
lambda-build: ## Empacota a API de leitura para a Lambda
	cd $(BACKEND) && ./scripts/build_lambda.sh

.PHONY: deploy
deploy: test-backend lambda-build ## Testa, empacota e publica a API de leitura
	cd $(INFRA) && terraform apply -auto-approve
	@$(MAKE) --no-print-directory smoke

.PHONY: worker-deploy
worker-deploy: ## Publica a imagem do worker no ECR e força novo deploy
	@$(call require_env,AWS_PROFILE)
	cd $(INFRA) && terraform output -raw docker_push_commands | bash

# --------------------------------------------------------------------------- #
# Operação
# --------------------------------------------------------------------------- #

.PHONY: smoke
smoke: ## Verifica a API publicada de ponta a ponta
	@$(call require_env,ARGUS_API_URL)
	@echo "Testando $$ARGUS_API_URL"
	@fail=0; \
	for path in \
	  "/health/ready" \
	  "/openapi.json" \
	  "/api/v1/events?limit=1" \
	  "/api/v1/facets?field=event_name" \
	  "/api/v1/metrics/breakdown?dimension=event_name"; do \
	  code=$$(curl -s -o /dev/null -w '%{http_code}' "$(ARGUS_API_URL)$$path"); \
	  t=$$(curl -s -o /dev/null -w '%{time_total}' "$(ARGUS_API_URL)$$path"); \
	  if [ "$$code" = "200" ]; then st="ok  "; else st="FALHA"; fail=1; fi; \
	  printf "  %s %3s %6.2fs  %s\n" "$$st" "$$code" "$$t" "$$path"; \
	done; \
	exit $$fail

.PHONY: replay
replay: ## Reenvia os eventos de exemplo para a API de ingestão
	@$(call require_env,ARGUS_INGEST_URL)
	python3 $(TOOLS)/replay_events.py --url "$(ARGUS_INGEST_URL)" --src "$(EVENTS_SRC)"

.PHONY: logs-worker
logs-worker: ## Acompanha os logs do worker
	@$(call require_env,AWS_PROFILE)
	aws logs tail "$$(cd $(INFRA) && terraform output -raw log_group_worker)" --follow

.PHONY: logs-api
logs-api: ## Acompanha os logs da API de leitura
	@$(call require_env,AWS_PROFILE)
	aws logs tail "/aws/lambda/$$(cd $(INFRA) && terraform output -raw ecs_service_name)-read-api" --follow

.PHONY: dlq
dlq: ## Mostra o que está na fila de eventos rejeitados
	@$(call require_env,AWS_PROFILE)
	aws sqs receive-message \
	  --queue-url "$$(cd $(INFRA) && terraform output -raw dlq_url)" \
	  --message-attribute-names All --max-number-of-messages 10 \
	  --query 'Messages[].{motivo:MessageAttributes.FailureReason.StringValue,corpo:Body}' \
	  --output json

.PHONY: count
count: ## Conta os eventos armazenados
	@$(call require_env,AWS_PROFILE)
	@aws dynamodb scan \
	  --table-name "$$(cd $(INFRA) && terraform output -raw table_name)" \
	  --select COUNT --query Count --output text

.PHONY: pause
pause: ## Desliga o worker sem destruir nada (economiza crédito)
	cd $(INFRA) && terraform apply -var="worker_desired_count=0"

.PHONY: resume
resume: ## Religa o worker
	cd $(INFRA) && terraform apply -var="worker_desired_count=1"

# --------------------------------------------------------------------------- #
# Limpeza
# --------------------------------------------------------------------------- #

.PHONY: clean
clean: ## Remove artefatos de build e caches
	rm -rf $(BACKEND)/dist $(BACKEND)/openapi.json
	find apps -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
	find apps -type d -name '.pytest_cache' -prune -exec rm -rf {} + 2>/dev/null || true
	find apps -type d -name '.ruff_cache' -prune -exec rm -rf {} + 2>/dev/null || true

# --------------------------------------------------------------------------- #
# Auxiliar
# --------------------------------------------------------------------------- #

# Falha com mensagem útil quando uma variável obrigatória não está definida,
# em vez de deixar o comando rodar com string vazia e errar de forma obscura.
define require_env
	if [ -z "$${$(1)}" ]; then \
	  echo "erro: $(1) não definida."; \
	  echo "      Preencha o .env (veja .env.example) ou rode 'make env'."; \
	  exit 1; \
	fi
endef
