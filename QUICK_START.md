# CookHero 快速部署参考（阶段二）

## 目标

在 5-10 分钟内确认生产链路可持续工作：

- Git push 到 `main` 可触发 Vercel 自动部署
- 前端走 `/api/v1` 同域代理访问 Render
- 烟测脚本可验证核心登录后链路

## 1. 一次性配置（仅需做一次）

### 1.1 Vercel 项目

确认以下配置:

- Git Repository: `Jonnys-Li/cookhero-collab-20260215`
- Production Branch: `main`
- Root Directory: `frontend`
- Install Command: `npm ci`
- Build Command: `npm run build`
- Output Directory: `dist`
- Env (Production + Preview):
- 若无法绑定仓库，先安装并授权 Vercel GitHub App: `https://github.com/apps/vercel`

```bash
VITE_API_BASE=/api/v1
```

### 1.2 Render 后端

确认关键变量:

```bash
CORS_ALLOW_ORIGINS=https://frontend-one-gray-39.vercel.app,http://localhost:5173
CORS_ALLOW_ORIGIN_REGEX=^https://.*\.vercel\.app$
JWT_SECRET_KEY=<稳定强随机值>
```

## 2. 标准发布

1. 合并代码到 `main`
2. 等待 Vercel 自动部署
3. 执行快速验证

## 3. 快速验证命令

```bash
# 前端代理是否生效（应返回 JSON 401，而不是 HTML）
curl -i https://frontend-one-gray-39.vercel.app/api/v1/health

# 登录路由是否命中后端（GET 应返回 405）
curl -i https://frontend-one-gray-39.vercel.app/api/v1/auth/login

# 后端根路径是否可用（应返回 200）
curl -i https://cookhero-collab-20260215.onrender.com/
```

## 4. 脚本验证

### 4.1 后端连通脚本

```bash
bash scripts/test-connection.sh \
  https://cookhero-collab-20260215.onrender.com \
  https://frontend-one-gray-39.vercel.app
```

### 4.2 生产烟测脚本

需要准备 smoke 账号:

```bash
FRONTEND_URL=https://frontend-one-gray-39.vercel.app \
BACKEND_URL=https://cookhero-collab-20260215.onrender.com \
SMOKE_USERNAME=<smoke_user> \
SMOKE_PASSWORD=<smoke_password> \
./scripts/smoke-prod.sh
```

## 5. GitHub Actions 监控

工作流: `.github/workflows/prod-smoke.yml`

触发方式:

- `push` 到 `main`
- 手动触发 `workflow_dispatch`
- 定时（每 30 分钟）

需要配置 Secrets:

- `PROD_FRONTEND_URL`
- `PROD_BACKEND_URL`
- `SMOKE_USERNAME`
- `SMOKE_PASSWORD`

## 6. 应急发布

仅当 Git 自动部署异常时使用:

```bash
cd frontend
vercel --prod --yes
```

发布后必须补跑烟测。

## 7. 详细文档

- 完整部署说明: `DEPLOYMENT_GUIDE.md`
- 运维执行手册: `docs/OPS_RUNBOOK.md`
