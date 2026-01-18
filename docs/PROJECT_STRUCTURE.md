# CookHero 项目结构详解

本文档详细说明 CookHero 项目的目录结构和各模块职责。

---

## 一、项目根目录

```
CookHero/
├── app/                    # 后端应用主目录
├── frontend/               # 前端应用
├── scripts/                # 工具脚本
├── tests/                  # 测试文件
├── data/                   # 数据目录
├── deployments/            # 部署配置
├── docs/                   # 项目文档
├── config.yml              # 主配置文件
├── .env.example            # 环境变量模板
├── requirements.txt        # Python 依赖
├── README.md              # 中文说明文档
└── .gitignore             # Git 忽略规则
```

---

## 二、后端应用 (`app/`)

### 2.1 API 层 (`app/api/`)

```
api/
└── v1/
    └── endpoints/
        ├── auth.py           # 用户认证接口（注册、登录、令牌刷新）
        ├── conversation.py   # 对话接口（创建、查询、流式响应）
        ├── agent.py          # Agent 接口（智能对话、工具调用、会话管理）
        ├── evaluation.py     # RAG 评估接口（统计、趋势、告警）
        ├── llm_stats.py      # LLM 使用统计接口（含工具统计）
        ├── personal_docs.py  # 个人文档接口（上传、删除、列表）
        └── user.py           # 用户信息接口（获取、更新）
```

**职责**：
- 定义 RESTful API 端点
- 请求验证（Pydantic 模型）
- 调用服务层处理业务逻辑
- 返回标准化响应
- 安全检查集成

---

### 2.2 配置模块 (`app/config/`)

```
config/
├── config_loader.py      # 配置加载器（从 config.yml 和 .env 加载）
├── config.py             # 全局配置类（Settings）
├── database_config.py    # 数据库配置（PostgreSQL, Redis, Milvus）
├── evaluation_config.py  # RAG 评估配置（RAGAS 指标、采样率、告警阈值）
├── llm_config.py         # LLM 提供商配置（fast/normal 两层）
├── rag_config.py         # RAG 管道配置（检索参数、重排序）
├── vision_config.py      # 视觉模型配置（多模态支持）
└── web_search_config.py  # Web 搜索配置（Tavily）
```

**职责**：
- 统一管理项目配置
- 环境变量注入
- 配置验证和默认值处理
- 提供全局 Settings 单例

---

### 2.3 对话管理 (`app/conversation/`)

```
conversation/
├── __init__.py           # 模块初始化和导出
├── types.py              # 类型定义（对话类型、意图类型等）
├── prompts.py            # 系统提示词模板
├── intent.py             # 意图识别（查询、推荐、闲聊等）
├── query_rewriter.py     # 查询改写（优化用户输入）
├── llm_orchestrator.py   # LLM 编排（多模型选择、调用、流式响应）
```

**职责**：
- 理解用户意图
- 优化查询语句
- 管理对话历史和上下文
- LLM 流式响应编排
- 持久化会话数据

---

### 2.4 上下文管理 (`app/context/`)

```
context/
├── __init__.py           # 模块初始化
├── manager.py            # 上下文管理器（构建检索上下文）
└── compress.py           # 上下文压缩（提取关键片段）
```

**职责**：
- 管理对话上下文窗口
- 压缩长文本以节省 token
- 提取最相关的检索结果
- 上下文信息结构化

---

### 2.5 数据库层 (`app/database/`)

```
database/
├── __init__.py           # 模块初始化和公共导出
├── models.py             # ORM 模型（User, Conversation, Message, RAGEvaluation, LLMUsageLog）
├── session.py            # 数据库会话管理（连接池、事务）
├── conversation_repository.py  # 对话仓库（CRUD）
├── document_repository.py      # 文档仓库（元数据缓存、CRUD）
├── evaluation_repository.py    # 评估仓库（RAG 评估记录 CRUD）
└── llm_usage_repository.py     # LLM 使用记录仓库（统计查询）
```

**职责**：
- 定义数据表结构（SQLAlchemy ORM）
- 管理数据库连接（PostgreSQL）
- 提供数据访问接口
- LLM 使用统计查询

---

### 2.6 LLM 提供商 (`app/llm/`)

```
llm/
├── __init__.py           # 模块初始化和导出
├── provider.py           # LLM 提供者和调用器（LLMProvider, LLMInvoker）
├── context.py            # LLM 调用上下文管理（contextvars 实现）
└── callbacks.py          # 回调处理器（Token 使用追踪、工具名称提取）
```

**职责**：
- 统一 LLM 调用接口
- 支持多模型切换和随机选择（负载均衡）
- Token 使用量追踪和持久化
- 调用上下文管理（module_name, user_id, conversation_id）
- 工具调用名称提取和记录

**核心类**：
- `LLMProvider`: 全局 LLM 提供者，管理配置和创建实例
- `LLMInvoker`: LLM 调用器，封装调用逻辑和 usage tracking
- `LLMCallContext`: 调用上下文信息
- `LLMUsageCallbackHandler`: Token 使用回调处理器

---

### 2.7 RAG 核心模块 (`app/rag/`)

#### 2.7.1 缓存系统 (`app/rag/cache/`)

```
cache/
├── __init__.py           # 模块初始化
├── base.py               # 缓存基类
├── backends.py           # Redis 和 Milvus 缓存后端实现
└── cache_manager.py      # 缓存管理器（L1+L2 双层缓存）
```

**职责**：
- L1 缓存（Redis）：精确匹配查询
- L2 缓存（Milvus）：语义相似查询
- 缓存失效和更新策略
- 缓存命中率统计

#### 2.7.2 嵌入模型 (`app/rag/embeddings/`)

```
embeddings/
├── __init__.py           # 模块初始化
└── embedding_factory.py  # 嵌入模型工厂（HuggingFace, OpenAI）
```

**职责**：
- 加载和管理嵌入模型
- 文本向量化
- 支持多种嵌入模型后端

#### 2.7.3 检索管道 (`app/rag/pipeline/`)

```
pipeline/
├── __init__.py           # 模块初始化
├── retrieval.py          # 检索模块（向量检索、BM25、混合检索）
├── generation.py         # 生成模块（LLM 答案生成）
├── metadata_filter.py    # 元数据过滤（烹饪时间、难度等）
└── document_processor.py # 文档处理（分块、解析、索引）
```

**职责**：
- 实现 RAG 全流程
- 多种检索策略融合
- 元数据过滤
- 生成最终答案

#### 2.7.4 重排序器 (`app/rag/rerankers/`)

```
rerankers/
├── __init__.py           # 模块初始化
├── base.py               # 重排序器基类
└── siliconflow_reranker.py # SiliconFlow Reranker 实现
```

**职责**：
- 对初步检索结果进行精排
- 提高结果相关性
- 支持多种 Reranker 模型

#### 2.7.5 向量存储 (`app/rag/vector_stores/`)

```
vector_stores/
├── __init__.py           # 模块初始化
└── vector_store_factory.py # 向量存储工厂（Milvus 集合管理）
```

**职责**：
- 初始化向量数据库
- 管理多个集合（全局食谱、个人食谱、缓存）
- 向量 CRUD 操作

---

### 2.8 业务服务层 (`app/services/`)

```
services/
├── __init__.py                # 模块初始化和导出
├── auth_service.py            # 认证服务（注册、登录、JWT、账户锁定）
├── conversation_service.py    # 对话服务（会话管理、消息处理、流式响应）
├── evaluation_service.py      # RAG 评估服务（RAGAS 框架集成）
├── rag_service.py             # RAG 服务（检索、生成）
├── personal_document_service.py # 个人文档服务（上传、索引）
└── user_service.py            # 用户服务（用户信息管理）
```

**职责**：
- 实现核心业务逻辑
- 协调多个模块协同工作
- 事务管理和错误处理
- 异步任务处理

---

### 2.9 工具集 (`app/tools/`)

```
tools/
├── __init__.py       # 模块初始化
└── web_search.py     # Web 搜索工具（Tavily 集成）
```

**职责**：
- 提供外部工具调用接口
- 扩展 RAG 系统能力
- Web 搜索结果格式化

---

### 2.10 工具函数 (`app/utils/`)

```
utils/
└── structured_json.py # JSON 解析和验证工具
```

**职责**：
- 通用工具函数
- 数据格式化和验证
- 结构化 JSON 处理

---

### 2.11 应用入口 (`app/main.py`)

**职责**：
- FastAPI 应用初始化
- 中间件配置（CORS、异常处理、安全头、速率限制）
- 路由注册
- 生命周期管理（数据库初始化、缓存清理）

---

### 2.12 安全模块 (`app/security/`)

```
security/
├── __init__.py           # 模块初始化和导出
├── prompt_guard.py       # 基于正则的提示词注入检测
├── sanitizer.py          # 敏感数据过滤和日志脱敏
├── audit.py              # 安全审计日志
├── dependencies.py       # 统一的安全检查辅助函数
├── middleware/           # 中间件
│   ├── __init__.py
│   └── rate_limiter.py   # Redis 速率限制器
└── guardrails/           # NeMo Guardrails 集成
    ├── __init__.py
    ├── guard.py          # Guardrails 封装类
    └── config/           # Guardrails 配置
        ├── config.yml    # 模型配置
        ├── prompts.yml   # 提示词模板
        └── rails/        # 安全规则定义
```

**职责**：
- **prompt_guard.py**：基于正则表达式的快速模式检测，识别常见提示词注入攻击
- **sanitizer.py**：日志敏感数据过滤，防止 API Key、密码等泄露到日志
- **audit.py**：结构化安全审计日志，支持 SIEM 系统对接
- **dependencies.py**：统一的消息安全检查函数，可在多个 endpoint 复用
- **middleware/rate_limiter.py**：基于 Redis 的滑动窗口速率限制
- **guardrails/**：NeMo Guardrails 集成，提供 LLM 驱动的深度安全检测

---

### 2.13 Agent 模块 (`app/agent/`)

```
agent/
├── __init__.py           # 模块初始化和导出（setup_agent_module）
├── types.py              # 类型定义（AgentChunk, ToolResult, AgentContext 等）
├── base.py               # Agent 基类和执行引擎（BaseAgent, DefaultAgent）
├── context.py            # 上下文构建器和压缩器
├── registry.py           # 注册中心（Agent 和 Tool 注册管理）
├── service.py            # 业务层（AgentService 主入口）
├── database/
│   ├── __init__.py
│   ├── models.py         # ORM 模型（AgentSession, AgentMessage）
│   └── repository.py     # 数据访问层（CRUD 操作）
└── tools/
    ├── __init__.py
    ├── base.py           # Tool 基类和执行器（BaseTool, ToolExecutor）
    └── builtin/
        ├── __init__.py
        └── common.py     # 内置工具（calculator, datetime, text_processor）
```

**职责**：
- **ReAct 模式执行**：实现 Reasoning + Acting 循环，支持自主推理和工具调用
- **会话管理**：独立的 Agent 会话系统，与 Conversation 模块分离
- **工具系统**：可扩展的工具注册和执行框架
- **上下文压缩**：自动压缩长对话历史，减少 Token 消耗
- **流式输出**：支持 SSE 事件流，实时反馈工具调用和结果

**核心类**：
- `AgentService`: 业务层入口，处理聊天请求和会话管理
- `BaseAgent`: Agent 基类，实现 ReAct 循环逻辑
- `AgentRegistry`: 静态注册中心，管理 Agent 和 Tool
- `BaseTool`: 工具基类，定义工具接口规范
- `ToolExecutor`: 工具执行器，安全执行工具调用
- `AgentContextBuilder`: 上下文构建器
- `AgentContextCompressor`: 上下文压缩器

**内置工具**：
| 工具名称 | 功能 | 参数 |
|---------|------|------|
| `calculator` | 数学计算 | `expression` (数学表达式) |
| `datetime` | 获取日期时间 | `format`, `timezone` |
| `text_processor` | 文本处理 | `text`, `operation` |

**事件类型**（SSE）：
- `session`: 会话信息
- `text`: 文本内容块
- `tool_call`: 工具调用请求
- `tool_result`: 工具执行结果
- `trace`: 执行轨迹
- `done`: 完成信号

---

### 2.14 视觉模块 (`app/vision/`)

```
vision/
├── __init__.py           # 模块初始化
├── agent.py              # 视觉 Agent（图片分析、意图识别）
└── provider.py           # 视觉模型提供商（OpenAI 兼容 API）
```

**职责**：
- 处理用户上传的图片
- 识别菜品、食材等食物相关内容
- 结合文字理解用户完整意图
- 支持多种视觉意图分类（菜品识别、食谱查询、烹饪指导等）

---

## 三、前端应用 (`frontend/`)

```
frontend/
├── src/
│   ├── components/       # React 组件
│   │   ├── chat/                # 对话相关组件
│   │   │   ├── ChatMessage.tsx       # 聊天消息组件
│   │   │   ├── ChatInput.tsx         # 输入框组件
│   │   │   ├── ChatWindow.tsx        # 聊天窗口
│   │   │   ├── MessageBubble.tsx     # 消息气泡
│   │   │   ├── MarkdownRenderer.tsx  # Markdown 渲染器
│   │   │   └── ThinkingBlock.tsx     # 思考过程展示
│   │   ├── agent/               # Agent 模式组件
│   │   │   ├── AgentChatInput.tsx    # Agent 输入框
│   │   │   ├── AgentChatWindow.tsx   # Agent 聊天窗口
│   │   │   ├── AgentMessageBubble.tsx # Agent 消息气泡
│   │   │   └── AgentThinkingBlock.tsx # Agent 思考过程
│   │   ├── layout/              # 布局组件
│   │   │   ├── Sidebar.tsx           # 侧边栏（支持 Agent 模式切换）
│   │   │   └── UserProfileModal.tsx  # 用户资料弹窗
│   │   ├── common/              # 通用组件
│   │   │   ├── Modal.tsx             # 模态框
│   │   │   ├── ThemeToggle.tsx       # 主题切换
│   │   │   └── CopyButton.tsx        # 复制按钮
│   │   └── KnowledgePanel.tsx   # 知识库面板
│   ├── pages/            # 页面组件
│   │   ├── Login.tsx             # 登录页面
│   │   ├── Register.tsx          # 注册页面
│   │   ├── Evaluation.tsx        # RAG 评估统计页面
│   │   └── LLMStats.tsx          # LLM 使用统计页面
│   ├── services/         # API 服务
│   │   ├── api.ts                # Axios 实例配置
│   │   ├── authService.ts        # 认证 API
│   │   ├── conversationService.ts# 对话 API
│   │   ├── agentService.ts       # Agent API
│   │   └── llmStatsService.ts    # LLM 统计 API
│   ├── contexts/         # React Context
│   │   ├── AuthContext.tsx       # 认证状态管理
│   │   ├── ThemeContext.tsx      # 主题状态管理
│   │   ├── ConversationContext.tsx # 对话状态管理
│   │   └── AgentContext.tsx      # Agent 状态管理
│   ├── hooks/            # 自定义 Hooks
│   │   └── useAuth.tsx           # 认证 Hook
│   ├── types/            # TypeScript 类型定义
│   │   └── index.ts
│   ├── utils/            # 工具函数
│   ├── App.tsx           # 应用根组件（含 Agent 路由）
│   ├── main.tsx          # 应用入口
│   └── index.css         # 全局样式
├── public/               # 静态资源
│   ├── favicon.ico       # 网站图标
│   └── logo.svg          # Logo 文件
├── package.json          # 依赖配置
├── tsconfig.json         # TypeScript 配置
├── vite.config.ts        # Vite 配置
└── tailwind.config.ts    # TailwindCSS 配置
```

**技术栈**：
- React 19 + TypeScript
- Vite（构建工具）
- TailwindCSS（样式）
- React Router（路由）
- Axios（HTTP 客户端）

**路由结构**：
- `/chat` - 标准对话模式
- `/chat/:id` - 指定对话
- `/agent` - Agent 智能模式
- `/agent/:id` - 指定 Agent 会话
- `/knowledge` - 知识库管理
- `/evaluation` - RAG 评估统计
- `/llm-stats` - LLM 使用统计
- `/login` - 登录
- `/register` - 注册

---

## 四、工具脚本 (`scripts/`)

```
scripts/
├── howtocook_loader.py   # HowToCook 数据加载器
├── run_ingestion.py      # 数据摄取主脚本
├── sync_data.py          # 数据同步工具
└── list_categories.py    # 列出菜谱分类
```

**职责**：
- 数据预处理
- 向量化和索引
- 数据库初始化

---

## 五、测试 (`tests/`)

```
tests/
├── __init__.py                  # 测试包初始化
├── test_rag.py                  # RAG 系统测试
├── test_agent.py                # Agent 模块测试
├── test_user_personalization.py # 用户个性化测试
├── test_vision.py               # 视觉模块测试
└── test_guardrails.py           # 安全防护测试
```

**职责**：
- 单元测试
- 集成测试
- 端到端测试
- 安全模块测试
- Agent 功能测试

---

## 六、数据目录 (`data/`)

```
data/
├── HowToCook/            # HowToCook 食谱库（Git Submodule）
│   ├── dishes/           # 菜谱 Markdown 文件
│   ├── tips/             # 烹饪技巧
│   └── README.md
└── debug/                # 调试数据（可选）
    ├── child_chunks.jsonl
    └── parent_documents.jsonl
```

---

## 七、部署配置 (`deployments/`)

```
deployments/
├── docker-compose.yml    # Docker Compose 编排文件
├── init-scripts/         # 数据库初始化脚本
│   └── init.sql
└── volumes/              # 持久化数据卷
    ├── postgres/
    ├── redis/
    ├── milvus/
    ├── minio/
    └── etcd/
```

**职责**：
- 一键启动基础设施
- 数据持久化
- 服务编排

---

## 八、文档目录 (`docs/`)

```
docs/
├── PROJECT_STRUCTURE.md  # 项目结构文档（本文档）
├── README_EN.md          # 英文说明文档
├── SECURITY.md           # 安全策略文档
└── image.png             # 项目 Logo
```

---

## 九、配置文件

### 9.1 `config.yml`

主配置文件，包含：
- LLM 提供商配置（fast/normal 两层模型）
- 数据库连接信息（主机、端口）
- RAG 管道参数（检索、重排序、缓存）
- 缓存策略
- 评估配置
- 视觉模型配置
- Web 搜索配置

### 9.2 `.env`

环境变量文件（不提交到 Git），包含：
- API Keys（LLM、Vision、Reranker、Web Search）
- 数据库密码
- JWT 密钥
- 安全配置

### 9.3 `requirements.txt`

Python 依赖列表，包含所有后端依赖的精确版本号。

---

## 十、数据流示例

### 用户查询流程

1. **用户输入**：前端发送查询请求到 `/api/v1/conversation/query`
2. **API 层**：`conversation.py` 接收请求，验证身份
3. **安全检查**：速率限制、提示词注入检测
4. **服务层**：`conversation_service.py` 处理业务逻辑
5. **意图识别**：`intent.py` 判断查询类型
6. **查询改写**：`query_rewriter.py` 优化查询
7. **缓存查询**：`cache_manager.py` 检查 Redis/Milvus 缓存
8. **检索**：`retrieval.py` 执行混合检索
9. **重排序**：`siliconflow_reranker.py` 精排结果
10. **生成答案**：`generation.py` 调用 LLM 生成回复
11. **LLM 追踪**：`callbacks.py` 记录 Token 使用量
12. **评估**：`evaluation_service.py` 异步评估（可选）
13. **返回结果**：流式或完整返回给前端

### 图片分析流程（多模态）

1. **用户上传**：前端发送图片 + 文字到 `/api/v1/conversation/query`
2. **视觉分析**：`vision/agent.py` 分析图片内容
3. **意图识别**：判断是否与食物相关，分类用户意图
4. **信息提取**：提取菜品名、食材等关键信息
5. **流程衔接**：食物相关则继续 RAG 流程，否则直接响应
6. **结果生成**：结合视觉信息和检索结果生成答案

### RAG 评估流程

1. **响应生成后**：根据采样率决定是否评估
2. **异步提交**：`evaluation_service.py` 后台异步执行
3. **指标计算**：使用 RAGAS 计算 Faithfulness 和 Answer Relevancy
4. **结果存储**：`evaluation_repository.py` 保存到 PostgreSQL
5. **告警检查**：指标低于阈值时触发告警

### 安全检查流程

1. **请求接收**：FastAPI 接收用户请求
2. **速率限制检查**：`rate_limiter.py` 检查 IP/用户请求频率
3. **输入验证**：Pydantic 模型验证消息长度、图片大小等
4. **基础模式检测**：`prompt_guard.py` 正则匹配危险模式
5. **深度安全检测**：`guardrails/guard.py` LLM 驱动的语义分析
6. **业务处理**：通过安全检查后进入正常业务流程
7. **审计记录**：`audit.py` 记录安全事件到结构化日志
8. **敏感数据过滤**：`sanitizer.py` 过滤日志中的敏感信息

### LLM 使用统计流程

1. **请求发起**：`llm/callbacks.py` 创建追踪上下文
2. **Token 计数**：统计输入/输出 Token 数量
3. **时间记录**：记录思考时间、生成时间
4. **成本计算**：基于模型计算请求成本
5. **工具名称提取**：从 Tool Calls 中提取工具名称
6. **持久化**：`llm_usage_repository.py` 保存到 PostgreSQL
7. **统计分析**：前端 `/api/v1/llm-stats/usage` 展示统计结果

### Agent 对话流程

1. **用户请求**：前端发送请求到 `/api/v1/agent/chat`
2. **API 层**：`agent.py` 接收请求，验证身份
3. **安全检查**：`dependencies.py` 统一安全检查
4. **会话管理**：`AgentService.chat()` 获取或创建 Session
5. **消息保存**：保存用户消息到数据库
6. **上下文构建**：`AgentContextBuilder` 构建完整上下文
7. **Agent 执行**：`BaseAgent.run()` 执行 ReAct 循环
   - 调用 LLM 判断是否需要工具
   - 如需工具，执行 `ToolExecutor.execute()`
   - 收集工具结果，更新消息历史
   - 重复直到生成最终回复
8. **流式输出**：SSE 事件流实时返回
9. **消息保存**：保存 Assistant 消息和执行轨迹
10. **上下文压缩**：后台触发压缩任务（如需要）

---

## 十一、扩展指南

### 添加新数据源

1. 在 `scripts/` 下创建新的数据加载器
2. 实现数据解析和向量化逻辑
3. 在 `config.yml` 中添加数据源配置

### 添加新检索策略

1. 在 `app/rag/pipeline/retrieval.py` 中实现新策略
2. 在 `config.yml` 中配置策略参数
3. 在 `rag_service.py` 中集成新策略

### 添加新 Reranker

1. 在 `app/rag/rerankers/` 下创建新文件
2. 继承 `BaseReranker` 基类
3. 在 `rag_config.py` 中添加配置模型
4. 在 `rag_service.py` 中注册新 Reranker

### 添加新安全检测规则

1. 在 `app/security/prompt_guard.py` 中添加正则模式
2. 如需深度检测，在 `app/security/guardrails/config/rails/` 添加新 rail
3. 在 `app/security/audit.py` 中添加事件类型

### 添加自定义 Agent

1. 创建新的 Agent 类继承 `BaseAgent`
2. 使用 `@register_agent` 装饰器注册
3. 配置 `AgentConfig`（名称、描述、系统提示、可用工具）

```python
from app.agent import BaseAgent, register_agent, AgentConfig

@register_agent(AgentConfig(
    name="cooking_agent",
    description="专门处理烹饪任务的 Agent",
    system_prompt="你是一个烹饪专家...",
    tools=["calculator", "datetime"],
    max_iterations=10
))
class CookingAgent(BaseAgent):
    pass  # 可覆盖 run() 方法自定义逻辑
```

### 添加自定义 Tool

1. 创建新的 Tool 类继承 `BaseTool`
2. 使用 `@register_tool` 装饰器注册
3. 实现 `execute()` 方法

```python
from app.agent.tools.base import BaseTool
from app.agent.types import ToolResult
from app.agent.registry import register_tool

@register_tool
class RecipeSearchTool(BaseTool):
    name = "recipe_search"
    description = "搜索食谱数据库"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"}
        },
        "required": ["query"]
    }

    async def execute(self, query: str, **kwargs) -> ToolResult:
        # 实现搜索逻辑
        results = await search_recipes(query)
        return ToolResult(success=True, data={"recipes": results})
```

---

## 十二、最近更新日志

| 版本 | 日期 | 主要变更 |
|------|------|---------|
| v1.6.0 | 2025-01 | 添加 Agent 模块（ReAct 模式、工具系统、会话管理） |
| v1.5.1 | 2025-01 | LLM 模块重构，添加工具名称追踪，优化流式 usage tracking |
| v1.5.0 | 2025-01 | 添加 LLM 使用统计功能 |
| v1.4.0 | 2025-01 | 添加 RAG 评估系统（RAGAS 集成） |
| v1.3.0 | 2024-12 | 添加安全防护体系（Guardrails、速率限制） |
| v1.2.0 | 2024-12 | 添加多模态支持（视觉分析） |
| v1.1.0 | 2024-11 | 添加重排序器、缓存系统 |
| v1.0.0 | 2024-10 | 初始版本 |

---

**此文档将随项目发展持续更新。**
