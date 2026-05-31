#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DOCKER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_ROOT="$(cd "$DOCKER_DIR/../.." && pwd)"

# ── 默认值 ──
DEPLOY_DIR="${DEPLOY_DIR:-/home/ubuntu/openclaw-api-consultant}"
IMAGE_NAME="${IMAGE_NAME:-openclaw-api-consultant:local}"

# ── 颜色 ──
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

log()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()  { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── 检查依赖 ──
check_prereqs() {
    log "检查运行依赖 ..."
    command -v docker >/dev/null 2>&1 || err "请先安装 Docker"
    docker compose version >/dev/null 2>&1 || err "需要 Docker Compose v2"
    log "依赖检查通过"
}

# ── 创建目录 ──
create_dirs() {
    log "创建部署目录 ..."
    mkdir -p "$DEPLOY_DIR/state/workspace/consultant-main/data/company"
    mkdir -p "$DEPLOY_DIR/state/workspace/consultant-main/skills"
    mkdir -p "$DEPLOY_DIR/state/logs"
    mkdir -p "$DEPLOY_DIR/auth-profile-secrets"
    log "目录创建完成"
}

# ── 构建镜像 ──
build_image() {
    log "构建 OpenClaw 镜像: $IMAGE_NAME ..."
    docker build -t "$IMAGE_NAME" -f "$DOCKER_DIR/Dockerfile" "$DOCKER_DIR"
    log "镜像构建完成"
}

# ── 复制配置文件 ──
copy_config() {
    local workspace_example="$DOCKER_DIR/../openclaw-workspace-example"

    log "复制配置文件 ..."
    cp "$DOCKER_DIR/docker-compose.yml" "$DEPLOY_DIR/"
    cp "$DOCKER_DIR/.env.example" "$DEPLOY_DIR/.env"

    # 从 workspace-example 复制 openclaw.json（如果存在）
    if [ -f "$DOCKER_DIR/../openclaw.json" ]; then
        cp "$DOCKER_DIR/../openclaw.json" "$DEPLOY_DIR/state/openclaw.json"
    elif [ -f "$workspace_example/openclaw.json" ]; then
        cp "$workspace_example/openclaw.json" "$DEPLOY_DIR/state/openclaw.json"
    else
        warn "未找到 openclaw.json，请手动放置到 $DEPLOY_DIR/state/"
    fi

    # 复制 workspace 文件
    if [ -d "$workspace_example/workspace" ]; then
        cp -r "$workspace_example/workspace/"* "$DEPLOY_DIR/state/workspace/consultant-main/"
    fi

    # 复制 data 目录到正确位置（相对于 workspace 根）
    if [ -d "$workspace_example/workspace/data" ]; then
        mkdir -p "$DEPLOY_DIR/state/workspace/data"
        cp -r "$workspace_example/workspace/data/"* "$DEPLOY_DIR/state/workspace/data/"
    fi

    log "配置文件复制完成"
}

# ── 检查 .env ──
check_env() {
    log "检查 .env 配置 ..."
    local missing=()

    grep -q "OPENCLAW_GATEWAY_TOKEN=REPLACE" "$DEPLOY_DIR/.env" 2>/dev/null \
        && missing+=("OPENCLAW_GATEWAY_TOKEN")
    grep -q "OPENCLAW_HOOKS_TOKEN=REPLACE" "$DEPLOY_DIR/.env" 2>/dev/null \
        && missing+=("OPENCLAW_HOOKS_TOKEN")
    grep -q "MINIMAX_API_KEY=REPLACE" "$DEPLOY_DIR/.env" 2>/dev/null \
        && missing+=("MINIMAX_API_KEY")

    if [ ${#missing[@]} -gt 0 ]; then
        warn "以下环境变量尚未替换真实值："
        for m in "${missing[@]}"; do
            echo "  - $m"
        done
        echo ""
        warn "请编辑 $DEPLOY_DIR/.env 并填入真实值后再启动"
        echo "  vim $DEPLOY_DIR/.env"
    else
        log ".env 配置已就绪"
    fi

    # 验证 OPENCLAW_HOST_DATA_DIR 指向的目录存在
    local data_dir
    data_dir=$(grep "^OPENCLAW_HOST_DATA_DIR=" "$DEPLOY_DIR/.env" 2>/dev/null | cut -d= -f2)
    if [ -z "$data_dir" ]; then
        warn "OPENCLAW_HOST_DATA_DIR 未配置，沙箱将无法挂载业务数据"
    elif [ ! -d "$data_dir" ]; then
        warn "OPENCLAW_HOST_DATA_DIR=$data_dir 目录不存在，请检查路径"
    else
        log "业务数据目录已就绪: $data_dir"
    fi
}

# ── 启动 ──
start_service() {
    log "启动 OpenClaw Gateway ..."
    cd "$DEPLOY_DIR"
    docker compose up -d openclaw-gateway
    log "等待服务就绪 ..."
    sleep 5
    docker compose ps
    echo ""
    log "健康检查:"
    curl -fsS "http://127.0.0.1:${OPENCLAW_GATEWAY_PORT:-18889}/healthz" 2>/dev/null \
        && log "Gateway 健康检查通过" \
        || warn "健康检查未通过，请检查日志: docker compose logs --tail=50"
}

# ── 验证 ──
verify() {
    log "首次验证 ..."
    cd "$DEPLOY_DIR"

    echo "  ✓ 容器状态:"
    docker compose ps

    echo "  ✓ Gateway 健康:"
    curl -fsS "http://127.0.0.1:${OPENCLAW_GATEWAY_PORT:-18889}/healthz" || true

    echo "  ✓ 模型状态:"
    docker compose --profile ops run --rm openclaw-cli models status 2>/dev/null || true

    echo "  ✓ 配置检查:"
    docker compose --profile ops run --rm openclaw-cli config get gateway.auth.mode 2>/dev/null || true
}

# ── 主流程 ──
main() {
    echo ""
    echo "============================================"
    echo "  OpenClaw API Consultant 部署"
    echo "  部署目录: $DEPLOY_DIR"
    echo "============================================"
    echo ""

    check_prereqs
    create_dirs
    build_image
    copy_config
    check_env
    start_service
    verify

    echo ""
    log "部署完成。部署目录: $DEPLOY_DIR"
    log "常用命令:"
    echo "  查看日志: cd $DEPLOY_DIR && docker compose logs -f"
    echo "  重启服务: cd $DEPLOY_DIR && docker compose restart"
    echo "  停止服务: cd $DEPLOY_DIR && docker compose down"
    echo "  运维工具: cd $DEPLOY_DIR && docker compose --profile ops run --rm openclaw-cli <command>"
}

main "$@"
