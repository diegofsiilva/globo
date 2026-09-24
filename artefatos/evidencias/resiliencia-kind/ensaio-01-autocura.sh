#!/usr/bin/env bash
# Ensaio 1 -- Autocura (reposicao de pod do backend) sob carga leve.
#
# Roda duas vezes:
#   A) 1 replica (o padrao do overlay kind): mede a janela de falha que o
#      usuario ve quando o UNICO pod e removido, e o tempo ate o novo Ready.
#   B) 2 replicas (condicao da meta de §3.1.1, "outra replica Ready"): remove
#      UM dos dois pods e mede se o usuario percebe.
#
# Saida: artefatos/evidencias/resiliencia-kind-01-autocura.txt
set -uo pipefail
source "$(dirname "$0")/comum.sh"
EV="${RAIZ}/artefatos/evidencias/resiliencia-kind-01-autocura.txt"

cabecalho "ENSAIO 1 -- AUTOCURA: reposicao de pod do backend sob carga (kind, local)"

executa_rodada() {
  local rotulo="$1" replicas="$2" alvo_delete="$3"
  log "=============== RODADA ${rotulo}: replicas=${replicas} ==============="
  cmd $K get deploy argus-backend
  local antigos
  antigos="$(pods_backend_ready | tr '\n' ' ')"
  log "pods do backend antes: ${antigos}"
  pods_backend | bruto

  inicia_watch "pods -l app.kubernetes.io/name=argus-backend" "$AQUI/watch-01-${rotulo}.txt"
  inicia_k6 "01-${rotulo}" "60s" 5
  log "aguardando 10 s de carga estavel antes de remover o pod"
  sleep 10

  local t_del t_ready novo
  t_del=$(epoch_ms)
  if [ "$alvo_delete" = "label" ]; then
    log "\$ $K delete pod -l app.kubernetes.io/name=argus-backend --wait=false"
    $K delete pod -l app.kubernetes.io/name=argus-backend --wait=false 2>&1 | bruto
  else
    log "\$ $K delete pod ${alvo_delete} --wait=false"
    $K delete pod "$alvo_delete" --wait=false 2>&1 | bruto
  fi
  log "T0 (delete emitido) = $(agora)"

  # Amostra o estado a cada 0,5 s ate o novo pod ficar Ready.
  (
    while :; do
      printf '[%s] %s\n' "$(agora)" "$(pods_backend | tr '\n' '|')"
      sleep 0.5
    done
  ) >> "$AQUI/poll-01-${rotulo}.txt" &
  local POLL_PID=$!

  if novo=$(espera_novo_pod_ready "$antigos" 120); then
    t_ready=$(epoch_ms)
    kill "$POLL_PID" 2>/dev/null || true
    log "novo pod Ready: ${novo}"
    log "T1 (novo pod Ready) = $(agora)"
    log "RESULTADO ${rotulo}: tempo entre delete e novo pod Ready = $(seg "$t_ready" "$t_del") s"
  else
    kill "$POLL_PID" 2>/dev/null || true
    log "ERRO: nenhum pod novo ficou Ready em 120 s"
  fi
  {
    echo "---- amostragem a cada 0,5 s (NAME|READY|PHASE|RESTARTS|IP|CREATED|DELETION) ----"
    cat "$AQUI/poll-01-${rotulo}.txt"
    echo "---- fim ----"
  } | bruto

  log "condicoes do pod novo (timestamps do API server, precisao de 1 s):"
  condicoes_pod "$novo" | bruto
  log "pods do backend depois:"
  pods_backend | bruto
  log "eventos recentes do namespace:"
  eventos_recentes 20 | bruto

  # Espera o pod antigo sumir de vez para a rodada seguinte comecar limpa.
  $K wait --for=delete pod -l app.kubernetes.io/name=argus-backend --field-selector=metadata.name!="$novo" --timeout=90s >/dev/null 2>&1 || true

  encerra_k6
  encerra_watch "$AQUI/watch-01-${rotulo}.txt" "watch dos pods do backend, rodada ${rotulo}"
  log "k6 rodada ${rotulo}: $(k6_numeros)"
  log "============================================================="
  echo | bruto
}

# ---- Rodada A: 1 replica (padrao do kind) ----
$K scale deploy/argus-backend --replicas=1 >/dev/null 2>&1 || true
$K rollout status deploy/argus-backend --timeout=120s >/dev/null 2>&1 || true
executa_rodada "A-1replica" 1 label

# ---- Rodada B: 2 replicas ----
# O HPA do overlay kind tem minReplicas=1 e reduziria o Deployment de volta
# para 1 no proximo ciclo; fixar minReplicas=2 SOMENTE durante a rodada.
log "preparando rodada B: HPA minReplicas=2 e scale para 2"
cmd $K patch hpa argus-backend --type=merge -p '{"spec":{"minReplicas":2}}'
cmd $K scale deploy/argus-backend --replicas=2
cmd $K rollout status deploy/argus-backend --timeout=180s
sleep 5
ALVO="$(pods_backend_ready | head -1)"
if [ -z "$ALVO" ]; then log "ERRO: nenhum pod Ready para remover"; exit 1; fi
executa_rodada "B-2replicas" 2 "$ALVO"

log "restaurando o overlay kind: HPA minReplicas=1 e scale para 1"
cmd $K patch hpa argus-backend --type=merge -p '{"spec":{"minReplicas":1}}'
cmd $K scale deploy/argus-backend --replicas=1
cmd $K rollout status deploy/argus-backend --timeout=120s
pods_backend | bruto

{
  echo
  echo "================================================================"
  echo "RESUMO (kind local, 1 no, commit $(git -C "$RAIZ" rev-parse --short=12 HEAD))"
  grep -h 'RESULTADO A-1replica' "$EV" | tail -1 | sed 's/^\[[^]]*\] //'
  echo "  k6 rodada A (1 replica): $(jq -r '"\(.metrics.http_reqs.count) req, \(.metrics.respostas_nao_200.count // 0) falhas"' "$AQUI/k6-01-A-1replica.summary.json")"
  grep -h 'RESULTADO B-2replicas' "$EV" | tail -1 | sed 's/^\[[^]]*\] //'
  echo "  k6 rodada B (2 replicas, 1 pod removido): $(jq -r '"\(.metrics.http_reqs.count) req, \(.metrics.respostas_nao_200.count // 0) falhas"' "$AQUI/k6-01-B-2replicas.summary.json")"
  echo "================================================================"
} | bruto
