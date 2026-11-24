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
  sed -i.bak "s/^JWT_SECRET=$/JWT_SECRET=$JWT/" .env && rm -f .env.bak
  echo "✓ Created .env — fill in DATABASE_URL (Supabase), SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY,"
  echo "  REDIS_URL (Upstash), QDRANT_URL/QDRANT_API_KEY and OPENAI_API_KEY. See docs/DEPLOYMENT.md."
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
echo "  Grafana:   http://localhost/grafana   (optional local monitoring)"
echo "  Qdrant:    http://localhost:6333"
echo ""
echo "Documents are stored in Supabase Storage (SUPABASE_* in .env)."
