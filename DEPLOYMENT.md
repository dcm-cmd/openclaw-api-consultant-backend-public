# OpenClaw API Consultant Backend 容器部署方案

本文档面向以下目标：

- 后端使用 Docker Compose 部署。
- 代码目录挂载在宿主机外部，后续改代码后只需重启容器即可生效。
- PostgreSQL 数据目录也放在宿主机，便于备份、迁移和排障。

## 1. 部署方式说明

当前仓库的部署思路是“宿主机目录 + 通用 Python 容器”：

- 后端容器通过本仓库内的 `Dockerfile` 构建，镜像里预装 Python 依赖。
- 宿主机项目目录整体挂载到容器内 `/app`。
- 平时只改代码的话，执行一次 `docker compose restart backend` 即可生效。
- 如果修改了 `requirements.txt`，需要执行 `docker compose build backend && docker compose up -d backend`。

这套方式适合当前项目处于持续迭代、经常直接改代码，但又不希望每次重启重新安装依赖的场景。

## 2. 推荐目录规划

推荐把项目放在固定目录，例如：

```bash
/srv/openclaw-api-consultant-backend/
```

项目部署后的关键目录如下：

```bash
openclaw-api-consultant-backend/
├─ app/                       # 后端源码
├─ sql/                       # 数据库初始化脚本
├─ runtime/postgres/          # PostgreSQL 数据目录，宿主机持久化
├─ docker/
│  ├─ backend/
│  │  ├─ Dockerfile           # 后端镜像
│  │  ├─ docker-compose.yml   # 后端 + DB + db-api 编排
│  │  └─ .env.example         # 环境变量模板
│  └─ openclaw-gateway/
│     └─ docker-compose.yml   # Gateway 编排
├─ .dockerignore
└─ .env                        # 实际运行配置（gitignored）
```

如果后端需要返回 OpenClaw 的真实回答文本，而不仅仅是接收 `runId`，还需要把 OpenClaw 的会话落盘目录只读挂载到后端容器。当前 `docker/backend/docker-compose.yml` 已按默认路径处理：

```bash
../openclaw-api-consultant/state -> /openclaw-state
```

如果你的实际目录不同，就在 `.env` 里改 `BACKEND_OPENCLAW_STATE_HOST_PATH`。

## 3. 前置条件

部署机器需要满足：

- 已安装 Docker 和 Docker Compose 插件。
- 目标 OpenClaw Gateway 已可访问。
- 已准备稳定的 `OPENCLAW_HOOKS_TOKEN`。

如果 OpenClaw 与本后端部署在同一台宿主机，但不在同一个 Compose 网络中，建议使用：

```bash
OPENCLAW_BASE_URL=http://host.docker.internal:18889
```

当前 `docker/backend/docker-compose.yml` 已加入：

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

这样 Linux Docker 容器可以访问宿主机服务。

如果你的 Docker 版本较老，不支持 `host-gateway`，则把 `OPENCLAW_BASE_URL` 改成宿主机实际 IP 即可。

### 当前环境判断

按当前机器上的目录和 Compose 配置来看：

- `openclaw-api-consultant` 使用自己的默认网络 `openclaw-api-consultant_default`。
- `openclaw-api-consultant-backend` 使用自己的默认网络 `openclaw-api-consultant-backend_default`。
- 这两个项目当前默认不在同一个 Compose 网络中。

这不影响部署后端，因为后端可以通过：

```bash
OPENCLAW_BASE_URL=http://host.docker.internal:18889
```

访问宿主机上的 OpenClaw Gateway。

如果你后面明确想让两个项目通过容器名直接互通，再单独补一个共享 external network 即可；对当前部署目标来说，这不是前置条件。

## 4. 部署步骤

### 4.1 放置代码

如果当前机器已经有目录，直接使用现有目录即可；否则把仓库放到目标目录：

```bash
cd /srv
git clone <你的仓库地址> openclaw-api-consultant-backend
cd /srv/openclaw-api-consultant-backend
```

### 4.2 准备环境变量

复制模板并修改：

```bash
cp docker/backend/.env.example .env
nano .env
```

建议至少修改以下变量：

```env
OPENCLAW_BASE_URL=http://host.docker.internal:18889
OPENCLAW_HOOKS_TOKEN=替换为真实 token
OPENCLAW_AGENT_ID=consultant-main
BACKEND_OPENCLAW_STATE_DIR=/openclaw-state
BACKEND_OPENCLAW_STATE_HOST_PATH=../openclaw-api-consultant/state
BACKEND_OPENCLAW_SESSION_POLL_INTERVAL_SECONDS=1.0
BACKEND_OPENCLAW_SESSION_TIMEOUT_SECONDS=60
JWT_SECRET=替换为高强度随机字符串

POSTGRES_DB=openclaw_consultant
POSTGRES_USER=postgres
POSTGRES_PASSWORD=替换为强密码
DATABASE_URL=postgresql+asyncpg://postgres:强密码@db:5432/openclaw_consultant

BACKEND_BIND=0.0.0.0
BACKEND_PORT=8000
```

说明：

- `DATABASE_URL` 在容器内部必须使用 `db` 作为数据库主机名，不能写 `127.0.0.1` 或 `localhost`。
- `BACKEND_OPENCLAW_STATE_HOST_PATH` 是宿主机上的 OpenClaw `state` 目录，后端通过它读取会话 transcript 和 trajectory，才能拿到真实回答文本。
- `BACKEND_OPENCLAW_STATE_DIR` 是这个目录在后端容器里的挂载点，通常不用改。
- 当前需求是局域网直接访问，因此建议使用 `BACKEND_BIND=0.0.0.0`。
- 如果机器同时对公网开放，请务必配合安全组、iptables、ufw 或上层网关限制来源网段。

### 4.3 启动服务

首次启动执行：

```bash
docker compose build backend
docker compose up -d
```

说明：

- PostgreSQL 首次启动时会自动执行 `sql/init.sql`。
- 数据库文件会落在宿主机的 `runtime/postgres/`。
- 后端代码目录直接来自宿主机当前项目目录。
- 后端依赖在 `docker compose build backend` 阶段安装，后续普通重启不再重复安装。
- OpenClaw 的 `state` 目录会只读挂载进后端容器，后端用它轮询本次会话的最终文本和错误信息。

### 4.4 查看状态

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f db
```

## 5. 日常更新方式

### 5.1 修改 Python 代码

直接修改宿主机中的源码，例如：

```bash
vim app/main.py
```

修改完成后重启后端容器：

```bash
docker compose restart backend
```

因为 `/app` 是宿主机挂载目录，所以容器会读取最新代码。

### 5.2 修改依赖

如果改了 `requirements.txt`，同样执行：

```bash
docker compose build backend
docker compose up -d backend
```

普通 `docker compose restart backend` 不会重新安装依赖；只有重新构建镜像时才会同步新的 Python 依赖。

### 5.3 更新数据库结构

如果只是第一次部署，`sql/init.sql` 会自动执行。

如果后续已经有旧数据，再修改 `sql/init.sql` 不会自动重新执行。此时应使用手动 SQL 变更或迁移脚本，不要指望重启数据库容器自动生效。

## 6. 备份与恢复建议

建议重点备份两个位置：

- `runtime/postgres/`
- `.env`

如需迁移服务器，最简单的方式是：

1. 停止容器。
2. 打包整个项目目录。
3. 在新机器恢复项目目录。
4. 执行 `docker compose up -d`。

## 7. 反向代理建议

如果要对外提供接口，建议使用 Nginx 或现有网关反代到：

```bash
127.0.0.1:8000
```

这样可以把 TLS、域名、访问控制统一收敛到网关层，而不是直接暴露 FastAPI 端口。

## 8. 局域网直接访问说明

如果你的目标是让同一局域网中的其他机器直接访问：

### 8.1 访问后端 API

后端保持以下配置即可：

```env
BACKEND_BIND=0.0.0.0
BACKEND_PORT=8000
```

启动后，局域网其他机器可访问：

```bash
http://服务器局域网IP:8000
```

### 8.2 访问 OpenClaw Gateway

Gateway 项目的 `docker-compose.yml` 已改为支持宿主机监听地址变量：

```env
OPENCLAW_HOST_BIND=0.0.0.0
OPENCLAW_GATEWAY_PORT=18889
OPENCLAW_BRIDGE_PORT=18890
```

如果 `.env` 里没有写 `OPENCLAW_HOST_BIND`，当前默认也会按 `0.0.0.0` 绑定。重启后生效：

```bash
cd /home/ubuntu/openclaw-api-consultant
docker compose up -d
```

重启后，局域网其他机器可访问：

```bash
http://服务器局域网IP:18889
```

### 8.3 防火墙检查

除了 Compose 绑定地址，还需要确认宿主机防火墙已放行：

- `8000/tcp`，用于后端 API。
- `18889/tcp`，用于 OpenClaw Gateway。
- `18890/tcp`，如果 Bridge 端口也要在局域网使用。

## 9. 常见问题

### 8.1 后端容器连不上 OpenClaw

优先检查：

- `OPENCLAW_BASE_URL` 是否写成了容器内可访问地址。
- OpenClaw 是否真的监听在对应端口。
- Hooks Token 是否正确。

如果 OpenClaw 在宿主机上，不要在容器里写 `http://127.0.0.1:18889`，应优先写：

```bash
http://host.docker.internal:18889
```

如果健康接口正常，但 `/api/chat/stream` 一直只有空结果，还要检查：

- `BACKEND_OPENCLAW_STATE_HOST_PATH` 是否指向真实的 OpenClaw `state` 目录。
- 该目录下是否存在 `agents/<agent_id>/sessions/sessions.json`。
- 后端容器内的 `BACKEND_OPENCLAW_STATE_DIR` 是否与 compose 挂载目标一致。

### 8.2 后端容器连不上数据库

优先检查：

- `.env` 里的 `DATABASE_URL` 主机名是否为 `db`。
- `POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_DB` 是否与数据库容器一致。
- 是否是旧数据目录里残留了不兼容配置。

### 8.3 修改代码后没有生效

检查顺序：

- 是否修改的是当前部署目录中的文件。
- 是否执行了 `docker compose restart backend`。
- 修改是否命中了实际运行路径。
- 是否存在 Python 依赖变化但容器尚未重启。

### 8.4 聊天接口返回上游限流或空结果

如果 `/api/chat/stream` 直接返回上游错误，优先检查：

- OpenClaw 侧模型账号是否可用。
- transcript/trajectory 中是否已经记录了 `errorMessage`。
- 当前 agent 是否真的有输出文本，还是只产生了失败事件。

## 10. 推荐运维命令

```bash
docker compose up -d
docker compose restart backend
docker compose logs -f backend
docker compose logs -f db
docker compose down
```

## 11. 联调脚本

仓库里已附带一个最小联调脚本：

```bash
./verify_chat_flow.sh
```

它会完成以下动作：

- 检查 `/health`
- 确保测试用户存在
- 生成本机 JWT
- 调用 `/api/chat/stream`
- 查询消息落库结果