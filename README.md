<p align="center">
  <img src="assets/inteli.png" alt="Inteli" height="60">
  &nbsp;&nbsp;&nbsp;&nbsp;
  <img src="assets/parceiro.png" alt="Grupo Globo" height="60">
</p>

# Argus — Monitoração Agêntica

**Grupo 4 · Turma 15 · Ciência da Computação · Módulo 7 · Inteli**

Projeto desenvolvido em parceria com o **Grupo Globo**.

## Integrantes

- Christian Santos
- Diego Silva
- Gabriel W. Bartmanovicz
- Livia Tavares
- Lorenzo Ferrari Aggio
- Luiz Gustavo Oliveira
- Nicole Neves
- Vinicius de Castro Cadena

## O projeto

Quando o streaming degrada, o time de operação do Globoplay hoje precisa de um
especialista por componente para descobrir onde está a falha: os sinais ficam
espalhados entre CDN, player, autorização e o próprio app, cada um no seu painel,
e correlacioná-los é trabalho manual que custa minutos caros em pleno incidente.
O Argus é uma plataforma de telemetria que recebe os eventos emitidos pelo app de
TV em qualquer escala, normaliza sob um vocabulário comum
(`request`, `vitals`, `screen_view`, `video_view`, `session`, `error`), grava sem
perda e devolve tudo numa linha do tempo única — o alicerce sobre o qual a camada
agêntica de correlação vai, em seguida, apontar a causa provável de um incidente
com o recorte afetado explícito.

## Estrutura do repositório

```
apps/basica/          a aplicação
  backend/            API de leitura (Flask em Lambda) — arquitetura hexagonal
  worker/             worker de ingestão (SQS → DynamoDB), em ECS Fargate
  frontend/           dashboard em Next.js, export estático servido por S3
  infra/              Terraform de toda a infraestrutura AWS
  tools/              conversão de CSV, replay de eventos e ETL do dump
  notebooks/          análise exploratória do dataset do parceiro
artefatos/            documentação do projeto
  assets/             imagens e diagramas
  postman/            coleção de testes das APIs
assets/               logos
Makefile              todos os comandos do projeto
```

`make` sozinho lista os alvos disponíveis.

## Documentação

| Documento | Conteúdo |
|---|---|
| [MVP inicial](artefatos/mvp-inicial.md) | o que está implantado, modelo de dados e relatório de testes |
| [Arquitetura](artefatos/arquitetura.md) | decisões técnicas e trade-offs |
| [Requisitos](artefatos/requisitos.md) | RF, RNF e critérios de verificação |
| [Entendimento de negócio](artefatos/entendimento_negocio.md) | matriz de valor, riscos e oportunidades |
| [Entendimento de UX](artefatos/entendimento_ux.md) | personas, protótipo e fluxo de investigação |

## Executar localmente

Requer **Python 3.12+**, **Node 20+** e **uv**. Em Codespaces ou VS Code, tudo o
que segue funciona sem configuração adicional.

```bash
git clone https://git.inteli.edu.br/graduacao/2026-2a/t15/g04.git
cd g04

cp .env.example .env    # preencha com os valores do terraform output
make install            # ambientes Python do backend e do worker
make test               # 58 testes do worker + 72 do backend
```

Para subir a API e o dashboard:

```bash
make api                # API de leitura local, contra o DynamoDB real
make frontend-install
make frontend-dev       # dashboard em http://localhost:3000
```

O backend também sobe por um único arquivo, sem `make`:

```bash
python apps/basica/backend/run.py
```

Esse ponto de entrada carrega o ambiente, cria a aplicação Flask e sobe o servidor;
na primeira execução ele instala as dependências sozinho. No VS Code, abra
`apps/basica/backend` como workspace, vá em **Run and Debug** e execute
**Backend Flask** — é o mesmo `run.py`. O Dev Container do serviço está em
`apps/basica/backend/.devcontainer`.

### Sem credenciais AWS

Os testes rodam contra um DynamoDB falso (moto), então `make test` e `make lint`
funcionam sem nenhuma configuração de nuvem. Só os alvos de operação
(`api`, `deploy`, `smoke`, `postman`) precisam do `.env` preenchido.

## Executar na AWS

As credenciais vêm do AWS Academy Learner Lab. Com o lab iniciado e o perfil
configurado:

```bash
cd apps/basica/infra
cp terraform.tfvars.example terraform.tfvars    # ajuste se necessário
terraform init && terraform apply

cd ../../..
make env                # gera o .env a partir dos outputs do Terraform
make deploy             # empacota e publica a API de leitura
make worker-deploy      # publica a imagem do worker no ECR
make frontend-deploy    # build do dashboard e sync no bucket S3
```

Verificação:

```bash
make smoke      # confere as rotas da API publicada
make postman    # roda a coleção de testes contra as duas APIs
make count      # conta os eventos armazenados
make dlq        # mostra os eventos rejeitados, com o motivo
```

Para economizar crédito do lab, `make pause` desliga o worker sem destruir nada e
`make resume` religa.

## Segredos

Nenhuma URL de API, ID de conta ou segredo é versionado. O `.env.example` mostra
as chaves e como obter os valores; o `.env` está no `.gitignore`. O mesmo vale
para o environment do Postman (`artefatos/postman/environment.example.json`).

## Qualidade

```bash
make check     # testes + ruff + terraform fmt/validate
make lint
make test
```
