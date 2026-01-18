<div align="center">
<img src="./image.png" alt="CookHero Logo" width="512" />

**Intelligent Cooking Assistant · Make Everyone a Kitchen Hero**

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.122-009688.svg)](https://fastapi.tiangolo.com/)
[![LangChain](https://img.shields.io/badge/LangChain-1.1-green.svg)](https://www.langchain.com/)
[![Milvus](https://img.shields.io/badge/Milvus-2.6-orange.svg)](https://milvus.io/)
[![NeMo Guardrails](https://img.shields.io/badge/NeMo%20Guardrails-0.12-76B900.svg)](https://github.com/NVIDIA/NeMo-Guardrails)
[![RAGAS](https://img.shields.io/badge/RAGAS-0.2-purple.svg)](https://docs.ragas.io/)
[![License](https://img.shields.io/badge/License-APACHE%202.0-blue.svg)](LICENSE)

[简体中文](README.md) | English

<div align="center">
<p align="center">
  <img src="./example.gif" width="48%">
  <img src="./show.jpg" width="48%">
</p>
</div>


---

## 📖 Project Overview

**CookHero** is an intelligent cooking assistant system based on Large Language Models (LLM) and Retrieval-Augmented Generation (RAG) technology. It's more than just a recipe database—it's your personal kitchen advisor that can:

- 🔍 **Smart Q&A**: Answer questions about cooking techniques, ingredient pairings, nutrition knowledge, and more
- 🍽️ **Personalized Recommendations**: Provide dish suggestions based on user preferences, health goals, and dietary restrictions
- 📝 **Recipe Management**: Upload and manage personal recipes, building a custom knowledge base
- 🧠 **Deep Understanding**: Understand user intent through multi-turn conversations and provide precise suggestions
- 🌐 **Real-time Search**: Integrate web search to obtain the latest cooking information and trends

CookHero targets kitchen beginners, fitness enthusiasts, health-conscious users, people with allergies, and more, aiming to make cooking simple, scientific, and fun.

---

## ✨ Core Features

### 1. Intelligent Conversational Queries
- Natural language understanding of user needs (e.g., "I want to make a low-fat, high-protein dinner")
- Multi-turn conversation support with context history
- Automatic intent recognition (query, recommendation, chat, etc.)
- Streaming responses with real-time display

### 2. Hybrid Retrieval System
- **Vector Retrieval**: Semantic similarity matching (based on Milvus)
- **BM25 Retrieval**: Keyword exact matching
- **Metadata Filtering**: Filter by cooking time, difficulty, nutrition, etc.
- **Multi-level Caching**: Redis + Milvus dual-layer caching for improved response speed

### 3. Personalized Settings
- Users can upload personal recipes, which are automatically analyzed and indexed
- Global recipe library (from [HowToCook](https://github.com/Anduin2017/HowToCook)) merged with personal recipes
- Intelligent parsing of Markdown format recipes
- User profiling for preference-based recommendations
- Customizable model response style

### 4. Advanced Reranking
- Use specialized Reranker models for secondary sorting of retrieval results
- Improve result relevance and accuracy
- Support for Qwen3-Reranker-8B and other mainstream models

### 5. Web Search Enhancement
- Integrate Tavily search engine to automatically query online when knowledge base is insufficient
- Combine real-time information with local knowledge for comprehensive answers
- LLM-based intelligent search trigger decision

### 6. User System
- User registration/login (JWT authentication)
- Session management (multi-session isolation, history saving)
- Dual token mechanism (access token + refresh token)

### 7. Multimodal Support
- **Image Recognition**: Upload food/ingredient images for intelligent identification
- **Intent Understanding**: Combine images and text to understand complete user intent
- **Multiple Scenarios**: Dish identification, ingredient recognition, cooking guidance, recipe queries
- **Flexible Integration**: Support for OpenAI-compatible vision model APIs

### 8. RAG Evaluation System
- **Quality Monitoring**: Automated evaluation based on the RAGAS framework
- **Core Metrics**: Faithfulness, Answer Relevancy
- **Async Evaluation**: Background asynchronous execution without affecting response speed
- **Trend Analysis**: Support for evaluation trend viewing and quality alerts
- **Data Persistence**: Evaluation results stored in PostgreSQL

### 9. LLM Usage Statistics
- **Real-time Monitoring**: Track Token usage for each request
- **Performance Metrics**: Record response time, thinking time, generation time
- **Statistical Analysis**: Usage statistics by user, session, and module
- **Tool Tracking**: Record Agent tool call names
- **Visualization**: Frontend LLM statistics page

### 10. Security Protection System
- **Multi-layer Defense**: Input validation → Pattern detection → LLM deep detection
- **Prompt Injection Protection**: Dual detection mechanism based on rules and AI
- **Rate Limiting**: Redis sliding window algorithm with endpoint-specific limits
- **Account Security**: Login failure lockout, JWT expiration policy, security headers
- **Sensitive Data Protection**: Log sanitization, API key filtering
- **Security Audit**: Structured JSON audit logs, SIEM system integration support

> 📖 For detailed security architecture, see [Security Documentation](SECURITY.md)

### 11. Agent Intelligent Mode (New Feature)
- **ReAct Pattern**: Implements reasoning + action loop for autonomous decision-making and tool invocation
- **Built-in Tools**: Calculator, datetime, text processing and other practical tools
- **Extensible Architecture**: Support for custom Agent and Tool registration
- **Independent Session Management**: Agent sessions separated from standard conversations
- **Context Compression**: Automatically compress long conversation history to reduce Token consumption
- **Real-time Feedback**: SSE event stream for live display of tool calls and results
- **Execution Tracing**: Complete recording of Agent execution trajectory for debugging and analysis

---

## 🏗️ Technical Architecture

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      Frontend (React + TypeScript)                       │
│                      [Chat Mode]        [Agent Mode]                     │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         FastAPI Backend Service                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │
│  │  Auth Module│  │ Conversation│  │ Agent Module│  │ Evaluation  │   │
│  │             │  │   Module    │  │             │  │   Module    │   │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              ▼                     ▼                     ▼
┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
│   RAG Pipeline      │  │  Agent Execution    │  │   Security Layer    │
│ Intent→Rewrite→RAG  │  │  ReAct Loop + Tools │  │ Rate Limit+Guards   │
└─────────────────────┘  └─────────────────────┘  └─────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                            Data Storage Layer                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐               │
│  │PostgreSQL│  │  Redis   │  │  Milvus  │  │  MinIO   │               │
│  │(Main DB) │  │(L1 Cache)|  │(Vectors) │  │(Files)   │               │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘               │
└─────────────────────────────────────────────────────────────────────────┘
```

### RAG Pipeline Flow

1. **Intent Recognition**: Determine query type (recipe search, cooking tips, chat, etc.)
2. **Query Rewriting**: Optimize user input and extract key information
3. **Cache Query**: Check Redis and Milvus cache
4. **Hybrid Retrieval**:
   - Vector retrieval (semantic similarity)
   - BM25 keyword retrieval
   - Metadata filtering (cooking time, difficulty, etc.)
5. **Result Fusion**: Use weighted fusion or RRF (Reciprocal Rank Fusion)
6. **Reranking**: Reranker model for precise ranking
7. **Context Compression**: Extract most relevant segments
8. **LLM Generation**: Generate final answer combining retrieved content
9. **Web Enhancement** (optional): Trigger Tavily search when information is insufficient

---

## 📂 Project Structure

See [Project Structure Documentation](PROJECT_STRUCTURE.md)

---

## 🚀 Quick Start

### Prerequisites

- **Python**: >= 3.12
- **Node.js**: >= 18
- **Docker** and **Docker Compose** (recommended)

### Method 1: Docker One-Click Deployment (Recommended)

1. **Clone the repository**
   ```bash
   git clone https://github.com/Decade-qiu/CookHero.git
   cd CookHero
   ```

2. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env file and fill in necessary API Keys
   ```

3. **Start infrastructure**
   ```bash
   cd deployments
   docker-compose up -d
   ```
   This will start:
   - PostgreSQL (port 5432)
   - Redis (port 6379)
   - Milvus (port 19530)
   - MinIO (port 9001)
   - Etcd (internal use)

4. **Install Python dependencies and start backend**
   ```bash
   cd ..
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements.txt

   # Initialize database
   python -m scripts.howtocook_loader

   # Start backend service
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

5. **Start frontend**
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

6. **Access the application**
   - Frontend: http://localhost:5173
   - Backend API: http://localhost:8000
   - API Documentation: http://localhost:8000/docs

---

## ⚙️ Configuration

### 1. Environment Variables (`.env`)

Create a `.env` file (refer to `.env.example`):

```env
# ==================== LLM API Configuration ====================
# Main API Key (default for all modules)
LLM_API_KEY=your_main_api_key

# Fast Model API Key (for intent detection, query rewriting)
FAST_LLM_API_KEY=your_fast_model_api_key

# Vision Model API Key (for multimodal analysis)
VISION_API_KEY=your_vision_model_api_key

# Reranker API Key (for result reranking)
RERANKER_API_KEY=your_reranker_api_key

# ==================== Database Configuration ====================
DATABASE_PASSWORD=your_postgres_password

# Redis Password (optional)
REDIS_PASSWORD=your_redis_password

# Milvus Authentication (optional)
MILVUS_USER=root
MILVUS_PASSWORD=your_milvus_password

# ==================== Web Search ====================
WEB_SEARCH_API_KEY=your_tavily_api_key

# ==================== Security / Authentication ====================
JWT_SECRET_KEY=your_secure_jwt_secret_key
JWT_ALGORITHM=HS256

# Access token expiration (minutes)
ACCESS_TOKEN_EXPIRE_MINUTES=60

# Refresh token expiration (days)
REFRESH_TOKEN_EXPIRE_DAYS=7

# ==================== Rate Limiting ====================
RATE_LIMIT_ENABLED=true
RATE_LIMIT_LOGIN_PER_MINUTE=5
RATE_LIMIT_CONVERSATION_PER_MINUTE=30
RATE_LIMIT_GLOBAL_PER_MINUTE=100

# ==================== Account Security ====================
LOGIN_MAX_FAILED_ATTEMPTS=5
LOGIN_LOCKOUT_MINUTES=15
MAX_MESSAGE_LENGTH=10000
MAX_IMAGE_SIZE_MB=5
PROMPT_GUARD_ENABLED=true
```

### 2. Main Configuration File (`config.yml`)

`config.yml` contains the core configuration of the application:

```yaml
# LLM Provider Configuration (Layered: fast / normal)
llm:
  fast:    # Fast models (low latency)
  normal:  # Standard models (high quality)

# Data paths
paths:
  base_data_path: "data/HowToCook"

# Embedding model
embedding:
  model_name: "BAAI/bge-small-zh-v1.5"

# Vector store
vector_store:
  type: "milvus"
  collection_names:
    recipes: "cook_hero_recipes"
    personal: "cook_hero_personal_docs"

# Retrieval configuration
retrieval:
  top_k: 9
  score_threshold: 0.2
  ranker_type: "weighted"
  ranker_weights: [0.8, 0.2]

# Reranker configuration
reranker:
  enabled: true
  model_name: "Qwen/Qwen3-Reranker-8B"

# Cache configuration
cache:
  enabled: true
  ttl: 3600
  l2_enabled: true
  similarity_threshold: 0.92

# Web search configuration
web_search:
  enabled: true
  max_results: 6

# Vision/Multimodal configuration
vision:
  model:
    enabled: true
    model_name: "Qwen/QVQ-72B-Preview"

# Evaluation configuration
evaluation:
  enabled: true
  async_mode: true
  sample_rate: 1.0

# Database connections
database:
  postgres:
    host: "localhost"
    port: 5432
  redis:
    host: "localhost"
    port: 6379
  milvus:
    host: "localhost"
    port: 19530
```

See comments in `config.yml` for detailed explanations.

### 3. Security Configuration Details

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `JWT_SECRET_KEY` | **Required** | JWT signing key, must be set in production |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Access token expiration time (minutes) |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token expiration time (days) |
| `RATE_LIMIT_ENABLED` | `false` | Enable rate limiting |
| `RATE_LIMIT_LOGIN_PER_MINUTE` | `5` | Login endpoint rate limit per minute |
| `RATE_LIMIT_CONVERSATION_PER_MINUTE` | `30` | Conversation endpoint rate limit per minute |
| `RATE_LIMIT_GLOBAL_PER_MINUTE` | `100` | Global endpoint rate limit per minute |
| `LOGIN_MAX_FAILED_ATTEMPTS` | `5` | Failed login attempts before lockout |
| `LOGIN_LOCKOUT_MINUTES` | `15` | Account lockout duration (minutes) |
| `PROMPT_GUARD_ENABLED` | `true` | Enable prompt injection protection |
| `MAX_MESSAGE_LENGTH` | `10000` | Maximum message length (characters) |
| `MAX_IMAGE_SIZE_MB` | `5` | Maximum image size (MB) |

---

## 🛠️ Development Guide

### Backend Development

```
app/
├── api/v1/endpoints/   # API endpoint definitions
├── services/           # Business logic services
├── conversation/       # Conversation management module
├── agent/             # Agent intelligent module (ReAct + Tools)
├── rag/               # RAG pipeline implementation
├── security/          # Security protection module
├── llm/               # LLM provider
├── vision/            # Multimodal vision module
├── database/          # Database layer
└── config/            # Configuration module
```

- **Add new API endpoints**: Create new files in `app/api/v1/endpoints/`
- **Add new services**: Implement business logic in `app/services/`
- **Modify conversation flow**: Adjust conversation management logic in `app/conversation/`
- **Modify RAG pipeline**: Adjust retrieval process in `app/rag/pipeline/`
- **Add new Agent**: Inherit `BaseAgent` and use `@register_agent` decorator
- **Add new Tool**: Inherit `BaseTool` and use `@register_tool` decorator

### Frontend Development

```bash
cd frontend
npm run dev     # Development server
npm run build   # Production build
npm run lint    # Code linting
```

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific module tests
pytest tests/test_rag.py -v
pytest tests/test_guardrails.py -v
```

---

## 🗺️ Roadmap

- [x] **Multimodal Support**: Ingredient image recognition, dish identification ✅
- [x] **RAG Evaluation System**: Quality monitoring based on RAGAS ✅
- [x] **Security Protection System**: Input validation, prompt injection protection, rate limiting ✅
- [x] **LLM Usage Statistics**: Token monitoring, performance analysis page ✅
- [x] **Agent Intelligent Mode**: ReAct reasoning, tool invocation, session management ✅
- [ ] **Voice Interaction**: Voice input queries, voice step narration
- [ ] **Nutrition Analysis**: Automatic calculation of calories and nutrients
- [ ] **Community Features**: User sharing, ratings, comments
- [ ] **Smart Ingredient Management**: Fridge inventory, expiration reminders
- [ ] **AR Cooking Guidance**: Augmented reality cooking assistance
- [ ] **More Agent Tools**: Recipe search, nutrition calculation, shopping list generation

---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome!

1. Fork the project
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the [APACHE LICENSE 2.0](LICENSE). See the LICENSE file for details.

---

## 🙏 Acknowledgments

- [HowToCook](https://github.com/Anduin2017/HowToCook) - Quality open-source recipe library
- [LangChain](https://www.langchain.com/) - Powerful LLM application framework
- [Milvus](https://milvus.io/) - High-performance vector database
- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [NVIDIA NeMo Guardrails](https://developer.nvidia.com/nvidia-nemo) - Advanced security protection framework
- [RAGAS](https://docs.ragas.io/) - RAG evaluation framework

---

<div align="center">

**If this project helps you, please give it a ⭐️ Star!**

</div>
