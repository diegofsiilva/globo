# Vídeo 2 — guia de gravação da integração do Argus

Meta: **3 minutos e 40 segundos**, dentro da faixa de 2 a 4 minutos da seção 7 de [infraestrutura-integracao.md](infraestrutura-integracao.md). O vídeo deve comprovar validação funcional e comunicação entre serviços no ambiente integrado.

Este é um roteiro de preparação, não um registro de testes executados. As telas e os resultados precisam ser confirmados no ambiente antes da gravação.

## Preparação

1. Abra o dashboard publicado, autentique-se fora da gravação e escolha uma janela que tenha dados. O Argus usa um relógio simulado: não escolha automaticamente a data atual do computador.
2. Confira que o frontend consulta a API do ambiente. Caso use Hipóteses, confirme o modo API; o painel “Ajustar o recorte” tem cenários informativos e não deve ser usado como evidência de comunicação real.
3. Abra as ferramentas do desenvolvedor do navegador, aba Network (Rede), com filtro Fetch/XHR. Deixe o Console disponível para conferir erros no ensaio.
4. Abra o CloudWatch no grupo de logs da API de leitura e selecione um intervalo recente. Ensaie localizar uma requisição pelo `request_id`.
5. Prepare uma segunda janela, sem autenticação, para o teste de acesso negado. Mantenha a sessão principal autenticada.
6. Não exponha tokens, cabeçalho Authorization, credenciais, IDs de conta ou endpoints sensíveis. Mostre caminho da rota, status e cabeçalhos de resposta com o restante oculto.

**Confirme a topologia:** o código local ainda define a API de leitura em Lambda. Se a migração não ocorreu, descreva navegador → API Gateway → Lambda → RDS, com frontend servido pelo S3 conforme o ambiente. Só mencione CloudFront → ALB → EC2 → RDS quando esse caminho estiver implantado e verificado. A aba Network mostra a chamada do navegador; sozinha não comprova todos os saltos internos.

## Roteiro com falas

### 0:00–0:15 — Abertura

**Tela:** dashboard na página Agora, já autenticado e com dados carregados.

**Fala:** “Somos o grupo 4. Neste vídeo vamos validar o funcionamento integrado do Argus e acompanhar uma requisição desde a interface até o registro do backend.”

### 0:15–1:05 — Fluxo funcional

**Ações:** mostre um sinal disponível em Agora; entre em Explorar, altere um filtro de fonte ou métrica e aguarde a resposta; depois abra Timeline e mostre eventos da janela escolhida. Ensaie os filtros para evitar um recorte vazio durante a gravação.

**Fala:** “Na tela Agora identificamos os sinais de degradação desta janela. Em Explorar, alteramos este filtro para investigar o comportamento dos dados. A interface atualiza o resultado da consulta. Na Timeline, visualizamos os eventos das fontes disponíveis no mesmo eixo de tempo para investigar o contexto do incidente.”

**Evidência:** filtro selecionado, atualização concluída e dados legíveis. Aponte um valor concreto da tela sem decorar números de exemplos ou fixtures. Se o conjunto de dados for sintético, informe isso. Uma resposta vazia pode ser válida, mas não sustenta uma fala sobre eventos que não aparecem.

### 1:05–1:35 — Caso de erro: acesso sem autenticação

**Ações:** na janela separada e sem token, acesse a rota de dados `/api/v1/timeline` da API publicada. Mostre o status e a resposta de acesso negado. Não use `/health/live`: essa rota é pública por definição.

**Fala, após confirmar o resultado:** “Agora tentamos consultar uma rota de dados sem autenticação. O serviço recusa o acesso e não retorna os dados protegidos. Isso demonstra que a validação também cobre uma condição de erro.”

**Resultado esperado:** na arquitetura documentada com API Gateway, ausência de token retorna 401; token inválido retorna 403. Confira o comportamento do ambiente implantado antes de narrar o código. Esse teste comprova proteção da API; não diga que comprova o tratamento visual de erro do frontend se ele não foi mostrado. Se aparecerem dados com status 200, corrija a proteção antes de usar o trecho como evidência de sucesso.

### 1:35–2:25 — Requisição real do frontend

**Ações:** volte à sessão principal. Limpe a lista da aba Network e recarregue Timeline para provocar uma nova chamada. Selecione a requisição de dados `/api/v1/timeline`, não o HTML da página nem uma requisição OPTIONS.

Mostre, nesta ordem:

- Método GET, caminho da rota e status 200.
- Parâmetros enviados, quando presentes.
- Aba Response/Preview, com a janela e os dados retornados.
- Cabeçalho de resposta `X-Request-Id`; copie o valor para localizar o log.

**Fala:** “Esta é a chamada que a própria interface fez para carregar a Timeline. Aqui estão a rota, o status de sucesso e o conteúdo retornado pelo backend. Este identificador de requisição também é registrado no log da API, permitindo localizar exatamente esta operação.”

Compare um evento ou horário da resposta com o que aparece na Timeline. Não confunda uma resposta em cache com uma nova execução: confirme que a requisição escolhida chegou ao backend.

### 2:25–3:20 — Mesmo identificador no CloudWatch

**Ações:** abra o grupo de logs da API, atualize o intervalo e procure o valor copiado de `X-Request-Id`. Abra o evento correspondente. O código de observabilidade local registra `request_id`, `route`, `method`, `status` e `latency_ms`.

**Fala, com o evento visível:** “No CloudWatch encontramos o mesmo identificador mostrado no navegador. O registro confirma a rota chamada, o método, o status e o tempo de processamento. Assim vinculamos a ação da interface à execução do backend.”

**Complete com a topologia efetiva:** explique em uma frase por onde essa requisição passou até a API e que ela consulta o PostgreSQL. O log HTTP comprova o processamento da API, mas não é um trace de consulta SQL. Não afirme que ele sozinho comprova cada salto até o banco.

Se o log demorar a chegar, espere e corte o tempo morto, preservando a mesma requisição e sinalizando a passagem de tempo. Se não houver o cabeçalho ou o evento correspondente, resolva essa pendência antes de gravar esse trecho; não use um log de outra chamada como se fosse o mesmo.

### 3:20–3:40 — Fechamento

**Tela:** volte à Timeline carregada.

**Fala, se todos os passos passaram:** “Demonstramos a consulta e a atualização dos dados na interface, a recusa de acesso sem autenticação e a correlação entre a requisição do navegador e o log do backend. Essas evidências mostram o funcionamento integrado do Argus no ambiente apresentado.”

## Registro do ensaio

Preencha com resultados observados; não transforme expectativa em teste aprovado.

| Caso | Resultado esperado | Resultado observado |
|---|---|---|
| Carregar Agora | Dados da janela disponíveis, sem falha de carregamento | A verificar |
| Alterar filtro em Explorar | Nova consulta e resultado coerente com o filtro | A verificar |
| Abrir Timeline | Resposta 200 e eventos compatíveis com a tela | A verificar |
| Consultar rota protegida sem token | Acesso negado, sem dados protegidos | A verificar |
| Correlacionar navegador e API | Mesmo identificador na resposta e no CloudWatch | A verificar |

## Checklist de entrega

- [ ] Vídeo entre 2 e 4 minutos, com console e texto legíveis.
- [ ] Fluxo funcional executado no ambiente apresentado.
- [ ] Caso de erro visível, com resultado confirmado.
- [ ] Requisição feita pelo frontend e resposta demonstradas.
- [ ] Mesmo identificador localizado no log da API.
- [ ] Falas correspondem à infraestrutura efetivamente implantada.
- [ ] Nenhuma credencial ou token aparece no vídeo.
- [ ] Arquivo final assistido e link testado sem login em janela anônima.
- [ ] Link inserido na seção 7 de `infraestrutura-integracao.md` e resultados do ensaio registrados na seção 7.1.
