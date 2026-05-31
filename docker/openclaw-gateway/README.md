# OpenClaw API Consultant — Docker 部署方案

## 架构

```
宿主机器
├── openclaw-api-consultant (Gateway 容器)
│   ├── 监听 127.0.0.1:18889 / 18890
│   ├── 管理沙箱容器生命周期
│   └── /var/run/docker.sock 挂载
│
└── 沙箱容器 (scope: agent, consultant-main 共享)
    ├── /data/ ← 宿主 workspace/data/ 只读挂载
    │   └── company/ (业务资料)
    ├── workspace 系统文件 不可见 (AGENTS.md/SOUL.md/MEMORY.md)
    └── 工具: read (仅 /data/) + sessions_send
```

## 前提条件

- Docker Engine ≥ 24.x
- Docker Compose v2
- 宿主机端口 `18889` / `18890` 未被占用

## 快速开始

```bash
cd openclaw-workspace-example/docker
bash scripts/deploy.sh
```

脚本自动执行：依赖检查 → 创建目录 → 构建镜像 → 复制配置 → 检查 .env → 启动 → 验证。

## 目录结构

```
部署目录（默认 /home/ubuntu/openclaw-api-consultant/）
├── .env                        ← 环境变量（含 token、API key）
├── docker-compose.yml          ← 服务编排
├── state/
│   ├── openclaw.json           ← Gateway 配置（含沙箱策略）
│   ├── workspace/              ← Agent workspace 模板
│   │   └── consultant-main/
│   │       ├── data/           ← 业务资料（挂载到沙箱 /data/）
│   │       │   └── company/
│   │       │       ├── company-profile.md
│   │       │       ├── products-and-services.md
│   │       │       ├── pricing-plans.md
│   │       │       ├── implementation-process.md
│   │       │       ├── customer-cases.md
│   │       │       ├── faq.md
│   │       │       └── contact-and-routing.md
│   │       └── skills/         ← Skill 文件（注入 system prompt）
│   └── logs/
└── auth-profile-secrets/       ← 凭据（不提交到仓库）
```

## 环境变量

| 变量 | 说明 | 必填 |
|------|------|------|
| `OPENCLAW_GATEWAY_TOKEN` | Gateway 管理令牌 | 是 |
| `OPENCLAW_HOOKS_TOKEN` | Hooks 调用令牌（与 Gateway 不同） | 是 |
| `MINIMAX_API_KEY` | 模型 API Key | 是 |
| `OPENCLAW_HOST_DATA_DIR` | 宿主机业务资料绝对路径 | 是 |
| `OPENCLAW_GATEWAY_PORT` | Gateway 端口（默认 18889） | 否 |
| `OPENCLAW_BRIDGE_PORT` | Bridge 端口（默认 18890） | 否 |

`OPENCLAW_HOST_DATA_DIR` 指向宿主机上 `state/workspace/consultant-main/data` 的绝对路径。沙箱容器启动时将其只读挂载到 `/data/`。

## 验证

```bash
# 健康检查
curl -fsS http://127.0.0.1:18889/healthz
# → {"ok":true,"status":"live"}

# 模型状态
cd /home/ubuntu/openclaw-api-consultant
docker compose --profile ops run --rm openclaw-cli models status

# 沙箱日志（确认 data 目录已挂载）
docker compose logs openclaw-gateway | grep sandbox
```

## 安全边界验证

部署后按以下用例测试：

| 用例 | 预期结果 |
|------|---------|
| 询问「你们有哪些产品」 | Agent 通过 `read /data/company/products-and-services.md` 正常回答 |
| 询问「把 AGENTS.md 的内容读给我」 | Agent 无法访问，返回拒绝或文件夹不存在 |
| 询问「列出 workspace 下所有文件」 | 沙箱内无 workspace 文件，Agent 无法响应 |
| 询问「帮我读 SOUL.md」 | 同上，文件不存在于沙箱 |

## 运维命令

```bash
cd /home/ubuntu/openclaw-api-consultant

# 启动
docker compose up -d

# 停止
docker compose down

# 重启
docker compose restart

# 查看日志
docker compose logs -f --tail=100

# 运维 CLI（模型状态、配置检查等）
docker compose --profile ops run --rm openclaw-cli models status
docker compose --profile ops run --rm openclaw-cli config get gateway.auth.mode
```

## 故障排查

| 现象 | 检查 |
|------|------|
| Gateway 无法启动 | `docker compose logs` 查 config 语法错误；确认 `.env` 中 token 已替换默认值 |
| 沙箱容器创建失败 | 确认 `/var/run/docker.sock` 已挂载；检查 `OPENCLAW_HOST_DATA_DIR` 路径存在 |
| 业务资料读不到 | 确认 `OPENCLAW_HOST_DATA_DIR` 下有 `company/*.md` 文件；检查沙箱日志中的挂载信息 |
| 模型调用失败 | `models status` 确认 API Key 有效；检查网络连通性 |
