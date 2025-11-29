# CookHero 技术栈

本文档详细说明了 CookHero 项目所采用的技术栈。

## 后端 (Backend)

-   **开发语言**: Python 3.9+
-   **Web 框架**: FastAPI
-   **LLM 编排框架**: LangChain
-   **异步服务网关接口 (ASGI)**: Uvicorn
-   **数据校验**: Pydantic

## 前端 (Frontend)

-   **UI 框架**: React
-   **开发语言**: TypeScript
-   **构建工具**: Vite
-   **样式方案**: 待定 (例如: Tailwind CSS, Material-UI)
-   **状态管理**: Zustand 或 React Context

## 数据库 (Databases)

-   **向量数据库**: Milvus - 用于存储和检索向量嵌入，是 RAG 的核心。
-   **关系型数据库**: PostgreSQL (生产环境推荐) 或 SQLite (开发环境使用) - 用于存储用户资料、菜谱元数据等结构化信息。
-   **缓存数据库**: Redis (可选，在后期用于性能优化)。

## 核心 AI/ML

-   **大语言模型 (LLM)**: 一个具备良好指令遵循能力的模型 (例如：OpenAI 的 GPT 系列、Anthropic 的 Claude 系列或 Llama 等开源模型)。
-   **嵌入模型 (Embedding Models)**: 用于从文本和图片创建向量嵌入的句向量模型或多模态模型。

## 开发运维与工具 (DevOps & Tooling)

-   **容器化**: Docker, Docker Compose
-   **版本控制**: Git
-   **包管理**:
    -   `pip` 和 `requirements.txt` (Python)
    -   `npm` 或 `yarn` (Node.js)
-   **测试框架**:
    -   `pytest` (后端)
    -   `Jest` 和 `React Testing Library` (前端)