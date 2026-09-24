# Teste de hipótese por ingestão CDC

Este roteiro exercita `POST /v1/changes` → `bronze.change_log` →
`silver.analysis_fact_version` → checkpoint Gold → detector →
`gold.hypothesis`. Eventos de TV enviados a `/v1/events` percorrem outro
caminho e não são a entrada direta deste experimento.

## Preparação

O lab precisa ter `merge-worker` e `processing` ativos, simulador parado,
RDS acessível e as migrations aplicadas. Configure `DATABASE_URL`,
`ARGUS_CHANGES_URL` e `ARGUS_INGEST_TOKEN` no ambiente local. Os valores não
entram no repositório. `DATABASE_URL` deve apontar ao **RDS atual**, por meio
do bastion quando necessário; não reutilize o endpoint de um lab antigo.

Escolha um caminho absoluto fora de `g04` para o arquivo do lote:

```bash
make -C apps/basica hypothesis-batch-prepare BATCH_FILE=/caminho/externo/lote.json
```

O comando lê `sim.now()` e o maior LSN do banco, grava o payload e um
`lote.manifest.json`, e **não envia dados**. Revise os dois arquivos. O lote
contém 52 mudanças em `signal_bucket`: 12 amostras normais e uma atual para
cada série de Prometheus e Apollo, em uma entidade incidente e uma de controle.
O incidente termina em 15% de erros; o controle, em 1%. As 12 amostras
anteriores são de três dias, na mesma hora de São Paulo, com cadência de 15
minutos. O identificador novo evita misturar o experimento com o dump.

## Envio e acompanhamento

```bash
make -C apps/basica hypothesis-batch-send BATCH_FILE=/caminho/externo/lote.json
make -C apps/basica hypothesis-batch-verify BATCH_FILE=/caminho/externo/lote.json
```

O envio faz um POST e grava `lote.sent.json` após HTTP 2xx. Esse status só
confirma a entrada na fila. Se houver timeout, consulte Bronze antes de
tentar qualquer novo envio. Um recibo existente bloqueia reenvio acidental.

Repita `hypothesis-batch-verify` enquanto o ETL avança. O comando retorna 2
enquanto falta alguma etapa e 0 quando todas as condições passam. O intervalo
padrão de Silver para Gold é 15 minutos. A verificação exige:

1. 52 mudanças do identificador em Bronze e 52 versões de fato em Silver;
2. watermark Bronze→Silver e checkpoint Gold que incluam o maior LSN;
3. run de análise concluído, sem truncamento, contendo os fatos do lote;
4. ao menos duas anomalias na entidade incidente e nenhuma no controle;
5. hipótese `backend_internal` com status `generated`, score ≥ 40 e cobertura
   ≥ 0,5, ligada por evidências favoráveis de Prometheus e Apollo aos LSNs do
   lote, e nenhuma hipótese ligada ao controle.

Não avance o watermark manualmente: todas as mudanças deste lote são novas e
estão depois do LSN do dump. Hipóteses `generated` de runs concluídos passam
automaticamente para a API e a tela após as migrations 032 e 033, respeitando
`sim.now()` e o período selecionado. A promoção do manifesto continua sendo
um registro auditável separado. Um fracasso em uma etapa deve ser investigado
nessa etapa antes de gerar outro lote com identificador novo.

## Execução no lab de 23/09/2026

O lote `lab-hyp-c201acfb6acf` passou por Bronze (52 mudanças), Silver (52
fatos) e checkpoint Gold 149, cujo `source_lsn` foi 137435709. O run 149
terminou sem truncamento. Foram detectadas duas anomalias no incidente e zero
no controle. A hipótese 2951, da família `backend_internal`, ficou como
`generated`, com score 94,64 e cobertura 0,8125. As duas evidências favoráveis
referenciam versões do lote, uma de Prometheus e outra de Apollo. A view
`gold.v_hypothesis` permaneceu vazia na execução original, quando o modo
sombra ainda estava ativo. Após as migrations 032 e 033, a hipótese é visível sem
publicação manual. O payload, o manifesto, o recibo e a verificação
ficam em `projeto/evidencias/hipoteses/`, fora do repositório.

## Visualizar as hipóteses no frontend do lab

A migration `031_lab_hypothesis_preview.sql` foi o caminho temporário usado
para inspecionar a hipótese 2951. A migration 032 remove a exigência de
prévia e publicação das views; a 033 mantém também as revisões anteriores.
Toda revisão com status `generated` e run concluído fica disponível pela API.
O frontend busca automaticamente as páginas adicionais da janela selecionada.
Para publicar a versão atual do frontend:

```bash
make -C apps/basica frontend-deploy NEXT_BUILD_ARGS=--webpack
```

O frontend precisa estar configurado com `HYPOTHESES_SOURCE=api` no `.env`
local ignorado pelo Git. Na tela `/hipoteses`, selecione **24 h** no período:
o evento de teste ocorreu mais de 30 minutos antes da publicação da prévia.
O detalhe apresenta o score, os fatores e as evidências de Apollo e
Prometheus. Os eventos históricos `preview` e `withdrawn` continuam no banco
para auditoria, mas não ocultam hipóteses geradas.
