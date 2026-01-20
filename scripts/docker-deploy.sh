#!/bin/bash
# Docker deployment script for local-mem

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

usage() {
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  build    Build Docker image"
    echo "  up       Start containers (detached)"
    echo "  down     Stop containers"
    echo "  logs     Show container logs"
    echo "  restart  Restart containers"
    echo "  full     Start with MCP server included"
    echo "  clean    Remove containers and images"
    echo "  status   Show container status"
    echo ""
}

build() {
    echo -e "${GREEN}Building Docker image...${NC}"
    docker compose build
}

up() {
    echo -e "${GREEN}Starting local-mem...${NC}"
    docker compose up -d
    echo -e "${GREEN}✓ local-mem is running at http://localhost:8080${NC}"
}

down() {
    echo -e "${YELLOW}Stopping local-mem...${NC}"
    docker compose down
}

logs() {
    docker compose logs -f
}

restart() {
    down
    up
}

full() {
    echo -e "${GREEN}Starting local-mem with MCP server...${NC}"
    docker compose --profile full up -d
    echo -e "${GREEN}✓ Web UI: http://localhost:8080${NC}"
    echo -e "${GREEN}✓ MCP Server: http://localhost:3000${NC}"
}

clean() {
    echo -e "${YELLOW}Removing containers and images...${NC}"
    docker compose down --rmi local -v
    echo -e "${GREEN}✓ Cleanup complete${NC}"
}

status() {
    docker compose ps
}

case "${1:-}" in
    build)
        build
        ;;
    up)
        build
        up
        ;;
    down)
        down
        ;;
    logs)
        logs
        ;;
    restart)
        restart
        ;;
    full)
        build
        full
        ;;
    clean)
        clean
        ;;
    status)
        status
        ;;
    *)
        usage
        exit 1
        ;;
esac
