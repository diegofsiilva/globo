#!/usr/bin/env bash
# Executa um cenario k6 a partir de uma EC2 descartavel dentro da VPC do Argus.
#
# A EC2 padroniza os recursos do gerador e reduz a dependencia da rede local
# nas comparacoes entre rodadas. O destino e a intensidade continuam definidos
# pelo operador para o ambiente de teste autorizado.
#
# A instancia nasce, instala k6, Prometheus e Grafana, baixa os roteiros e o
# dashboard do bucket de origem, le o token de um parametro SSM criptografado,
# roda o cenario, devolve os resultados ao bucket e se desliga -- com
# `terminate` no desligamento, para nao sobrar nada ligado. Durante a rodada, o
# operador pode abrir um tunel SSM para o Grafana, sem portas de entrada.
#
# Uso: gerador_ec2.sh [carga-ui|rnf01-acumulo]
# Le ARGUS_API_URL do .env e ARGUS_READ_TOKEN do ambiente (ou do .env).

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP="$DIR/../.."
INFRA="$APP/infra"
ENV_FILE="$APP/.env"
RESULTADOS="$DIR/resultados"
CENARIO="${1:-carga-ui}"

case "$CENARIO" in
  carga-ui) SCRIPT="carga_ui.js" ;;
  rnf01-acumulo) SCRIPT="rnf01_lote_drenagem.js" ;;
  *) echo "Uso: $0 [carga-ui|rnf01-acumulo]"; exit 2 ;;
esac

# Igual ao executar_testes.sh: o que esta exportado no terminal vence o .env.
declare -A EXPLICITAS=()
for nome in ARGUS_API_URL ARGUS_READ_TOKEN ARGUS_INGEST_URL ARGUS_INGEST_TOKEN AWS_PROFILE AWS_REGION; do
  if [[ -v "$nome" ]]; then EXPLICITAS["$nome"]="${!nome}"; fi
done
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi
for nome in "${!EXPLICITAS[@]}"; do
  printf -v "$nome" '%s' "${EXPLICITAS[$nome]}"
  export "$nome"
done

: "${AWS_PROFILE:?AWS_PROFILE e obrigatorio (profile g4 do Learner Lab)}"
: "${AWS_REGION:=us-east-1}"
: "${ARGUS_API_URL:?ARGUS_API_URL e obrigatorio (make env)}"
: "${ARGUS_READ_TOKEN:?ARGUS_READ_TOKEN e obrigatorio}"
if [ "$CENARIO" = rnf01-acumulo ]; then
  : "${ARGUS_INGEST_URL:?ARGUS_INGEST_URL e obrigatoria}"
  : "${ARGUS_INGEST_TOKEN:?ARGUS_INGEST_TOKEN e obrigatorio}"
fi
export AWS_REGION

AWS=(aws --profile "$AWS_PROFILE" --region "$AWS_REGION")
TEST_ID="${K6_TEST_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
INSTANCIA_TIPO="${CARGA_EC2_TIPO:-t4g.small}"
K6_VERSAO="0.54.0"

tf_out() { (cd "$INFRA" && terraform output -raw "$1"); }
BUCKET="$(tf_out origem_bucket)"
VPC_ID="$(tf_out vpc_id)"
SUBNET_ID="$(cd "$INFRA" && terraform output -json public_subnet_ids | python3 -c 'import json,sys; print(json.load(sys.stdin)[0])')"
# Instance profile da EC2 descartavel. No Learner Lab e o LabInstanceProfile,
# que ja existe na conta (iam:CreateRole e negado); fora dele, exporte
# CARGA_EC2_PERFIL com um profile que leia o bucket e o parametro SSM.
PERFIL_INSTANCIA="${CARGA_EC2_PERFIL:-LabInstanceProfile}"

PREFIXO="carga/$TEST_ID"
PARAMETRO="/argus/carga/$TEST_ID/read-token"
PARAMETRO_INGESTAO="/argus/carga/$TEST_ID/ingest-token"
NOME="argus-gerador-carga-$TEST_ID"
INSTANCIA_ID=""

limpar() {
  echo
  echo "Limpando: parametro SSM, prefixo s3://$BUCKET/$PREFIXO e a instancia."
  "${AWS[@]}" ssm delete-parameter --name "$PARAMETRO" >/dev/null 2>&1 || true
  if [ "$CENARIO" = rnf01-acumulo ]; then
    "${AWS[@]}" ssm delete-parameter --name "$PARAMETRO_INGESTAO" >/dev/null 2>&1 || true
  fi
  "${AWS[@]}" s3 rm "s3://$BUCKET/$PREFIXO" --recursive --quiet >/dev/null 2>&1 || true
  if [ -n "$INSTANCIA_ID" ]; then
    "${AWS[@]}" ec2 terminate-instances --instance-ids "$INSTANCIA_ID" >/dev/null 2>&1 || true
    # O security group so pode ser apagado depois que a instancia sumiu.
    "${AWS[@]}" ec2 wait instance-terminated --instance-ids "$INSTANCIA_ID" >/dev/null 2>&1 || true
  fi
  [ -n "${SG_ID:-}" ] && "${AWS[@]}" ec2 delete-security-group --group-id "$SG_ID" >/dev/null 2>&1 || true
}
trap limpar EXIT

echo "Gerador de carga: $NOME ($INSTANCIA_TIPO), cenario $CENARIO"

# 1. Roteiros e token.
"${AWS[@]}" s3 cp "$DIR/helpers.js" "s3://$BUCKET/$PREFIXO/scripts/helpers.js" --quiet
"${AWS[@]}" s3 cp "$DIR/$SCRIPT" "s3://$BUCKET/$PREFIXO/scripts/$SCRIPT" --quiet
"${AWS[@]}" s3 cp "$APP/observability/prometheus.yml" "s3://$BUCKET/$PREFIXO/scripts/observability/prometheus.yml" --quiet
"${AWS[@]}" s3 cp "$APP/observability/grafana/dashboards/argus-k6.json" \
  "s3://$BUCKET/$PREFIXO/scripts/observability/grafana/dashboards/argus-k6.json" --quiet
"${AWS[@]}" s3 cp "$APP/observability/grafana/provisioning/dashboards/dashboards.yaml" \
  "s3://$BUCKET/$PREFIXO/scripts/observability/grafana/provisioning/dashboards/dashboards.yaml" --quiet
"${AWS[@]}" s3 cp "$APP/observability/grafana/provisioning/datasources/prometheus.yaml" \
  "s3://$BUCKET/$PREFIXO/scripts/observability/grafana/provisioning/datasources/prometheus.yaml" --quiet
"${AWS[@]}" ssm put-parameter --name "$PARAMETRO" --type SecureString --value "$ARGUS_READ_TOKEN" --overwrite >/dev/null
if [ "$CENARIO" = rnf01-acumulo ]; then
  "${AWS[@]}" ssm put-parameter --name "$PARAMETRO_INGESTAO" --type SecureString --value "$ARGUS_INGEST_TOKEN" --overwrite >/dev/null
fi

# 2. Security group so de saida: nada entra na instancia, nem SSH.
SG_ID="$("${AWS[@]}" ec2 create-security-group --group-name "$NOME" \
  --description "gerador de carga k6, descartavel" --vpc-id "$VPC_ID" \
  --query GroupId --output text)"

# 3. AMI: Amazon Linux 2023 arm64 pelo parametro publico, como o bastion faz.
AMI="$("${AWS[@]}" ssm get-parameter \
  --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64 \
  --query Parameter.Value --output text)"

# 4. user_data: instala, sobe observabilidade local na instancia, roda, devolve,
#    desliga. As variaveis CARGA_UI_* do terminal seguem para a instancia, para
#    que preflight e rodada oficial usem o mesmo caminho.
ENV_K6=""
for v in CARGA_UI_VUS_1 CARGA_UI_VUS_2 CARGA_UI_VUS_3 CARGA_UI_DURACAO CARGA_UI_PAUSA CARGA_UI_PENSAR_S K6_QUANTIDADE_LOTES K6_EVENTOS_POR_LOTE K6_VUS_INJECAO K6_MAX_BODY_BYTES; do
  if [[ -v "$v" ]]; then ENV_K6+="export $v='${!v}'"$'\n'; fi
done
ENV_INGESTAO=""
if [ "$CENARIO" = rnf01-acumulo ]; then
  ENV_INGESTAO="$(cat <<EOF
export ARGUS_INGEST_URL='$ARGUS_INGEST_URL'
ARGUS_INGEST_TOKEN="\$(aws ssm get-parameter --name '$PARAMETRO_INGESTAO' --with-decryption --query Parameter.Value --output text)"
export ARGUS_INGEST_TOKEN
EOF
)"
fi
USER_DATA="$(cat <<EOF
#!/bin/bash
set -euxo pipefail
exec > /var/log/carga.log 2>&1
mkdir -p /work/resultados
# Publica o marcador por ultimo, inclusive quando a preparacao falha, para que
# o operador receba o diagnostico sem esperar o timeout da rodada.
finalizar() {
  status=\$?
  trap - EXIT
  set +ex
  if [ ! -f /work/resultados/${CENARIO}_output.txt ]; then
    printf 'Falha na preparacao da EC2 (codigo %s). Consulte o log da instancia.\n' "\$status" > /work/resultados/${CENARIO}_output.txt
  fi
  aws s3 cp /work/resultados "s3://$BUCKET/$PREFIXO/resultados/" --recursive --quiet
  aws s3 cp /var/log/carga.log "s3://$BUCKET/$PREFIXO/resultados/carga.log" --quiet
  printf '%s\n' "\$status" | aws s3 cp - "s3://$BUCKET/$PREFIXO/resultados/finalizado.txt" --quiet
  shutdown -h now
  exit "\$status"
}
trap finalizar EXIT
# A AMI ja traz curl-minimal; instalar curl junto causa conflito e impede Docker.
dnf install -y -q tar gzip docker
command -v curl >/dev/null
systemctl enable --now docker
curl -fsSL -o /tmp/k6.tgz "https://github.com/grafana/k6/releases/download/v${K6_VERSAO}/k6-v${K6_VERSAO}-linux-arm64.tar.gz"
tar -xzf /tmp/k6.tgz -C /tmp
install "/tmp/k6-v${K6_VERSAO}-linux-arm64/k6" /usr/local/bin/k6
cd /work
aws s3 cp "s3://$BUCKET/$PREFIXO/scripts/" /work/ --recursive --quiet
docker network create argus-observability
docker volume create argus-prometheus-data
docker run -d --name argus-prometheus --restart unless-stopped \\
  --network argus-observability --network-alias prometheus \\
  -p 127.0.0.1:9090:9090 \\
  -v /work/observability/prometheus.yml:/etc/prometheus/prometheus.yml:ro \\
  -v argus-prometheus-data:/prometheus \\
  prom/prometheus:v2.53.0 \\
  --config.file=/etc/prometheus/prometheus.yml \\
  --web.enable-remote-write-receiver --storage.tsdb.retention.time=1d
for tentativa in {1..30}; do
  curl -fsS http://127.0.0.1:9090/-/ready >/dev/null && break
  sleep 2
done
curl -fsS http://127.0.0.1:9090/-/ready >/dev/null
docker run -d --name argus-grafana --restart unless-stopped \\
  --network argus-observability -p 127.0.0.1:3000:3000 \\
  -e GF_AUTH_ANONYMOUS_ENABLED=true -e GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer \\
  -e GF_SECURITY_ADMIN_USER=admin -e GF_SECURITY_ADMIN_PASSWORD=admin \\
  -v /work/observability/grafana/provisioning/datasources/prometheus.yaml:/etc/grafana/provisioning/datasources/prometheus.yaml:ro \\
  -v /work/observability/grafana/provisioning/dashboards/dashboards.yaml:/etc/grafana/provisioning/dashboards/dashboards.yaml:ro \\
  -v /work/observability/grafana/dashboards/argus-k6.json:/var/lib/grafana/dashboards/argus-k6.json:ro \\
  grafana/grafana:11.2.0
for tentativa in {1..30}; do
  curl -fsS http://127.0.0.1:3000/api/health >/dev/null && break
  sleep 2
done
curl -fsS http://127.0.0.1:3000/api/health >/dev/null
export ARGUS_API_URL='$ARGUS_API_URL'
# O \`set -x\` da linha acima imprime cada comando JA EXPANDIDO em /var/log/carga.log,
# que este script baixa para resultados/. Sem desligar o rastreamento aqui, o token
# recuperado do SSM aparece em texto claro no log -- o que anula o motivo de ele vir
# de um SecureString em vez de viajar no user_data.
set +x
ARGUS_READ_TOKEN="\$(aws ssm get-parameter --name '$PARAMETRO' --with-decryption --query Parameter.Value --output text)"
export ARGUS_READ_TOKEN
$ENV_INGESTAO
set -x
export K6_TEST_ID='$TEST_ID'
export K6_RESULT_FILE='resultados/${CENARIO}_resultado.json'
export K6_PROMETHEUS_RW_SERVER_URL='http://localhost:9090/api/v1/write'
export K6_PROMETHEUS_RW_TREND_STATS='p(50),p(90),p(95),p(99),min,max,avg,count'
$ENV_K6
if k6 run -o experimental-prometheus-rw --tag "testid=$TEST_ID" --tag "requisito=$CENARIO" --tag origem=ec2 \\
  --summary-export="resultados/${CENARIO}_summary.json" "$SCRIPT" \\
  > "resultados/${CENARIO}_output.txt" 2>&1; then
  K6_STATUS=0
else
  K6_STATUS=\$?
fi
echo "k6 exit \$K6_STATUS" >> "resultados/${CENARIO}_output.txt"
exit "\$K6_STATUS"
EOF
)"

INSTANCIA_ID="$("${AWS[@]}" ec2 run-instances \
  --image-id "$AMI" --instance-type "$INSTANCIA_TIPO" \
  --subnet-id "$SUBNET_ID" --security-group-ids "$SG_ID" \
  --iam-instance-profile "Name=$PERFIL_INSTANCIA" \
  --instance-initiated-shutdown-behavior terminate \
  --metadata-options HttpTokens=required \
  --user-data "$USER_DATA" \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NOME},{Key=Projeto,Value=argus},{Key=Papel,Value=gerador-carga}]" \
  --query 'Instances[0].InstanceId' --output text)"
echo "Instancia $INSTANCIA_ID lancada; aguardando o resultado em s3://$BUCKET/$PREFIXO/resultados/"
echo "Grafana ao vivo: em OUTRO terminal, execute:"
echo "  aws --profile $AWS_PROFILE --region $AWS_REGION ssm start-session --target $INSTANCIA_ID --document-name AWS-StartPortForwardingSession --parameters '{\"portNumber\":[\"3000\"],\"localPortNumber\":[\"13001\"]}'"
echo "Depois abra http://localhost:13001 e escolha o dashboard 'Argus — Testes de Carga (RNF01/02/03)'."

# 5. Espera. Boot + instalacao levam ~2 min; o cenario padrao, 7,5 min.
LIMITE_S="${CARGA_EC2_TIMEOUT_S:-1500}"
inicio=$(date +%s)
until "${AWS[@]}" s3 ls "s3://$BUCKET/$PREFIXO/resultados/finalizado.txt" >/dev/null 2>&1; do
  agora=$(date +%s)
  if [ $((agora - inicio)) -ge "$LIMITE_S" ]; then
    echo "Tempo esgotado ($LIMITE_S s) sem resultado. Log parcial, se houver:"
    "${AWS[@]}" s3 cp "s3://$BUCKET/$PREFIXO/resultados/carga.log" - 2>/dev/null | tail -20 || true
    exit 1
  fi
  estado="$("${AWS[@]}" ec2 describe-instances --instance-ids "$INSTANCIA_ID" --query 'Reservations[0].Instances[0].State.Name' --output text 2>/dev/null || echo desconhecido)"
  printf '\r  %4ds  instancia: %-12s' "$((agora - inicio))" "$estado"
  sleep 20
done
echo

# 6. Baixa com o mesmo padrao de nome do executar_testes.sh.
mkdir -p "$RESULTADOS"
instante="$(date -u +%Y%m%dT%H%M%SZ)"
"${AWS[@]}" s3 cp "s3://$BUCKET/$PREFIXO/resultados/${CENARIO}_output.txt" \
  "$RESULTADOS/${CENARIO}-ec2_output_${instante}.txt" --quiet
"${AWS[@]}" s3 cp "s3://$BUCKET/$PREFIXO/resultados/carga.log" \
  "$RESULTADOS/${CENARIO}-ec2_instancia_${instante}.log" --quiet || true
for arq in summary.json resultado.json; do
  # Uma falha de preparacao nao produz relatorio do k6.
  "${AWS[@]}" s3 ls "s3://$BUCKET/$PREFIXO/resultados/${CENARIO}_${arq}" >/dev/null 2>&1 || continue
  "${AWS[@]}" s3 cp "s3://$BUCKET/$PREFIXO/resultados/${CENARIO}_${arq}" \
    "$RESULTADOS/${CENARIO}-ec2_${arq%%.*}_${instante}.${arq##*.}" --quiet
done

echo "Resultados em $RESULTADOS/${CENARIO}-ec2_*_${instante}.*"
grep -E '^k6 exit' "$RESULTADOS/${CENARIO}-ec2_output_${instante}.txt" || true
status="$("${AWS[@]}" s3 cp "s3://$BUCKET/$PREFIXO/resultados/finalizado.txt" - --quiet)"
if [ "$status" != 0 ]; then
  echo "A rodada falhou (codigo $status). Consulte os arquivos output e instancia."
fi
exit "$status"
