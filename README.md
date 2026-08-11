# Monitoração Agêntica - G04

Backend inicial em Flask para receber, normalizar, armazenar e consultar eventos de
telemetria de TVs, aplicações web e dispositivos móveis.

## Funcionalidades disponíveis

- ingestão de um evento ou lote em JSON;
- ingestão CSV, inclusive com objetos JSON escapados nas colunas;
- normalização dos seis eventos do MVP: `request`, `vitals`, `screen_view`,
  `video_view`, `session` e `error`;
- persistência transacional por um repositório independente do domínio;
- suporte a SQLite local e PostgreSQL por configuração;
- filtros cumulativos, paginação e sugestões de valores para filtros;
- pseudonimização de `user_id` e allowlist de cabeçalhos;
- health checks e respostas de erro no formato Problem Details.

## Executar com Docker

Requer Docker com Compose:

```bash
docker compose up --build
```

A API estará disponível em `http://localhost:5000`. O Compose inicia PostgreSQL,
aguarda o banco ficar saudável e então inicia a aplicação.

## Executar localmente

É necessário Python 3.12 ou superior. No Windows:

```powershell
.\backend\scripts\dev.ps1
```

Em Linux, macOS ou Codespaces:

```bash
sh ./backend/scripts/dev.sh
```

O script cria `.venv`, instala as dependências e inicia a API com SQLite. Copie
`backend/.env.example` para `backend/.env` se desejar personalizar a configuração.

No VS Code, abra **Run and Debug**, selecione **Backend Flask** e clique em **Run**.
O repositório também contém um Dev Container compatível com GitHub Codespaces.

## Exemplos da API

Enviar um evento:

```bash
curl -X POST http://localhost:5000/api/v1/events \
  -H "Content-Type: application/json" \
  -d '{
    "timestamp": "2026-07-13T20:04:44Z",
    "event_name": "request",
    "duration": 0.033,
    "app_env": "production",
    "device_os": "Tizen"
  }'
```

Consultar com filtros cumulativos:

```bash
curl "http://localhost:5000/api/v1/events?event_name=request&device_os=Tizen&page=1"
```

Consultar valores sugeridos para filtros:

```bash
curl "http://localhost:5000/api/v1/events/facets?field=event_name&field=device_os"
```

Consultar contagem e latência média por tipo de evento:

```bash
curl "http://localhost:5000/api/v1/metrics?app_env=production&device_os=Tizen"
```

Endpoints de operação:

```text
GET /health/live
GET /health/ready
```

## Configuração

| Variável | Padrão | Finalidade |
|---|---|---|
| `DATABASE_URL` | `sqlite:///instance/telemetry.db` | Conexão SQLAlchemy |
| `USER_ID_HASH_SALT` | somente desenvolvimento | Salt da pseudonimização |
| `MAX_CONTENT_LENGTH` | `2097152` | Limite do corpo em bytes |

Em ambiente compartilhado, `USER_ID_HASH_SALT` deve ser um segredo forte e nunca
deve ser versionado.

## Arquitetura

O código segue portas e adaptadores em quatro áreas:

```text
interfaces -> application -> domain
                    ^
                    |
             infrastructure
```

- `domain`: entidade e erros sem dependência de framework;
- `application`: normalização e casos de uso;
- `ports`: contratos dos repositórios;
- `infrastructure`: implementação SQLAlchemy;
- `interfaces`: API Flask e adaptação de JSON/CSV.

Para trocar o banco, implemente `EventRepository` e injete a implementação na
factory da aplicação. As regras de negócio e os casos de uso permanecem inalterados.

## Qualidade

Dentro de `backend`:

```bash
python -m pytest --cov=telemetry
ruff check .
ruff format --check .
```
