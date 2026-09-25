#!/usr/bin/env bash
# Ensaio 4 -- HPA no kind (opcional): 50 VUs por 3 min em /api/v1/clock.
#
# O overlay kind limita o HPA do backend a 1..2 replicas e o pod pede 100m de
# CPU com alvo de 60%. O que se mede: se e quando o HPA sobe para 2 e o que o
# metrics-server reporta ao longo da carga. A reducao (janela de estabilizacao
# de 300 s) nao e aguardada.
#
# Saida: artefatos/evidencias/resiliencia-kind-04-hpa.txt
set -uo pipefail
source "$(dirname "$0")/comum.sh"
EV="${RAIZ}/artefatos/evidencias/resiliencia-kind-04-hpa.txt"

cabecalho "ENSAIO 4 -- HPA SOB CARGA (kind, local, 1 no)"

cmd $K get hpa argus-backend
cmd $K get hpa argus-backend -o jsonpath='{.spec.metrics}{"\n"}{.spec.behavior}{"\n"}'
cmd $K top pods

inicia_watch "hpa argus-backend" "$AQUI/watch-04-hpa.txt"
log "k6: 50 VUs por 180 s so em /api/v1/clock (ROTAS=/api/v1/clock, sem pausa)"
K6_OUT="$AQUI/k6-04.stdout.txt"
K6_JSON="$AQUI/k6-04.summary.json"
BASE_URL="$BASE_URL" VUS=50 DURACAO=180s ROTAS=/api/v1/clock PAUSA_S=0 \
  k6 run --quiet --summary-export="$K6_JSON" "$AQUI/carga_leve.js" > "$K6_OUT" 2>&1 &
K6_PID=$!
T0=$(epoch_ms)

T_ESCALOU=""
for i in $(seq 1 16); do
  sleep 15
  REPL="$($K get deploy argus-backend -o jsonpath='{.status.replicas}')"
  READY="$($K get deploy argus-backend -o jsonpath='{.status.readyReplicas}')"
  HPA="$($K get hpa argus-backend -o jsonpath='cpu={.status.currentMetrics[0].resource.current.averageUtilization}% alvo={.spec.metrics[0].resource.target.averageUtilization}% desired={.status.desiredReplicas} current={.status.currentReplicas}')"
  TOP="$($K top pods -l app.kubernetes.io/name=argus-backend --no-headers 2>/dev/null | awk '{printf "%s(%s,%s) ", $1, $2, $3}')"
  printf '[%s] t+%3ds deploy replicas=%s ready=%s | hpa %s | top: %s\n' "$(agora)" $(( ($(epoch_ms) - T0) / 1000 )) "${REPL:-?}" "${READY:-0}" "$HPA" "$TOP" | bruto
  if [ -z "$T_ESCALOU" ] && [ "${REPL:-1}" -ge 2 ]; then
    T_ESCALOU=$(epoch_ms)
    log "HPA escalou para ${REPL} replicas $(seg "$T_ESCALOU" "$T0") s apos o inicio da carga"
  fi
  if ! kill -0 "$K6_PID" 2>/dev/null && [ "$i" -ge 13 ]; then break; fi
done

wait "$K6_PID" || true
{
  echo
  echo "---- saida do k6 ----"; cat "$K6_OUT"
  echo "---- numeros-chave ----"
  jq -r '"http_reqs=\(.metrics.http_reqs.count) rps=\(.metrics.http_reqs.rate | . * 10 | round / 10) falhas=\(.metrics.respostas_nao_200.count // 0) p95_ms=\(.metrics.http_req_duration["p(95)"] | round) max_ms=\(.metrics.http_req_duration.max | round)"' "$K6_JSON"
  echo "---- fim ----"
} | bruto
cmd $K describe hpa argus-backend
cmd $K get events --field-selector involvedObject.name=argus-backend,involvedObject.kind=HorizontalPodAutoscaler --sort-by=.lastTimestamp
encerra_watch "$AQUI/watch-04-hpa.txt" "watch do HPA (TARGETS/REPLICAS ao longo do tempo)"

{
  echo
  echo "================================================================"
  echo "RESUMO (kind local, 1 no, HPA 1..2 replicas, alvo CPU 60% de 100m, commit $(git -C "$RAIZ" rev-parse --short=12 HEAD))"
  if [ -n "$T_ESCALOU" ]; then
    grep -h 'HPA escalou' "$EV" | tail -1 | sed 's/^\[[^]]*\] //'
  else
    echo "  o HPA NAO escalou durante os 180 s de carga (ver utilizacao acima)"
  fi
  echo "  k6: $(jq -r '"\(.metrics.http_reqs.count) req a \(.metrics.http_reqs.rate | round) rps, \(.metrics.respostas_nao_200.count // 0) falhas, p95 \(.metrics.http_req_duration["p(95)"] | round) ms"' "$K6_JSON")"
  echo "  reducao para 1 replica nao aguardada (stabilizationWindowSeconds=300)"
  echo "================================================================"
} | bruto
