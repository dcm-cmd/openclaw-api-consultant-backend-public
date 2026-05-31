#!/bin/bash
# ============================================================
# openclaw-api-consultant 部署切换脚本
# ============================================================
# 用法: bash deploy.sh <sandbox|nosandbox> <state目录>
# 示例: bash deploy.sh sandbox <project-root>/state
#       bash deploy.sh nosandbox <project-root>/state
# ============================================================
set -e

MODE="${1:?用法: bash deploy.sh <sandbox|nosandbox> <state目录>}"
STATE_DIR="${2:?用法: bash deploy.sh <sandbox|nosandbox> <state目录>}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_DIR="${STATE_DIR}/workspace/consultant-main"

echo "=== openclaw-api-consultant 部署 ==="
echo "模式: $MODE"
echo "State 目录: $STATE_DIR"

# 1. 复制 openclaw.json
cp "${SCRIPT_DIR}/openclaw.${MODE}.json" "${STATE_DIR}/openclaw.json"
echo "✓ openclaw.json → openclaw.${MODE}.json"

# 2. 更新 SKILL.md 路径
if [ "$MODE" = "sandbox" ]; then
  # 沙箱模式: data/company/ → /data/company/
  for skill in "${WORKSPACE_DIR}/skills/"*/SKILL.md; do
    [ -f "$skill" ] && sed -i 's|data/company/|/data/company/|g' "$skill"
  done
  echo "✓ SKILL.md 路径 → /data/company/"
else
  # 无沙箱模式: /data/company/ → data/company/
  for skill in "${WORKSPACE_DIR}/skills/"*/SKILL.md; do
    [ -f "$skill" ] && sed -i 's|/data/company/|data/company/|g' "$skill"
  done
  echo "✓ SKILL.md 路径 → data/company/"
fi

# 3. 沙箱模式额外检查
if [ "$MODE" = "sandbox" ]; then
  echo ""
  echo "=== 沙箱前置检查 ==="

  # 检查 Docker CLI
  if docker --version &>/dev/null; then
    echo "✓ Docker CLI: $(docker --version)"
  else
    echo "✗ Docker CLI 未安装。请将 docker 二进制放入容器 /usr/local/bin/"
  fi

  # 检查 mount --bind
  if mount | grep -q '/home/node/.openclaw/workspace/consultant-main/data'; then
    echo "✓ data 目录绑定挂载已存在"
  else
    echo "⚠ 需要以 root 执行绑定挂载："
    echo "  sudo mkdir -p /home/node/.openclaw/workspace/consultant-main"
    echo "  sudo mount --bind $(realpath "${WORKSPACE_DIR}/data") /home/node/.openclaw/workspace/consultant-main/data"
  fi

  # 检查沙箱镜像
  if docker image inspect openclaw-sandbox:bookworm-slim &>/dev/null; then
    echo "✓ 沙箱镜像: openclaw-sandbox:bookworm-slim"
  else
    echo "⚠ 沙箱镜像不存在，请构建："
    echo "  echo -e 'FROM debian:bookworm-slim\nRUN apt-get update && apt-get install -y --no-install-recommends python3 && rm -rf /var/lib/apt/lists/*' | docker build -t openclaw-sandbox:bookworm-slim -f - ."
  fi

  # 检查 docker.sock
  if [ -S /var/run/docker.sock ] && [ -r /var/run/docker.sock ]; then
    echo "✓ docker.sock 可用"
  else
    echo "⚠ docker.sock 不可访问，请：chmod 0666 /var/run/docker.sock"
  fi
fi

echo ""
echo "=== 部署完成 ==="
echo "重启 OpenClaw 使配置生效"
