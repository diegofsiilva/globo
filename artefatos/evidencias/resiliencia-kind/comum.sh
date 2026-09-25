# Funcoes compartilhadas pelos ensaios de resiliencia no kind.
#
# Uso: cada ensaio faz `source "$(dirname "$0")/comum.sh"` e define EV
# (arquivo de evidencia) antes de chamar `cabecalho`.
#
# Tudo o que os ensaios imprimem vai para o arquivo de evidencia via `tee -a`,
# com timestamp de milissegundo, para que a saida bruta seja o registro.

set -u

KCTX="${KCTX:-kind-argus}"
NS="${NS:-argus}"
K="kubectl --context ${KCTX} -n ${NS}"
BASE_URL="${BASE_URL:-http://localhost:8080}"
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
APP="${RAIZ}/apps/fullstack"
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

agora() { gdate '+%H:%M:%S.%3N'; }
epoch_ms() { gdate '+%s%3N'; }
# Diferenca em segundos (1 casa) entre dois instantes em ms: seg <depois> <antes>.
# Em funcao propria porque o bash 3.2 do macOS engole `$(awk "...\"%.1f\"...")`
# dentro de string com aspas duplas.
seg() { awk -v a="$1" -v b="$2" 'BEGIN{printf "%.1f", (a-b)/1000}'; }

log() { printf '[%s] %s\n' "$(agora)" "$*" | tee -a "$EV"; }
bruto() { tee -a "$EV"; }

# Executa um comando, registrando a linha de comando e a saida bruta.
cmd() {
  printf '[%s] $ %s\n' "$(agora)" "$*" | tee -a "$EV"
  "$@" 2>&1 | tee -a "$EV"
  return "${PIPESTATUS[0]}"
}

# Cabecalho padrao: data/hora, commit, cluster, imagens/digests, recursos.
cabecalho() {
  local titulo="$1"
  : > "$EV"
  {
    echo "================================================================"
    echo "$titulo"
    echo "================================================================"
    echo "data/hora (local)  : $(gdate '+%Y-%m-%d %H:%M:%S %Z')"
    echo "data/hora (UTC)    : $(gdate -u '+%Y-%m-%dT%H:%M:%SZ')"
    echo "commit             : $(git -C "$RAIZ" rev-parse HEAD)"
    echo "ambiente           : kind (local, Docker via colima), NAO e o EKS"
    echo "contexto kubectl   : ${KCTX}   namespace: ${NS}"
    echo "kind               : $(kind version)"
    echo "kubectl/k8s        : $(kubectl --context "$KCTX" version 2>/dev/null | tr '\n' ' ')"
    echo "no                 : $(kubectl --context "$KCTX" get nodes -o jsonpath='{range .items[*]}{.metadata.name} {.status.nodeInfo.kubeletVersion} {.status.nodeInfo.architecture} {.status.nodeInfo.containerRuntimeVersion}{"\n"}{end}')"
    echo "colima             : $(colima list 2>/dev/null | tail -n +2 | tr -s ' ')"
    echo "k6                 : $(k6 version 2>/dev/null | head -1)"
    echo "imagens (spec)     :"
    $K get deploy -o jsonpath='{range .items[*]}{"  "}{.metadata.name}{" -> "}{.spec.template.spec.containers[0].image}{"\n"}{end}'
    echo "imagens (imageID nos pods, digest local do containerd):"
    $K get pods -o jsonpath='{range .items[*]}{"  "}{.metadata.name}{" -> "}{.status.containerStatuses[0].imageID}{"\n"}{end}'
    echo "digests no docker da maquina:"
    docker images --digests --format '  {{.Repository}}:{{.Tag}} id={{.ID}} criada={{.CreatedSince}}' | grep -E '^  argus-' || true
    echo "backend: strategy/probes (do Deployment aplicado):"
    $K get deploy argus-backend -o jsonpath='  replicas={.spec.replicas} minReadySeconds={.spec.minReadySeconds} maxUnavailable={.spec.strategy.rollingUpdate.maxUnavailable} maxSurge={.spec.strategy.rollingUpdate.maxSurge} readiness={.spec.template.spec.containers[0].readinessProbe.httpGet.path}/{.spec.template.spec.containers[0].readinessProbe.periodSeconds}s liveness={.spec.template.spec.containers[0].livenessProbe.httpGet.path}/{.spec.template.spec.containers[0].livenessProbe.periodSeconds}s startup={.spec.template.spec.containers[0].startupProbe.httpGet.path}/{.spec.template.spec.containers[0].startupProbe.periodSeconds}s preStop={.spec.template.spec.containers[0].lifecycle.preStop.exec.command}{"\n"}'
    echo "hpa:"
    $K get hpa -o jsonpath='{range .items[*]}{"  "}{.metadata.name}{" min="}{.spec.minReplicas}{" max="}{.spec.maxReplicas}{"\n"}{end}'
    echo "estado inicial:"
    $K get pods -o wide | sed 's/^/  /'
    echo "scripts             : artefatos/evidencias/resiliencia-kind/ (este ensaio: $(basename "$0"))"
    echo "================================================================"
    echo
  } | tee -a "$EV"
}

# `kubectl get ... -w --output-watch-events` com timestamp por linha, em
# segundo plano. Grava em $2; devolve o PID em WATCH_PID.
inicia_watch() {
  local recurso="$1" arquivo="$2"
  : > "$arquivo"
  # $recurso sem aspas de proposito: pode trazer "-l selector".
  # shellcheck disable=SC2086
  $K get $recurso -w --output-watch-events 2>&1 \
    | perl "$AQUI/ts.pl" > "$arquivo" &
  WATCH_PID=$!
}

# Encerra um watch e anexa o arquivo ao registro.
encerra_watch() {
  local arquivo="$1" titulo="$2"
  # mata o kubectl (filho do subshell do pipe) e o pipe
  pkill -P "$WATCH_PID" 2>/dev/null || true
  kill "$WATCH_PID" 2>/dev/null || true
  sleep 0.3
  {
    echo
    echo "---- $titulo (kubectl get ... -w --output-watch-events, com timestamp) ----"
    cat "$arquivo"
    echo "---- fim ----"
    echo
  } | tee -a "$EV"
}

# Dispara o k6 em segundo plano. $1 = rotulo, $2 = duracao, $3 = VUs.
inicia_k6() {
  local rotulo="$1" duracao="$2" vus="$3"
  K6_OUT="$AQUI/k6-${rotulo}.stdout.txt"
  K6_JSON="$AQUI/k6-${rotulo}.summary.json"
  log "k6: ${vus} VUs por ${duracao} contra ${BASE_URL} (/api/v1/clock + /api/v1/hypotheses), resumo em $(basename "$K6_JSON")"
  BASE_URL="$BASE_URL" VUS="$vus" DURACAO="$duracao" \
    k6 run --quiet --summary-export="$K6_JSON" "$AQUI/carga_leve.js" > "$K6_OUT" 2>&1 &
  K6_PID=$!
}

# Espera o k6 terminar e anexa saida + numeros-chave.
encerra_k6() {
  wait "$K6_PID" || true
  {
    echo
    echo "---- saida do k6 ----"
    cat "$K6_OUT"
    echo "---- numeros-chave (de $(basename "$K6_JSON")) ----"
    jq -r '"http_reqs=\(.metrics.http_reqs.count) http_req_failed=\(.metrics.http_req_failed.passes // 0) (taxa=\(.metrics.http_req_failed.value)) respostas_200=\(.metrics.respostas_200.count // 0) respostas_nao_200=\(.metrics.respostas_nao_200.count // 0) p95_ms=\(.metrics.http_req_duration["p(95)"]) max_ms=\(.metrics.http_req_duration.max)"' "$K6_JSON"
    echo "---- fim ----"
    echo
  } | tee -a "$EV"
}

k6_numeros() {
  jq -r '"\(.metrics.http_reqs.count) requisicoes, \(.metrics.respostas_200.count // 0) respostas 200, \(.metrics.respostas_nao_200.count // 0) falhas (taxa \(.metrics.http_req_failed.value * 100 | . * 100 | round / 100)%), p95 \(.metrics.http_req_duration["p(95)"] | round) ms"' "$K6_JSON"
}

# Tabela compacta dos pods do backend (nome, ready, status, restarts, ip).
pods_backend() {
  $K get pods -l app.kubernetes.io/name=argus-backend \
    -o custom-columns='NAME:.metadata.name,READY:.status.conditions[?(@.type=="Ready")].status,PHASE:.status.phase,RESTARTS:.status.containerStatuses[0].restartCount,IP:.status.podIP,CREATED:.metadata.creationTimestamp,DELETION:.metadata.deletionTimestamp' --no-headers 2>/dev/null
}

# Nomes dos pods do backend prontos (Ready=True) e nao marcados para remocao,
# um por linha. O jsonpath do kubectl nao aceita filtro aninhado, por isso o
# filtro final e feito no awk.
pods_backend_ready() {
  $K get pods -l app.kubernetes.io/name=argus-backend \
    -o jsonpath='{range .items[*]}{.metadata.name}{" "}{range .status.conditions[?(@.type=="Ready")]}{.status}{end}{" "}{.metadata.deletionTimestamp}{"\n"}{end}' 2>/dev/null \
    | awk '$2=="True" && $3=="" {print $1}'
}

# Espera ate que exista um pod do backend Ready cujo nome NAO esteja em $1
# (lista separada por espaco). Imprime o nome. Timeout em $2 segundos.
espera_novo_pod_ready() {
  local antigos=" $1 " limite="$2" inicio fim nome
  inicio=$(epoch_ms)
  while :; do
    for nome in $(pods_backend_ready); do
      case "$antigos" in *" $nome "*) ;; *) echo "$nome"; return 0 ;; esac
    done
    fim=$(epoch_ms)
    if (( fim - inicio > limite * 1000 )); then return 1; fi
    sleep 0.25
  done
}

condicoes_pod() {
  local pod="$1"
  $K get pod "$pod" -o jsonpath='creationTimestamp={.metadata.creationTimestamp}{"\n"}{range .status.conditions[*]}{.type}={.status} em {.lastTransitionTime}{"\n"}{end}containerStatuses: started={.status.containerStatuses[0].state.running.startedAt} restarts={.status.containerStatuses[0].restartCount} image={.status.containerStatuses[0].image}{"\n"}'
}

eventos_recentes() {
  $K get events --sort-by=.lastTimestamp -o custom-columns='LAST:.lastTimestamp,TYPE:.type,REASON:.reason,KIND:.involvedObject.kind,OBJECT:.involvedObject.name,MESSAGE:.message' | tail -n "${1:-25}"
}

# Codigo HTTP em ate 3 s; "000" quando a conexao falha ou estoura o tempo.
http_code() { curl -s -o /dev/null -m 3 -w '%{http_code}' "$1" 2>/dev/null || true; }
