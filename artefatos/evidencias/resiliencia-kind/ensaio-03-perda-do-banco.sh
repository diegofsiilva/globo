#!/usr/bin/env bash
# Ensaio 3 -- Perda do banco: readiness != liveness.
#
#   1. Postgres escalado para 0: o backend deve ficar NOT READY (readiness em
#      /health/ready falha) SEM reiniciar (liveness em /health/live passa);
#      o Ingress, sem endpoint pronto, responde 503.
#   2. Postgres de volta (replicas=1). Como o Postgres do kind usa emptyDir,
#      o banco volta VAZIO: a readiness continua falhando ("relation does not
#      exist"), ainda sem reinicio -- o mesmo comportamento descrito em
#      conteineres-final §5.1.
#   3. Job de migration reaplicado: o backend volta a Ready sozinho, com o
#      mesmo contador de RESTARTS.
#
# Saida: artefatos/evidencias/resiliencia-kind-03-perda-do-banco.txt
set -uo pipefail
source "$(dirname "$0")/comum.sh"
EV="${RAIZ}/artefatos/evidencias/resiliencia-kind-03-perda-do-banco.txt"

cabecalho "ENSAIO 3 -- PERDA DO BANCO: readiness falha, liveness passa, pod nao reinicia (kind, local)"

POD="$(pods_backend_ready | head -1)"
if [ -z "$POD" ]; then log "ERRO: nenhum pod do backend Ready"; exit 1; fi
RESTARTS_ANTES="$($K get pod "$POD" -o jsonpath='{.status.containerStatuses[0].restartCount}')"
log "pod do backend: ${POD}  RESTARTS antes: ${RESTARTS_ANTES}"
cmd $K get deploy argus-postgres
cmd $K get endpoints argus-backend argus-postgres

# port-forward direto ao POD (ignora readiness/Endpoints) para consultar as
# duas sondas como o kubelet as ve.
$K port-forward "pod/${POD}" 15000:5000 >/dev/null 2>&1 &
PF_PID=$!
sleep 2
sondas() {
  printf 'live=%s ready=%s' "$(http_code http://127.0.0.1:15000/health/live)" "$(http_code http://127.0.0.1:15000/health/ready)"
}
ingress() {
  printf 'ingress:/api/v1/clock=%s /health/ready=%s' "$(http_code "$BASE_URL/api/v1/clock")" "$(http_code "$BASE_URL/health/ready")"
}
estado() {
  printf 'Ready=%s RESTARTS=%s' \
    "$($K get pod "$POD" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}')" \
    "$($K get pod "$POD" -o jsonpath='{.status.containerStatuses[0].restartCount}')"
}
log "linha de base: $(estado) | $(sondas) | $(ingress)"

inicia_watch "pods" "$AQUI/watch-03-pods.txt"

# ---------------- 1. derruba o Postgres ----------------
log "=============== 1. POSTGRES -> 0 REPLICAS ==============="
T0=$(epoch_ms)
cmd $K scale deploy/argus-postgres --replicas=0
T_NOTREADY=""
for i in $(seq 1 90); do
  E="$(estado)"
  printf '[%s] %s | %s | %s | postgres: %s\n' "$(agora)" "$E" "$(sondas)" "$(ingress)" \
    "$($K get pods -l app.kubernetes.io/name=argus-postgres -o jsonpath='{range .items[*]}{.metadata.name}:{.status.phase}{" "}{end}' 2>/dev/null)" | bruto
  if [ -z "$T_NOTREADY" ] && echo "$E" | grep -q 'Ready=False'; then
    T_NOTREADY=$(epoch_ms)
    log "T1: backend saiu de Ready $(seg "$T_NOTREADY" "$T0") s apos o scale (readiness periodSeconds=5, failureThreshold=3)"
    log "continuando a observar por 30 s para comprovar que NAO ha reinicio (liveness em /health/live segue 200)"
    for j in $(seq 1 15); do
      sleep 2
      printf '[%s] %s | %s | %s\n' "$(agora)" "$(estado)" "$(sondas)" "$(ingress)" | bruto
    done
    break
  fi
  sleep 1
done
log "corpo de /health/ready direto no pod (sem banco):"
curl -s -m 3 http://127.0.0.1:15000/health/ready | head -c 600 | bruto; echo | bruto
log "corpo de /health/live direto no pod:"
curl -s -m 3 http://127.0.0.1:15000/health/live | head -c 300 | bruto; echo | bruto
log "Endpoints do backend (esperado: sem endereco pronto):"
cmd $K get endpoints argus-backend -o wide
log "describe do pod (Conditions e Events):"
$K describe pod "$POD" 2>&1 | awk '/^Conditions:/{p=1} /^Volumes:/{p=0} p' | bruto
$K describe pod "$POD" 2>&1 | awk '/^Events:/{p=1} p' | bruto
log "logs do backend com as sondas (ultimas 12 linhas com /health):"
$K logs "$POD" --tail=400 2>/dev/null | grep -E '/health/(live|ready)' | tail -12 | bruto
RESTARTS_SEM_BANCO="$($K get pod "$POD" -o jsonpath='{.status.containerStatuses[0].restartCount}')"
log "RESULTADO 1: sem banco, pod ${POD} Ready=False, RESTARTS=${RESTARTS_SEM_BANCO} (antes: ${RESTARTS_ANTES}); Ingress responde $(http_code "$BASE_URL/api/v1/clock") em /api/v1/clock"

# ---------------- 2. Postgres de volta ----------------
log "=============== 2. POSTGRES -> 1 REPLICA (emptyDir: banco volta vazio) ==============="
T2=$(epoch_ms)
cmd $K scale deploy/argus-postgres --replicas=1
cmd $K rollout status deploy/argus-postgres --timeout=180s
T3=$(epoch_ms)
log "postgres Ready $(seg "$T3" "$T2") s apos o scale"
for i in $(seq 1 10); do
  printf '[%s] %s | %s | %s\n' "$(agora)" "$(estado)" "$(sondas)" "$(ingress)" | bruto
  sleep 2
done
log "corpo de /health/ready com banco de pe mas vazio:"
curl -s -m 3 http://127.0.0.1:15000/health/ready | head -c 600 | bruto; echo | bruto
log "RESULTADO 2: banco de pe e vazio -> readiness segue falhando, RESTARTS=$($K get pod "$POD" -o jsonpath='{.status.containerStatuses[0].restartCount}')"

# ---------------- 3. migrations ----------------
log "=============== 3. JOB DE MIGRATION (make k8s-migrate K8S_OVERLAY=kind) ==============="
T4=$(epoch_ms)
log "\$ make -C apps/fullstack k8s-migrate K8S_OVERLAY=kind KUBECTL=\"kubectl --context ${KCTX}\""
make -C "$APP" --no-print-directory k8s-migrate K8S_OVERLAY=kind KUBECTL="kubectl --context ${KCTX}" 2>&1 | tail -25 | bruto
T5=$(epoch_ms)
log "job concluido em $(seg "$T5" "$T4") s"
T_READY=""
for i in $(seq 1 60); do
  E="$(estado)"
  printf '[%s] %s | %s | %s\n' "$(agora)" "$E" "$(sondas)" "$(ingress)" | bruto
  if echo "$E" | grep -q 'Ready=True'; then T_READY=$(epoch_ms); break; fi
  sleep 1
done
RESTARTS_DEPOIS="$($K get pod "$POD" -o jsonpath='{.status.containerStatuses[0].restartCount}')"
if [ -n "$T_READY" ]; then
  log "RESULTADO 3: backend Ready de novo $(seg "$T_READY" "$T5") s apos o fim das migrations ($(seg "$T_READY" "$T2") s apos o scale do Postgres para 1); RESTARTS=${RESTARTS_DEPOIS} (antes: ${RESTARTS_ANTES}) -- mesmo pod, sem reinicio"
else
  log "ERRO: backend nao voltou a Ready em 60 s apos as migrations"
fi
cmd $K get endpoints argus-backend -o wide
pods_backend | bruto
log "eventos recentes:"
eventos_recentes 20 | bruto

kill "$PF_PID" 2>/dev/null || true
encerra_watch "$AQUI/watch-03-pods.txt" "watch de todos os pods do namespace"

{
  echo
  echo "================================================================"
  echo "RESUMO (kind local, commit $(git -C "$RAIZ" rev-parse --short=12 HEAD))"
  grep -h 'RESULTADO 1:' "$EV" | tail -1 | sed 's/^\[[^]]*\] //'
  grep -h 'RESULTADO 2:' "$EV" | tail -1 | sed 's/^\[[^]]*\] //'
  grep -h 'RESULTADO 3:' "$EV" | tail -1 | sed 's/^\[[^]]*\] //'
  echo "================================================================"
} | bruto
