# Backend image; Node/npm provide npx for MCP servers.
ARG NODE_MAJOR=22
FROM node:${NODE_MAJOR}-bookworm-slim AS node-runtime
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl build-essential libpq-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node-runtime /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

# Install Docker CLI (for DooD: allows starting sandbox containers via host Docker socket)
COPY --from=docker:cli /usr/local/bin/docker /usr/local/bin/docker

# Install uv from a pinned versioned image (avoids curl|sh from untrusted remote)
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /uvx /usr/local/bin/

# Set working directory
WORKDIR /app

COPY backend ./backend

# Install dependencies with cache mount
RUN --mount=type=cache,target=/root/.cache/uv \
    sh -c "cd backend && uv sync --locked"

# Expose ports (gateway: 8001, langgraph: 2024)
EXPOSE 8001 2024

# Default command (can be overridden in docker-compose)
CMD ["sh", "-c", "cd backend && PYTHONPATH=. uv run --frozen uvicorn app.gateway.app:app --host 0.0.0.0 --port 8001"]
