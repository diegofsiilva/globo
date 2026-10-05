# Ingestão por arquivos

A imagem `worker` mantém os modos SQS `event`/`merge` e acrescenta `file-api`
e `file-worker`. O primeiro recebe o original por multipart, o segundo valida
o arquivo completo e grava eventos em `bronze.event` pelo contrato compartilhado
`keys.build_row`. A API de leitura continua sem gravação ou dependência AWS.

## Execução local

1. Prepare o banco com `make -C apps/fullstack db-ensure` (migration 034).
2. Configure `DASHBOARD_TOKEN_SHA256` com o SHA-256 da credencial do painel;
   o envio reutiliza a sessão existente, sem token adicional na página.
   Na AWS, `make auth-rotate` e `make k8s-secret` já atendem
   geração e distribuição dos hashes.
3. Inicie `make -C apps/fullstack file-api` e, em outro terminal,
   `make -C apps/fullstack file-worker`. Ambos usam `DATABASE_URL`, com o banco
   local como padrão; a API escuta na porta 5002.
4. Abra `/ingestao/` na sessão do painel, selecione arquivo, abra a prévia,
   revise as colunas, valide a amostra e pressione “Enviar arquivo”.

O frontend estático usa a mesma origem por padrão. Para desenvolver em portas
diferentes, configure `NEXT_PUBLIC_INGEST_API_URL` antes do build e permita a
origem do frontend em `INGEST_CORS_ORIGINS` no serviço de arquivos. Em Kubernetes,
o Ingress serve `/ingestion` na origem do dashboard; não exige CORS.
No Windows, recipes POSIX podem usar `SHELL="C:/Program Files/Git/bin/bash.exe"`.

## Contrato e limites

- `GET /ingestion/v1/session`: verifica a sessão existente do painel.
- `POST /ingestion/v1/files`: multipart com `file`, `mapping` (JSON de campo
  de destino para nome da coluna) e `delimiter` opcional; retorna 202 e protocolo.
- `GET /ingestion/v1/jobs/{id}`: estado, total, inseridos, duplicados, rejeitados
  e até cem motivos sanitizados. Conteúdo e credenciais não são retornados.
- `POST /ingestion/v1/jobs/{id}/retry`: retoma falha transitória com bytes retidos.
- `GET /ingestion/openapi.json`: contrato completo, autenticado.
- `/ingestion/live`: vida do processo; `/ingestion/health`: prontidão do banco.

CSV UTF-8/BOM e Parquet, até 50 MiB, 100.000 registros e 64 colunas únicas.
Separadores CSV: vírgula, ponto e vírgula, tabulação e barra vertical. Arquivos
Parquet criptografados não são suportados; cada grupo pode expandir até 64 MiB.
Os eventos preparados têm orçamento de 64 MiB. A fila de cada credencial aceita
até dez arquivos e 100 MiB de bytes retidos. Estes limites são conferidos no
servidor, independentemente da amostra local.

Destino inicial: envelope de eventos do app de TV, com os mesmos quatro campos
obrigatórios e oito opcionais da tela. Campos não mapeados ficam preservados em
`payload._file_extra`; eventos desconhecidos usam o fallback existente. Datas
sem fuso são UTC. Não é um carregador genérico das tabelas CDC.

## Durabilidade e operação

`ingest.file_job` armazena fila e bytes no PostgreSQL. O fingerprint considera
conteúdo, formato, mapeamento e separador; repetir upload retorna o mesmo job.
Os eventos também usam a deduplicação da bronze. O job recebe `available_at`
de `sim.now()` na entrada, preservado como `_captured_at` durante o processamento.
Horários operacionais e expiração de lease usam relógio real.

Estados: `na_fila`, `processando`, `concluido`, `concluido_com_rejeicoes`,
`rejeitado` e `falhou`. Linhas inválidas são contadas e reportadas; as válidas
são gravadas. Arquivo estruturalmente inválido é rejeitado inteiro. Eventos
e resultado final são confirmados na mesma transação: falha não publica falso
sucesso. Workers concorrentes usam `SKIP LOCKED` e lease com UUID; um worker
antigo não pode confirmar após outro assumir. Jobs interrompidos são retomados
após cinco minutos; três interrupções passam a falha temporária.

Conclusão e rejeição permanente removem os bytes. Falhas transitórias retêm
arquivo por sete dias, com limpeza oportunista ao receber novo upload dessa
credencial. Se expirou, reenviar o original restaura o mesmo protocolo.
O histórico da interface tem os últimos cinquenta jobs da aba; fechar a página
não cancela jobs aceitos no servidor. Descartar uma seleção local não exclui
um job enviado. Diagnósticos não incluem valores pessoais das linhas.

Kubernetes usa `DATABASE_URL_MASTER` para os dois serviços de escrita e o hash
`DASHBOARD_TOKEN_SHA256` na API de arquivos, reutilizando o hash do painel;
a leitura permanece com seu usuário de banco próprio.
A imagem agora deve ser publicada em amd64 e arm64. Deployments, sondas, limites
de upload do Ingress e rotação de credencial estão versionados em `k8s/`.

Validação: `make -C apps/fullstack test-worker` usa PostgreSQL real e dados
sintéticos para CSV, Parquet, transação, idempotência, autorização e recuperação.
No Windows, o teste legado que envia SIGTERM ao próprio processo precisa rodar
em Linux. Nesta máquina foi executado `uv run pytest -k 'not sigterm_encerra'`
com diretório temporário próprio e todas as demais verificações habilitadas.
