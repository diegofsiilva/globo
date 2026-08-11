<p align="center">
  <img src="assets/inteli-logo.png" alt="Inteli" width="180"/>
  &nbsp;&nbsp;&nbsp;&nbsp;
  <img src="assets/grupoglobo.png" alt="Grupo Globo" width="180"/>
</p>

# _[Nome do Projeto]_

**Sistema distribuído de telemetria para diagnóstico de degradação de streaming**

**Grupo 04** — Turma T15 · 2026-2A · Parceiro: **Grupo Globo**

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

A cadeia de entrega do Globoplay (player, CDN, backend, identidade, catálogo) é monitorada em silos: cada área tem seu próprio painel e vocabulário de métricas, o que faz com que a triagem de um incidente consuma mais tempo para descobrir *quem* conserta do que para de fato consertar — e degradações que não geram erro (buffer alto, tempo de início ruim) sequer acendem os alertas atuais. A solução é um sistema distribuído de telemetria com API única de ingestão, normalização dos eventos sob vocabulário comum, pipeline assíncrono de alta escala e camada de consulta que devolve uma linha do tempo única do incidente com o recorte afetado explícito, permitindo identificar a causa provável em minutos e sem depender de um especialista por componente.

---

## Arquitetura

```
signal_point ──> loader ──> API de ingestão (Flask) ──> SQS ──> worker ──> DynamoDB ──> API de consulta (Flask) ──> dashboard
```

| Camada | Responsabilidade | Serviço AWS |
|--------|------------------|-------------|
| API de ingestão | Recebe eventos via HTTP (`POST /events`), valida e publica na fila | EC2 |
| Fila de mensagens | Absorve picos de requisições e desacopla ingestão do processamento | SQS |
| Worker | Consome a fila e grava os eventos como itens no banco | EC2 |
| Banco de dados | Armazenamento não relacional dos sinais (`telemetry_signals`) | DynamoDB |
| API de consulta | Filtragem e ordenação dos sinais (`GET /events`) | EC2 |
| Dashboard | Visualização final | S3 (site estático) |

Detalhamento completo em [`/artefatos/mvp-inicial.md`](artefatos/mvp-inicial.md).

---

## Estrutura de pastas

| Pasta / Arquivo | Conteúdo |
|-----------------|----------|
| `/artefatos` | Documentação das sprints — entendimento de negócio, UX, requisitos e documentação técnica do MVP |
| `/apps` | Código das aplicações, organizado em subpastas |
| `/apps/basica` | Aplicação do MVP inicial: `api-ingestao`, `api-consulta`, `worker`, `loader` e `frontend` |
| `/slides` | Apresentações das sprints |
| `/assets` | Imagens e recursos usados na documentação |
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

_[a definir]_
