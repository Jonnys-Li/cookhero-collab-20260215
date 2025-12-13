# CookHero 系统架构说明

本文档描述了 CookHero 前后端对话系统的整体架构和调用流程。

## 系统架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (React)                          │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────────┐ │
│  │  ChatInput  │→ │ useConversation │→ │    API Service (SSE)   │ │
│  └─────────────┘  └──────────────┘  └─────────────────────────┘ │
│                                              ↓                   │
└──────────────────────────────────────────────┼───────────────────┘
                                               │
                                         HTTP/SSE
                                               │
┌──────────────────────────────────────────────┼───────────────────┐
│                        Backend (FastAPI)      ↓                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                  Conversation API                            │ │
│  │                 POST /api/v1/conversation                    │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                              ↓                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │              ConversationService                             │ │
│  │   - 管理对话历史                                              │ │
│  │   - 协调意图检测和响应生成                                     │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                              ↓                                   │
│  ┌──────────────────┐       ↓       ┌──────────────────────────┐ │
│  │  IntentDetector  │───────┼──────→│  need_rag = true/false  │ │
│  │  (LLM 意图分类)   │               └──────────────────────────┘ │
│  └──────────────────┘                                            │
│           │                                                      │
│           ├── need_rag = false ──→ 直接 LLM 对话                  │
│           │                                                      │
│           └── need_rag = true ──→ RAG Pipeline                   │
│                                        ↓                         │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    RAG Service                               │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │ │
│  │  │Query Rewrite│→ │  Retrieval  │→ │      Reranker       │  │ │
│  │  └─────────────┘  └─────────────┘  └─────────────────────┘  │ │
│  │         ↓                                     ↓              │ │
│  │  ┌─────────────────────────────────────────────────────────┐│ │
│  │  │              Context + LLM Generation                   ││ │
│  │  └─────────────────────────────────────────────────────────┘│ │
│  └─────────────────────────────────────────────────────────────┘ │
│                              ↓                                   │
│                    Streaming Response (SSE)                      │
└──────────────────────────────────────────────────────────────────┘
```

## 核心调用流程

### 1. 用户发送消息

```
用户输入 → ChatInput 组件 → useConversation Hook → API Service
```

### 2. 后端处理流程

```
POST /api/v1/conversation
    │
    ├── 1. 添加用户消息到对话历史
    │
    ├── 2. IntentDetector.detect(query)
    │       │
    │       ├── 返回 need_rag = false
    │       │       └── 直接使用 LLM 回复
    │       │
    │       └── 返回 need_rag = true
    │               └── 调用 RAGService.ask(query)
    │                       │
    │                       ├── Query Rewriting (查询重写)
    │                       ├── Vector Retrieval (向量检索)
    │                       ├── Reranking (重排序)
    │                       ├── Context Building (上下文构建)
    │                       └── LLM Generation (生成回复)
    │
    └── 3. 流式返回 SSE 事件
```

### 3. SSE 事件类型

| 事件类型 | 说明 | 数据结构 |
|---------|------|----------|
| `intent` | 意图检测结果 | `{need_rag, intent, reason}` |
| `text` | 回复文本块 | `{content: "..."}` |
| `sources` | RAG 引用来源 | `[{type, info, ...}]` |
| `done` | 完成信号 | `{conversation_id: "..."}` |

## 文件结构

### 后端新增文件

```
app/
├── api/v1/endpoints/
│   └── conversation.py      # 对话 API 端点
├── services/
│   ├── __init__.py
│   └── conversation_service.py  # 对话服务
└── rag/pipeline/
    └── intent_detector.py   # 意图检测模块
```

### 前端文件结构

```
frontend/src/
├── components/
│   ├── ChatInput.tsx        # 输入组件
│   ├── ChatWindow.tsx       # 聊天窗口
│   ├── Header.tsx           # 头部组件
│   ├── MessageBubble.tsx    # 消息气泡
│   └── MarkdownRenderer.tsx # Markdown 渲染
├── hooks/
│   └── useConversation.ts   # 对话状态管理
├── services/
│   └── api.ts               # API 调用服务
├── types/
│   └── index.ts             # 类型定义
└── App.tsx                  # 主应用
```

## 运行说明

### 启动后端

```bash
# 在项目根目录
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端开发服务器会自动将 `/api` 请求代理到后端。

## 设计考虑

### 已实现

1. **意图检测分流** - 非烹饪相关问题直接由 LLM 回答，避免不必要的 RAG 调用
2. **流式响应** - 使用 SSE 实现实时响应，提升用户体验
3. **多轮对话** - 支持上下文记忆的多轮对话
4. **来源展示** - 前端可展示 RAG 检索的参考来源

### 预留扩展

1. **对话记忆** - 当前使用内存存储，可替换为 Redis/PostgreSQL
2. **用户画像** - ConversationService 可扩展支持用户偏好
3. **多 Agent** - IntentDetector 可扩展为 Agent Router
4. **工具调用** - 可在 ConversationService 中添加工具调用逻辑
