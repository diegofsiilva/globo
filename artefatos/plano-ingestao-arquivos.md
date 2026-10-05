# Ingestão por arquivos — entrega em duas semanas

Branch: `feat/ingestao`. Página auxiliar: `/ingestao/`, aberta diretamente pela
URL, sem entrada na sidebar. A tela reutiliza a sessão, a moldura e os tokens
de tema do Argus. Formatos iniciais: CSV e Parquet.

## Limite da primeira entrega (concluída)

A primeira entrega executou **4 das 8 entregas abaixo (50% do plano)** e parou.
Isso representa metade dos marcos de entrega, não uma estimativa de horas.
Em 04/10/2026, a continuação solicitada avançou apenas o marco 5: agora são
**5 de 8 marcos concluídos (62,5%)**. Nenhum dado é enviado ou gravado; os marcos
6–8 continuam reservados à próxima entrega.

| Marco | Entrega | Semana | Estado |
| --- | --- | --- | --- |
| 1 | Documentar escopo, limites e critérios de aceite | Atual | Concluído |
| 2 | Criar página auxiliar com a paleta existente, sem link na navegação | Atual | Concluído |
| 3 | Selecionar/arrastar múltiplos CSV e Parquet, listar e remover arquivos | Atual | Concluído |
| 4 | Validar seleção local e testar rejeições, duplicatas e interação | Atual | Concluído |
| 5 | Ler CSV e Parquet, detectar esquema e mostrar amostra limitada | Continuação | Concluído |
| 6 | Mapear colunas à fonte de destino e validar tipos/campos obrigatórios | Próxima | Pendente |
| 7 | Implementar envio autenticado e processamento assíncrono com idempotência | Próxima | Pendente |
| 8 | Acompanhar processamento, rejeições e testar o fluxo integrado | Próxima | Pendente |

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

## Retomada

Continuar na mesma branch a partir do marco 6, revisando os limites antes de
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
