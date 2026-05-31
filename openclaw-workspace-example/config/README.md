# openclaw-api-consultant 配置

提供两套部署方案，通过 `deploy.sh` 切换。

## 方案对比

| | Sandbox | No Sandbox |
|---|---|---|
| **配置文件** | `openclaw.sandbox.json` | `openclaw.nosandbox.json` |
| **适用环境** | Linux 原生 Docker | Windows/Mac Docker Desktop |
| **隔离方式** | Docker 沙箱容器 | `workspaceOnly` + AGENTS.md |
| **data 可读** | 是（bind mount） | 是（workspace 内） |
| **系统文件保护** | 硬隔离（不进沙箱） | 软约束 + 输出过滤 |
| **SKILL.md 路径** | `/data/company/xxx.md` | `data/company/xxx.md` |
| **前置条件** | 见下方沙箱前置清单 | 无 |

## 部署

```bash
# 沙箱方案
bash config/deploy.sh sandbox <project-root>/state

# 无沙箱方案
bash config/deploy.sh nosandbox <project-root>/state
```

## 沙箱前置条件

Linux 宿主机需执行（仅一次）：

```bash
# 1. 创建路径映射（需 root）
sudo mkdir -p /home/node/.openclaw/workspace/consultant-main
sudo mount --bind <实际data目录> /home/node/.openclaw/workspace/consultant-main/data

# 2. 构建沙箱镜像
echo -e 'FROM debian:bookworm-slim\nRUN apt-get update && apt-get install -y --no-install-recommends python3 && rm -rf /var/lib/apt/lists/*' | docker build -t openclaw-sandbox:bookworm-slim -f - .

# 3. OpenClaw 容器内安装 Docker CLI
docker cp /usr/bin/docker <gateway-container>:/usr/local/bin/docker
docker exec -u root <gateway-container> chmod +x /usr/local/bin/docker

# 4. 修复 socket 权限
docker exec -u root <gateway-container> chmod 0666 /var/run/docker.sock

# 5. 在 docker-compose.yml 添加 docker.sock 挂载
#    volumes:
#      - /var/run/docker.sock:/var/run/docker.sock
```

## 安全模型

### Sandbox
```
请求 → Backend → OpenClaw → Agent（系统提示中有 MEMORY.md + skills）
                                ↓
                          Docker 沙箱容器
                          /data 只读挂载（业务资料）
                          /scripts 只读挂载（查询脚本）
                          AGENTS.md 等不进沙箱
                          exec 仅允许 python3 /scripts/query_db.py
                          ↓
                     PostgREST → PostgreSQL
```

### 数据库查询（CR-2026-0530-001）

沙箱内可通过 `exec` 工具执行 `/scripts/query_db.py` 查询 PostgreSQL：

```
用户问"最近订单量" → Agent exec python3 /scripts/query_db.py orders_total
  → 脚本请求 PostgREST API (db-api:3000)
  → 查询 business_metrics 表
  → Agent 分析 JSON 生成中文回复
```

前置条件：
- PostgREST 容器（`db-api`）在 docker-compose 中配置
- `api.business_metrics` 表已创建并有测试数据
- 沙箱加入 compose 网络
                          write/edit 禁用
```

### No Sandbox  
```
L1: tools.fs.workspaceOnly  → read 限制到 workspace
L2: AGENTS.md 安全规则      → 禁止读系统文件，拒绝后引导到业务
L3: 后端输出脱敏             → 80+ 指标检测，统一拒答
```
