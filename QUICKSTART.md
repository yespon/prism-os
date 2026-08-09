# PrismOS Quick Start

[中文](./QUICKSTART_zh.md) | English

This guide starts a local PrismOS alpha instance with Docker. It gets you to a
first authenticated workspace; it does not create a production security
boundary for you.

## Prerequisites

- Docker Desktop or Docker Engine with Compose v2, running locally
- A model API key for a provider supported by the admin UI
- At least 8 GB of available memory is recommended for the core services

The default `LocalSandboxProvider` executes on the host. Review the sandbox
warning in [SECURITY.md](./SECURITY.md) before using untrusted code.

## 1. Clone and bootstrap configuration

```bash
git clone https://github.com/yespon/prism-os.git
cd prism-os
make config
```

`make config` creates local `config.yaml` and `frontend/.env` files only when
they do not already exist. Do not commit either file after adding credentials.

New deployments use `PRISMOS_*` variables and `backend/.prismos`. Existing
installations should read the [brand migration guide](./docs/migrations/prismos-brand-migration.md)
before changing a data path.

## 2. Start PrismOS

```bash
make up
```

This initializes the configured database, builds local images, and starts the
reverse proxy, frontend, gateway, and LangGraph services. Verify the gateway:

```bash
curl http://localhost:2026/health
```

Open <http://localhost:2026> in a browser.

## 3. Complete bootstrap setup

On first visit, use the setup wizard to create the initial administrator. The
bootstrap status endpoint can be inspected without logging in:

```bash
curl http://localhost:2026/api/auth/bootstrap-status
```

After setup, sign in and change temporary credentials immediately. Do not put
credentials or provider keys in an issue, terminal transcript, or committed
configuration file.

## 4. Add a model

From the administrator UI, open **Settings → Models**, select a provider
template, enter the API key and model name, and save it. Model records are
stored in the database and assigned to tenants; production model configuration
should not be placed in `config.yaml`.

## 5. Try the workspace

- Start a conversation and inspect generated artifacts.
- Upload a file and review the thread file flow.
- Create or import a Skill and use its sandbox testing flow.
- Configure an MCP server only after reviewing its command, network access,
  credentials, and tenant scope.
- Use **Settings** to manage users, tenants, models, Skills, MCP servers, and
  optional vertical plugins.

AI operations can be used as a validation scenario, but it is not required for
the platform to run and is not the architectural boundary of PrismOS.

## Container options

The first local deployment builds images from the repository. The planned alpha
release publishes a GHCR image for supported architectures:

```bash
docker pull ghcr.io/yespon/prism-os:v0.1.0-alpha.1
```

Use the exact tag from the release notes. PrismOS alpha releases do not publish
or imply a `latest` tag. The current Compose files build local service images;
release-specific notes describe the corresponding image consumption path.

## Development commands

```bash
make check                 # Check local prerequisites
make install               # Install uv and pnpm dependencies
make dev                   # Run local services with hot reload
make docker-init           # Prepare Docker development images
make docker-start          # Start Docker development mode
make docker-logs           # Follow Docker development logs
make stop                  # Stop local development processes
make down                  # Stop production Compose services
```

The public entry point remains <http://localhost:2026>. The gateway serves
`/api/*`; LangGraph traffic is exposed through `/api/langgraph/*`.

## Troubleshooting

### Health endpoint does not respond

```bash
docker compose ps
docker compose logs --tail=200 gateway langgraph nginx
```

If configuration came from an earlier checkout, verify `PRISMOS_CONFIG_PATH`
and the runtime data path. Use the migration guide before moving existing data.

### Model requests fail

Verify the provider key, base URL, model name, tenant assignment, and provider
availability from **Settings → Models**. The health endpoint only confirms
service availability; it does not validate an external model provider.

### Sandbox execution fails

The local sandbox runs on the host. For Docker mode, verify Docker socket access
and pull the configured sandbox image. For Kubernetes provisioner mode, review
the [provisioner guide](./docker/provisioner/README.md), kubeconfig mount, and
namespace permissions.

## Stop and reset

```bash
make down
```

`make clean` removes temporary development state and logs while preserving
PrismOS runtime data and database volumes. `make clean-db` is destructive;
back up data before using it.
