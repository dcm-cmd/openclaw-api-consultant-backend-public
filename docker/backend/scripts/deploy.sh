#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DOCKER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_DIR="$(cd "$DOCKER_DIR/.." && pwd)"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()  { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

check_prereqs() {
    log "检查依赖 ..."
    command -v docker >/dev/null 2>&1 || err "请先安装 Docker"
    docker compose version >/dev/null 2>&1 || err "需要 Docker Compose v2"
    log "依赖检查通过"
}

check_env() {
    log "检查 .env ..."
    if [ ! -f "$PROJECT_DIR/.env" ]; then
        if [ -f "$PROJECT_DIR/.env.example" ]; then
            cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
            log "已从 .env.example 创建 .env，请编辑后重新运行"
            echo "  vim $PROJECT_DIR/.env"
            exit 0
        else
            err "未找到 .env 或 .env.example"
        fi
    fi

    local missing=()
    grep -q "OPENCLAW_HOOKS_TOKEN=REPLACE" "$PROJECT_DIR/.env" 2>/dev/null && missing+=("OPENCLAW_HOOKS_TOKEN")
    grep -q "JWT_SECRET=REPLACE" "$PROJECT_DIR/.env" 2>/dev/null && missing+=("JWT_SECRET")
    grep -q "POSTGRES_PASSWORD=REPLACE" "$PROJECT_DIR/.env" 2>/dev/null && missing+=("POSTGRES_PASSWORD")

    if [ ${#missing[@]} -gt 0 ]; then
        warn "以下变量尚未替换真实值:"
        for m in "${missing[@]}"; do echo "  - $m"; done
        warn "请编辑 $PROJECT_DIR/.env"
        exit 1
    fi
    log ".env 已就绪"
}

create_dirs() {
    log "创建数据目录 ..."
    mkdir -p "$PROJECT_DIR/runtime/postgres"
    log "数据目录已就绪"
}

build_and_start() {
    log "构建镜像 ..."
    cd "$DOCKER_DIR"
    docker compose build backend

    log "启动服务 ..."
    docker compose up -d

    log "等待服务就绪 ..."
    sleep 8
    docker compose ps
    echo ""

    log "健康检查:"
    curl -fsS "http://127.0.0.1:${BACKEND_PORT:-8000}/health" 2>/dev/null \
        && log "后端健康检查通过" \
        || warn "后端未就绪，查看日志: docker compose -f $DOCKER_DIR/docker-compose.yml logs --tail=50"
}

main() {
    echo ""
    echo "============================================"
    echo "  OpenClaw API Consultant Backend 部署"
    echo "  项目目录: $PROJECT_DIR"
    echo "============================================"
    echo ""

    check_prereqs
    create_dirs
    check_env
    build_and_start

    echo ""
    log "部署完成"
    echo "  API 文档: http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo '服务器IP'):${BACKEND_PORT:-8000}/docs"
    echo "  查看日志: cd $DOCKER_DIR && docker compose logs -f"
    echo "  停止服务: bash $SCRIPT_DIR/stop.sh"
}

main "$@"
