#!/usr/bin/env bash
set -e

cd "$(dirname "$0")/.."
source "./scripts/prismos-env.sh"

echo "Removing all PrismOS images..."
docker images --format '{{.Repository}}:{{.Tag}}' 2>/dev/null | grep '^prismos' | xargs -r docker rmi -f 2>/dev/null || true
docker images --filter "reference=prismos-*" -q 2>/dev/null | xargs -r docker rmi -f 2>/dev/null || true

echo ""
echo "Building images..."
echo ""

echo "[1/3] backend (gateway / langgraph / db-init)..."
docker build -t prismos-gateway:latest -f backend/Dockerfile .
docker tag prismos-gateway:latest prismos-langgraph:latest
docker tag prismos-gateway:latest prismos-db-init:latest

echo ""
echo "[2/3] frontend..."
docker build -t prismos-frontend:latest -f frontend/Dockerfile --target prod --build-arg NPM_REGISTRY=${NPM_REGISTRY:-https://registry.npmjs.org} .

echo ""
echo "[3/3] provisioner..."
docker build -t prismos-provisioner:latest -f docker/provisioner/Dockerfile docker/provisioner

echo ""
echo "✓ All images rebuilt"
