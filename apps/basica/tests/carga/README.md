# Testes de performance — lotes, RNF01, RNF02 e RNF03

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

## RNF01 revisado: lote de 150 mil eventos

O requisito de 10.000 eventos/min em ciclos de 15 minutos equivale a um lote
logico de 150.000 eventos. O endpoint aceita arrays, mas cada corpo HTTP vira
uma mensagem SQS; por isso `rnf01_lote_drenagem.js` fragmenta o lote pelo
tamanho serializado, com teto conservador de 240.000 bytes por mensagem.

O k6 mede aceite, latencia e vazao HTTP. Ele nao declara drenagem: resposta 2xx
prova apenas que o fragmento entrou na fila. Depois da injecao, a evidencia
precisa combinar fila principal, mensagens em voo, DLQ, persistencia e
disponibilidade do evento sentinela na API de leitura.

```bash
# Um lote: 150.000 eventos.
make -C apps/basica teste-lote-drenagem COM_GRAFANA=1

# Acumulo: execute com event-worker parado e escolha 2, 3 ou 4 lotes.
make -C apps/basica teste-lotes-acumulados LOTES=2 COM_GRAFANA=1
```

Cada rodada escreve no resumo o `test_id`, os horarios da injecao e a
`sentinela_session_id`. Para o cenario acumulado, pare apenas o `event-worker`,
confirme que ele chegou a zero, injete a carga, registre a fila e restaure a
mesma quantidade de tasks que existia antes do teste. Nao use `make pause`,
pois ele tambem interrompe processamento e outros servicos.

Durante a drenagem, registre a cada cinco segundos:

```bash
aws sqs get-queue-attributes --profile g4 --region us-east-1 \
  --queue-url "$(terraform -chdir=apps/basica/infra output -raw queue_url)" \
  --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible
```

A profundidade SQS conta fragmentos, nao eventos. A contagem exata e o frescor
em `bronze.event` saem de `tools/loadtest/drenagem_lotes.sql`. O evento final
de cada execucao usa a sessao sentinela e deve ser consultado ate aparecer:

```bash
curl -fsS -H "Authorization: Bearer $ARGUS_READ_TOKEN" \
  "$ARGUS_API_URL/api/v1/sessions/<sentinela_session_id>"
```

Definicoes usadas no relatorio:

- tempo de injecao: primeiro envio ate o aceite do ultimo fragmento;
- tempo de drenagem: aceite do ultimo fragmento ate persistencia completa;
- vazao de drenagem: eventos persistidos divididos pelo tempo de drenagem;
- frescor ponta a ponta: geracao ate primeira disponibilidade na API;
- capacidade minima sustentavel: mais de 166,67 eventos/s.

Como criterio operacional proposto, ate 7min30s e aprovado, entre 7min30s e
15 minutos exige atencao, e 15 minutos ou mais reprova. A margem deve ser
confirmada com o responsavel pelo requisito antes da execucao real.

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
make teste-performance CENARIO=rnf01 COM_GRAFANA=1
make teste-performance CENARIO=rnf02 COM_GRAFANA=1

# RNF03 exige uma alteração real entre as duas chamadas.
RNF03_RECURSOS='1 task por worker; 256 CPU; 512 MiB' \
  make teste-performance CENARIO=rnf03-baseline COM_GRAFANA=1

# Aplique worker_desired_count=2 e espere services-stable antes desta fase.
RNF03_RECURSOS='2 tasks por worker; 256 CPU; 512 MiB por task' \
  make teste-performance CENARIO=rnf03-escalado COM_GRAFANA=1

# Timeout de cliente + recuperação.
make teste-performance CENARIO=falha-timeout COM_GRAFANA=1
```

Para o backlog, coloque `event-worker` e `merge-worker` em zero antes da carga,
registre `ApproximateNumberOfMessages`, restaure os workers e espere a fila
zerar. O teste k6 é:

```bash
make teste-performance CENARIO=falha-backlog COM_GRAFANA=1
```

Os JSONs e logs brutos ficam em `tests/carga/resultados/` e são ignorados pelo
Git. Cada execução recebe um `testid`, que também aparece como filtro no
dashboard.

## Prometheus e Grafana locais

O Grafana desta suíte é o mesmo usado pelos testes de resiliência (RNF04/05/11):
uma única stack local, com CloudWatch e Prometheus já provisionados como
datasource.

```bash
make -C apps/basica observabilidade-up
make -C apps/basica observabilidade-check
```

- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3001` (`admin` / `admin`, ou acesso anônimo de
  leitura), acessível só pela própria máquina (bind em `127.0.0.1`)
- Dashboards disponíveis: **Argus — Testes de Carga (RNF01/02/03)** e
  **RNF04/05/11 - Resiliencia Argus**

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

O datasource CloudWatch já vem provisionado (perfil `g4`, sem chave estática
no YAML) junto com o `make observabilidade-up`. Quando o perfil existe, o
Makefile extrai só o bloco `[g4]` de `~/.aws/credentials` para um arquivo
temporário, monta esse arquivo read-only no container e nunca versiona nada
disso. Sem o perfil, a stack ainda sobe para os testes k6; apenas as consultas
CloudWatch ficam sem autenticação. Crie um painel com
`Namespace = AWS/ECS`, `Metric = CPUUtilization`, dimensões `ClusterName` e
`ServiceName`, estatísticas `Average` e `Maximum`, período `1m`; para o banco,
`AWS/RDS → CPUUtilization → DBInstanceIdentifier`.

Quando a sessão do Learner Lab expirar, rode `make -C apps/basica
observabilidade-up` de novo para recriar o container com a credencial
renovada.

## Evidência e interpretação

Aceitação HTTP não é persistência. Depois de RNF01/RNF03, registre:

1. total aceito pelo k6;
2. fila visível e em voo igual a zero;
3. diferença de `count(*)` em `bronze.event` igual ao total emitido;
4. CPU no CloudWatch no mesmo intervalo UTC.

O relatório unificado da execução está em
[`artefatos/testes-carga-inicial.md`](../../../../artefatos/testes-carga-inicial.md),
incluindo carga, resiliência e observabilidade de RNF01–RNF05 e RNF11.
