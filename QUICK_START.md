# CookHero 部署快速参考

## 🚀 快速部署 (5 分钟)

### 1️⃣ Render 后端部署

直接推送代码到 GitHub，然后在 Render 创建 Web Service：

```
https://dashboard.render.com/new/web-service
```

**关键配置**：
- Runtime: Python 3
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

**环境变量** (复制粘贴到 Render)：
```bash
PYTHON_VERSION=3.12.7
JWT_SECRET_KEY=cookhero_jwt_secret_key_2024_secure_random_string
RATE_LIMIT_ENABLED=false
CORS_ALLOW_ORIGINS=https://frontend-one-gray-39.vercel.app,http://localhost:5173
```

**API 密钥** (在 Render 中手动添加)：
```bash
LLM_API_KEY=<你的密钥>
FAST_LLM_API_KEY=<你的密钥>
VISION_API_KEY=<你的密钥>
```

### 2️⃣ Vercel 前端配置

1. 打开 [Vercel Dashboard](https://vercel.com/dashboard)
2. 进入项目 Settings → Environment Variables
3. 添加环境变量：

| Key | Value | Environments |
|-----|-------|--------------|
| `VITE_API_BASE` | `https://[你的后端URL].onrender.com/api/v1` | Production, Preview |

4. 保存后重新部署

### 3️⃣ 验证连接

```bash
# 测试后端
curl https://[你的后端URL].onrender.com/

# 应返回: {"message":"Welcome to CookHero API!"}

# 运行完整测试
bash scripts/test-connection.sh https://[你的后端URL].onrender.com
```

## 📋 配置清单

### 已完成的配置 ✅

- [x] 修复 `requirements.txt` - 所有依赖添加版本号
- [x] 更新 `render.yaml` - 后端部署配置
- [x] 更新 `.env.example` - 前端环境变量说明
- [x] 创建 `DEPLOYMENT_GUIDE.md` - 完整部署指南
- [x] 创建 `scripts/test-connection.sh` - 连接测试脚本

### 需要你完成的操作 ⚠️

- [ ] 在 Render 上创建 Web Service 并配置环境变量
- [ ] 在 Vercel 上配置 `VITE_API_BASE` 环境变量
- [ ] 触发 Vercel 重新部署
- [ ] 运行测试脚本验证连接

## 🔍 故障排查

| 问题 | 解决方案 |
|------|----------|
| CORS 错误 | 检查 `CORS_ALLOW_ORIGINS` 是否包含前端 URL |
| 401 错误 | 检查 JWT token 是否正确发送 |
| 连接失败 | 在浏览器控制台检查 `import.meta.env.VITE_API_BASE` 值 |

## 📞 需要帮助？

查看完整指南：[DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md)
