# CookHero Ops Runbook（阶段二）

本 Runbook 面向生产发布与稳定性维护，目标是把“已联调可用”升级为“可持续交付”。

## 1. 生产基线

- 前端生产域名: `https://frontend-one-gray-39.vercel.app`
- 后端生产域名: `https://cookhero-collab-20260215.onrender.com`
- 前端 API 策略: `VITE_API_BASE=/api/v1`（通过 `frontend/vercel.json` 代理）
- 后端部署策略: Render Free（当前阶段仅监控，不升级付费）
- 自动监控: GitHub Actions `Production Smoke Test`（每 30 分钟）
- 自动修复: GitHub Actions `Cloud Config Sync`（push main / 手动触发）
- （可选）错误追踪: Sentry（后端 `SENTRY_DSN`，前端 `VITE_SENTRY_DSN`）

## 2. 标准发布流程（常规）

1. 开发完成后合并到 `main`（`Jonnys-Li/cookhero-collab-20260215`）。
2. 确认 Vercel 项目绑定仓库为 `Jonnys-Li/cookhero-collab-20260215` 且 Production Branch 为 `main`。
   - 若提示未安装 GitHub integration，先安装 `https://github.com/apps/vercel` 并授权目标仓库。
3. 等待 Vercel 自动部署完成。
4. 观察 GitHub Actions `Production Smoke Test` 是否通过。
5. 如 Smoke 失败，按第 6 节故障处置执行。

## 3. Vercel 配置标准（必须保持）

- Project Root Directory: `frontend`
- Install Command: `npm ci`
- Build Command: `npm run build`
- Output Directory: `dist`
- Environment Variables（Production + Preview）:
  - `VITE_API_BASE=/api/v1`
  - （可选）`VITE_SENTRY_DSN=<sentry_dsn>`
  - （可选）`VITE_SENTRY_TRACES_SAMPLE_RATE=0`

说明:
- 生产流量应由前端同域请求 `/api/v1/*`，再由 `frontend/vercel.json` 转发到 Render。
- 不将前端配置为直连 Render 绝对地址，避免配置分叉与排障复杂度上升。

## 4. 应急发布（仅在 Git 集成异常时）

触发条件:
- Vercel 未响应 Git push 自动部署。
- 紧急热修需要立即发布且 Git 集成暂时不可用。

命令:

```bash
cd frontend
vercel --prod --yes
```

执行后验证:
1. `GET https://frontend-one-gray-39.vercel.app/api/v1/health` 返回 JSON `401`。
2. 运行 `scripts/smoke-prod.sh`（默认演示稳定模式）或等待下一次 GitHub 定时烟测结果。
3. 发布前手工补跑一次严格模式:
   - `SMOKE_STRICT=true SMOKE_USERNAME=<smoke_user> SMOKE_PASSWORD=<smoke_password> ./scripts/smoke-prod.sh`

## 5. 手工烟测清单（10 分钟）

每次生产发布后至少执行 1 轮:

1. 打开 `https://frontend-one-gray-39.vercel.app/login`，使用测试账号登录成功。
2. 普通对话模式发送一条消息，确认返回正常（非空、非报错）。
3. Agent 模式发送一条消息，确认会话创建与响应正常。
4. 打开知识库页面，确认列表加载正常。
5. 打开饮食管理页面，确认页面正常加载且无接口报错。
6. 打开模型统计页面，确认页面可访问。
7. 打开评估监控页面，确认页面可访问。
8. 回到对话页面，确认历史会话可见。
9. 执行退出登录，确认会跳转到登录页。
10. 刷新任意已登录页面，确认未出现异常白屏或循环重定向。

## 6. 监控与故障处置规则

监控来源:
- GitHub Actions 工作流: `.github/workflows/prod-smoke.yml`
- 触发方式: `push main`、`workflow_dispatch`、每 30 分钟定时
- 默认运行模式: 演示稳定模式（`SMOKE_STRICT=false`，fail-open）

故障分级:
- 单次失败: 记录失败端点与状态码，人工复查一次。
- 连续 2 次失败: 进入人工排查流程（必须处理）。
- 冷启动导致的慢响应/超时: 记录并观察，不立即升级 Render 付费方案。

人工排查流程:
1. 在 Actions 日志中定位失败步骤（端点、状态码、响应头/响应体）。
2. 本地复现实验:
   - `scripts/smoke-prod.sh`
   - `scripts/test-connection.sh https://cookhero-collab-20260215.onrender.com https://frontend-one-gray-39.vercel.app`
3. 判断故障范围:
   - 仅前端代理异常（Vercel 路由/部署问题）
   - 仅后端异常（Render 服务不可用/启动失败）
   - 鉴权与配置异常（`JWT_SECRET_KEY`、CORS 等）
4. 根据根因执行修复并重新触发 `workflow_dispatch`。

## 7. GitHub Secrets 配置

在仓库 Settings -> Secrets and variables -> Actions 中设置:

- `PROD_FRONTEND_URL`
- `PROD_BACKEND_URL`
- `SMOKE_USERNAME`（仅严格模式必需）
- `SMOKE_PASSWORD`（仅严格模式必需）
- `MCP_DIET_SERVICE_KEY`（用于 MCP 鉴权与烟测）
- `RENDER_API_KEY`（用于自动回填 Render 环境变量）
- `RENDER_SERVICE_ID`（推荐）或 `RENDER_SERVICE_NAME`（兜底）

推荐值:

- `PROD_FRONTEND_URL=https://frontend-one-gray-39.vercel.app`
- `PROD_BACKEND_URL=https://cookhero-collab-20260215.onrender.com`
- `RENDER_SERVICE_NAME=cookhero-backend`

## 8. 云配置自动同步（新增）

- 工作流: `.github/workflows/cloud-config-sync.yml`
- 同步脚本: `scripts/sync-render-env.sh`
- 默认行为:
  1. 将 `MCP_DIET_SERVICE_KEY` 写入 Render 服务环境变量
  2. 可选触发一次 Render 部署
  3. 轮询验证 `POST /api/v1/mcp/diet-adjust` 的 `tools/list` 是否恢复可用
- 触发方式:
  - `push main` 自动触发
  - Actions 页面手工 `workflow_dispatch` 触发
- 本地手工执行（紧急排障）:

```bash
RENDER_API_KEY=<render_api_key> \
RENDER_SERVICE_ID=<render_service_id> \
MCP_DIET_SERVICE_KEY=<mcp_key> \
BACKEND_URL=https://cookhero-collab-20260215.onrender.com \
./scripts/sync-render-env.sh --trigger-deploy
```

- 说明:
  - `RENDER_SERVICE_ID` 更稳定，优先推荐。
  - 如仅提供 `RENDER_SERVICE_NAME`，脚本会先调用 Render API 解析 id。
  - 若缺少必需 secrets，工作流会给出 warning，不会进行同步。

## 9. 变更约束

- 本阶段不修改后端公开 API 路径与返回协议。
- 本阶段不引入额外付费监控服务。
- 本阶段不执行 Render 资源升级，仅通过监控与排查规则控制风险。

## 10. PR 合并门禁（新增）

为实现“失败不可合并”的质量门禁，需要在 GitHub 仓库设置中开启分支保护规则（这一步无法通过代码仓库自动完成）。

推荐设置:

1. GitHub -> Settings -> Branches -> Branch protection rules（对 `main` 生效）
2. 勾选 `Require status checks to pass before merging`
3. 将以下 checks 设为必需（名称以实际 Actions 展示为准）:
- `CI / Backend (pytest + coverage)`
- `CI / Frontend (lint + vitest)`

本地如何跑测试、覆盖率门禁如何查看/调整，可参考：
- `docs/TESTING_AND_QUALITY.md`
