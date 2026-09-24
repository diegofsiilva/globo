#!/usr/bin/env bash
# Executa os testes k6 dos RNF01–03 e preserva resultados por execução.

set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
ENV_FILE="$DIR/../../.env"
RESULTADOS="$DIR/resultados"
COM_GRAFANA=0
TESTE="todos"
STATUS_FINAL=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --com-grafana) COM_GRAFANA=1 ;;
    rnf01|rnf01-lote|rnf01-acumulo|rnf02|rnf03-baseline|rnf03-escalado|falha-backlog|falha-timeout|carga-ui|todos) TESTE="$1" ;;
    *)
      echo "Uso: $0 [rnf01|rnf01-lote|rnf01-acumulo|rnf02|rnf03-baseline|rnf03-escalado|falha-backlog|falha-timeout|carga-ui|todos] [--com-grafana]"
      exit 2
      ;;
  esac
  shift
done

declare -A VARIAVEIS_EXPLICITAS=()
for nome in ARGUS_INGEST_URL ARGUS_API_URL ARGUS_INGEST_TOKEN ARGUS_READ_TOKEN; do
  if [[ -v "$nome" ]]; then
    VARIAVEIS_EXPLICITAS["$nome"]="${!nome}"
  fi
done

if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

# A configuracao exportada no shell e mais recente que um .env local e deve
# prevalecer, especialmente depois de um novo apply do Learner Lab.
for nome in "${!VARIAVEIS_EXPLICITAS[@]}"; do
  printf -v "$nome" '%s' "${VARIAVEIS_EXPLICITAS[$nome]}"
  export "$nome"
done
unset VARIAVEIS_EXPLICITAS nome

mkdir -p "$RESULTADOS"
export K6_TEST_ID="${K6_TEST_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"

if command -v k6 >/dev/null 2>&1; then
  K6_CMD=(k6)
else
  K6_CMD=(
    docker run --rm --network host --user "$(id -u):$(id -g)"
    -v "$DIR:/work" -w /work
    -e ARGUS_INGEST_URL -e ARGUS_API_URL
    -e ARGUS_INGEST_TOKEN -e ARGUS_READ_TOKEN
    -e K6_TEST_ID -e K6_RESULT_FILE
    -e RNF03_FASE -e RNF03_RATE_PER_MIN -e RNF03_RECURSOS
    -e FALHA_CENARIO
    -e K6_QUANTIDADE_LOTES -e K6_EVENTOS_POR_LOTE -e K6_MAX_BODY_BYTES -e K6_VUS_INJECAO
    -e CARGA_UI_VUS_1 -e CARGA_UI_VUS_2 -e CARGA_UI_VUS_3 -e CARGA_UI_DURACAO -e CARGA_UI_PAUSA -e CARGA_UI_PENSAR_S
    -e K6_PROMETHEUS_RW_SERVER_URL -e K6_PROMETHEUS_RW_TREND_STATS
    grafana/k6:0.54.0
  )
fi

K6_OPTS=()
if [ "$COM_GRAFANA" -eq 1 ]; then
  make -C "$DIR/../.." observabilidade-up
  export K6_PROMETHEUS_RW_SERVER_URL="http://localhost:9090/api/v1/write"
  export K6_PROMETHEUS_RW_TREND_STATS="p(50),p(90),p(95),p(99),min,max,avg,count"
  K6_OPTS=(-o experimental-prometheus-rw)
  echo "Grafana: http://localhost:3001 | Prometheus: http://localhost:9090"
fi

executar() {
  local nome="$1"
  local script="$2"
  local instante
  instante="$(date -u +%Y%m%dT%H%M%SZ)"
  export K6_RESULT_FILE="resultados/${nome}_resultado_${instante}.json"

  echo
  echo "Executando $nome (test_id=$K6_TEST_ID)"
  "${K6_CMD[@]}" run "${K6_OPTS[@]}" \
    --tag "testid=$K6_TEST_ID" \
    --tag "requisito=$nome" \
    --summary-export="resultados/${nome}_summary_${instante}.json" \
    "$script" 2>&1 | tee "$RESULTADOS/${nome}_output_${instante}.txt"
  local status="${PIPESTATUS[0]}"
  if [ "$status" -ne 0 ]; then
    echo "FALHA: $nome terminou com status $status; o resultado foi preservado."
    STATUS_FINAL=1
  fi
}

executar_rnf03() {
  local fase="$1"
  if [ "$fase" = "baseline" ]; then
    export RNF03_FASE=baseline
    export RNF03_RATE_PER_MIN="${RNF03_RATE_PER_MIN:-1000}"
  else
    export RNF03_FASE=escalado
    export RNF03_RATE_PER_MIN="${RNF03_RATE_PER_MIN:-2000}"
  fi
  if [ -z "${RNF03_RECURSOS:-}" ]; then
    echo "RNF03_RECURSOS é obrigatória (ex.: '1 task, 256 CPU, 512 MiB')."
    STATUS_FINAL=1
    return
  fi
  executar "rnf03-$fase" "rnf03_escalabilidade.js"
}

executar_falha() {
  export FALHA_CENARIO="$1"
  executar "falha-$1" "falhas_resiliencia.js"
}

case "$TESTE" in
  rnf01) executar rnf01 rnf01_capacidade_ingestao.js ;;
  rnf01-lote)
    export K6_QUANTIDADE_LOTES=1
    executar rnf01-lote rnf01_lote_drenagem.js
    ;;
  rnf01-acumulo)
    if [ -z "${K6_QUANTIDADE_LOTES:-}" ] || [ "$K6_QUANTIDADE_LOTES" -lt 2 ] || [ "$K6_QUANTIDADE_LOTES" -gt 4 ]; then
      echo "K6_QUANTIDADE_LOTES deve ser 2, 3 ou 4 no cenario de acumulo."
      exit 2
    fi
    executar "rnf01-acumulo-${K6_QUANTIDADE_LOTES}x" rnf01_lote_drenagem.js
    ;;
  rnf02) executar rnf02 rnf02_tempo_resposta.js ;;
  carga-ui) executar carga-ui carga_ui.js ;;
  rnf03-baseline) executar_rnf03 baseline ;;
  rnf03-escalado) executar_rnf03 escalado ;;
  falha-backlog) executar_falha backlog ;;
  falha-timeout) executar_falha timeout ;;
  todos)
    executar rnf01 rnf01_capacidade_ingestao.js
    executar rnf02 rnf02_tempo_resposta.js
    echo "RNF03 exige mudança real de recursos; execute baseline e escalado separadamente."
    ;;
esac

exit "$STATUS_FINAL"
