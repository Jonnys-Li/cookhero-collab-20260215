<div align="center">

<img src="./docs/image.png" alt="CookHero Logo" width="512" />

**智能烹饪助手 · 让每个人都能成为厨房英雄**

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.122-009688.svg)](https://fastapi.tiangolo.com/)
[![LangChain](https://img.shields.io/badge/LangChain-1.1-green.svg)](https://www.langchain.com/)
[![Milvus](https://img.shields.io/badge/Milvus-2.6-orange.svg)](https://milvus.io/)
[![License](https://img.shields.io/badge/License-APACHE%202.0-blue.svg)](LICENSE)

简体中文 | [English](./docs/README_EN.md)

</div>

---

## 📖 项目简介

**CookHero**（烹饪英雄）是一个基于大语言模型（LLM）和检索增强生成（RAG）技术的智能烹饪助手系统。它不仅是一个菜谱库，更是您的私人厨房顾问，能够：

- 🔍 **智能问答**：解答烹饪技巧、食材搭配、营养知识等问题
- 🍽️ **个性化推荐**：根据用户口味、健康目标、饮食限制提供菜品推荐
- 📝 **食谱管理**：上传并管理个人食谱，构建专属知识库
- 🧠 **深度理解**：通过多轮对话理解用户意图，提供精准建议
- 🌐 **实时搜索**：结合 Web 搜索获取最新烹饪资讯和趋势

CookHero 面向厨房新手、健身爱好者、健康饮食倡导者、过敏体质用户等多种人群，致力于让烹饪变得简单、科学、有趣。

<div align="center">

<video width="640" height="360" controls>

<source src="./docs/example.mp4" type="video/mp4">

您的浏览器不支持 video 标签。

</video>

</div>

---

## ✨ 核心功能

### 1. 智能对话式查询
- 自然语言理解用户需求（如"我想做一道低脂高蛋白的晚餐"）
- 支持多轮对话，记录上下文历史
- 自动识别用户意图（查询、推荐、闲聊等）

### 2. 混合检索系统
- **向量检索**：语义相似度匹配（基于 Milvus）
- **BM25 检索**：关键词精确匹配
- **元数据过滤**：根据烹饪时间、难度、营养成分等筛选
- **多级缓存**：Redis + Milvus 双层缓存，提升响应速度

### 3. 个性化设置
- 用户可上传私人食谱，系统自动分析并索引
- 全局食谱库（来自 [HowToCook](https://github.com/Anduin2017/HowToCook)）与个人食谱融合查询
- 支持 Markdown 格式食谱的智能解析
- 支持用户画像，基于用户偏好进行推荐
- 支持设置模型回答风格

### 4. 高级重排序 (Reranking)
- 使用专门的 Reranker 模型对检索结果进行二次排序
- 提高结果相关性和准确度

### 5. Web 搜索增强
- 集成 Tavily 搜索引擎，在知识库不足时自动联网查询
- 结合实时信息和本地知识，给出综合答案

### 6. 用户体系
- 用户注册/登录（JWT 身份认证）
- 会话管理（多会话隔离，历史记录保存）

---

## 🏗️ 技术架构

### RAG 管道流程

1. **意图识别**：判断用户查询类型（菜谱查询、烹饪技巧、闲聊等）
2. **查询改写**：优化用户输入，提取关键信息
3. **缓存查询**：检查 Redis 和 Milvus 缓存
4. **混合检索**：
   - 向量检索（语义相似度）
   - BM25 关键词检索
   - 元数据过滤（烹饪时间、难度等）
5. **结果融合**：使用加权融合或 RRF (Reciprocal Rank Fusion)
6. **重排序**：Reranker 模型对结果精排
7. **上下文压缩**：提取最相关片段
8. **LLM 生成**：结合检索内容生成最终答案
9. **Web 增强**（可选）：信息不足时触发 Tavily 搜索

---

## 📂 项目结构

详见 [项目结构文档](docs/PROJECT_STRUCTURE.md)

---

## 🚀 快速开始

### 前置要求

- **Python**：>= 3.12
- **Node.js**：>= 18
- **Docker** 和 **Docker Compose**（推荐）

### 方法一：Docker 一键部署（推荐）

1. **克隆项目**
   ```bash
   git clone https://github.com/yourusername/CookHero.git
   cd CookHero
   ```

2. **配置环境变量**
   ```bash
   cp .env.example .env
   # 编辑 .env 文件，填入必要的 API Key
   ```

3. **启动基础设施**
   ```bash
   cd deployments
   docker-compose up -d
   ```
   这将启动：
   - PostgreSQL (端口 5432)
   - Redis (端口 6379)
   - Milvus (端口 19530)
   - MinIO (端口 9001)
   - Etcd (内部使用)

4. **安装 Python 依赖并启动后端**
   ```bash
   cd ..
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   
   # 初始化数据库
   python -m scripts.howtocook_loader
   
   # 启动后端服务
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

5. **启动前端**
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

6. **访问应用**
   - 前端：http://localhost:5173
   - 后端 API：http://localhost:8000
   - API 文档：http://localhost:8000/docs

---

## ⚙️ 配置说明

### 1. 环境变量 (`.env`)

创建 `.env` 文件（参考 `.env.example`）：

### 2. 主配置文件 (`config.yml`)

包含：
- LLM 提供商配置（快速/标准两层模型）
- 向量存储配置
- 检索参数（top_k, score_threshold）
- Reranker 配置
- 缓存策略
- 数据库连接信息

详细说明见 [config.yml](config.yml) 中的注释。

---

## 🛠️ 开发指南

### 后端开发

- **添加新 API 端点**：在 `app/api/v1/endpoints/` 下创建新文件
- **添加新服务**：在 `app/services/` 下实现业务逻辑
- **修改对话流程**：在 `app/conversation/` 下调整对话管理逻辑
- **修改 RAG 管道**：在 `app/rag/pipeline/` 下调整检索流程

### 前端开发

```bash
cd frontend
npm run dev     # 开发服务器
npm run build   # 生产构建
npm run lint    # 代码检查
```

---

## 🗺️ 未来规划 (Roadmap)

- [ ] **多模态支持**：食材图片识别、菜品图片生成
- [ ] **语音交互**：语音输入查询、语音播报步骤
- [ ] **营养分析**：自动计算卡路里、营养成分
- [ ] **社区功能**：用户分享、评分、评论
- [ ] **智能食材管理**：冰箱清单、食材过期提醒
- [ ] **AR 烹饪指导**：增强现实辅助烹饪

---

## 🤝 贡献指南

欢迎贡献代码、提出问题或建议！

1. Fork 本项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 提交 Pull Request

---

## 📄 开源协议

本项目基于 [APACHE LICENSE 2.0](LICENSE) 许可证开源。详情请参阅 LICENSE 文件。

---

## 🙏 致谢

- [HowToCook](https://github.com/Anduin2017/HowToCook) - 优质的开源食谱库
- [LangChain](https://www.langchain.com/) - 强大的 LLM 应用框架
- [Milvus](https://milvus.io/) - 高性能向量数据库
- [FastAPI](https://fastapi.tiangolo.com/) - 现代化的 Python Web 框架

---

<div align="center">

**如果这个项目对您有帮助，请给一个 ⭐️ Star 支持一下！**

</div>
