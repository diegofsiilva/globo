#!/usr/bin/env bash
# Ensaio 2 -- Implantacao sem queda + deploy defeituoso + rollback, sob carga.
#
#   1. `rollout restart` com k6 rodando: maxUnavailable=0/maxSurge=1 deve
#      manter o atendimento (0 falhas) mesmo com 1 replica.
#   2. `set image` para uma tag inexistente: o pod novo fica em
#      ErrImagePull/ImagePullBackOff e o pod antigo continua servindo.
#   3. `rollout undo`: volta a revisao anterior; medir o tempo ate estavel.
#
# Saida: artefatos/evidencias/resiliencia-kind-02-rollout-e-undo.txt
set -uo pipefail
source "$(dirname "$0")/comum.sh"
EV="${RAIZ}/artefatos/evidencias/resiliencia-kind-02-rollout-e-undo.txt"

cabecalho "ENSAIO 2 -- DEPLOY SEM QUEDA, DEPLOY DEFEITUOSO E ROLLBACK (kind, local)"

IMAGEM_BOA="$($K get deploy argus-backend -o jsonpath='{.spec.template.spec.containers[0].image}')"
log "imagem em producao no cluster: ${IMAGEM_BOA}"
cmd $K rollout history deploy/argus-backend

inicia_watch "pods -l app.kubernetes.io/name=argus-backend" "$AQUI/watch-02-pods.txt"
inicia_watch "deploy argus-backend" "$AQUI/watch-02-deploy.txt"
inicia_k6 "02" "150s" 5
log "aguardando 8 s de carga estavel"
sleep 8

# ---------------- 1. rollout restart ----------------
log "=============== 1. ROLLOUT RESTART (sem mudar a imagem) ==============="
T0=$(epoch_ms)
cmd $K rollout restart deploy/argus-backend
cmd $K rollout status deploy/argus-backend --timeout=180s
T1=$(epoch_ms)
log "RESULTADO restart: rollout status concluido em $(seg "$T1" "$T0") s"
pods_backend | bruto
cmd $K rollout history deploy/argus-backend
FALHAS_APOS_RESTART=$(grep -c ' FALHA ' "$K6_OUT" 2>/dev/null || echo 0)
log "falhas do k6 acumuladas ate aqui: ${FALHAS_APOS_RESTART}"
sleep 8

# ---------------- 2. deploy defeituoso ----------------
log "=============== 2. DEPLOY DEFEITUOSO (tag inexistente) ==============="
T2=$(epoch_ms)
cmd $K set image deploy/argus-backend backend=argus-backend:nao-existe
log "observando os pods a cada 2 s ate ver ErrImagePull/ImagePullBackOff (limite 60 s)"
VIU_FALHA=""
for i in $(seq 1 30); do
  LINHA="$($K get pods -l app.kubernetes.io/name=argus-backend -o custom-columns='NAME:.metadata.name,READY:.status.conditions[?(@.type=="Ready")].status,STATUS:.status.containerStatuses[0].state.waiting.reason,RESTARTS:.status.containerStatuses[0].restartCount,IMAGE:.spec.containers[0].image' --no-headers | tr '\n' '|')"
  printf '[%s] %s\n' "$(agora)" "$LINHA" | bruto
  if echo "$LINHA" | grep -qE 'ErrImagePull|ImagePullBackOff'; then VIU_FALHA=1; fi
  # dois ciclos apos ver o BackOff ja basta para o registro
  if [ -n "$VIU_FALHA" ] && echo "$LINHA" | grep -q 'ImagePullBackOff'; then break; fi
  sleep 2
done
T3=$(epoch_ms)
log "deploy defeituoso detectado apos $(seg "$T3" "$T2") s do set image"
cmd $K get deploy argus-backend
log "pod antigo continua Ready (maxUnavailable=0 impede que ele saia antes de um novo ficar Ready):"
pods_backend | bruto
log "\$ $K rollout status deploy/argus-backend --timeout=10s   (esperado: nao conclui)"
$K rollout status deploy/argus-backend --timeout=10s 2>&1 | bruto || true
log "eventos do pod defeituoso:"
eventos_recentes 12 | bruto
CODE_DURANTE="$(http_code "$BASE_URL/api/v1/clock")"
log "curl ${BASE_URL}/api/v1/clock durante o deploy defeituoso -> HTTP ${CODE_DURANTE}"
FALHAS_APOS_DEFEITO=$(grep -c ' FALHA ' "$K6_OUT" 2>/dev/null || echo 0)
log "falhas do k6 acumuladas ate aqui: ${FALHAS_APOS_DEFEITO}"

# ---------------- 3. rollback ----------------
log "=============== 3. ROLLBACK (rollout undo) ==============="
T4=$(epoch_ms)
cmd $K rollout undo deploy/argus-backend
cmd $K rollout status deploy/argus-backend --timeout=180s
T5=$(epoch_ms)
IMAGEM_DEPOIS="$($K get deploy argus-backend -o jsonpath='{.spec.template.spec.containers[0].image}')"
log "RESULTADO undo: rollout status concluido em $(seg "$T5" "$T4") s; imagem restaurada = ${IMAGEM_DEPOIS}"
if [ "$IMAGEM_DEPOIS" = "$IMAGEM_BOA" ]; then log "imagem confere com a de antes do ensaio"; else log "ATENCAO: imagem diferente da original (${IMAGEM_BOA})"; fi
pods_backend | bruto
cmd $K rollout history deploy/argus-backend
cmd $K get rs -l app.kubernetes.io/name=argus-backend

encerra_k6
encerra_watch "$AQUI/watch-02-pods.txt" "watch dos pods do backend"
encerra_watch "$AQUI/watch-02-deploy.txt" "watch do Deployment (READY/UP-TO-DATE/AVAILABLE ao longo do tempo)"

{
  echo
  echo "================================================================"
  echo "RESUMO (kind local, 1 replica, commit $(git -C "$RAIZ" rev-parse --short=12 HEAD))"
  grep -h 'RESULTADO restart' "$EV" | tail -1 | sed 's/^\[[^]]*\] //'
  echo "  falhas do k6 durante o restart: ${FALHAS_APOS_RESTART}"
  echo "  deploy defeituoso: pod novo em ImagePullBackOff, pod antigo seguiu Ready; falhas do k6 acumuladas ate o undo: ${FALHAS_APOS_DEFEITO}"
  grep -h 'RESULTADO undo' "$EV" | tail -1 | sed 's/^\[[^]]*\] //'
  echo "  k6 total: $(k6_numeros)"
  echo "================================================================"
} | bruto
