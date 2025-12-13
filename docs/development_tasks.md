# CookHero 开发任务清单

本文档列出了 CookHero 项目接下来可以进行的开发任务，按照优先级和可行性进行分类。

---

## 当前任务（高优先级）

### 任务 1: 搭建前端对话系统 (MVP) 💬 ✅ 已完成
**优先级**: 🔴 高  
**难度**: ⭐⭐⭐ 中等  
**预计时间**: 3-5 天  
**收益**: 实现完整的用户交互闭环
**完成日期**: 2025-12-13

**已完成内容**:
- ✅ 使用 Vite + React + TypeScript 搭建前端项目
- ✅ 实现基础对话 UI（消息气泡、输入框、头部）
- ✅ 实现 SSE 流式响应处理
- ✅ 实现意图检测模块（IntentDetector）
- ✅ 实现对话服务（ConversationService）
- ✅ 实现对话 API 端点（/api/v1/conversation）
- ✅ 前端展示 RAG 检索/直接回复标识
- ✅ 支持 Markdown 内容渲染
- ✅ 添加 CORS 支持和 API 代理配置

**新增文件**:
- `frontend/` - 完整的前端项目
- `app/api/v1/endpoints/conversation.py` - 对话 API
- `app/services/conversation_service.py` - 对话服务
- `app/rag/pipeline/intent_detector.py` - 意图检测
- `docs/architecture.md` - 系统架构文档

**任务描述**:
- 使用 React + TypeScript 实现基础对话页面
- 前端支持与 LLM 进行多轮对话
- 默认由 LLM 直接回复，当需要外部知识时触发 RAG 检索
- 将 RAG 返回的上下文注入 LLM 生成流程
- 前端展示用户输入、LLM 回复、（可选）RAG 引用来源

**技术要点**:
- 使用 Vite + React + TypeScript 搭建前端
- 使用 TailwindCSS 快速实现 UI 样式
- 支持 SSE (Server-Sent Events) 流式响应
- 实现消息历史管理和状态管理

**接口设计**:
```
POST /api/v1/conversation
Request:
{
  "message": "用户输入",
  "conversation_id": "可选，用于多轮对话",
  "stream": true
}

Response (SSE stream):
data: {"type": "text", "content": "..."}
data: {"type": "rag_sources", "sources": [...]}
data: {"type": "done"}
```

**调用流程**:
```
用户输入 → LLM 判断意图 → [需要知识] → RAG 检索 → 注入上下文 → LLM 生成回复
                        → [不需要知识] → LLM 直接回复
```

**相关文件**:
- `frontend/` - 前端项目目录
- `app/api/v1/endpoints/conversation.py` - 对话 API 端点
- `app/rag/pipeline/intent_detector.py` - 意图检测模块

**设计约束**:
- 当前阶段以最小可用闭环 (MVP) 为目标
- 不要求一次性实现复杂能力

**后续扩展预留**:
- 多 Agent 协作机制
- 对话记忆管理（短期/长期记忆）
- 用户 Profile / 偏好画像
- 更复杂的工具调用与决策逻辑

---

## 🔮 低优先级任务（长期规划）

### 任务 7: 实现多模态 RAG（图像输入）🖼️
**优先级**: 🟢 中低  
**难度**: ⭐⭐⭐⭐ 困难  
**预计时间**: 7-10 天  
**收益**: 支持"以图搜菜"功能

**任务描述**:
- 集成多模态 embedding 模型（如 CLIP）
- 支持图像上传和向量化
- 实现图像-文本跨模态检索
- 支持"这是什么食材"、"能做什么菜"等查询

**技术要点**:
- 使用 `transformers` 加载多模态模型
- 图像预处理和向量化
- Milvus 支持多模态向量存储
- API 支持 multipart/form-data 上传

**相关文件**:
- `app/rag/embeddings/multimodal_embedding.py` - 新建
- `app/rag/data_sources/image_data_source.py` - 新建
- `app/api/v1/endpoints/image.py` - 新建

---

### 任务 9: 实现用户画像系统 👤
**优先级**: 🟢 低  
**难度**: ⭐⭐⭐ 较难  
**预计时间**: 5-7 天  
**收益**: 支持深度个性化推荐

**任务描述**:
- 设计用户画像数据模型
- 实现用户偏好学习（显式 + 隐式）
- 实现画像持久化存储
- 集成到推荐系统

**技术要点**:
- 使用 SQLite 或 PostgreSQL 存储用户数据
- 特征向量：口味偏好、营养目标、历史行为
- 增量学习：基于用户交互更新画像

---

### 任务 10: 开发前端界面 🎨
**优先级**: 🟢 低  
**难度**: ⭐⭐⭐⭐ 困难  
**预计时间**: 14-21 天  
**收益**: 提供用户友好的交互界面

**任务描述**:
- 使用 React + TypeScript 开发前端
- 实现对话界面、菜谱浏览、推荐界面
- 实现用户管理功能