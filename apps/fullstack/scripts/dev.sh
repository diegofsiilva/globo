#!/usr/bin/env bash
# Sobe banco local, API de leitura e dashboard no MESMO terminal, e derruba os
# tres no Ctrl-C. E o que `make dev` executa; nao chame direto sem precisar.
#
# Este script nao reproduz passo nenhum: cada etapa e um alvo do Makefile
# (db-ensure, api, frontend-dev), e a regra 2 do AGENTS.md continua valendo.
# O que ele acrescenta -- e que um Makefile nao faz bem -- e a orquestracao:
# dois processos de longa duracao em paralelo, espera pela API antes de subir
# o dashboard, URL e token impressos quando os dois respondem, e a derrubada
# da ARVORE de processos na saida. `make api` e `make frontend-dev` sao
# make -> sh -> python/node; matar so o make deixaria a API e o Next orfaos,
# presos nas portas ate alguem achar o pid.
#
# Roda no bash 3.2 do macOS e em qualquer Linux: nada de `wait -n`, arrays
# associativos ou `setsid`.
#
# Variaveis (o Makefile passa todas; os defaults sao para rodar o script solto):
#   API_PORT      porta da API                     (5000)
#   WEB_PORT      porta do dashboard               (3000)
#   PG_CONTAINER  container do PostgreSQL local    (argus-pg)
#   PG_URL        URL do banco local
#   DEV_TOKEN     token da tela de acesso no ambiente local (64 zeros)
#   DEV_API_URL   URL da API como o NAVEGADOR a alcanca. Por padrao
#                 http://localhost:API_PORT; num devcontainer remoto aberto
#                 pelo navegador e a URL encaminhada da porta da API.
set -euo pipefail

cd "$(dirname "$0")/.."

MAKE=${MAKE:-make}
API_PORT=${API_PORT:-5000}
WEB_PORT=${WEB_PORT:-3000}
PG_CONTAINER=${PG_CONTAINER:-argus-pg}
PG_URL=${PG_URL:-postgresql://argus:argus@localhost:55432/argus}
DEV_TOKEN=${DEV_TOKEN:-0000000000000000000000000000000000000000000000000000000000000000}
DEV_API_URL=${DEV_API_URL:-http://localhost:$API_PORT}

falha() { echo "erro: $*" >&2; exit 1; }

# porta_ocupada PORTA -> 0 quando algo ja escuta nela. Usa o /dev/tcp do bash
# para nao depender de lsof (ausente em imagem slim) nem de nc (sintaxe varia
# entre BSD e GNU).
porta_ocupada() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }

# esperar URL SEGUNDOS PID -> 0 quando a URL responde 2xx antes do limite.
# Desiste cedo se o processo ja morreu, em vez de esperar o limite inteiro
# olhando para uma porta que nunca vai abrir.
esperar() {
  local url=$1 limite=$2 pid=$3 i
  for i in $(seq 1 "$limite"); do
    if command -v curl >/dev/null 2>&1; then
      curl -fsS --max-time 30 -o /dev/null "$url" 2>/dev/null && return 0
    else
      porta_ocupada "${url##*:}" && return 0
    fi
    kill -0 "$pid" 2>/dev/null || return 1
    sleep 1
  done
  return 1
}

# --- derrubada -------------------------------------------------------------
PIDS=""
matar_arvore() {  # filhos primeiro, depois o pai: o make nao repassa sinal
  local pid=$1 filho
  for filho in $(pgrep -P "$pid" 2>/dev/null); do matar_arvore "$filho"; done
  kill "$pid" 2>/dev/null || true
}
derrubar() {
  trap - EXIT INT TERM
  [ -n "$PIDS" ] || return 0
  echo
  echo "derrubando API e dashboard..."
  for pid in $PIDS; do matar_arvore "$pid"; done
  wait 2>/dev/null || true
  echo "pronto. O banco continua no ar ('make db-stop' derruba)."
}
trap derrubar EXIT
trap 'derrubar; exit 130' INT TERM

# --- pre-requisitos --------------------------------------------------------
for ferramenta in docker uv npm; do
  command -v "$ferramenta" >/dev/null 2>&1 \
    || falha "'$ferramenta' nao encontrado. Veja 'Pre-requisitos' no README da raiz."
done
docker info >/dev/null 2>&1 || falha "o Docker nao esta rodando, e o banco local e um container."
porta_ocupada "$API_PORT" && falha "a porta $API_PORT ja esta em uso (no macOS costuma ser o AirPlay Receiver). Rode: make dev API_PORT=5001"
porta_ocupada "$WEB_PORT" && falha "a porta $WEB_PORT ja esta em uso. Rode: make dev WEB_PORT=3001"
[ -d frontend/node_modules ] || "$MAKE" --no-print-directory frontend-install

# --- banco -----------------------------------------------------------------
"$MAKE" --no-print-directory db-ensure

# --- API -------------------------------------------------------------------
# DATABASE_URL explicito: um .env com a URL do RDS nao pode desviar a API
# local para a nuvem em silencio.
echo "subindo a API em http://localhost:$API_PORT ..."
"$MAKE" --no-print-directory api API_PORT="$API_PORT" DATABASE_URL="$PG_URL" &
API_PID=$!
PIDS="$API_PID"
esperar "http://127.0.0.1:$API_PORT/health/live" 120 "$API_PID" \
  || falha "a API nao respondeu em /health/live; o motivo esta no log acima."

# --- dashboard -------------------------------------------------------------
echo "subindo o dashboard em http://localhost:$WEB_PORT ..."
"$MAKE" --no-print-directory frontend-dev ARGUS_API_URL="$DEV_API_URL" WEB_PORT="$WEB_PORT" &
WEB_PID=$!
PIDS="$PIDS $WEB_PID"
esperar "http://127.0.0.1:$WEB_PORT/" 180 "$WEB_PID" \
  || falha "o dashboard nao respondeu na porta $WEB_PORT; o motivo esta no log acima."

cat <<BANNER

=====================================================================
  Argus no ar
    dashboard  http://localhost:$WEB_PORT
    API        $DEV_API_URL   (Swagger em $DEV_API_URL/docs)

  Token da tela de acesso (ambiente local, AUTH_REQUIRED=0):
    $DEV_TOKEN

  Banco vazio? 'make dev-seed' carrega a amostra do parceiro
  (precisa de ../../data/parquet; sem ela o alvo so avisa).
  Ctrl-C derruba API e dashboard; o banco fica.
=====================================================================

BANNER

# Fica de pe ate um dos dois cair ou o Ctrl-C. `wait -n` seria o ideal, mas
# so existe no bash 4.3+, e o macOS ainda embarca o 3.2.
while kill -0 "$API_PID" 2>/dev/null && kill -0 "$WEB_PID" 2>/dev/null; do
  sleep 1
done
if ! kill -0 "$API_PID" 2>/dev/null; then
  echo "a API encerrou sozinha; derrubando o dashboard." >&2
else
  echo "o dashboard encerrou sozinho; derrubando a API." >&2
fi
exit 1
