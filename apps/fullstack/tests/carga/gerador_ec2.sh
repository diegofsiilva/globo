#!/usr/bin/env bash
# Executa um cenario k6 a partir de uma EC2 descartavel dentro da VPC do Argus.
#
# Por que nao rodar da maquina de desenvolvimento: carga sustentada saindo de um
# IP residencial contra um endpoint da AWS parece ataque, e contas de laboratorio
# ja foram suspensas por isso. Saindo de uma instancia da propria conta, o
# trafego e interno a AWS e a origem e identificavel.
#
# A instancia nasce, instala o k6, baixa os roteiros do bucket de origem, le o
# token de um parametro SSM criptografado, roda o cenario, devolve os resultados
# ao bucket e se desliga -- com `terminate` no desligamento, para nao sobrar
# nada ligado. Este script espera o resultado aparecer no bucket, baixa para
# `resultados/` e apaga o parametro, o prefixo no bucket e, por garantia, a
# instancia.
#
# Uso: gerador_ec2.sh [carga-ui]
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
  *) echo "Uso: $0 [carga-ui]"; exit 2 ;;
esac

# Igual ao executar_testes.sh: o que esta exportado no terminal vence o .env.
declare -A EXPLICITAS=()
for nome in ARGUS_API_URL ARGUS_READ_TOKEN AWS_PROFILE AWS_REGION; do
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
NOME="argus-gerador-carga-$TEST_ID"
INSTANCIA_ID=""

limpar() {
  echo
  echo "Limpando: parametro SSM, prefixo s3://$BUCKET/$PREFIXO e a instancia."
  "${AWS[@]}" ssm delete-parameter --name "$PARAMETRO" >/dev/null 2>&1 || true
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
"${AWS[@]}" ssm put-parameter --name "$PARAMETRO" --type SecureString --value "$ARGUS_READ_TOKEN" --overwrite >/dev/null

# 2. Security group so de saida: nada entra na instancia, nem SSH.
SG_ID="$("${AWS[@]}" ec2 create-security-group --group-name "$NOME" \
  --description "gerador de carga k6, descartavel" --vpc-id "$VPC_ID" \
  --query GroupId --output text)"

# 3. AMI: Amazon Linux 2023 arm64 pelo parametro publico, como o bastion faz.
AMI="$("${AWS[@]}" ssm get-parameter \
  --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64 \
  --query Parameter.Value --output text)"

# 4. user_data: instala, roda, devolve, desliga. As variaveis CARGA_UI_* do
#    terminal seguem para a instancia, para que preflight e rodada oficial usem
#    o mesmo caminho.
ENV_K6=""
for v in CARGA_UI_VUS_1 CARGA_UI_VUS_2 CARGA_UI_VUS_3 CARGA_UI_DURACAO CARGA_UI_PAUSA CARGA_UI_PENSAR_S; do
  if [[ -v "$v" ]]; then ENV_K6+="export $v='${!v}'"$'\n'; fi
done
USER_DATA="$(cat <<EOF
#!/bin/bash
set -uxo pipefail
exec > /var/log/carga.log 2>&1
dnf install -y -q tar gzip
curl -fsSL -o /tmp/k6.tgz "https://github.com/grafana/k6/releases/download/v${K6_VERSAO}/k6-v${K6_VERSAO}-linux-arm64.tar.gz"
tar -xzf /tmp/k6.tgz -C /tmp && install "/tmp/k6-v${K6_VERSAO}-linux-arm64/k6" /usr/local/bin/k6
mkdir -p /work/resultados && cd /work
aws s3 cp "s3://$BUCKET/$PREFIXO/scripts/" /work/ --recursive --quiet
export ARGUS_API_URL='$ARGUS_API_URL'
# O \`set -x\` da linha acima imprime cada comando JA EXPANDIDO em /var/log/carga.log,
# que este script baixa para resultados/. Sem desligar o rastreamento aqui, o token
# recuperado do SSM aparece em texto claro no log -- o que anula o motivo de ele vir
# de um SecureString em vez de viajar no user_data.
set +x
export ARGUS_READ_TOKEN="\$(aws ssm get-parameter --name '$PARAMETRO' --with-decryption --query Parameter.Value --output text)"
set -x
export K6_TEST_ID='$TEST_ID'
export K6_RESULT_FILE='resultados/${CENARIO}_resultado.json'
$ENV_K6
k6 run --tag "testid=$TEST_ID" --tag "requisito=$CENARIO" --tag origem=ec2 \\
  --summary-export="resultados/${CENARIO}_summary.json" "$SCRIPT" \\
  > "resultados/${CENARIO}_output.txt" 2>&1
echo "k6 exit \$?" >> "resultados/${CENARIO}_output.txt"
aws s3 cp /work/resultados "s3://$BUCKET/$PREFIXO/resultados/" --recursive --quiet
aws s3 cp /var/log/carga.log "s3://$BUCKET/$PREFIXO/resultados/carga.log" --quiet
shutdown -h now
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

# 5. Espera. Boot + instalacao levam ~2 min; o cenario padrao, 7,5 min.
LIMITE_S="${CARGA_EC2_TIMEOUT_S:-1500}"
inicio=$(date +%s)
until "${AWS[@]}" s3 ls "s3://$BUCKET/$PREFIXO/resultados/${CENARIO}_output.txt" >/dev/null 2>&1; do
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
for arq in output.txt summary.json resultado.json; do
  "${AWS[@]}" s3 cp "s3://$BUCKET/$PREFIXO/resultados/${CENARIO}_${arq}" \
    "$RESULTADOS/${CENARIO}-ec2_${arq%%.*}_${instante}.${arq##*.}" --quiet
done
"${AWS[@]}" s3 cp "s3://$BUCKET/$PREFIXO/resultados/carga.log" "$RESULTADOS/${CENARIO}-ec2_instancia_${instante}.log" --quiet || true

echo "Resultados em $RESULTADOS/${CENARIO}-ec2_*_${instante}.*"
grep -E '^k6 exit' "$RESULTADOS/${CENARIO}-ec2_output_${instante}.txt" || true
