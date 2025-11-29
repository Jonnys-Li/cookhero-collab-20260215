# CookHero 构建与开发指南

本文档根据 `docs/requirement.md` 中的规划，阐述了 CookHero 项目的开发流程以及如何构建和运行项目。

## 开发流程

项目遵循分阶段的敏捷开发方法。每个阶段（Sprint）都聚焦于交付一组特定的功能。核心原则是**后端先行**，即优先完成所有核心功能的开发和测试，待后端稳定后再进行前端的开发与集成。

-   **阶段一：核心后端与 RAG 管道**: 建立后端基础和菜谱问答的最小可行产品。
-   **阶段二：用户系统与推荐功能**: 在后端实现用户管理和基础推荐引擎。
-   **阶段三：智能代理与高级功能**: 引入代理以处理复杂的多步骤任务。
-   **阶段四：全功能集成与 API 定型**: 完成所有后端功能的集成测试，并最终确定 API 规范。
-   **阶段五：前端页面实现与最终集成**: 开发前端 UI 并与稳定的后端 API 对接。
-   **阶段六：最终优化、文档与部署**: 对系统进行整体优化，并为生产部署做准备。

## 构建与运行指南

本部分将在项目进展中逐步更新，提供更具体的命令。

### 先决条件

-   Python 3.9+
-   Node.js 16+
-   Docker 和 Docker Compose
-   Git

### 后端 (FastAPI)

1.  **克隆仓库:**
    ```bash
    git clone <repository-url>
    cd CookHero
    ```

2.  **设置 Python 虚拟环境:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # Windows: venv\Scripts\activate
    ```

3.  **安装依赖 (当 `requirements.txt` 文件创建后):**
    ```bash
    pip install -r requirements.txt
    ```

4.  **运行 FastAPI 服务 (当应用创建后):**
    ```bash
    uvicorn app.main:app --reload
    ```

### 前端 (React)

1.  **进入前端目录 (当目录创建后):**
    ```bash
    cd frontend
    ```

2.  **安装依赖 (当 `package.json` 文件创建后):**
    ```bash
    npm install
    ```

3.  **启动开发服务器:**
    ```bash
    npm run dev
    ```

### 使用 Docker (推荐方式)

当 `docker-compose.yml` 文件创建后，您可以使用单个命令构建并运行整个应用技术栈：

```bash
docker-compose up --build
```