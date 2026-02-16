# CookHero 生产部署指南（阶段二）

本指南统一当前线上发布机制，目标是让生产部署具备可持续、可回归、可排障能力。

## 1. 生产架构

```text
Browser
  -> https://frontend-one-gray-39.vercel.app
  -> /api/v1/* (same-origin)
  -> frontend/vercel.json route proxy
  -> https://cookhero-collab-20260215.onrender.com/api/v1/*
```

关键点:

- 前端生产环境默认 `VITE_API_BASE=/api/v1`
- API 请求统一走前端同域路径，再由 Vercel 代理转发到 Render
- 不建议在生产前端直接配置 Render 绝对地址，避免配置分叉

## 2. 仓库与发布源收敛

### 2.1 标准发布源

- GitHub 仓库: `Jonnys-Li/cookhero-collab-20260215`
- 生产分支: `main`

### 2.2 Vercel 项目绑定要求

在 Vercel Project Settings 中确认:

1. Git Repository 绑定为 `Jonnys-Li/cookhero-collab-20260215`
2. Production Branch 为 `main`
3. Production Domain 包含 `frontend-one-gray-39.vercel.app`

若绑定仓库时报错提示需要 GitHub integration:

- 先安装 Vercel GitHub App: `https://github.com/apps/vercel`
- 确认该 App 对目标仓库 `Jonnys-Li/cookhero-collab-20260215` 有访问权限

## 3. Vercel 前端配置标准

在 Vercel 项目中统一如下配置:

- Root Directory: `frontend`
- Install Command: `npm ci`
- Build Command: `npm run build`
- Output Directory: `dist`

环境变量（Production + Preview）:

```bash
VITE_API_BASE=/api/v1
```

说明:

- `frontend/vercel.json` 已配置 `/api/v1/(.*)` 转发到 Render 后端。
- 该策略可确保前端代码在本地和生产都使用统一 API 相对路径。

## 4. Render 后端配置标准

Render Web Service 建议配置:

- Runtime: Python
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

关键环境变量:

```bash
PYTHON_VERSION=3.12.7
JWT_SECRET_KEY=<强随机字符串>
RATE_LIMIT_ENABLED=false
CORS_ALLOW_ORIGINS=https://frontend-one-gray-39.vercel.app,http://localhost:5173
CORS_ALLOW_ORIGIN_REGEX=^https://.*\.vercel\.app$
RAG_INIT_ON_STARTUP=false
MCP_STARTUP_TIMEOUT_SECONDS=15
METADATA_CACHE_TIMEOUT_SECONDS=20
LLM_API_KEY=<secret>
FAST_LLM_API_KEY=<secret>
VISION_API_KEY=<secret>
WEB_SEARCH_API_KEY=<secret>
AMAP_API_KEY=<secret>
```

## 5. 标准发布流程（推荐）

1. 代码合并到 `main`
2. Vercel 自动触发生产部署
3. 等待部署完成
4. 执行自动或手工烟测（见第 7 节）

## 6. 应急回退流程（仅异常时使用）

适用场景:

- Git push 未触发 Vercel 自动部署
- 紧急修复需立即发布，且 Git 集成短时不可用

执行命令:

```bash
cd frontend
vercel --prod --yes
```

注意:

- 该方式是应急手段，不替代标准 Git 自动发布。
- 发布后必须执行烟测，确认代理链路仍正常。

## 7. 验收与联调检查

### 7.1 快速验证命令

```bash
# 1) 前端代理是否命中后端鉴权层（应返回 JSON 401）
curl -i https://frontend-one-gray-39.vercel.app/api/v1/health

# 2) 登录路由是否命中后端（GET 应返回 405）
curl -i https://frontend-one-gray-39.vercel.app/api/v1/auth/login

# 3) 后端根路径可用性
curl -i https://cookhero-collab-20260215.onrender.com/
```

### 7.2 脚本化验证

```bash
# 连接脚本（后端直连）
bash scripts/test-connection.sh \
  https://cookhero-collab-20260215.onrender.com \
  https://frontend-one-gray-39.vercel.app

# 生产烟测（需要 SMOKE_USERNAME / SMOKE_PASSWORD）
FRONTEND_URL=https://frontend-one-gray-39.vercel.app \
BACKEND_URL=https://cookhero-collab-20260215.onrender.com \
SMOKE_USERNAME=<smoke_user> \
SMOKE_PASSWORD=<smoke_password> \
./scripts/smoke-prod.sh
```

## 8. 监控策略（本阶段）

- 监控方式: GitHub Actions 定时烟测（每 30 分钟）
- 工作流文件: `.github/workflows/prod-smoke.yml`
- 当前策略: 监控优先，不立即升级 Render 付费方案

排查门槛:

- 单次失败: 记录并复查
- 连续 2 次失败: 进入人工排查
- 冷启动慢响应: 记录观察，不立即升级

## 9. 常见故障定位

### 9.1 访问 `/api/v1/*` 返回前端 HTML

原因:

- `frontend/vercel.json` 未生效或未部署到生产版本

处理:

1. 检查 Vercel 当前部署对应 commit 是否包含最新 `frontend/vercel.json`
2. 触发一次重新部署
3. 再次执行第 7 节验证命令

### 9.2 CORS 预检失败

原因:

- `CORS_ALLOW_ORIGINS` 未包含前端域名
- `CORS_ALLOW_ORIGIN_REGEX` 缺失或配置错误

处理:

1. 校验 Render 环境变量
2. 部署后重试 `OPTIONS` 请求

### 9.3 登录后受保护接口仍 401

原因:

- JWT 不正确或过期
- `JWT_SECRET_KEY` 变更导致旧 token 失效

处理:

1. 重新登录获取 token
2. 校验 Render 端 `JWT_SECRET_KEY` 是否稳定

## 10. 参考文档

- 运维执行手册: `docs/OPS_RUNBOOK.md`
- 快速部署参考: `QUICK_START.md`
