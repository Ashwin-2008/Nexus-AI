#!/usr/bin/env bash
# Nexus AI – Service Health Check
# Usage: bash platform/scripts/health-check.sh [base_url]

BASE_URL="${1:-http://localhost}"
API="$BASE_URL/api/v1"

PASS="\033[92m✓\033[0m"
FAIL="\033[91m✗\033[0m"
WARN="\033[93m!\033[0m"

ok=0
fail=0

check() {
  local name="$1"
  local url="$2"
  local expected="${3:-200}"
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$url" 2>/dev/null || echo "000")
  if [ "$code" = "$expected" ]; then
    echo -e "  $PASS $name ($code)"
    ((ok++))
  else
    echo -e "  $FAIL $name — expected $expected, got $code"
    ((fail++))
  fi
}

echo ""
echo "=== Nexus AI Health Check ==="
echo "    Base URL: $BASE_URL"
echo ""

check "Nginx gateway"          "$BASE_URL"
check "Backend API health"     "$API/health"
check "Frontend served"        "$BASE_URL/"

echo ""
echo "=== Results: $ok passed, $fail failed ==="
echo ""

[ "$fail" -eq 0 ] && exit 0 || exit 1
