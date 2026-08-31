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
INFRA      := infra
TOOLS      := tools
FRONTEND   := frontend
POSTMAN    := ../../artefatos/postman

# O motor de hipóteses ainda não possui endpoint no MVP. O modo mock é
# explícito nos fluxos suportados e pode ser trocado por `api` quando existir.
HYPOTHESES_SOURCE ?= mock
HYPOTHESES_API_URL ?=

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

.PHONY: env
env: ## Cria o .env a partir dos outputs do Terraform
	@test -f .env && { echo ".env ja existe — apague antes se quiser regerar."; exit 1; } || true
	@echo "Lendo os endpoints do Terraform..."
	@{ \
	  echo "ARGUS_API_URL=$$(cd $(INFRA) && terraform output -raw read_api_url 2>/dev/null)"; \
	  echo "ARGUS_INGEST_URL=$$(cd $(INFRA) && terraform output -raw ingest_url 2>/dev/null)"; \
	  echo "HYPOTHESES_SOURCE=mock"; \
	  echo "HYPOTHESES_API_URL="; \
	  echo "AWS_PROFILE=$${AWS_PROFILE:-default}"; \
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
test: test-worker test-simulator test-processing test-backend test-authorizer test-frontend ## Roda as suites que tem teste

.PHONY: test-authorizer
test-authorizer: ## Testes do Lambda authorizer (Bearer, audiencias, rotacao)
	cd $(AUTHORIZER) && uv run --quiet --group dev pytest

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

.PHONY: test-processing
test-processing: ## Testes do ETL incremental (watermarks, workers)
	cd $(PROCESSING) && TEST_DATABASE_URL=$${TEST_DATABASE_URL:-$(PG_TEST_URL)} $(UV) pytest

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
	  echo "  pulado: PostgreSQL local ausente (rode 'make -C apps/basica db-local')."; \
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
	  NEXT_PUBLIC_HYPOTHESES_API_URL="http://127.0.0.1:5100" \
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
	cd $(BACKEND) && $(UV) ruff check src tests
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
	cd $(BACKEND) && ($(UV) ruff check --fix src tests || true) && $(UV) ruff format src tests
	cd $(AUTHORIZER) && uv run --quiet --with ruff ruff format handler.py tests
	cd $(INFRA) && terraform fmt -recursive

.PHONY: check
check: lint test frontend-build-check test-frontend-e2e tf-validate ## Tudo que a CI deveria rodar

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
	  docker build --platform linux/arm64 -f $$nome/Dockerfile \
	    -t "$$url:$(IMAGE_TAG)" -t "$$url:latest" .; \
	  docker push "$$url:$(IMAGE_TAG)"; \
	  docker push "$$url:latest"; \
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
	@if [ "$(HYPOTHESES_SOURCE)" = "api" ] && [ -z "$(HYPOTHESES_API_URL)" ]; then \
	  echo "erro: HYPOTHESES_API_URL é obrigatória no modo api."; exit 1; \
	fi
	cd $(FRONTEND) && \
	  NEXT_PUBLIC_API_URL="$(ARGUS_API_URL)" \
	  NEXT_PUBLIC_HYPOTHESES_SOURCE="$(HYPOTHESES_SOURCE)" \
	  NEXT_PUBLIC_HYPOTHESES_API_URL="$(HYPOTHESES_API_URL)" \
	  npm run build

.PHONY: frontend-deploy
frontend-deploy: frontend-build ## Publica o dashboard no website S3
	@$(call require_env,AWS_PROFILE)
	aws s3 sync $(FRONTEND)/out/ \
	  "s3://$$(cd $(INFRA) && terraform output -raw frontend_bucket)/" --delete
	@echo
	@echo "Dashboard no ar: $$(cd $(INFRA) && terraform output -raw frontend_url)"

.PHONY: frontend-dev
frontend-dev: ## Sobe o dashboard local contra a API publicada
	@$(call require_env,ARGUS_API_URL)
	@if [ "$(HYPOTHESES_SOURCE)" = "api" ] && [ -z "$(HYPOTHESES_API_URL)" ]; then \
	  echo "erro: HYPOTHESES_API_URL é obrigatória no modo api."; exit 1; \
	fi
	cd $(FRONTEND) && \
	  NEXT_PUBLIC_API_URL="$(ARGUS_API_URL)" \
	  NEXT_PUBLIC_HYPOTHESES_SOURCE="$(HYPOTHESES_SOURCE)" \
	  NEXT_PUBLIC_HYPOTHESES_API_URL="$(HYPOTHESES_API_URL)" \
	  npm run dev

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
	allow_origin=$$(awk -F': *' 'tolower($$1) == "access-control-allow-origin" {gsub(/\r/, "", $$2); print $$2}' "$$headers" | tail -1); \
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
