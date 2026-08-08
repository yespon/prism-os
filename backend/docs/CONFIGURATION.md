# Configuration Guide

## What Goes in config.yaml

`config.yaml` handles **platform-level infrastructure** settings only. It is NOT where you configure models, MCP servers, or skills — those are managed through the admin UI and stored in the database.

### config.yaml Sections

| Section            | Purpose                                                                 |
| ------------------ | ----------------------------------------------------------------------- |
| `config_version`   | Schema version tracking for `make config-upgrade`                       |
| `log_level`        | Logging level for PrismOS modules                                       |
| `database`         | Database connection strings (SQLite/PostgreSQL for tenant and auth DBs) |
| `sandbox`          | Sandbox provider (local or Docker-based)                                |
| `title`            | Auto conversation title generation settings                             |
| `summarization`    | Context summarization triggers and retention                            |
| `memory`           | User context and conversation history persistence                       |
| `checkpointer`     | LangGraph state persistence (memory/sqlite/postgres)                    |

## Models

**Models are configured via the admin UI** — not in `config.yaml`.

1. Log in as platform admin
2. Go to **Settings → Models**
3. Pick a provider template from the dropdown (OpenAI, Anthropic, DeepSeek, Gemini, Ollama, etc.)
4. Enter your API key
5. The model is saved to the database and available to all tenants

The `models:` field in `config.yaml` is a bootstrap fallback for when no models exist in the database yet (e.g., very first startup with no admin setup). For production, keep it as `models: []`.

## Database

```yaml
database:
  type: sqlite
  url: sqlite+aiosqlite:///./data/tenant.db
  echo: false
  auth:
    type: sqlite
    url: sqlite+aiosqlite:///./data/auth.db
```

**PostgreSQL** (for production):

```yaml
database:
  type: postgres
  url: postgresql+asyncpg://user:pass@host:5432/tenant_db
  auth:
    type: postgres
    url: postgresql+asyncpg://user:pass@host:5432/auth_db
```

The `db-init` Docker service runs `alembic upgrade head` before gateway and langgraph start. Better Auth tables are created automatically on first user registration.

## Sandbox

Two modes:

**Local** (development, simpler):

```yaml
sandbox:
  use: LocalSandboxProvider
```

**Docker** (production, isolated):

```yaml
sandbox:
  use: AioSandboxProvider
  image: enterprise-public-cn-beijing.cr.volces.com/vefaas-public/all-in-one-sandbox:latest
  port: 8080
  container_prefix: prismos-sandbox
  replicas: 3
```

## Title Generation

```yaml
title:
  enabled: true
  max_words: 6
  max_chars: 60
  model_name: null  # uses the conversation's model
```

## Summarization

```yaml
summarization:
  enabled: true
  model_name: null  # uses the conversation's model
  trigger:
    - type: tokens
      value: 15564
  keep:
    type: messages
    value: 10
  trim_tokens_to_summarize: 15564
```

## Memory

```yaml
memory:
  enabled: true
  storage_path: memory.json
  debounce_seconds: 30
  model_name: null
  max_facts: 100
  fact_confidence_threshold: 0.7
  injection_enabled: true
  max_injection_tokens: 2000
```

## Checkpointer

```yaml
checkpointer:
  type: sqlite
  connection_string: checkpoints.db
```

**PostgreSQL** (multi-process, production):

```yaml
checkpointer:
  type: postgres
  connection_string: postgresql://user:password@localhost:5432/prismos
```

<br />
