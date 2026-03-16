# CookHero 交接包：密钥/Token/配置整理（给接手同事）

> 目的：让接手同事不需要反复问“缺什么 key、在哪配、怎么验证”，拿到必要权限后即可直接继续开发、部署与排障。  
> 安全原则：**不要在聊天/邮件/Issue/PR/commit 里粘贴任何密钥**；建议使用密码管理器或加密文件安全交付。

---

## 0. 你需要先给同事开的权限

1. **GitHub 仓库权限**
   - 至少 `read`（拉代码），建议 `write`（修复、合并、触发 CI）
2. **Vercel 项目权限（前端）**
   - 可查看/编辑 Environment Variables
   - 可触发 Deploy / 查看 Deploy Logs
3. **Render 项目权限（后端）**
   - 可查看/编辑 Environment Variables
   - 可查看 Deploy Logs / Restart 服务
4. **第三方服务账号/Key（按需）**
   - LLM Provider（fast/normal/vision）
   - Reranker Provider（SiliconFlow rerank）
   - Tavily（Web Search）
   - imgbb（图片持久化）
   - 高德（AMAP/MCP，若使用）

> 说明：本项目生产链路是 **Vercel(前端) 同域代理 `/api/v1/*` → Render(后端)**，不依赖 SSH 部署。

---

## 1. “不要交接私钥”的 SSH 约定（非常重要）

### 1.1 GitHub 拉代码（推荐做法）

- **不要把你自己的私钥 `~/.ssh/id_*` 交给别人。**
- 接手同事应自行生成 SSH key，并把 **公钥** 添加到 GitHub：

```bash
ssh-keygen -t ed25519 -C "teammate@example.com"
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
cat ~/.ssh/id_ed25519.pub
```

可选的 `~/.ssh/config` 示例（如公司网络/多账号）：

```sshconfig
Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_ed25519
  IdentitiesOnly yes
```

### 1.2 如果你有额外的服务器 SSH（可选）

本仓库文档没有使用 SSH 上线流程；如果你个人额外维护了云主机/跳板机，请单独提供下面信息（不要给私钥）：

- 服务器用途：
- Host/IP：
- 端口：
- 用户名：
- 认证方式：建议改为“同事自己的公钥 + 你在服务器上加到 `authorized_keys`”
- `~/.ssh/config` 示例：

---

## 2. 生产地址与固定链路（给同事快速定位）

当前仓库文档记录的示例地址（可能会随时间变更，以平台控制台为准）：

- 前端（Vercel）：见 `docs/LOCAL_CONFIG_MEMORY.md`
- 后端（Render）：见 `docs/LOCAL_CONFIG_MEMORY.md`
- API 路由策略：
  - 前端请求基地址：`VITE_API_BASE=/api/v1`
  - Vercel 同域代理：`frontend/vercel.json` 把 `/api/v1/*` 转发到 Render 后端

快速验证命令（不需要登录）：

```bash
# 代理是否生效（应返回 JSON 401，而不是 HTML）
curl -i https://<VERCEL_DOMAIN>/api/v1/health

# 后端是否存活
curl -i https://<RENDER_DOMAIN>/
```

---

## 3. 配置与密钥总清单（最核心）

### 3.1 本地开发（local）如何配置

1. 复制环境变量模板：

```bash
cp .env.example .env
```

2. 按需填入 `.env`（不要提交到 git）
3. 启动依赖（可选）：`cd deployments && docker-compose up -d`
4. 启动后端：`uvicorn app.main:app --reload --port 8000`
5. 启动前端：`cd frontend && npm install && npm run dev`

> `.env.example` 是“变量名与用途”的单一真相来源，缺什么先看它。

### 3.2 生产环境（Render / Vercel / GitHub Actions）如何配置

下面按“在哪里配置”整理（同事只要照表补齐即可）。

#### A) Render（后端）环境变量

| 变量名 | 用途 | 必需 | 在哪用 | 备注 |
|---|---|---:|---|---|
| `DATABASE_URL` | Postgres 连接串 | 生产建议必需 | `app/config/config_loader.py` | 优先级最高；也兼容分字段配置 |
| `JWT_SECRET_KEY` | 登录 token 签名密钥 | 必需 | `app/main.py` + auth | Render 可 `generateValue`；要稳定不要频繁变 |
| `LLM_API_KEY` | 主 LLM key（normal） | 取决于功能 | LLM 调用 | 用于主回答生成 |
| `FAST_LLM_API_KEY` | fast tier key（可回落） | 建议 | LLM 调用 | 未配置时可回落 `LLM_API_KEY` |
| `VISION_API_KEY` | vision tier key（可回落） | 可选 | `app/vision/*` | 不配置则视觉能力不可用 |
| `RERANKER_API_KEY` | reranker key | 建议 | `app/rag/rerankers/*` | 未配则可能降级/禁用精排 |
| `WEB_SEARCH_API_KEY` | Tavily key | 可选 | `app/tools/web_search.py` | 开启 web_search 时需要 |
| `OPENAI_IMAGE_API_KEY` | 图片生成 key（OpenAI-compatible） | 可选 | `app/agent/tools/common/image_generator.py` | base_url 见 `config.yml` |
| `IMGBB_STORAGE_API_KEY` | 图片上传持久化 | 可选 | `app/utils/image_storage.py` | 用于上传用户图/生成图 |
| `MCP_DIET_SERVICE_KEY` | 内置 diet-adjust MCP 鉴权 | 取决于功能 | MCP / smoke | 当前演示值见 `render.yaml`/`docs/LOCAL_CONFIG_MEMORY.md`，生产应换强随机并轮换 |
| `CORS_ALLOW_ORIGINS` | CORS allowlist | 必需 | `app/main.py` | 包含本地与 Vercel 域名 |
| `CORS_ALLOW_ORIGIN_REGEX` | 允许 Vercel preview | 建议 | `app/main.py` | 默认会放行 `*.vercel.app` |
| `RATE_LIMIT_ENABLED` | 限流开关 | 可选 | `app/security/middleware/rate_limiter.py` | 演示环境常设 false |

> Render 的推荐基线配置写在 `DEPLOYMENT_GUIDE.md`、`docs/OPS_RUNBOOK.md`、`render.yaml`。

#### B) Vercel（前端）环境变量

| 变量名 | 用途 | 必需 | 在哪用 | 备注 |
|---|---|---:|---|---|
| `VITE_API_BASE` | API base path | 必需 | `frontend/src/constants/index.ts` | 生产推荐固定 `/api/v1`（同域代理） |

#### C) GitHub Actions Secrets（CI 烟测/同步）

| Secret 名称 | 用途 | 必需 | 在哪用 | 备注 |
|---|---|---:|---|---|
| `PROD_FRONTEND_URL` | 前端生产地址 | 建议 | `.github/workflows/prod-smoke.yml` | 用于 smoke |
| `PROD_BACKEND_URL` | 后端生产地址 | 建议 | `.github/workflows/prod-smoke.yml` | 用于 smoke |
| `SMOKE_USERNAME` | 烟测账号 | 可选 | `scripts/smoke-prod.sh` | 严格模式需要 |
| `SMOKE_PASSWORD` | 烟测密码 | 可选 | `scripts/smoke-prod.sh` | 严格模式需要 |
| `MCP_DIET_SERVICE_KEY` | MCP 鉴权 key | 取决于功能 | smoke + sync | 与 Render env 对齐 |
| `RENDER_API_KEY` | Render API key | 可选 | `.github/workflows/cloud-config-sync.yml` | 用于自动回填 Render env |
| `RENDER_SERVICE_ID` / `RENDER_SERVICE_NAME` | Render 服务定位 | 可选 | cloud-config-sync | 推荐用 ID 更稳定 |

---

## 4. 接手同事的“最小可运行”与“全功能运行”

### 4.1 最小可运行（不依赖外部 AI Key）

目标：能启动前后端并跑通基础页面与 API（可能缺少 AI 功能）。

- 后端可启动（健康检查可用）
- 前端可访问（登录页/页面路由）
- 数据库可用（SQLite 模式即可）

### 4.2 全功能运行（需要外部 Key）

要让以下能力可用，需要把对应 key 配齐：

- LLM 对话：`LLM_API_KEY`（建议同时给 `FAST_LLM_API_KEY`）
- Vision 多模态：`VISION_API_KEY`
- Web Search：`WEB_SEARCH_API_KEY`
- Rerank：`RERANKER_API_KEY`
- 图片生成与持久化：`OPENAI_IMAGE_API_KEY` + `IMGBB_STORAGE_API_KEY`
- MCP diet-adjust：`MCP_DIET_SERVICE_KEY`（以及后端 MCP 配置）

---

## 5. 验收与排障（交接时建议跑一遍）

### 5.1 本地（local）快速验收

1. 后端接口文档：`http://localhost:8000/docs`
2. 前端：`http://localhost:5173`
3. 关键链路：登录 -> 对话 -> Agent -> 饮食管理 -> 统计/评估页

### 5.2 生产（prod）快速验收

参考：

- `QUICK_START.md`
- `DEPLOYMENT_GUIDE.md`
- `docs/OPS_RUNBOOK.md`

并建议执行：

```bash
FRONTEND_URL=https://<VERCEL_DOMAIN> \
BACKEND_URL=https://<RENDER_DOMAIN> \
./scripts/smoke-prod.sh
```

---

## 6. 安全交付建议（你如何把这些“真密钥值”交给同事）

推荐交付方式（从高到低）：

1. 共享密码库（1Password/Bitwarden 等）创建一个“CookHero”条目：
   - 分字段保存：LLM keys、Render key、Tavily key、imgbb key、DB URL 等
2. 加密文件交付（例如使用 `age`/GPG）：
   - 提供 `cookhero.env.enc`，同事用自己的私钥解密得到 `.env`
3. 临时一次性渠道（例如企业 IM 的“阅后即焚”），交付后立即轮换

交付后建议做的“清理/轮换”：

- 如这些 key 绑定到个人账户：建议创建团队账号或在供应商侧为同事新建 key
- Render/Vercel/GitHub 权限：移交后按需下掉你的个人权限或降权

---

## 7. 参考文件（同事找不到时可直接看这里）

- `.env` 模板：`.env.example`
- 部署指南：`DEPLOYMENT_GUIDE.md`
- 快速部署参考：`QUICK_START.md`
- 运维手册：`docs/OPS_RUNBOOK.md`
- 本地/演示固定记忆：`docs/LOCAL_CONFIG_MEMORY.md`
- Vercel 代理：`frontend/vercel.json`
- Render 基线：`render.yaml`
- CI：
  - `.github/workflows/prod-smoke.yml`
  - `.github/workflows/cloud-config-sync.yml`

