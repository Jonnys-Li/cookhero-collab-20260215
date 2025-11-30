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

## RAG 技术亮点（可写入简历）

-   **Milvus 驱动的混合检索引擎**：基于 Milvus + LangChain 构建的 RAG 检索层，单次查询即可同时完成稠密向量检索与 BM25 稀疏检索，兼顾语义理解与关键词精确匹配，显著提升菜谱问答和烹饪知识场景下的召回率与相关性。
-   **Dense + Sparse 双通道向量建模**：为每个文档同时维护语义向量（dense）和 BM25 稀疏向量（sparse），通过 Milvus 内置 `BM25BuiltInFunction` 在向量库内部完成稀疏向量构建与打分，避免 Python 侧重复索引，降低内存占用并提升查询吞吐。
-   **可配置的检索融合策略（RRF / Weighted Ranker）**：支持基于 Reciprocal Rank Fusion (RRF) 的默认融合策略，同时提供可配置的加权融合模式（例如 dense: 0.7 / sparse: 0.3 或 dense: 0.3 / sparse: 0.7），可以根据业务场景在“语义理解优先”和“关键词精确命中优先”之间灵活切换。
-   **智能检索策略选择（Query-aware Ranking）**：在检索前对用户 Query 进行轻量级解析与特征判断，针对“如何做 / 步骤类”操作性问题自动提升 BM25 权重，针对“推荐 / 相似 / 适合”类语义问题自动提升向量检索权重，使系统在不同类型的菜谱查询和饮食规划请求上都具备更符合直觉的表现。
-   **检索结果打分与低质量过滤（Score-aware Filtering）**：对每个命中的文档输出可观测的相似度得分，并在服务层实现可配置的 score 阈值过滤（如丢弃得分过低的 chunk），有效削减噪声上下文，提升 LLM 生成答案的稳定性和可信度。
-   **配置中心化的 RAG 编排**：通过 `config.yml + Pydantic` 建模的 `RAGConfig` 统一管理数据路径、向量库、Embedding、LLM 参数以及检索相关超参数（top_k、score_threshold、ranker_type、ranker_weights 等），实现“改配置即可调策略”的能力，便于在不同环境（开发 / 生产 / 实验）之间快速切换。
-   **模块化 RAG 服务与可扩展数据源**：RAG 服务通过独立的 `RAGService`、`RetrievalOptimizationModule` 和 `DataSource` 抽象解耦实现，支持在不影响现有管线的前提下，引入新的数据源（如更多菜谱库、营养知识库）或替换检索与重排策略，为后续接入推荐系统、智能代理等高级能力预留扩展空间。