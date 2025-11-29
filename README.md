## 1 Project Overview

CookHero is an intelligent dietary assistant system aimed at the general public, providing full-process support from kitchen preparation, recipe learning, nutrition planning, dietary recommendations to personalized plan creation. The system is primarily developed in Python, utilizes LangChain to build retrieval-augmented generation (RAG), intelligent agents, and vector retrieval capabilities, employs Milvus as a vector database, and provides unified REST APIs for frontend use. The frontend is planned to be implemented with React and TypeScript for user interface development.

The system integrates built-in recipes, user-uploaded recipes, cafeteria menus, and potential external delivery platform data. Using large language models and retrieval systems, it provides users with cooking knowledge Q&A, food recommendations, and diet plan formulation. The system supports both on-demand queries and deep personalized recommendations based on users’ long-term habits and health goals.

## 2 Project Technology Stack

The main technology choices for this project include:

Python as the core development language, responsible for backend logic, RAG pipelines, data processing, and model invocation. LangChain is used for constructing retrieval chains, data processing chains, intelligent agent workflows, and tool-call interfaces. Milvus serves as the vector store, supporting high-performance vector retrieval, suitable for managing recipe texts, images, and multi-modal embeddings. The backend web service encapsulates core capabilities and exposes them via REST API. The frontend uses React with TypeScript to provide conversational interfaces, recipe display pages, recommendation pages, and user management interfaces. Additional foundational components include relational databases for storing structured information, high-performance caching for recommendation efficiency, multi-modal embedding models for recipe image-text vectorization, and language models for answer generation, plan generation, and intelligent routing.

## 3 User Roles and Use Cases

CookHero targets a diverse range of users, designed to meet the dietary learning, health management, and efficient decision-making needs of different groups. Key user roles include kitchen novices, fitness or weight-loss users, health-conscious users, users with allergies or dietary restrictions, users relying on cafeterias or external dining services, and those who enjoy homemade dishes and want to record and manage them.

Typical use cases include daily recipe queries. When a user needs a low-fat, high-protein dinner, wants to understand kitchen preparation methods, or wishes to learn how to cook a particular dish, the system will combine its knowledge base and LLM to generate explanations and guidance. Users can also quickly receive optional dish recommendations, such as selecting suitable dishes from current cafeteria menus according to dietary restrictions and preferences. For users with health goals, the system can generate daily or weekly diet plans based on basic information, exercise records, and long-term goals, dynamically adjusting as the user updates their lifestyle. The system can also automatically generate shopping lists based on recipes, guiding ingredient preparation or storage. As user interactions accumulate, the system will gradually learn user tastes and behavior patterns to provide increasingly precise personalized recommendations.

## 4 System Architecture Overview

The overall architecture of CookHero consists of frontend interface layer, backend service layer, intelligent engine layer, and data storage layer. Clear interfaces between layers ensure flexibility while maintaining scalability. The architecture centers around RAG pipelines, intelligent agents, recommendation systems, and multi-source data management, facilitating easy integration of new model capabilities and data sources in future versions.

Example workflow:

1. Users input their needs through the conversational interface, such as “I want a low-fat, high-protein dinner with chicken breast and broccoli,” “Please recommend some light dishes suitable for summer,” or “I am allergic to peanuts, can you suggest peanut-free recipes?” or “I want to learn how to prepare kitchen utensils and ingredients.”
2. The Query Translation module converts user queries into a format suitable for retrieval using rule matching or LLM, possibly splitting into multiple sub-queries.
3. The Query Routing module decides whether the query requires knowledge base retrieval or direct LLM generation. If retrieval is needed, it routes the query to the corresponding retrieval module, using rule-based or LLM-based routing.
4. The Query Construction module transforms the routed query into a retrievable format, e.g., converting to SQL for relational database retrieval or vector query for vector database retrieval (future expansion may include graph database queries).
5. The Indexing module preprocesses and indexes recipe and other content for retrieval, involving:
   - **Chunk Optimization**: Segment long texts to ensure chunks are suitable for vectorization and retrieval.
   - **Multimodal Embedding**: Convert images and other modalities into vectors using multi-modal embedding.
   - **Hybrid Embedding**: Combine sparse and dense vectors to improve retrieval performance.
   - **Context Expansion**: Use sentence windows to extend context for small chunks, enhancing retrieval relevance.
   - **Structured Indexing**: Attach structured metadata (e.g., nutrition, cooking time) to enable filtered, targeted vector similarity search.
   - **Hierarchical Indexing**: Organize multiple indices, performing coarse-grained retrieval first, then fine-grained retrieval for efficiency and accuracy.
6. The Re-Ranking and Refinement module enhances initial retrieval results using more complex models:
   - **Reciprocal Rank Fusion (RRF)**: Fuse multiple retrievers’ results by ranking scores.
   - **RankLLM / LLM-based Reranker**: Use LLMs to rerank preliminary retrieval results.
   - **Cross-Encoder Re-Ranking**: Score query-document pairs using Cross-Encoder models.
   - **ColBERT Re-Ranking**: Use ColBERT for refined ranking.
7. Optionally, a Correction-RAG approach can be applied, where a Retrieval Evaluator assesses each document’s relevance, labeling them as “Correct,” “Incorrect,” or “Ambiguous.” Correct documents proceed to knowledge refinement and answer generation; incorrect or ambiguous results trigger query rewriting and external web searches for additional information.
8. Finally, retrieved information is integrated by the LLM to generate user responses.

The main data flow begins with user input, which passes through query understanding modules for intent recognition and query conversion. Parsed queries are routed to appropriate retrieval methods—vector retrieval, structured query, rule-based query, or external sources. Retrieved content is combined with the LLM in the generation stage to produce answers. For recommendation queries, the system uses user profiles and dish metadata to generate strategies and return suitable dishes or diet plans.

Major submodules include the frontend interaction module, backend API service, query understanding module, routing module, RAG pipeline, recommendation module, user profiling module, data synchronization module, and indexing module. Each module maintains single responsibility, facilitating maintenance and replacement. The RAG pipeline handles text and multi-modal retrieval; the recommendation module computes dish, cafeteria, or meal plan suggestions; the data synchronization module ingests user uploads and external recipe data; the indexing module builds vector indices, metadata structures, and hybrid retrieval structures.

Backend technology choices prioritize Python with FastAPI for REST API construction, facilitating integration with LangChain. The RAG pipeline uses LangChain and Milvus for hybrid retrieval, extendable to sparse retrieval, multi-modal vectors, or hierarchical indexing. Intelligent agents rely on LangChain Agents for query parsing, tool calling, and task allocation. Recommendation systems combine rule-based, statistical, and model inference approaches, with potential upgrades to deep learning-based personalization. Relational databases store structured user and recipe information, while vector databases handle semantic content and embeddings.

Module responsibilities:

- Frontend: presents pages and passes user input.
- Backend: manages data scheduling and API encapsulation.
- Query understanding: analyzes user request types.
- Routing: selects optimal retrieval or generation methods.
- RAG pipeline: knowledge retrieval and enhancement.
- Recommendation: returns suitable dishes based on preferences and context.
- User profiling: aggregates historical behavior and health info.
- Data storage: persists text, structured data, and vectors.

Each module collaborates to form a clear data and task flow from input to answer generation.

## 5 Module Design

CookHero’s module design follows the “high cohesion, low coupling” principle, achieving a maintainable, extensible service system. Modules communicate via standardized interfaces, enabling independent evolution while supporting overall data flow and business logic. The following sections describe the design rationale and responsibilities of core modules.

### 5.1 Frontend Interaction Module

The frontend is implemented in React and TypeScript, consisting of conversational interface, recipe browsing, recommendation and planning, and user management. It communicates with the backend via REST API, structuring user input and displaying results visually. The interface emphasizes simplicity and intuitiveness, with a component-based design enabling extensions like image-text recipe previews, interactive nutrition charts, or personalized recommendation entry points.

### 5.2 API Service Module

The backend core is implemented with FastAPI, unifying query, retrieval, recommendation, user management, and data synchronization endpoints. The API layer handles request validation, access control, logging, exception handling, and orchestrates downstream intelligent engines. Asynchronous processing and caching can enhance performance under high concurrency. All user-facing capabilities are exposed via this module as the service entry point.

### 5.3 Query Understanding Module

The query understanding module analyzes user input, extracting task types and relevant parameters. It consists of an intent classifier, parameter extractor, and query standardization component. The intent classifier determines whether the user request involves recipe Q&A, step parsing, nutrition query, dish recommendation, or diet plan creation. The parameter extractor identifies ingredients, dish names, nutrition goals, timeframes, or user constraints. Finally, queries are converted into a unified internal format for subsequent processing.

### 5.4 Routing Module

The routing module selects the most appropriate handling method based on query type, acting as a system scheduler. Queries involving recipe content go to the RAG pipeline; those related to user status or health goals go to the recommendation module; cross-module or multi-step queries are handled by the intelligent agent. Routing rules may be rule-based or dynamically model-driven to handle complex scenarios.

### 5.5 RAG Pipeline

The RAG pipeline is the core knowledge retrieval and response generation component. It includes text vector retrieval, multi-modal retrieval, retrieval-augmented generation, template-based response generation, and retrieval caching. All recipe texts, steps, ingredient info, and user-uploaded documents are vectorized and stored in Milvus, then combined with the language model for response synthesis. Multi-modal embeddings for images and notes allow cross-modal retrieval.

### 5.6 Intelligent Agent Module

The intelligent agent handles multi-step, cross-module tasks, e.g., “Generate a one-week high-protein, low-fat plan and corresponding shopping list.” It calls the query understanding module, recommendation module, and data processing tools, integrating results for the user. Built on LangChain Agents, it supports tool invocation, task decomposition, reflection, and result validation, providing high flexibility.

### 5.7 Recommendation Module

The recommendation module combines rules, statistical features, and model inference to provide personalized dish suggestions. Recommendation logic covers cafeteria menu filtering, dish similarity calculation, preference-based collaborative filtering, nutrition goal matching, and historical behavior analysis. For users with weight-loss, muscle gain, or dietary restrictions, recommendations are dynamically adjusted. The module can evolve to deep learning-based or sequential recommendation models for enhanced personalization.

### 5.8 User Profiling Module

The user profiling module aggregates historical queries, taste preferences, nutrition needs, health goals, allergy info, and behavior patterns to build continuously updated feature vectors. It supports both explicit user input and implicit behavior inference, forming the foundation for precise recommendations and personalized plan creation.

### 5.9 Data Synchronization Module

The data synchronization module handles user-uploaded recipes, external recipe data, cafeteria menus, and delivery platform data. It standardizes formats, parses text, processes images, extracts metadata, and updates indices to ensure multi-source data is ready for the RAG pipeline and recommendation module. For dynamic sources like daily cafeteria menus, scheduled synchronization is provided.

### 5.10 Indexing Module

The indexing module generates and updates vector, sparse, and structured indices. It supports incremental updates and batch construction, allowing index upgrades without affecting live services. Multi-modal content maintains separate embeddings; complex queries leverage hybrid retrieval to improve recall and accuracy.

------

## 6 RAG Pipeline Design and Implementation

RAG (Retrieval-Augmented Generation) is one of CookHero’s core capabilities, providing a reliable information foundation for recipe Q&A, step parsing, nutrition explanation, and dish comparison. To accommodate multi-source, multi-modal recipe content, CookHero’s RAG pipeline adopts a hierarchical and extensible design, supporting unified retrieval from text, images, structured metadata, and external sources.

### 6.1 Overall Process

The RAG pipeline data flow starts from the parsed query and goes through retrieval, candidate fusion, and generation stages. First, the appropriate retrieval mode—vector, keyword, or hybrid—is selected based on query content. Retrieved candidates are semantically filtered and re-ranked, selecting the most relevant information as context. The context and original query are sent to the language model, which generates structured or natural language responses.

### 6.2 Data Preparation and Vector Construction

High-quality vectorized data is fundamental. CookHero builds a unified content pipeline for recipes, ingredients, cooking techniques, nutrition info, and user uploads. Text undergoes sentence splitting, denoising, and metadata completion to ensure retrievability. Recipe or user-uploaded images are encoded into vectors via multi-modal embedding models, enabling cross-modal retrieval. All vectors and metadata are synchronized to Milvus for efficient retrieval.

### 6.3 Retrieval Strategy Design

Retrieval strategies differ by scenario. Structured info like calories, macronutrients, or cooking time is primarily retrieved via keyword or structured queries. Cooking steps, dish reviews, and technical knowledge are retrieved via semantic vector search. For complex queries like “low-fat, high-protein, non-spicy stir-fry,” hybrid retrieval combining keyword filtering and vector recall improves accuracy.

### 6.4 Result Filtering and Re-Ranking

Initial retrieval may contain duplicates, noise, or fragmented content, requiring secondary filtering and re-ranking. Filtering rules consider query topic, dish category, and ingredient consistency. Re-ranking uses semantic matching models to score candidates, ensuring context entering generation aligns with user needs. Context diversity may also be considered to avoid overly uniform outputs or missing critical info.

### 6.5 Context Assembly and Response Generation

Once candidates are selected, they are organized into a unified context format and combined with the original query for the LLM. Context organization varies by task: Q&A uses concise paragraphs, step parsing uses sequential step lists, and nutrition info uses parameterized formats. The model generates responses, including reasoning or guidance as needed.

### 6.6 Multi-Modal RAG

CookHero supports multi-modal RAG for image-text tasks. For example, if a user uploads an ingredient photo asking “What can I cook,” the system encodes the image into a vector and retrieves related dishes or ingredients. Multi-modal RAG also handles illustrated recipes, cooking demonstration images, and mixed media notes for natural interaction understanding.

### 6.7 Caching and Performance Optimization

To reduce redundant retrieval and generation costs, the RAG pipeline implements query and result caching. Popular recipes, common cooking methods, and frequently requested tips are pre-cached. Retrieval caching alleviates vector database load under high concurrency; generation caching accelerates response times for stable outputs.

### 6.8 Reliability and Continuous Iteration

For robustness, fallback mechanisms exist. If vector retrieval fails, the system reverts to keyword search; if the model load is high, complex queries are paused in favor of essential Q&A. The RAG design allows integration of new embedding models, re-rankers, or structured knowledge sources for continuous iteration.

## 7 Recommendation System Design and Implementation

The recommendation system provides personalized dish and dietary plan suggestions, leveraging user profiles, historical behavior, dish features, and health goals for precise, efficient service.

### 7.1 System Goals

- Offer personalized dish recommendations satisfying user taste, nutrition, and dietary restrictions.
- Support multi-source recommendations from cafeteria menus, user-uploaded dishes, and external platforms.
- Dynamically adjust daily or weekly plans according to user activity, health goals, and behavior changes.
- Provide explainable recommendations to enhance user trust and system usability.

### 7.2 Data Sources and Processing

Sources include:

- **Built-in and user-uploaded recipes**: forming dish feature vectors and category labels.
- **Cafeteria and delivery platform data**: obtained via scraping or APIs.
- **User profiles and behavior**: historical queries, preferences, dietary restrictions, and health goals.

Data is standardized, cleaned, feature-extracted, and converted into embeddings. Text and image embeddings support similarity computation and recall.

### 7.3 Recommendation Strategies

Hybrid methods:

- **Rule and constraint strategies**: filter by allergies, restrictions, and nutritional needs.
- **Feature-based similarity**: recommend similar dishes based on embedding similarity.
- **Collaborative filtering and behavior prediction**: leverage past behavior and similar users.
- **Health goal alignment**: generate daily or weekly plans matching objectives.
- **Dynamic adjustment**: update recommendations with real-time feedback or new behaviors.

### 7.4 Output and Interaction

Recommendations include dish lists, personalized diet plans, nutrition info, and shopping lists. Frontend displays rationale and matching metrics. Recommendation module integrates with RAG to provide explanatory guidance.

### 7.5 Performance and Scalability

Caching and batch computation support high concurrency and large-scale users. Interfaces can be extended to deep learning, sequential recommendation, or reinforcement learning models for long-term personalization.

## 8 Intelligent Agent System Design

The intelligent agent system handles complex, multi-step tasks, orchestrating modules for multi-objective, cross-module intelligent operations.

### 8.1 System Goals

- Automatically handle complex tasks like “Generate a weekly diet plan with shopping list.”
- Orchestrate RAG, recommendation, and data processing tools.
- Support task decomposition, reflection, and self-correction.
- Provide flexible interfaces for integrating new tools or external services.

### 8.2 Core Capabilities

- **Task parsing and decomposition**: split complex queries into sub-tasks.
- **Tool invocation**: call RAG, recommendation, or external APIs as needed.
- **Result integration**: merge, reason, or format outputs into a complete response.
- **Self-correction and optimization**: retry or use alternatives when sub-tasks fail or results are unsatisfactory.

### 8.3 Implementation

Built on LangChain Agents:

- **Multi-tool support**: flexible invocation of retrieval, recommendation, computation, and planning modules.
- **Dynamic task scheduling**: decide execution order based on complexity and real-time state.
- **Strategy extensibility**: gradually increase task types or complexity.
- **Explainability**: log agent decisions for analysis and optimization.

### 8.4 Application Examples

- Generate a personalized weekly meal plan with daily meals and nutrition info.
- Recommend cafeteria options with nutrition analysis and allergy warnings.
- Integrate multiple sources to answer complex queries like “I want light, high-protein summer dishes avoiding peanuts.”

The intelligent agent enables CookHero to handle single queries to comprehensive cross-module tasks automatically, enhancing user experience and system intelligence.

## 9 Non-Functional Requirements and System Performance Design

Non-functional requirements ensure CookHero’s reliability, efficiency, and sustainability beyond functionality, forming a critical part of system design.

### 9.1 Performance and Responsiveness

CookHero must maintain good response under high concurrency:

- **Query response time**: 1–2 seconds for standard Q&A or recommendation, 3–5 seconds for high-complexity generation tasks.
- **Throughput**: support hundreds to thousands of concurrent users.
- **Retrieval efficiency**: optimize Milvus indices and strategies for high recall with low latency.
- **Caching**: cache popular queries, recipes, and generated content to accelerate response and reduce computation.

### 9.2 Scalability

Design supports functional and user-scale expansion:

- **Modular architecture**: modules deploy independently, allowing upgrades or extensions

(RAG, recommendation, intelligent agent).

- **Multi-source data expansion**: import new recipe sources, cafeteria APIs, or delivery platform data without altering core logic.
- **Model upgrades**: smoothly replace LLMs, vectorization, or recommendation models to enhance performance or integrate new algorithms.

### 9.3 Availability and Reliability

Ensure stability across environments:

- **Fault isolation**: modules can degrade gracefully without halting overall service.
- **Fault tolerance**: RAG and intelligent agent employ fallback strategies.
- **Health monitoring**: backend provides logs and status monitoring for timely issue detection.

### 9.4 Security and Privacy

Protect user health and dietary data:

- **Data transmission security**: HTTPS for API communication.
- **User data isolation**: separate storage for different users’ history and preferences.
- **Access control**: restrict sensitive operations and data access.
- **Sensitive info handling**: anonymize uploaded photos and personal health data during storage and analysis.

### 9.5 Maintainability and Testability

Support long-term maintenance and fast iteration:

- **Independent testing**: unit and integration tests for each module.
- **Logging and tracing**: detailed logs for RAG queries, recommendation generation, and intelligent agent tasks.
- **Configurable management**: system parameters, model paths, and recommendation strategies adjustable via configuration files or management interfaces without code changes.

### 9.6 User Experience and Usability

Enhance overall user experience:

- **Smooth interface response**: frontend interactions are fluid with timely feedback.
- **Result explainability**: recommendations and generated responses include explanations or references.
- **Multi-device support**: system works well on desktops, mobile, and tablets.

Through these non-functional designs, CookHero delivers a feature-rich, stable, secure, efficient, and continuously iteratable service, providing users with a long-term reliable dietary assistant experience.