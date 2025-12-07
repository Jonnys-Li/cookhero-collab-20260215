# CookHero 构建与开发指南

本文档为开发者提供清晰的指南，说明如何配置开发环境、构建和运行 CookHero 项目。

---

## 1. 环境与配置

### 1.1. 环境准备 (Prerequisites)

在开始之前，请确保您的开发环境中已安装以下工具：

- **Python**: 版本 `3.9` 或更高。请通过 `python --version` 或 `python3 --version` 命令确认。
- **Docker** 与 **Docker Compose**: 用于快速启动 Milvus 向量数据库等依赖服务。
- **Git**: 用于版本控制和克隆项目知识库数据。

### 1.2. 配置文件说明

CookHero 采用 **`config.yml`** 作为唯一的中心配置文件，并结合 **`.env`** 文件来管理敏感凭证。

- **`config.yml`**: 包含了所有应用程序的配置项，如模型名称、检索参数、数据源路径等。你可以直接修改此文件来调整系统行为。

- **`.env` 文件**: 用于存储敏感数据，主要是第三方服务的 API 密钥。在项目根目录下创建一个 `.env` 文件，并至少填入以下内容：
    
    ```dotenv
    LLM_API_KEY="your-llm-api-key"
    # 如果 Embedding 模型或 Reranker 模型使用独立的 key，也在此处添加
    # EMBEDDING_API_KEY="your-embedding-api-key"
    # RERANKER_API_KEY="your-reranker-api-key"
    ```
    `config_loader.py` 会在程序启动时自动加载此文件，并将密钥安全地注入到配置中。

**重要提示**: `.env` 文件已被添加到 `.gitignore` 中，请勿将其提交到版本控制系统。

---

## 2. 快速开始 (本地开发)

### 2.1. 启动依赖服务

项目依赖 Milvus 向量数据库。我们提供了一个 `docker-compose.yml` 文件用于快速启动所有必要的后端服务。

在 `deployments/` 目录下，运行：
```sh
cd deployments
docker-compose up -d
```
此命令会以后台模式启动 Milvus 数据库及其所有依赖项（etcd、MinIO）。

**验证服务状态**:
```sh
# 检查 Milvus 是否运行
docker ps | grep milvus

# 或访问 Milvus HTTP 端口
curl http://localhost:9091/healthz
```

### 2.2. 同步知识库数据

项目所需的菜谱和技巧知识库存储在一个独立的 Git 仓库中。首次运行时，你需要同步该数据。

在项目根目录下，执行以下脚本：
```sh
python ./scripts/sync_data.py
```
此脚本会将 `data/HowToCook` 仓库克隆到本地，为后续的数据入库做准备。

### 2.3. 安装 Python 依赖

1. **创建并激活虚拟环境** (推荐):
   ```sh
   python -m venv .venv
   source .venv/bin/activate  # On Windows, use `.venv\Scripts\activate`
   ```

2. **安装依赖包**:
   ```sh
   pip install -r requirements.txt
   ```
   
   如果 `requirements.txt` 不存在或不完整，你可能需要手动安装核心依赖:
   ```sh
   pip install fastapi "uvicorn[standard]" pydantic PyYAML python-dotenv \
       langchain langchain-openai langchain-milvus langchain-huggingface \
       sentence-transformers httpx llama-index
   ```

### 2.4. 数据入库 (Ingestion)

在首次运行或知识库更新后，你需要运行数据入库脚本，将菜谱和技巧文档处理并存入 Milvus 数据库。

**重要**: 确保你的 Python 虚拟环境已激活，并且 `PYTHONPATH` 设置正确。
```sh
PYTHONPATH=. python scripts/run_ingestion.py
```

此脚本会：
- 连接到 Docker 中运行的 Milvus 服务
- 清空并重建以下集合：
  - `cook_hero_recipes` (菜谱数据)
  - `cook_hero_tips` (烹饪技巧)
  - `cook_hero_generic_text` (通用文本)
- 将所有文档的向量化表示存入其中
- 支持混合索引（稠密向量 + 稀疏BM25）

**注意**: 数据入库过程可能需要几分钟时间，取决于数据量大小。

### 2.5. 运行应用

完成数据入库后，启动 FastAPI 后端服务：
```sh
PYTHONPATH=. uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

服务启动后，你可以通过以下方式访问：
- **API 文档**: `http://localhost:8000/docs` - Swagger UI 接口文档
- **API 根路径**: `http://localhost:8000/` - 健康检查端点
- **Chat 端点**: `http://localhost:8000/api/v1/chat` - 对话接口

---

## 3. 核心功能测试

项目在 `tests/` 目录下提供了一个测试脚本，用于快速验证 RAG 管道的核心功能是否正常工作。

**运行测试**:

```sh
PYTHONPATH=. python tests/test_rag.py
```

此脚本会：
- 模拟用户提问
- 打印出 RAG 服务从查询重写、并行检索、后处理、排序、重排到最终生成答案的全过程日志
- 是调试和验证系统行为的重要工具

**测试示例问题**:
- "皮蛋瘦肉粥怎么做？"
- "有什么荤素搭配的家常菜？"

---

## 4. 配置说明

### 4.1. 检索配置

在 `config.yml` 中的 `retrieval` 部分可以调整：
- `top_k`: 每个数据源检索的文档数量（默认: 9）
- `score_threshold`: 最低分数阈值，过滤低质量结果（默认: 0.1）
- `ranker_type`: 排序器类型，`rrf` 或 `weighted`（默认: `weighted`）
- `ranker_weights`: 混合搜索权重 `[稠密向量, 稀疏BM25]`（默认: `[0.8, 0.2]`）

### 4.2. 重排序配置

在 `config.yml` 中的 `reranker` 部分可以调整：
- `enabled`: 是否启用重排序（默认: `true`）
- `model_name`: 重排序模型（默认: `BAAI/bge-reranker-v2-m3`）
- `score_threshold`: 重排序分数阈值（默认: 0.1）

### 4.3. LLM 配置

在 `config.yml` 中的 `llm` 部分可以调整：
- `model_name`: 语言模型名称（默认: `deepseek-ai/DeepSeek-R1-0528-Qwen3-8B`）
- `temperature`: 生成温度（默认: 0.1）
- `max_tokens`: 最大生成token数（默认: 131072）

---

## 5. 故障排除

### 5.1. Milvus 连接失败

**问题**: 无法连接到 Milvus 数据库

**解决方案**:
1. 检查 Docker 容器是否运行: `docker ps | grep milvus`
2. 检查端口是否被占用: `lsof -i :19530`
3. 查看 Milvus 日志: `docker logs cookhero_milvus`
4. 重启服务: `cd deployments && docker-compose restart`

### 5.2. 数据入库失败

**问题**: 运行 `run_ingestion.py` 时出错

**解决方案**:
1. 确保 Milvus 服务正常运行
2. 检查数据路径是否正确: `ls data/HowToCook/dishes`
3. 检查 Python 环境是否激活: `which python`
4. 查看详细错误日志

### 5.3. API 请求超时

**问题**: API 请求响应时间过长

**解决方案**:
1. 检查 Milvus 索引是否已构建完成
2. 减少 `retrieval.top_k` 值
3. 检查网络连接和 API 密钥是否有效
4. 考虑启用缓存机制（未来功能）

### 5.4. 依赖安装问题

**问题**: `pip install` 失败

**解决方案**:
1. 升级 pip: `pip install --upgrade pip`
2. 使用国内镜像源: `pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple`
3. 检查 Python 版本是否符合要求（3.9+）

---

## 6. 开发模式

### 6.1. 热重载

使用 `--reload` 参数启动服务，代码变更会自动重启：
```sh
PYTHONPATH=. uvicorn app.main:app --reload
```

### 6.2. 调试模式

设置环境变量启用详细日志：
```sh
export LOG_LEVEL=DEBUG
PYTHONPATH=. uvicorn app.main:app --reload
```

### 6.3. 测试数据源

可以添加测试数据到 `data/generic_text/` 目录，系统会自动识别 `.txt` 文件并索引。

---

## 7. 生产部署

### 7.1. Docker 部署

（待实现）未来将提供完整的 Docker 镜像和 docker-compose 配置。

### 7.2. 环境变量

生产环境建议使用环境变量覆盖配置：
```sh
export MILVUS_HOST=your-milvus-host
export MILVUS_PORT=19530
export LLM_API_KEY=your-api-key
```

### 7.3. 性能优化

- 使用 Gunicorn + Uvicorn workers 提高并发
- 配置 Redis 缓存（未来功能）
- 优化 Milvus 索引参数
- 使用 CDN 加速静态资源（前端）

---

## 8. 下一步

- 查看 `docs/requirement.md` 了解功能需求
- 查看 `docs/technology.md` 了解技术架构
- 查看 `README.md` 了解项目概述
