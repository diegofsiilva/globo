# Inteli - Instituto de Tecnologia e Liderança

<p align="center">
  <img src="assets/inteli-logo.png" alt="Inteli" width="260"/>
  &nbsp;&nbsp;&nbsp;&nbsp;
  <img src="assets/grupoglobo.png" alt="Grupo Globo" width="260"/>
</p>

## G04 - Vale a Pena Ver de Novo

**Sistema distribuído de telemetria para diagnóstico de degradação de streaming**

Turma T15 · 2026-2A · Parceiro: **Grupo Globo**

### Integrantes

- [Christian Gandra](https://www.linkedin.com/in/christian-gandra/)
- [Diego Figueiredo](https://www.linkedin.com/in/diegofigueiredos/)
- [Gabriel Bartmanovicz](https://www.linkedin.com/in/gabriel-bartmanovicz/)
- [Livia Saboia Tavares](https://www.linkedin.com/in/livia-saboia-tavares/)
- [Lorenzo Ferrari Aggio](https://www.linkedin.com/in/lorenzo-ferrari-aggio/)
- [Luiz Gustavo](https://www.linkedin.com/in/luiz-gustavo-0b33b62b7/)
- [Nicole Riedla](https://www.linkedin.com/in/nicoleriedla/)
- [Vinicius Cadena](https://github.com/ViniCadena1405)

---

## Descrição do projeto

A cadeia de entrega do Globoplay (player, CDN, backend, identidade, catálogo) é monitorada em silos: cada área tem seu próprio painel e vocabulário de métricas, o que faz com que a triagem de um incidente consuma mais tempo para descobrir *quem* conserta do que para de fato consertar. Além disso, degradações que não geram erro (buffer alto, tempo de início ruim) sequer acendem os alertas atuais. A solução é um sistema distribuído de telemetria com API única de ingestão, normalização dos eventos sob vocabulário comum, pipeline assíncrono de alta escala e camada de consulta que devolve uma linha do tempo única do incidente com o recorte afetado explícito, permitindo identificar a causa provável em minutos e sem depender de um especialista por componente.

O sistema ingere os seis eventos do MVP (`request`, `screen_view`, `session`, `video_view`, `vitals` e `error`) e ainda aceita tipos novos sem alteração de código, porque o parque de TVs atualiza devagar e um schema estrito viraria perda de dados em massa.

---

## Arquitetura

São dois fluxos independentes ligados por um banco em comum: **ingestão** (aceita na borda, enfileira, valida de forma assíncrona e grava) e **leitura** (consulta, agrega e serve o dashboard).

```
App de TV ──> API Gateway ──> SQS ──> ECS Fargate ──> DynamoDB ──> Lambda ──> API Gateway ──> Dashboard
             (ingestão)       │        (worker)                   (API de     (leitura)      (Next.js
                              ▼                                   leitura)                    estático)
                            SQS DLQ
```

| Camada | Responsabilidade | Serviço AWS |
|--------|------------------|-------------|
| API de ingestão | Recebe os eventos e publica na fila por integração direta, sem Lambda no caminho | API Gateway (HTTP API) |
| Fila de mensagens | Absorve picos e garante a entrega; payload inválido vai para a DLQ com o motivo | SQS + DLQ |
| Worker | Consome a fila por long polling, valida, deduplica e grava em lote | ECS Fargate (ARM64) |
| Banco de dados | Tabela única com GSI1 (tipo + dia, com shard) e GSI2 (aparelho), TTL nativo | DynamoDB |
| API de leitura | Filtros cumulativos, agregações, paginação por cursor e redação de dado pessoal | AWS Lambda (Flask) + API Gateway |
| Dashboard | Visualização e investigação de incidentes | S3 + CloudFront (site estático) |

Escolhas de projeto, modelo de dados, garantias de entrega, custo e pendências estão detalhados em [`artefatos/arquitetura.md`](artefatos/arquitetura.md).

> **Estado:** os fluxos de ingestão e leitura estão aplicados e validados ponta a ponta em AWS Academy Learner Lab. O dashboard está em desenvolvimento na branch `feat/frontend-inicial`.

---

## Estrutura de pastas

| Pasta / Arquivo | Conteúdo |
|-----------------|----------|
| `/apps/backend` | API de leitura em Flask sobre Lambda, com arquitetura hexagonal |
| `/apps/worker` | Worker de ingestão, que consome o SQS e grava no DynamoDB |
| `/apps/infra` | Terraform de toda a infraestrutura AWS |
| `/apps/tools` | Conversão dos CSVs de evento, replay para a API e ETL do dump |
| `/apps/notebooks` | Análise exploratória do dataset do parceiro |
| `/apps/frontend` | Dashboard Next.js *(em desenvolvimento)* |
| `/artefatos` | Documentação das sprints: negócio, UX, requisitos e arquitetura |
| `/artefatos/assets` | Imagens usadas nos artefatos |
| `/assets` | Logos usados neste README |
| `Makefile` | Comandos do projeto; `make` sozinho lista os alvos |
| `.env.example` | Chaves de configuração; os valores ficam no `.env`, fora do repositório |
| `README.md` | Este arquivo |
| `.gitignore` | Arquivos e pastas ignorados pelo controle de versão |

---

## Execução local

### Pré-requisitos

- _[Python 3.x]_
- _[Node.js 20+]_
- _[Docker (opcional)]_
- Credenciais AWS do AWS Academy configuradas (`~/.aws/credentials`)

### Passos

```bash
# 1. clonar o repositório
git clone https://git.inteli.edu.br/graduacao/2026-2a/t15/g04.git
cd g04/apps/basica

# 2. configurar variáveis de ambiente
cp .env.example .env
# preencher AWS_REGION, SQS_QUEUE_URL, DYNAMO_TABLE, ...

# 3. instalar dependências
_[comando]_

# 4. subir os serviços
_[comando]_
```

| Serviço | Porta local |
|---------|-------------|
| API de ingestão | _[porta]_ |
| API de consulta | _[porta]_ |
| Frontend | _[porta]_ |

> **GitHub Codespaces / VS Code:** o repositório inclui _[devcontainer / tasks.json]_, bastando acionar **Run** para iniciar o sistema.

---

## Execução na AWS

| Serviço | Configuração | Endpoint |
|---------|-------------|----------|
| EC2 | _[tipo da instância, AMI, security group e portas liberadas]_ | _[IP ou DNS público]_ |
| SQS | _[nome da fila e visibility timeout]_ | _[URL da fila]_ |
| DynamoDB | Tabela `telemetry_signals` (PK/SK) | _[região]_ |
| S3 | _[nome do bucket do site estático]_ | _[URL do site]_ |

### Passos de implantação

1. _[Provisionar a instância EC2 no lab do AWS Academy]_
2. _[Criar a fila SQS e a tabela DynamoDB]_
3. _[Clonar o repositório na instância e configurar as variáveis de ambiente]_
4. _[Iniciar a API de ingestão, a API de consulta e o worker]_
5. _[Publicar o frontend no bucket S3 com hospedagem de site estático habilitada]_

---

## Documentação

| Artefato | Descrição |
|----------|-----------|
| [Entendimento do negócio](artefatos/entendimento_negocio.md) | Matriz de Oceano Azul, análise de riscos e oportunidades, Value Proposition Canvas |
| [Entendimento de UX](artefatos/entendimento_ux.md) | Personas, jornadas e decisões de experiência |
| [Requisitos](artefatos/requisitos.md) | Requisitos funcionais e não funcionais (ISO 25010) com planos de teste |
| [MVP inicial](artefatos/mvp-inicial.md) | Arquitetura, modelo de dados e documentação do código do protótipo |

---

## Padrões de contribuição

- **Documentação de código:** docstrings (PEP 257) em Python e JSDoc em JavaScript. Todo módulo tem cabeçalho descritivo e toda função documenta parâmetros, retorno e comportamento.
- **Commits:** mensagens descritivas, distribuídas ao longo da sprint.
- **Tags:** uma tag `SPRINTX` por entrega, criada na data de entrega da sprint.

---

## Licença

<p>
  <img style="height:22px!important;margin-left:3px;vertical-align:text-bottom;" src="https://mirrors.creativecommons.org/presskit/icons/cc.svg?ref=chooser-v1" alt="Creative Commons">
  <img style="height:22px!important;margin-left:3px;vertical-align:text-bottom;" src="https://mirrors.creativecommons.org/presskit/icons/by.svg?ref=chooser-v1" alt="Attribution">
</p>

<p xmlns:cc="http://creativecommons.org/ns#" xmlns:dct="http://purl.org/dc/terms/">
  <a property="dct:title" rel="cc:attributionURL" href="https://git.inteli.edu.br/graduacao/2026-2a/t15/g04">Aplicação Escalável em Sistemas Distribuídos - Globo</a>
  by
  <a rel="cc:attributionURL dct:creator" property="cc:attributionName" href="https://www.inteli.edu.br/">Inteli</a>,
  Christian Vinícius Gandra dos Santos,
  Diego Figueiredo Silva,
  Gabriel Willian Bartmanovicz,
  Lívia Sabóia Tavares,
  Lorenzo Ferrari Aggio,
  Luiz Gustavo Borges Oliveira,
  Nicole Riedla Paiva Neves e
  Vinícius de Castro Cadena
  is licensed under
  <a href="https://creativecommons.org/licenses/by/4.0/?ref=chooser-v1" target="_blank" rel="license noopener noreferrer" style="display:inline-block;">Attribution 4.0 International</a>.
</p>
