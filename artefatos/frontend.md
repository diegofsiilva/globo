# Front-end

Este artefato documenta a implementação da interface gráfica da plataforma de
telemetria, incluindo a validação das entradas do usuário, a rastreabilidade dos
requisitos funcionais, a organização do código, a integração com o back-end e a
publicação do site estático na AWS S3.

> **Status do documento:** estrutura inicial. Os trechos marcados com
> **PREENCHER** devem ser atualizados com os resultados e as evidências da versão
> entregue.

---

## 1. Visão geral da interface

**PREENCHER:** descrever, em um ou dois parágrafos, quais problemas a interface
resolve e quais funcionalidades estão disponíveis na versão entregue.

### 1.1 Funcionalidades implementadas

- **PREENCHER:** consulta de eventos por período e tipo;
- **PREENCHER:** aplicação de filtros cumulativos;
- **PREENCHER:** sugestão de valores para os filtros;
- **PREENCHER:** visualização de indicadores e gráficos;
- **PREENCHER:** inspeção dos detalhes de um evento;
- **PREENCHER:** estados de carregamento, ausência de dados e erro da API.

### 1.2 Tecnologias utilizadas

| Tecnologia | Finalidade | Versão |
|---|---|---|
| Next.js | Framework da aplicação e exportação do site estático | **PREENCHER** |
| React | Construção dos componentes da interface | **PREENCHER** |
| TypeScript | Tipagem e manutenção do código | **PREENCHER** |
| Tailwind CSS | Estilização e responsividade | **PREENCHER** |
| TanStack Query | Consulta, cache e estados das requisições ao back-end | **PREENCHER** |
| **PREENCHER** | Biblioteca de gráficos, testes ou outra dependência relevante | **PREENCHER** |

## 2. Organização e qualidade do código

O código-fonte do front-end está localizado em
[`apps/basica/frontend`](../apps/basica/frontend). A especificação original cita
`/apps/frontend`; portanto, antes da entrega final, a equipe deve confirmar se a
estrutura atual será mantida ou se a aplicação será movida para o caminho
solicitado.

### 2.1 Estrutura de pastas

```text
apps/basica/frontend/
├── app/                 # Páginas, layout e estilos globais
├── components/          # PREENCHER: componentes reutilizáveis
├── hooks/               # PREENCHER: hooks da aplicação
├── lib/                 # PREENCHER: cliente HTTP, utilitários e configurações
├── types/               # PREENCHER: contratos e tipos compartilhados
└── tests/               # PREENCHER: testes automatizados
```

**PREENCHER:** ajustar a árvore acima à estrutura efetivamente entregue e
explicar brevemente as decisões de modularização, nomenclatura e separação de
responsabilidades.

### 2.2 Convenções adotadas

- Componentes React: **PREENCHER** (exemplo: `PascalCase`).
- Funções, variáveis e hooks: **PREENCHER** (exemplo: `camelCase`).
- Tipos e interfaces: **PREENCHER**.
- Estratégia de comentários: **PREENCHER**; priorizar comentários que expliquem
  decisões e regras não evidentes.
- Ferramentas de qualidade: **PREENCHER** (ESLint, TypeScript, formatter e
  outras).

## 3. Acessibilidade e responsividade

### 3.1 Acessibilidade

**PREENCHER:** registrar como a interface atende aos critérios de acessibilidade,
incluindo, quando aplicável:

- navegação completa por teclado e foco visível;
- elementos HTML semânticos e nomes acessíveis;
- rótulos e mensagens de erro associados aos campos;
- contraste de cores e ausência de dependência exclusiva da cor;
- textos alternativos para imagens relevantes;
- comunicação dos estados de carregamento e erro a tecnologias assistivas.

| Verificação | Ferramenta ou método | Resultado | Evidência |
|---|---|---|---|
| Navegação por teclado | Teste manual | **PREENCHER** | **PREENCHER** |
| Análise automatizada | Lighthouse, axe ou equivalente | **PREENCHER** | **PREENCHER** |
| Contraste | **PREENCHER** | **PREENCHER** | **PREENCHER** |
| Leitor de tela | **PREENCHER** | **PREENCHER** | **PREENCHER** |

### 3.2 Responsividade

**PREENCHER:** explicar as adaptações de layout para telas pequenas, médias e
grandes.

| Dispositivo ou viewport | Navegador | Resultado | Evidência |
|---|---|---|---|
| Celular — **PREENCHER** px | **PREENCHER** | **PREENCHER** | **PREENCHER** |
| Tablet — **PREENCHER** px | **PREENCHER** | **PREENCHER** | **PREENCHER** |
| Desktop — **PREENCHER** px | **PREENCHER** | **PREENCHER** | **PREENCHER** |

## 4. Validação das entradas do usuário

Os testes desta seção verificam se os campos aceitam dados válidos, impedem ou
tratam entradas inválidas e apresentam mensagens compreensíveis sem provocar
requisições incorretas ao back-end.

### 4.1 Estratégia de teste

- **Ambiente:** **PREENCHER** (local, homologação ou produção).
- **Versão testada:** **PREENCHER** (branch, tag ou hash do commit).
- **Data da execução:** **PREENCHER**.
- **Navegador e dispositivo:** **PREENCHER**.
- **Ferramentas:** **PREENCHER** (exemplo: Vitest, Testing Library, Playwright e
  inspeção manual).
- **Comando executado:** `PREENCHER`.

### 4.2 Casos de teste e resultados

> Substituir ou complementar os casos abaixo de acordo com os controles que
> realmente existirem na interface. Cada evidência deve apontar para uma captura
> de tela, relatório automatizado ou arquivo de teste versionado.

| ID | Entrada ou cenário | Procedimento | Resultado esperado | Resultado obtido | Situação | Evidência |
|---|---|---|---|---|---|---|
| TF-01 | Período válido | Informar data inicial anterior à data final e pesquisar | A consulta é enviada com o período selecionado | **PREENCHER** | **PREENCHER** | **PREENCHER** |
| TF-02 | Período invertido | Informar data inicial posterior à data final | A consulta não é enviada e uma mensagem orienta a correção | **PREENCHER** | **PREENCHER** | **PREENCHER** |
| TF-03 | Data inválida ou ausente | Apagar ou digitar uma data fora do formato aceito | O campo inválido é identificado de forma acessível | **PREENCHER** | **PREENCHER** | **PREENCHER** |
| TF-04 | Filtro por tipo | Selecionar um tipo de evento existente | Apenas dados compatíveis são apresentados | **PREENCHER** | **PREENCHER** | **PREENCHER** |
| TF-05 | Filtros cumulativos | Aplicar dois ou mais filtros na mesma consulta | Todos os filtros são preservados e enviados ao back-end | **PREENCHER** | **PREENCHER** | **PREENCHER** |
| TF-06 | Valor inexistente | Informar ou selecionar um valor sem correspondência | A interface apresenta estado vazio sem falhar | **PREENCHER** | **PREENCHER** | **PREENCHER** |
| TF-07 | Caracteres especiais | Inserir caracteres especiais em um campo textual | A entrada é tratada sem quebrar a tela nem alterar indevidamente a requisição | **PREENCHER** | **PREENCHER** | **PREENCHER** |
| TF-08 | Limite de tamanho | Informar texto maior que o limite definido | O limite é aplicado ou uma mensagem de validação é exibida | **PREENCHER** | **PREENCHER** | **PREENCHER** |
| TF-09 | Envio por teclado | Preencher os filtros e acionar a pesquisa pelo teclado | A ação funciona e o foco permanece previsível | **PREENCHER** | **PREENCHER** | **PREENCHER** |
| TF-10 | Falha do back-end | Simular resposta de erro ou indisponibilidade | A interface informa a falha e permite nova tentativa | **PREENCHER** | **PREENCHER** | **PREENCHER** |

### 4.3 Síntese dos resultados

| Indicador | Resultado |
|---|---|
| Total de testes executados | **PREENCHER** |
| Testes aprovados | **PREENCHER** |
| Testes reprovados | **PREENCHER** |
| Testes bloqueados ou não executados | **PREENCHER** |
| Taxa de aprovação | **PREENCHER**% |

**PREENCHER:** interpretar os resultados. Para cada reprovação, registrar o
impacto, a correção prevista e, se disponível, o identificador da issue.

## 5. Matriz de rastreabilidade

A matriz relaciona os requisitos funcionais pertinentes à interface, definidos
em [`requisitos.md`](./requisitos.md), às funcionalidades implementadas e aos
testes que fornecem evidência de atendimento. Devem permanecer apenas os
requisitos efetivamente incluídos na versão entregue.

| Requisito | Funcionalidade ou critério verificado | Testes relacionados | Situação | Evidência |
|---|---|---|---|---|
| RF08 | Pesquisa por tipo, período e demais atributos disponíveis | TF-01, TF-02, TF-03, TF-04, TF-06 | **PREENCHER** | **PREENCHER** |
| RF09 | Aplicação de mais de um filtro em uma consulta | TF-05 | **PREENCHER** | **PREENCHER** |
| RF10 | Sugestão de valores existentes durante o preenchimento | **PREENCHER** | **PREENCHER** | **PREENCHER** |
| RF11 | Agrupamento de eventos por critérios disponíveis | **PREENCHER** | **PREENCHER** | **PREENCHER** |
| RF12 | Apresentação de gráficos e indicadores | **PREENCHER** | **PREENCHER** | **PREENCHER** |
| RF13 | Consultas simples de falhas críticas | **PREENCHER** | **PREENCHER** | **PREENCHER** |
| RF14 | Comparação com período anterior | **PREENCHER** | **PREENCHER** | **PREENCHER** |
| RF15 | Destaque de aumentos relevantes de erros ou latência | **PREENCHER** | **PREENCHER** | **PREENCHER** |
| RF16 | Exibição de informações que apoiam a investigação | **PREENCHER** | **PREENCHER** | **PREENCHER** |
| RF17 | Apresentação de hipóteses de causa e suas evidências, se implementada | **PREENCHER** | **PREENCHER** | **PREENCHER** |

## 6. Integração com o back-end

**PREENCHER:** descrever o fluxo entre a interface e a API, incluindo a variável
de ambiente que define a URL, os endpoints consumidos, os parâmetros enviados e
o tratamento dos estados de carregamento, sucesso, ausência de dados e erro.

| Ação na interface | Método e endpoint | Dados enviados | Resposta utilizada |
|---|---|---|---|
| **PREENCHER** | `GET PREENCHER` | **PREENCHER** | **PREENCHER** |
| **PREENCHER** | `GET PREENCHER` | **PREENCHER** | **PREENCHER** |
| **PREENCHER** | `GET PREENCHER` | **PREENCHER** | **PREENCHER** |

### 6.1 Evidência do fluxo ponta a ponta

**PREENCHER:** registrar ao menos um cenário em que uma ação no front-end gera
uma requisição para o back-end e apresenta os dados retornados. Incluir captura
da interface e, quando útil, da requisição na aba de rede do navegador.

## 7. Publicação na AWS S3

- **URL do front-end publicado:** **PREENCHER**.
- **Data da última publicação:** **PREENCHER**.
- **Versão publicada:** **PREENCHER** (tag ou hash do commit).
- **Região AWS:** **PREENCHER**.
- **Nome ou identificador não sensível do bucket:** **PREENCHER**.
- **Procedimento de build:** `PREENCHER`.
- **Procedimento de publicação:** `PREENCHER`.

**PREENCHER:** explicar como o build estático é gerado e enviado ao bucket, como
o acesso ao site foi configurado e como a integração com a API foi validada no
ambiente publicado. Não registrar credenciais, tokens ou URLs privadas.

### 7.1 Evidências da publicação

| Evidência | Link ou arquivo |
|---|---|
| Site carregado a partir da URL publicada | **PREENCHER** |
| Arquivos do build armazenados no S3 | **PREENCHER** |
| Versão do código correspondente à publicação | **PREENCHER** |
| Integração do site publicado com o back-end | **PREENCHER** |

## 8. Vídeo demonstrativo

- **Link do vídeo (2 a 3 minutos):** **PREENCHER**.
- **Duração:** **PREENCHER**.
- **Data de gravação:** **PREENCHER**.

### 8.1 Roteiro sugerido

| Tempo aproximado | Conteúdo |
|---|---|
| 0:00–0:20 | Apresentar o objetivo do dashboard e a URL publicada na AWS S3 |
| 0:20–1:10 | Demonstrar consultas, validações de entrada e filtros cumulativos |
| 1:10–1:50 | Demonstrar gráficos, indicadores e detalhes que apoiam a investigação |
| 1:50–2:30 | Mostrar a integração com o back-end e o tratamento de carregamento ou erro |
| 2:30–3:00 | Destacar responsividade, acessibilidade e encerrar com o resultado obtido |

> Antes da entrega, conferir se o link permite visualização sem solicitar acesso
> individual e se o vídeo permanece entre 2 e 3 minutos.

## 9. Frontend das hipóteses

![Tela do frontend](../../assets/prototipo_hipoteses.png "Tela do frontend)


## 10. Limitações e próximos passos

- **PREENCHER:** limitações conhecidas da interface entregue;
- **PREENCHER:** testes ainda não automatizados;
- **PREENCHER:** melhorias de acessibilidade ou responsividade pendentes;
- **PREENCHER:** funcionalidades planejadas para a próxima versão.

## 11. Checklist da entrega

- [ ] Todos os marcadores **PREENCHER** foram substituídos ou removidos.
- [ ] Os resultados de validação de entradas incluem evidências reproduzíveis.
- [ ] A matriz liga cada requisito pertinente a pelo menos um teste.
- [ ] O caminho do código-fonte corresponde ao solicitado na especificação.
- [ ] O código publicado no S3 corresponde à versão indicada no relatório.
- [ ] A URL do site está acessível e a integração com o back-end funciona.
- [ ] O vídeo tem entre 2 e 3 minutos e seu link está público para visualização.
- [ ] Nenhuma credencial, token ou informação sensível foi adicionada ao arquivo.
