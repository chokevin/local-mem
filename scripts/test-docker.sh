#!/bin/bash
# Test mem changes against Docker server
# Run this before closing any bead that modifies mem

set -e

echo "=== Testing mem Docker server ==="

# Rebuild and restart
echo "1. Rebuilding Docker image..."
docker compose build 2>&1 | tail -3

echo "2. Restarting container..."
docker compose down 2>/dev/null || true
docker compose up -d

echo "3. Waiting for server..."
for i in {1..30}; do
    if curl -sf http://localhost:8080/api/workstreams > /dev/null 2>&1; then
        break
    fi
    sleep 1
done

echo "4. Running tests..."

# Test API endpoints
echo -n "   GET /api/workstreams: "
STATUS=$(curl -sf -o /dev/null -w "%{http_code}" http://localhost:8080/api/workstreams)
[ "$STATUS" = "200" ] && echo "✓ OK" || { echo "✗ FAIL ($STATUS)"; exit 1; }

# Count workstreams
COUNT=$(curl -sf http://localhost:8080/api/workstreams | python3 -c "import sys,json; print(len(json.load(sys.stdin)))")
echo "   Workstreams in DB: $COUNT"

# Test health-ish endpoint (list works as health check)
echo -n "   Server responsive: "
curl -sf http://localhost:8080/api/workstreams > /dev/null && echo "✓ OK" || { echo "✗ FAIL"; exit 1; }

echo ""
echo "=== All tests passed ==="
