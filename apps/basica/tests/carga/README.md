# Testes de performance — RNF01, RNF02 e RNF03

Suíte k6 para medir a aplicação Argus publicada, enviar as métricas por
Prometheus Remote Write e visualizá-las no Grafana. Os scripts exigem endpoints
e tokens explícitos: uma execução sem alvo real falha no `setup()`.

## O que cada teste comprova

| Requisito | Cenário real | Critério automatizado |
|---|---|---|
| RNF01 | 1.000/min, pico de 10.000/min e recuperação em 1.000/min | sucesso, p95, eventos aceitos e zero descarte do gerador |
| RNF02 | 11 rotas × 5, 10 usuários concorrentes, filtros semânticos e 600 consultas/min | 100% HTTP 200, nenhuma resposta acima de 5 s, p99 < 5 s |
| RNF03 | mesmo contrato antes/depois de alterar tasks ECS de 1× para 2× | capacidade 2×, sucesso, p95/p99, zero descarte e persistência |
| Resiliência | consumidor parado e timeout de cliente em 1 ms | backlog cresce/drena; timeout é detectado e a consulta seguinte recupera |

O SQS Standard não tem uma capacidade fixa que possa ficar literalmente
“cheia”. O cenário tecnicamente equivalente interrompe o consumidor, confirma
o acúmulo de backlog e depois comprova a drenagem e a persistência sem perda.

## Pré-requisitos e variáveis

- Docker com acesso à imagem `grafana/k6:0.54.0`;
- endpoints atuais obtidos por `terraform output`;
- tokens Bearer atuais da implantação;
- para mudar tasks/consultar SQS e CloudWatch, perfil AWS válido do Learner Lab.

```bash
export ARGUS_INGEST_URL="$(terraform -chdir=apps/basica/infra output -raw ingest_url)"
export ARGUS_API_URL="$(terraform -chdir=apps/basica/infra output -raw read_api_url)"
export ARGUS_INGEST_TOKEN='<token atual>'
export ARGUS_READ_TOKEN='<token atual>'
```

Não inclua tokens, credenciais AWS ou URLs privadas nos resultados
versionados. Credenciais do Learner Lab expiram; valide antes de testar:

```bash
aws sts get-caller-identity --profile g4
```

## Execução

```bash
cd apps/basica

# Sobe Prometheus :9090 e Grafana :3001 e executa um requisito.
./tests/carga/executar_testes.sh rnf01 --com-grafana
./tests/carga/executar_testes.sh rnf02 --com-grafana

# RNF03 exige uma alteração real entre as duas chamadas.
RNF03_RECURSOS='1 task por worker; 256 CPU; 512 MiB' \
  ./tests/carga/executar_testes.sh rnf03-baseline --com-grafana

# Aplique worker_desired_count=2 e espere services-stable antes desta fase.
RNF03_RECURSOS='2 tasks por worker; 256 CPU; 512 MiB por task' \
  ./tests/carga/executar_testes.sh rnf03-escalado --com-grafana

# Timeout de cliente + recuperação.
./tests/carga/executar_testes.sh falha-timeout --com-grafana
```

Para o backlog, coloque `event-worker` e `merge-worker` em zero antes da carga,
registre `ApproximateNumberOfMessages`, restaure os workers e espere a fila
zerar. O teste k6 é:

```bash
./tests/carga/executar_testes.sh falha-backlog --com-grafana
```

Os JSONs e logs brutos ficam em `tests/carga/resultados/` e são ignorados pelo
Git. Cada execução recebe um `testid`, que também aparece como filtro no
dashboard.

## Prometheus e Grafana locais

```bash
make -C apps/basica observabilidade-up
make -C apps/basica observabilidade-check
```

- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3001` (`admin` / `admin` no ambiente local)
- Dashboard: **Argus — Testes de Carga (RNF01/02/03)**

O Prometheus inicia com `--web.enable-remote-write-receiver`. O executor define
`K6_PROMETHEUS_RW_SERVER_URL=http://localhost:9090/api/v1/write` e envia p50,
p90, p95 e p99. Os painéis mostram throughput, latência, erros/s, sucesso, VUs,
total de requisições, latência por rota/cenário e tráfego de rede.

Prometheus e Grafana usam os volumes nomeados `argus-prometheus-data` e
`argus-grafana-data`. Um `docker compose down` comum preserva os resultados;
`docker compose down -v` remove os volumes e apaga as métricas.

Durante um teste, o dashboard pode usar **Last 5 minutes**. Para consultar uma
execução encerrada, selecione no canto superior direito um intervalo absoluto
que inclua o horário do teste e escolha o `testid` correspondente. Uma consulta
feita apenas no instante atual fica vazia depois que as séries do k6 se tornam
inativas, mesmo que o histórico ainda esteja armazenado.

Consultas PromQL úteis:

```promql
sum(rate(k6_http_reqs_total{testid=~"$testid"}[1m]))
max by (scenario) (k6_http_req_duration_p95{testid=~"$testid"}) * 1000
sum(rate(k6_http_reqs_total{testid=~"$testid",expected_response="false"}[1m]))
```

## CPU real da AWS no mesmo Grafana

O plugin CloudWatch já vem embutido no Grafana. Para o Learner Lab, prefira um
arquivo de credenciais temporárias montado somente para leitura, com o perfil
`g4` e os três campos da sessão (`aws_access_key_id`,
`aws_secret_access_key`, `aws_session_token`). Nunca versionar esse arquivo.

1. Monte o arquivo no container como
   `/usr/share/grafana/.aws/credentials:ro` e reinicie o Grafana.
2. Em **Connections → Add new connection → CloudWatch**, use:
   `Authentication Provider = Credentials file`, `Profile = g4`,
   `Default Region = us-east-1`.
3. Clique em **Save & test**.
4. Crie um painel com `Namespace = AWS/ECS`,
   `Metric = CPUUtilization`, dimensões `ClusterName` e `ServiceName`,
   estatísticas `Average` e `Maximum`, período `1m`.
5. Para o banco, use `AWS/RDS → CPUUtilization → DBInstanceIdentifier`.

Provisionamento equivalente, sem qualquer segredo no YAML:

```yaml
apiVersion: 1
datasources:
  - name: CloudWatch
    type: cloudwatch
    jsonData:
      authType: credentials
      defaultRegion: us-east-1
      profile: g4
```

Quando a sessão do Learner Lab expirar, atualize o arquivo montado, reinicie o
container e repita **Save & test**. Em uma conta permanente, use IAM Role/
`AWS SDK Default` em vez de chaves estáticas.

## Evidência e interpretação

Aceitação HTTP não é persistência. Depois de RNF01/RNF03, registre:

1. total aceito pelo k6;
2. fila visível e em voo igual a zero;
3. diferença de `count(*)` em `bronze.event` igual ao total emitido;
4. CPU no CloudWatch no mesmo intervalo UTC.

O relatório executado em 2026-09-02 está em
[`artefatos/testes-performance.md`](../../../../artefatos/testes-performance.md).
