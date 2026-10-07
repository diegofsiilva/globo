# Ingestão por arquivos — entrega em duas semanas

Branch: `feat/ingestao`. Página auxiliar: `/ingestao/`, aberta diretamente pela
URL, sem entrada na sidebar. A tela reutiliza a sessão, a moldura e os tokens
de tema do Argus. Formatos iniciais: CSV e Parquet.

## Estado atual — 100% implementado

Em 05/10/2026, o pedido explícito de finalizar autorizou concluir os marcos 7–8:
**8 de 8 marcos concluídos**. A página continua auxiliar, sem item na sidebar,
com a paleta existente. Há envio autenticado do original, processamento
assíncrono durável, deduplicação, rejeições e retomada. Esta conclusão refere-se
à implementação e validação local; publicação em AWS não foi executada.

Ajuste posterior solicitado: removidos o indicador de desenvolvimento do Next
e o formulário de token de ingestão. O envio agora reutiliza a sessão do painel;
cliente HTTP, serviço e manifests usam a mesma credencial, sem bloquear o fluxo
por falta de uma segunda autorização. As evidências históricas abaixo descrevem
a versão anterior a esse ajuste.

## Histórico da entrega parcial

A primeira entrega executou **4 das 8 entregas abaixo (50% do plano)** e parou.
Isso representa metade dos marcos de entrega, não uma estimativa de horas.
Em 04/10/2026, a continuação solicitada avançou apenas o marco 5. Em 05/10/2026,
a nova continuação concluiu o marco 6, chegando a **6 de 8 marcos (75%)**.
Até esse ponto não havia envio ou gravação; a finalização está registrada abaixo.

| Marco | Entrega | Semana | Estado |
| --- | --- | --- | --- |
| 1 | Documentar escopo, limites e critérios de aceite | Atual | Concluído |
| 2 | Criar página auxiliar com a paleta existente, sem link na navegação | Atual | Concluído |
| 3 | Selecionar/arrastar múltiplos CSV e Parquet, listar e remover arquivos | Atual | Concluído |
| 4 | Validar seleção local e testar rejeições, duplicatas e interação | Atual | Concluído |
| 5 | Ler CSV e Parquet, detectar esquema e mostrar amostra limitada | Continuação | Concluído |
| 6 | Mapear colunas à fonte de destino e validar tipos/campos obrigatórios | Continuação | Concluído |
| 7 | Implementar envio autenticado e processamento assíncrono com idempotência | Finalização | Concluído |
| 8 | Acompanhar processamento, rejeições e testar o fluxo integrado | Finalização | Concluído |

## Critérios da primeira metade

- `/ingestao/` preserva o acesso por sessão e não altera a navegação desktop/móvel.
- Cores usam tokens existentes e acompanham claro/escuro; layout responsivo.
- Seleção pelo seletor nativo e por arrastar arquivos, com alternativa por teclado.
- Aceitar extensões `.csv` e `.parquet`, independentemente de maiúsculas e MIME
  (o MIME desses formatos varia por sistema operacional).
- Rejeitar arquivos vazios, formatos diferentes e arquivos acima de 50 MiB.
- Limitar a lista a 10 arquivos e 100 MiB no total; deduplicar por nome,
  tamanho e última modificação. Limites locais provisórios, a alinhar com o backend.
- Mostrar nome, formato e tamanho; permitir remover um arquivo ou limpar o lote.
- Explicar que a verificação cobre apenas seleção e metadados, não conteúdo ou esquema.
- A ingestão permanece desabilitada, com explicação visível da próxima etapa.
- Validar testes, lint e build estático antes da entrega; registrar limitações reais.

## Decisões reservadas à próxima semana

O dashboard é estático: upload não deve ser implementado em uma rota de API do
Next.js. Definir o serviço de ingestão e sua autorização separadamente da API
de leitura, mantendo segredos fora do bundle e usando o cliente HTTP comum.
Avaliar upload direto para armazenamento com URL assinada para lotes grandes.
Validação real deve ocorrer no servidor, incluindo assinatura/estrutura Parquet,
codificação/delimitador CSV, esquema, autorização de destino e limites.
Preservar `available_at` e a semântica do relógio virtual na adaptação ao domínio.
Não carregar nem alterar o dump ou os Parquet cedidos pelo parceiro para testar.

## Retomada histórica após o marco 6

Continuar na mesma branch a partir do marco 7, revisando os limites antes de
implementar o contrato de upload. Os arquivos selecionados e suas amostras
existem apenas na memória da página e são descartados
ao recarregar ou sair. Não prometer sucesso de ingestão nesta etapa.

## Evidências da primeira entrega — 01/10/2026

- `make -C apps/fullstack test-frontend`: 37 testes passaram em 10 arquivos;
  9 cenários novos cobrem a preparação de arquivos e a ausência na navegação.
- `npm run lint`: passou sem erros.
- Build estático: passou, com `/ingestao` na relação de rotas exportadas.
  `frontend-build-check` não executou no shell Windows porque seu recipe usa
  atribuição POSIX de variáveis; executado o mesmo `npm run build` em PowerShell
  com as variáveis de placeholder do alvo, sem alterar o Makefile.
- Export servido localmente e verificado com Chrome headless: página carregou
  com sessão sintética, temas claro/escuro e viewport móvel de 390 px.
  Capturas inspecionadas; nenhuma rolagem horizontal no viewport móvel.
- Na primeira entrega não havia parser, mapeamento, upload ou gravação de dados.
  Os marcos 5–8 foram deixados pendentes intencionalmente.

## Continuação — 04/10/2026

O marco 5 foi concluído com prévia individual de até 10 linhas e 64 colunas.
“Ver prévia” inicia um worker local; trocar/remover o arquivo, limpar o lote
ou fechar a prévia encerra a leitura. Há interrupção automática após 30 segundos.
O botão de revisão do destino continua desabilitado, e a página continua fora
da sidebar. Não foram implementados mapeamento, upload nem processamento.

- CSV: UTF-8 (BOM aceito), cabeçalho obrigatório, separador detectado entre
  vírgula, ponto e vírgula, tabulação e barra vertical; campos entre aspas e
  registros com quebras de linha são preservados. Cabeçalhos vazios/duplicados,
  aspas malformadas e quantidade inconsistente de campos na amostra geram erro.
  Leitura limitada ao primeiro 1 MiB; o total de registros não é calculado.
  Tipos são inferidos somente da amostra, sem converter os valores originais.
- Parquet: assinatura e rodapé conferidos, esquema e contagem extraídos dos
  metadados e amostra descomprimida localmente. Até 2 MiB de metadados,
  orçamento de leitura de 16 MiB e limite de 64 MiB descomprimidos por grupo
  necessário à amostra. Arquivos criptografados não são suportados.
- Células exibidas limitadas a 500 caracteres; inteiros de 64 bits preservados.
  A amostra não valida o arquivo inteiro nem o esquema de destino.
- Dependências: Papa Parse, Hyparquet e seus descompressores. O writer Parquet
  existe somente como dependência de desenvolvimento para testes sintéticos.
- `make -C apps/fullstack test-frontend`: 56 testes passaram em 12 arquivos,
  incluindo 19 novos cenários de parsing e ciclo de vida da prévia.
- `npm run lint` e build estático passaram. Build executado com as mesmas
  variáveis de placeholder do alvo `frontend-build-check` via PowerShell, pela
  incompatibilidade já registrada do recipe POSIX com o shell Windows.
- Export verificado em Chrome headless com workers reais: leitura de CSV e
  Parquet Snappy sintéticos, preservação de identificadores e inteiros grandes,
  remoção da prévia e viewport móvel sem rolagem horizontal. Capturas claro e
  escuro inspecionadas. Nenhum dado do parceiro utilizado.

## Continuação — 05/10/2026

O marco 6 adiciona o mapeamento dentro da prévia de cada arquivo. O destino
suportado nesta etapa é o envelope de eventos do app de TV, baseado em
`apps/fullstack/worker/src/argus_worker/models.py`; não é uma importação das
33 tabelas da carga inicial nem do fluxo CDC. A página mantém a paleta, a sessão
e a ausência de item na sidebar. O botão “Enviar lote” continua desabilitado.

- Obrigatórios: `timestamp`, `event_name`, `session_id` e `device_id`.
- Opcionais nesta revisão: `event_id`, `user_id`, `app_version`, `device_model`,
  `duration`, `request_status`, `media_ads` e `media_drm`. Outros campos continuam
  no arquivo original e são sinalizados como fora desta revisão.
- Sugestão por nome exato, ignorando espaços nas extremidades e maiúsculas;
  cabeçalhos ambíguos não são selecionados automaticamente. Escolha manual e
  limpeza de mapeamento disponíveis. A mesma coluna não pode servir a dois campos.
- Validação explícita da amostra com problemas por campo e linha. Mudar uma
  escolha ou aplicar sugestões remove o resultado anterior e exige revalidação.
- Campos obrigatórios não podem estar vazios. Datas devem ser ISO 8601, com
  calendário e fuso válidos; datas sem fuso são sinalizadas como UTC, conforme
  o worker. Epoch numérico e datas em formatos locais não são convertidos nesta tela.
- Números devem ser finitos; inteiros não podem perder precisão em JavaScript;
  booleanos aceitam `true`, `false`, `1` e `0`. Opcionais vazios são permitidos.
  Tipos desconhecidos de evento geram aviso, seguindo o fallback genérico do worker.
- Valores cortados pela prévia e conteúdos estruturados/binários Parquet são
  marcados pelo parser e não podem receber aprovação para campos escalares.
  Os valores originais não são sobrescritos nem transformados em payload de upload.
- Escolhas e resultado são efêmeros: fechar/trocar a prévia ou remover o arquivo
  os descarta. A aprovação refere-se apenas às linhas da amostra; a validação do
  arquivo completo, a autorização e os limites do servidor permanecem no marco 7.
- `make -C apps/fullstack test-frontend`: 84 testes passaram em 14 arquivos;
  28 novos casos cobrem regras de mapeamento, tipos e interação do formulário.
- Lint e build estático passaram. Corrigida a inclusão indevida de arquivos
  gerados em `out/` na checagem TypeScript, que fazia um build subsequente falhar;
  `tsconfig.json` agora exclui esse diretório, mantendo a checagem do código-fonte.
- Chrome headless sobre o export confirmou sugestão, aprovação da amostra,
  rejeição de coluna reutilizada, invalidação/revalidação, descarte ao fechar,
  envio desabilitado e viewport móvel sem rolagem horizontal. Temas claro e
  escuro conferidos com dados sintéticos.
- Envio autenticado, processamento assíncrono, idempotência e acompanhamento
  continuam intencionalmente sem implementação.

## Finalização — 05/10/2026

O pedido “finalize agora, 100%” concluiu os dois marcos restantes. A tela
autoriza escrita com credencial independente da leitura, envia cada arquivo
original por multipart e acompanha resultados sem acrescentar navegação.
O serviço separado roda nos modos `file-api` e `file-worker` da imagem existente.
A migration 034 acrescenta a fila PostgreSQL; não há dependência de S3/SQS no
novo fluxo nem alteração da API de leitura.

- Validação do arquivo completo no servidor, contagem de inseridos, duplicados
  e rejeitados, até cem motivos sem valores pessoais e relatório JSON baixável.
- Fingerprint de conteúdo/mapeamento e deduplicação canônica dos eventos;
  conclusão e inserções na mesma transação. Testada interrupção depois de SQL
  real: rollback sem falso sucesso, seguido de retomada com o mesmo protocolo.
- Lease com fencing, recuperação de processamento interrompido, limite de
  tentativas, limite de fila por credencial e descarte dos bytes após conclusão.
- `available_at` vem de `sim.now()`; campos não mapeados são preservados.
- Histórico de cinquenta protocolos por aba e consultas periódicas apenas
  enquanto há jobs ativos. Recarregar mantém o acompanhamento; o processamento
  não depende da página permanecer aberta.
- Manifests AWS/kind, rota `/ingestion`, sondas, imagem multiarch, hash no Secret
  e comandos Make versionados. Runbook em
  [worker/README.md](../apps/fullstack/worker/README.md).

Evidências desta finalização:

- Frontend: **92 testes passaram em 16 arquivos**, incluindo oito novos casos
  de autenticação de escrita, multipart original, polling, retomada e contrato.
  Execução com `npm test -- --maxWorkers=2`, após falta de memória com o
  paralelismo padrão. Lint e build estático passaram; `/ingestao` exportada.
- Worker: **125 testes passaram com PostgreSQL real**; dezesseis casos novos
  cobrem CSV, Parquet Snappy, linhas além da amostra, extras/identificadores,
  deduplicação, autorização, leases, rollback, retry, limites e CORS. Um teste
  legado de SIGTERM foi excluído no Windows, pois `os.kill(..., SIGTERM)` encerra
  o processo em vez de exercitar o handler POSIX. Foi utilizado diretório
  temporário próprio devido a uma pasta antiga do pytest sem permissão.
- Ruff e formatação passaram. Overlays Kustomize renderizados; verificador
  confirmou ordem do Ingress, quatro imagens multiarch e chaves dos Secrets.
  O verificador foi executado com `uv run --project worker python`, pois não
  há executável `python3` no PATH do Windows.
- Chrome headless sobre o export: CSV com worker real, validação, envio do
  original, polling e rejeição na linha 12; Parquet com parser real e aprovação
  da amostra. Nesta verificação visual a fronteira HTTP foi simulada; a gravação
  real foi exercitada separadamente pelos testes Python acima. Temas claro/escuro
  e viewport de 390 px inspecionados, sem overflow horizontal ou erros de página.
- Uma imagem Linux com as novas dependências foi construída. A reconstrução
  final, após ajustar a sonda Docker, foi interrompida pela indisponibilidade
  do Docker Desktop; essa imagem final e os Deployments não foram executados.
  Não houve publicação na AWS. Nenhum dado do parceiro foi utilizado.
