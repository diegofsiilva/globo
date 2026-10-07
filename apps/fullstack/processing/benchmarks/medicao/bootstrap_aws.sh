#!/bin/bash
# Template de inicialização da EC2 temporária; parâmetros vêm do executor.
set -euo pipefail
exec > /var/log/argus-benchmark.log 2>&1
export AWS_DEFAULT_REGION=@@REGION@@
export AWS_REGION=@@REGION@@
export AWS_PAGER=''
mkdir -p /root/.aws /work/output
printf '[profile g4]\nregion = %s\n' "$AWS_REGION" > /root/.aws/config
export AWS_PROFILE=g4

status() {
  printf '{"phase":"%s","exit_code":%s}\n' "$1" "$2" > /tmp/benchmark-status.json
  aws s3 cp /tmp/benchmark-status.json @@STATUS_URI@@ --profile g4 --quiet
}

finish() {
  code=$?
  trap - EXIT
  set +e
  aws s3 cp /work/output @@OUTPUT_URI@@ --recursive --profile g4 --quiet
  aws s3 cp /var/log/argus-benchmark.log @@LOG_URI@@ --profile g4 --quiet
  if [ "$code" -eq 0 ]; then status completed 0; else status failed "$code"; fi
  shutdown -h now
  exit "$code"
}
trap finish EXIT
# Também encerra se o controlador local perder a conexão ou as credenciais.
shutdown -h +35
status installing 0
dnf install -y -q git make tar gzip
curl -fsSL --retry 3 -o /tmp/uv.tar.gz @@UV_URL@@
printf '%s  /tmp/uv.tar.gz\n' @@UV_SHA256@@ | sha256sum -c -
tar -xzf /tmp/uv.tar.gz -C /tmp
install /tmp/uv-aarch64-unknown-linux-gnu/uv /usr/local/bin/uv
curl -fsSL --retry 3 -o /tmp/go.tar.gz @@GO_URL@@
printf '%s  /tmp/go.tar.gz\n' @@GO_SHA256@@ | sha256sum -c -
tar -xzf /tmp/go.tar.gz -C /usr/local
export PATH="/usr/local/go/bin:$PATH"
export GOCACHE=/work/go-cache
export GOMODCACHE=/work/go-mod-cache
aws s3 cp @@SOURCE_URI@@ /tmp/source.tar.gz --profile g4 --quiet
printf '%s  /tmp/source.tar.gz\n' @@SOURCE_SHA256@@ | sha256sum -c -
mkdir -p /work/source
tar -xzf /tmp/source.tar.gz -C /work/source
cd /work/source
git init -q -b codex/benchmark-aws
git add .
git -c user.name='Snapshot do benchmark' -c user.email='benchmark@localhost' \
  commit -qm 'Snapshot dos arquivos enviados para o benchmark'
cd apps/fullstack/processing
uv python install @@PYTHON_VERSION@@
uv sync --frozen --all-groups --python @@PYTHON_VERSION@@
cd ..
status validating 0
make test-processing benchmark-paridade
for round in $(seq 1 @@ROUNDS@@); do
  number=$(printf '%02d' "$round")
  status "measuring-$number" 0
  make benchmark-medir GO=/usr/local/go/bin/go \
    BENCHMARK_ARGS="--label @@LABEL@@-rodada-$number --warmups @@WARMUPS@@ --repetitions @@REPETITIONS@@ --output-dir /work/output/rodada-$number"
  aws s3 cp /work/output @@OUTPUT_URI@@ --recursive --profile g4 --quiet
done
status uploading 0
