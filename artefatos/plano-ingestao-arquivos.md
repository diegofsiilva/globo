# Ingestão por arquivos — entrega em duas semanas

Branch: `feat/ingestao`. Página auxiliar: `/ingestao/`, aberta diretamente pela
URL, sem entrada na sidebar. A tela reutiliza a sessão, a moldura e os tokens
de tema do Argus. Formatos iniciais: CSV e Parquet.

## Limite desta entrega

Executar **4 das 8 entregas abaixo (50% do plano)** e parar. Isso representa
metade dos marcos de entrega, não uma estimativa de horas. Nesta semana, o
operador prepara uma lista local de arquivos; nenhum dado é enviado ou gravado.
Não antecipar a segunda etapa para completar o fluxo.

| Marco | Entrega | Semana | Estado |
| --- | --- | --- | --- |
| 1 | Documentar escopo, limites e critérios de aceite | Atual | Concluído |
| 2 | Criar página auxiliar com a paleta existente, sem link na navegação | Atual | Concluído |
| 3 | Selecionar/arrastar múltiplos CSV e Parquet, listar e remover arquivos | Atual | Concluído |
| 4 | Validar seleção local e testar rejeições, duplicatas e interação | Atual | Concluído |
| 5 | Ler CSV e Parquet, detectar esquema e mostrar amostra limitada | Próxima | Pendente |
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

Na próxima semana, continuar na mesma branch a partir do marco 5, revisando os
limites antes de implementar o contrato de upload. Os arquivos selecionados
nesta primeira versão existem apenas na memória da página e são descartados
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
- Não há parser, mapeamento, upload ou gravação de dados nesta entrega.
  Os marcos 5–8 permanecem pendentes intencionalmente.
