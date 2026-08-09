# Setup Guide

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) installed and running
- Git

## Quick Setup

```bash
git clone https://github.com/yespon/prism-os.git
cd prism-os
make config
docker compose up -d
```

Open http://localhost:2026. Log in with username `admin` — you'll be prompted to set your email and password on first login. Then add models via the admin UI (**Settings → Models**).

For a step-by-step guide, see [QUICKSTART.md](../../QUICKSTART.md).

## Local Development (without Docker)

```bash
make check    # Verify prerequisites (Node.js 22+, pnpm, uv, nginx)
make install  # Install all dependencies
make dev      # Start development servers at http://localhost:2026
```

## Where config.yaml Goes

`config.yaml` should be in the project root directory (`prism-os/config.yaml`). The backend searches in this order:

1. `PRISMOS_CONFIG_PATH` environment variable
2. `backend/config.yaml`
3. `prism-os/config.yaml` (recommended)

> Models, MCP servers, and skills are managed through the admin UI and stored in the database. Do **not** put them in `config.yaml` for production use.

## Sandbox Setup

If using Docker-based sandbox (default in `config.example.yaml`), pre-pull the sandbox image:

```bash
make setup-sandbox
```

Otherwise the image is pulled automatically on first agent execution (may take a few minutes).

## Bootstrap Admin

On first startup, a platform admin user is created automatically:
- Username: `admin`
- No pre-set email or password
- First login prompts you to set email and password
- After setup, you can log in with either the username or email

If you lose access, run:
```bash
cd backend
PYTHONPATH=. uv run python scripts/reset_admin_password_explicit.py
```

## Troubleshooting

### Config file not found
```bash
# Check where the backend looks
cd backend && python -c "from deerflow.config.app_config import AppConfig; print(AppConfig.resolve_config_path())"
```

### Permission denied
```bash
chmod 600 config.yaml
```

### Docker sandbox fails
Ensure Docker is running and the sandbox image is pulled: `make setup-sandbox`

## See Also

- [Configuration Guide](CONFIGURATION.md)
- [Architecture Overview](ARCHITECTURE.md)
- [Quick Start (5 min)](../../QUICKSTART.md)
