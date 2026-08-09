# Frontend Dockerfile
# Supports two targets:
#   --target dev   — install deps only, run `pnpm dev` at container start
#   --target prod  — full build baked in, run `pnpm start` at container start (default if no --target is specified)

ARG PNPM_STORE_PATH=/root/.local/share/pnpm/store
ARG NPM_REGISTRY=https://registry.npmjs.org

# ── Base: shared setup ────────────────────────────────────────────────────────
FROM node:22-alpine AS base
ARG PNPM_STORE_PATH
RUN corepack enable && corepack install -g pnpm@10.26.2
RUN pnpm config set store-dir ${PNPM_STORE_PATH}
WORKDIR /app
COPY frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml frontend/package.json frontend/.npmrc ./frontend/

# ── Dev: install only, CMD is overridden by docker-compose ───────────────────
FROM base AS dev
ARG NPM_REGISTRY
RUN cd /app/frontend && pnpm config set registry ${NPM_REGISTRY} && pnpm install --frozen-lockfile
COPY frontend ./frontend
EXPOSE 3000

# ── Builder: install + compile Next.js ───────────────────────────────────────
FROM base AS builder
ARG NPM_REGISTRY
ARG NEXT_PUBLIC_BACKEND_BASE_URL
ARG NEXT_PUBLIC_LANGGRAPH_BASE_URL
ENV NEXT_PUBLIC_BACKEND_BASE_URL=${NEXT_PUBLIC_BACKEND_BASE_URL}
ENV NEXT_PUBLIC_LANGGRAPH_BASE_URL=${NEXT_PUBLIC_LANGGRAPH_BASE_URL}
RUN cd /app/frontend && pnpm config set registry ${NPM_REGISTRY} && pnpm install --frozen-lockfile
COPY frontend ./frontend
RUN cd /app/frontend && SKIP_ENV_VALIDATION=1 pnpm build

# ── Prod: minimal runtime with pre-built output ───────────────────────────────
FROM node:22-alpine AS prod
ARG PNPM_STORE_PATH
RUN corepack enable && corepack install -g pnpm@10.26.2
RUN pnpm config set store-dir ${PNPM_STORE_PATH}
WORKDIR /app
COPY --from=builder /app/frontend ./frontend
EXPOSE 3000
CMD ["sh", "-c", "cd /app/frontend && pnpm start"]
