# CookHero 前后端联调部署指南

本指南将帮助你完成 Vercel (前端) 和 Render (后端) 的联调配置。

## 部署架构

```
┌─────────────────────────────┐
│   Vercel (前端)             │
│   frontend-xxx.vercel.app   │
│   React + Vite              │
└──────────┬──────────────────┘
           │
           │ HTTP Requests
           │ (Authorization Bearer token)
           ▼
┌─────────────────────────────┐
│   Render (后端)             │
│   cookhero-backend.onrender.com│
│   FastAPI + Python          │
└─────────────────────────────┘
```

## 步骤 1: 部署后端到 Render

### 1.1 准备代码

确保 `requirements.txt` 已更新（已完成），所有依赖都包含版本号。

### 1.2 在 Render 上创建 Web Service

1. 登录 [Render Dashboard](https://dashboard.render.com/)
2. 点击 **New** -> **Web Service**
3. 连接你的 Git 仓库
4. 配置如下：

| 配置项 | 值 |
|--------|-----|
| Name | `cookhero-backend` |
| Environment | `Python 3` |
| Region | 任意（推荐 Singapore） |
| Branch | `main` |
| Root Directory | `.` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |

### 1.3 配置环境变量

在 Render 的 Environment 部分添加以下环境变量：

| Key | Value | 说明 |
|-----|-------|------|
| `PYTHON_VERSION` | `3.12.7` | Python 版本 |
| `JWT_SECRET_KEY` | （生成随机字符串） | JWT 密钥 |
| `RATE_LIMIT_ENABLED` | `false` | 禁用速率限制（免费版无 Redis） |
| `CORS_ALLOW_ORIGINS` | `https://frontend-one-gray-39.vercel.app,http://localhost:5173` | CORS 允许的前端域名 |
| `LLM_API_KEY` | 你的 API 密钥 | LLM API 密钥 |
| `FAST_LLM_API_KEY` | 你的 API 密钥 | 快速模型 API 密钥 |
| `VISION_API_KEY` | 你的 API 密钥 | 视觉模型 API 密钥 |

### 1.4 部署

点击 **Create Web Service** 开始部署。

部署完成后，你将获得一个后端 URL，例如：
```
https://cookhero-backend.onrender.com
```

## 步骤 2: 配置前端连接后端

### 2.1 获取后端 URL

部署完成后，从 Render Dashboard 复制你的后端 URL。

### 2.2 在 Vercel 配置环境变量

1. 登录 [Vercel Dashboard](https://vercel.com/dashboard)
2. 找到你的前端项目
3. 进入 **Settings** -> **Environment Variables**
4. 添加以下环境变量：

| Key | Value | Environment |
|-----|-------|-------------|
| `VITE_API_BASE` | `https://cookhero-backend.onrender.com/api/v1` | Production, Preview |

**重要**: 将 `https://cookhero-backend.onrender.com` 替换为你的实际 Render 后端 URL。

### 2.3 触发重新部署

添加环境变量后，需要在 Vercel 触发一次重新部署：

1. 进入 **Deployments** 标签
2. 点击最新部署右侧的 **...** 菜单
3. 选择 **Redeploy**

## 步骤 3: 验证部署

### 3.1 检查后端健康状态

```bash
curl https://cookhero-backend.onrender.com/
```

应返回：
```json
{"message": "Welcome to CookHero API!"}
```

### 3.2 检查 API 文档

访问：
```
https://cookhero-backend.onrender.com/docs
```

应该能看到 FastAPI 的 Swagger 文档。

### 3.3 检查前端

访问你的 Vercel 前端 URL：
```
https://frontend-one-gray-39.vercel.app
```

打开浏览器开发者工具 (F12) -> Network 标签，尝试登录或发送请求，检查：
- 请求是否发送到正确的后端 URL
- 是否有 CORS 错误
- 是否有 401 Unauthorized 错误

## 常见问题排查

### 问题 1: CORS 错误

**错误**: `Access to fetch at ... has been blocked by CORS policy`

**解决方案**:
1. 检查后端 `CORS_ALLOW_ORIGINS` 是否包含前端 URL
2. 确认前端 URL 完全匹配（包括 https:// 和无尾部斜杠）

### 问题 2: 401 Unauthorized

**错误**: `{"detail": "需要登录"}` 或 `{"detail": "登录已失效"}`

**解决方案**:
1. 检查请求头是否包含 `Authorization: Bearer <token>`
2. 检查 `JWT_SECRET_KEY` 是否设置正确
3. 尝试重新登录获取新 token

### 问题 3: Render 部署失败

**常见原因**:
- 构建超时（免费版 15 分钟限制）
- 内存不足（免费版 512MB）

**解决方案**:
1. 检查 `requirements.txt` 中是否移除了不必要的重型依赖
2. 考虑升级到 Render Starter 计划 ($7/月)

### 问题 4: 前端无法连接后端

**检查步骤**:
1. 在浏览器 Console 执行: `console.log(import.meta.env.VITE_API_BASE)`
2. 确认显示的是完整的 Render 后端 URL
3. 如果是 `/api/v1`，说明 Vercel 环境变量未生效，需要重新部署

## 本地开发环境配置

本地开发时，前端使用 Vite proxy，无需配置额外环境变量：

```bash
# 后端（终端 1）
cd CookHero
uvicorn app.main:app --reload

# 前端（终端 2）
cd frontend
npm run dev
```

Vite proxy 会自动将 `/api/*` 请求转发到 `http://localhost:8000`。

## 环境变量配置汇总

### 后端 (Render)

```bash
PYTHON_VERSION=3.12.7
JWT_SECRET_KEY=<生成随机字符串>
RATE_LIMIT_ENABLED=false
CORS_ALLOW_ORIGINS=https://frontend-one-gray-39.vercel.app,http://localhost:5173
LLM_API_KEY=<你的API密钥>
FAST_LLM_API_KEY=<你的API密钥>
VISION_API_KEY=<你的API密钥>
```

### 前端 (Vercel)

```bash
VITE_API_BASE=https://cookhero-backend.onrender.com/api/v1
```

## 下一步

部署完成后，你可以：

1. 配置自定义域名
2. 启用 CDN 加速
3. 配置监控和日志
4. 设置自动备份
