# PrismOS - Unified Development Environment

.PHONY: help config config-upgrade check install dev dev-daemon start stop up down clean docker-init docker-start docker-stop docker-logs docker-logs-frontend docker-logs-gateway

PYTHON ?= python3
BASH ?= bash

# Detect OS for Windows compatibility
ifeq ($(OS),Windows_NT)
    SHELL := cmd.exe
endif

help:
	@echo "PrismOS Development Commands:"
	@echo "  make config          - Generate local config files (skips files that already exist)"
	@echo "  make config-upgrade  - Merge new fields from config.example.yaml into config.yaml"
	@echo "  make check           - Check if all required tools are installed"
	@echo "  make install         - Install all dependencies (frontend + backend)"
	@echo "  make setup-sandbox   - Pre-pull sandbox container image (recommended)"
	@echo "  make dev             - Start all services in development mode (with hot-reloading)"
	@echo "  make dev-daemon      - Start all services in background (daemon mode)"
	@echo "  make start           - Start all services in production mode (optimized, no hot-reloading)"
	@echo "  make stop            - Stop all running services"
	@echo "  make clean           - Clean up processes and temporary files"
	@echo ""
	@echo "Docker Production Commands:"
	@echo "  make up              - Build and start production Docker services (localhost:2026)"
	@echo "  make up-nobuild      - Start production Docker services without rebuilding"
	@echo "  make down            - Stop and remove production Docker containers"
	@echo "  make rebuild-images  - Remove all PrismOS images and rebuild from scratch"
	@echo ""
	@echo "Docker Development Commands:"
	@echo "  make docker-init     - Pull the sandbox image"
	@echo "  make docker-start    - Start Docker services (mode-aware from config.yaml, localhost:2026)"
	@echo "  make docker-stop     - Stop Docker development services"
	@echo "  make docker-logs     - View Docker development logs"
	@echo "  make docker-logs-frontend - View Docker frontend logs"
	@echo "  make docker-logs-gateway - View Docker gateway logs"

config:
	@$(PYTHON) ./scripts/configure.py

config-upgrade:
	@./scripts/config-upgrade.sh

# Check required tools
check:
	@$(PYTHON) ./scripts/check.py

# Install all dependencies
install:
	@echo "Installing backend dependencies..."
	@cd backend && uv sync
	@echo "Installing frontend dependencies..."
	@cd frontend && pnpm install
	@echo "✓ All dependencies installed"
	@echo ""
	@echo "=========================================="
	@echo "  Optional: Pre-pull Sandbox Image"
	@echo "=========================================="
	@echo ""
	@echo "If you plan to use Docker/Container-based sandbox, you can pre-pull the image:"
	@echo "  make setup-sandbox"
	@echo ""

# Pre-pull sandbox Docker image (optional but recommended)
setup-sandbox:
	@echo "=========================================="
	@echo "  Pre-pulling Sandbox Container Image"
	@echo "=========================================="
	@echo ""
	@IMAGE=$$(grep -A 20 "# sandbox:" config.yaml 2>/dev/null | grep "image:" | awk '{print $$2}' | head -1); \
	if [ -z "$$IMAGE" ]; then \
		IMAGE="enterprise-public-cn-beijing.cr.volces.com/vefaas-public/all-in-one-sandbox:latest"; \
		echo "Using default image: $$IMAGE"; \
	else \
		echo "Using configured image: $$IMAGE"; \
	fi; \
	echo ""; \
	if command -v container >/dev/null 2>&1 && [ "$$(uname)" = "Darwin" ]; then \
		echo "Detected Apple Container on macOS, pulling image..."; \
		container pull "$$IMAGE" || echo "⚠ Apple Container pull failed, will try Docker"; \
	fi; \
	if command -v docker >/dev/null 2>&1; then \
		echo "Pulling image using Docker..."; \
		if docker pull "$$IMAGE"; then \
			echo ""; \
			echo "✓ Sandbox image pulled successfully"; \
		else \
			echo ""; \
			echo "⚠ Failed to pull sandbox image (this is OK for local sandbox mode)"; \
		fi; \
	else \
		echo "✗ Neither Docker nor Apple Container is available"; \
		echo "  Please install Docker: https://docs.docker.com/get-docker/"; \
		exit 1; \
	fi

# Start all services in development mode (with hot-reloading)
dev:
ifeq ($(OS),Windows_NT)
	@echo "Detected Windows - using Git Bash..."
	@$(BASH) ./scripts/serve.sh --dev
else
	@./scripts/serve.sh --dev
endif

# Start all services in production mode (with optimizations)
start:
ifeq ($(OS),Windows_NT)
	@echo "Detected Windows - using Git Bash..."
	@$(BASH) ./scripts/serve.sh --prod
else
	@./scripts/serve.sh --prod
endif

# Start all services in daemon mode (background)
dev-daemon:
	@./scripts/start-daemon.sh

# Stop all services
stop:
	@echo "Stopping all services..."
	@-pkill -f "langgraph dev" 2>/dev/null || true
	@-pkill -f "uvicorn app.gateway.app:app" 2>/dev/null || true
	@-pkill -f "next dev" 2>/dev/null || true
	@-pkill -f "next start" 2>/dev/null || true
	@-pkill -f "next-server" 2>/dev/null || true
	@-pkill -f "next-server" 2>/dev/null || true
	@-nginx -c $(PWD)/docker/nginx/nginx.local.conf -p $(PWD) -s quit 2>/dev/null || true
	@sleep 1
	@-pkill -9 nginx 2>/dev/null || true
	@echo "Cleaning up sandbox containers..."
	@-./scripts/cleanup-containers.sh prismos-sandbox 2>/dev/null || true
	@echo "✓ All services stopped"

# Clean up
clean: down
	@echo "Cleaning up..."
	@-rm -rf backend/.langgraph_api 2>/dev/null || true
	@-rm -rf logs/*.log 2>/dev/null || true
	@echo "Preserving PrismOS runtime data and database volumes. Use make clean-db only after a backup."
	@echo "✓ Cleanup complete"

# ==========================================
# Docker Development Commands
# ==========================================

# Initialize Docker containers and install dependencies
docker-init:
	@./scripts/docker.sh init

# Start Docker development environment
docker-start:
	@./scripts/docker.sh start

# Stop Docker development environment
docker-stop:
	@./scripts/docker.sh stop

# View Docker development logs
docker-logs:
	@./scripts/docker.sh logs

# View Docker development logs
docker-logs-frontend:
	@./scripts/docker.sh logs --frontend
docker-logs-gateway:
	@./scripts/docker.sh logs --gateway

# ==========================================
# Production Docker Commands
# ==========================================

# Build and start production services
up:
	@./scripts/deploy.sh

# Start production services without rebuilding
up-nobuild:
	@./scripts/deploy.sh --no-build

# Remove all PrismOS images and rebuild from scratch
rebuild-images:
	@./scripts/rebuild-images.sh

# Clean databases (supports both SQLite and PostgreSQL)
clean-db:
	@chmod +x ./scripts/clean-db.sh
	@./scripts/clean-db.sh

# Create PostgreSQL databases (reads config.yaml)
create-db:
	@chmod +x ./scripts/create-db.sh
	@./scripts/create-db.sh

# Stop and remove production containers
down:
	@./scripts/deploy.sh down


# Incremental Octop integration gates. Keep source-only imports distinct from runtime capability.
UV ?= uv
PNPM ?= pnpm
.PHONY: octop-verify octop-check octop-build octop-smoke octop-postgres octop-inventory octop-upgrade octop-compose
octop-verify:
	$(PYTHON) scripts/octop_sync.py verify
	$(PYTHON) scripts/octop_external.py verify
octop-check: octop-verify
	cd backend && $(UV) sync --locked
	cd backend && $(UV) run --locked pytest tests/test_octop_catalog_integrity.py tests/test_octop_integration.py tests/test_octop_presentation.py tests/test_octop_resources.py tests/test_octop_resource_installations.py tests/test_octop_skill_packages.py tests/test_skill_import_recovery.py tests/test_skill_resource_identity.py tests/test_skill_mutation_boundaries.py tests/test_skill_enablement_boundaries.py tests/test_skill_manual_creation.py tests/test_skill_resource_deletion.py tests/test_skill_reference_transactions.py tests/test_skills_installer.py tests/test_skills_scope_router.py tests/test_octop_inventory.py tests/test_octop_source_curation.py tests/test_octop_source_fetch.py tests/test_bootstrap_identity_schema.py tests/test_custom_agent.py tests/test_ticket_secret_admin_api.py tests/test_ticket_secret_provider.py tests/test_ticket_secret_migration_command.py -q
	cd backend && $(UV) run --locked python ../scripts/octop_inventory.py verify
	cd frontend && $(PNPM) typecheck
	cd frontend && $(PNPM) exec vitest run src/core/agents/catalog.test.ts src/components/workspace/agents/agent-presentation.test.tsx src/components/workspace/agents/agent-avatar.test.tsx src/server/demo-files.test.ts src/components/workspace/agents/agent-resource-preflight.test.tsx src/core/skills/imports.test.ts src/core/skills/mutations.test.ts src/core/skills/deletions.test.ts src/components/workspace/skills/skill-delete-control.test.tsx src/core/skills/hooks.test.tsx src/app/workspace/skills/\[name\]/page.test.tsx src/core/skills/import-context.test.tsx src/components/workspace/skills/skill-import-controls.test.tsx src/components/tenant-admin/tenant-admin-skills-page.test.tsx src/components/workspace/settings/skill-settings-page.test.tsx src/components/workspace/skills/skill-creation-flows.test.tsx src/components/workspace/skills/skill-creation-inspection.test.tsx --maxWorkers=2
octop-build: octop-check octop-smoke
	cd backend && $(UV) build --package prismos-octop-capabilities
	cd backend && $(UV) run --locked python ../scripts/octop_wheel_verify.py dist/prismos_octop_capabilities-0.1.0-py3-none-any.whl --sdist dist/prismos_octop_capabilities-0.1.0.tar.gz
	cd frontend && $(PNPM) build
octop-smoke: octop-verify
	cd backend && $(UV) run --locked python ../scripts/octop_gateway_smoke.py

# Explicit isolated database probe; requires Docker and a cached PostgreSQL image.
octop-postgres:
	cd backend && $(UV) run --locked python -m scripts.verify_ticket_secret_postgres

# Static item/dependency inventories; no upstream code or plugins are activated.
octop-inventory: octop-verify
	cd backend && $(UV) run --locked python ../scripts/octop_inventory.py verify

# Explicit, empty absolute evidence directories preserve earlier verification runs.
octop-upgrade:
	test -n "$(OCTOP_UPGRADE_DIR)"
	cd backend && $(UV) run --locked python ../scripts/octop_source_fetch.py --revision e473dd3c4a4741618ffde1a42a3492341a189e8e --release 0.3.0b5 --output-dir "$(OCTOP_UPGRADE_DIR)/previous"
	cd backend && $(UV) run --locked python ../scripts/octop_upgrade_probe.py --previous-archive "$(OCTOP_UPGRADE_DIR)/previous/upstream.tar.gz" --previous-receipt "$(OCTOP_UPGRADE_DIR)/previous/manifest.json" --previous-revision e473dd3c4a4741618ffde1a42a3492341a189e8e --previous-release 0.3.0b5 --output "$(OCTOP_UPGRADE_DIR)/upgrade.json"

# Uses production Dockerfiles/Compose; the smoke owns unique runtime resources.
octop-compose:
	test -n "$(OCTOP_COMPOSE_EVIDENCE)"
	docker build -f backend/Dockerfile -t prismos-octop-backend:verification .
	docker build -f frontend/Dockerfile --target prod -t prismos-octop-frontend:verification .
	cd backend && $(UV) run --locked python ../scripts/octop_compose_smoke.py --backend-image prismos-octop-backend:verification --frontend-image prismos-octop-frontend:verification --output-dir "$(OCTOP_COMPOSE_EVIDENCE)"

# Explicit owned PostgreSQL import/recovery probe; keeps execution facts untouched.
.PHONY: octop-skill-postgres
octop-skill-postgres:
	test -n "$(OCTOP_SKILL_PG_DIR)"
	cd backend && $(UV) run --locked python ../scripts/octop_skill_postgres.py --output-dir "$(OCTOP_SKILL_PG_DIR)"
