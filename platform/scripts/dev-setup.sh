#!/usr/bin/env bash
# Nexus AI – Development Setup Script
# Usage: bash platform/scripts/dev-setup.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "=== Nexus AI Dev Setup ==="

# 1. Create .env if missing
if [ ! -f .env ]; then
  cp .env.example .env
  # Generate a random JWT secret
  JWT=$(openssl rand -hex 32 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(32))")
  sed -i.bak "s/change_me_generate_with_openssl_rand_hex_32/$JWT/" .env && rm -f .env.bak
  echo "✓ Created .env — fill in POSTGRES_PASSWORD, REDIS_PASSWORD, MINIO_ACCESS_KEY, MINIO_SECRET_KEY, OPENAI_API_KEY"
else
  echo "✓ .env already exists"
fi

# 2. Check Docker
if ! command -v docker &>/dev/null; then
  echo "✗ Docker not found. Install Docker Desktop: https://docs.docker.com/get-docker/"
  exit 1
fi
echo "✓ Docker found: $(docker --version)"

# 3. Check Docker Compose
if ! docker compose version &>/dev/null; then
  echo "✗ Docker Compose v2 not found."
  exit 1
fi
echo "✓ Docker Compose found: $(docker compose version)"

echo ""
echo "=== Ready ==="
echo "Edit .env with your credentials, then run:"
echo "  docker compose up --build"
echo ""
echo "Services will be available at:"
echo "  App:       http://localhost"
echo "  API:       http://localhost/api/v1"
echo "  Grafana:   http://localhost/grafana"
echo "  MinIO:     http://localhost:9001  (dev only)"
