# AI FastAPI RAG Platform

一个面向中小规模知识库场景的 RAG 后端项目，使用 FastAPI、PostgreSQL/pgvector、LiteLLM 和 Langfuse 构建。

项目覆盖文档解析、文本切分、Embedding、向量检索、关键词检索、RRF 融合、Rerank、RAG 问答和调用链追踪。

## 技术栈

| 模块 | 技术 |
|---|---|
| Web API | FastAPI, Uvicorn |
| 数据库 | PostgreSQL 16 |
| 向量检索 | pgvector, HNSW, cosine distance |
| 关键词检索 | pg_trgm |
| 融合排序 | Reciprocal Rank Fusion |
| 二次排序 | BAAI/bge-reranker-v2-m3 |
| 模型接入 | LiteLLM |
| Embedding | BAAI/bge-m3, 1024 dimensions |
| 数据迁移 | Alembic |
| 可观测性 | Langfuse |
| 文档解析 | TXT, Markdown, PDF, DOCX |

## 核心能力

- 支持 TXT、Markdown、PDF、DOCX 文档上传和文本提取。
- 对文本进行可配置分块，并保存来源、块序号和元数据。
- 使用 LiteLLM 调用 OpenAI-compatible Embedding 和 Chat 模型。
- 使用 PostgreSQL/pgvector 持久化 1024 维向量。
- 使用 HNSW 索引执行余弦相似度检索。
- 使用 pg_trgm 补充字符级关键词召回。
- 使用 RRF 融合向量排名和关键词排名。
- 使用 BGE Reranker 对候选文本进行二次排序。
- Rerank 失败时自动降级到 RRF 排序。
- 使用 Langfuse 记录 Embedding、Rerank 和 RAG Chat 调用链。
- 提供可重复运行的检索评测脚本。

## 系统架构

```mermaid
flowchart LR
    C[Client] --> API[FastAPI API]
    API --> UP[Document Upload]
    UP --> P[Parser]
    P --> CH[Text Chunker]
    CH --> E[LiteLLM Embedding]
    E --> DB[(PostgreSQL + pgvector)]

    API --> Q[Query Embedding]
    Q --> VR[pgvector Vector Search]
    API --> LR[pg_trgm Lexical Search]
    VR --> RRF[RRF Fusion]
    LR --> RRF
    RRF --> RR[BGE Reranker]
    RR --> CTX[Context Builder]
    CTX --> LLM[LiteLLM Chat Model]
    LLM --> API
    API --> LF[Langfuse]
```

## RAG 流程

### 文档写入

```text
Upload
-> Parse
-> Chunk
-> Embedding
-> documents
-> document_chunks
```

### 在线检索

```text
Question
-> Query Embedding
-> pgvector Top-N
-> pg_trgm Top-N
-> RRF Fusion
-> BGE Rerank
-> Final Top-K
```

### 问答生成

```text
Question + Retrieved Context
-> LiteLLM Chat Model
-> Answer + Sources
-> Langfuse Trace
```

## 数据模型

```mermaid
erDiagram
    DOCUMENTS ||--o{ DOCUMENT_CHUNKS : contains

    DOCUMENTS {
        uuid id PK
        string filename
        string content_type
        int file_size
        string status
        datetime created_at
        datetime updated_at
    }

    DOCUMENT_CHUNKS {
        uuid id PK
        uuid document_id FK
        int chunk_index
        text content
        vector embedding
        jsonb metadata
        datetime created_at
    }
```

## API

| Method | Path | Description |
|---|---|---|
| GET | `/health` | 服务健康检查 |
| GET | `/health/db` | 数据库连接检查 |
| POST | `/api/documents/upload` | 上传并解析文档 |
| POST | `/api/documents/{document_id}/embed` | 为未处理的文本块生成 Embedding |
| POST | `/api/search` | Hybrid Search + Rerank |
| POST | `/api/chat` | RAG 问答并返回引用来源 |
| POST | `/api/chat/stream` | SSE 流式 RAG 问答 |

Swagger UI：

```text
http://127.0.0.1:8000/docs
```

## 流式问答

接口：

```text
POST /api/chat/stream
```

响应类型：

```text
text/event-stream
```

事件类型：

- `sources`：先返回本次检索到的引用来源。
- `token`：逐段返回模型生成内容。
- `done`：返回完整回答。
- `error`：流式调用失败时返回错误信息。

示例：

```json
{"query":"pgvector 是什么","top_k":3}
```

SSE 输出示例：

```text
event: sources
data: {"sources":[...]}

event: token
data: {"content":"pgvector"}

event: done
data: {"answer":"pgvector 是 PostgreSQL 的向量扩展..."}
```

Python 客户端示例：

```python
import httpx

with httpx.stream(
    "POST",
    "http://127.0.0.1:8000/api/chat/stream",
    json={"query": "pgvector 是什么", "top_k": 3},
) as response:
    for line in response.iter_lines():
        print(line)
```

流式调用完成后仍会写入 Langfuse，Trace 名称为 `rag-chat`。
## 一键演示

启动 FastAPI 后执行：

```powershell
python -m scripts.demo_rag
```

脚本会自动完成：

```text
上传 sample.pdf
生成 Embedding
执行 Hybrid Search + Rerank
调用 SSE 流式问答
打印 sources、token 和 done 事件
```

可选参数：

```powershell
python -m scripts.demo_rag `
  --file sample.pdf `
  --query "What is pgvector?" `
  --top-k 3
```

面试讲解、技术取舍和常见问题整理在：

```text
docs/interview.md
```
## 环境要求

- Python 3.11
- Docker Desktop
- PostgreSQL + pgvector container
- SiliconFlow 或其他 OpenAI-compatible 模型服务
- Langfuse Cloud 或自托管 Langfuse

## 本地启动

### 1. 创建并激活环境

```powershell
conda create -n ai-app python=3.11 -y
conda activate ai-app
python -m pip install -r requirements.txt
```

### 2. 配置环境变量

```powershell
Copy-Item .env.example .env
```

编辑 `.env`，至少配置：

```dotenv
DATABASE_URL=postgresql+asyncpg://aiuser:ai_password_123@127.0.0.1:5433/airag
EMBEDDING_API_KEY=your_key
EMBEDDING_API_BASE=https://api.siliconflow.cn/v1
CHAT_MODEL=openai/Qwen/Qwen2.5-7B-Instruct
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=your_public_key
LANGFUSE_SECRET_KEY=your_secret_key
LANGFUSE_HOST=https://us.cloud.langfuse.com
```

不要提交 `.env`。

### 3. 启动 PostgreSQL

```powershell
docker compose up -d postgres
docker compose ps
```

### 4. 执行数据库迁移

```powershell
alembic upgrade head
```

### 5. 启动 FastAPI

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## 检索评测

评测数据：

```text
evaluation/corpus
evaluation/qa_dataset_corpus.jsonl
```

批量导入评测语料：

```powershell
python -m scripts.import_evaluation_corpus
```

运行评测：

```powershell
python -m scripts.evaluate_retrieval `
  --dataset evaluation/qa_dataset_corpus.jsonl `
  --top-k 5
```

当前合成评测集包含 18 篇文档和 36 条唯一来源问题。

| Pipeline | HitRate@1 | HitRate@5 | MRR |
|---|---:|---:|---:|
| Hybrid Search | 0.9444 | 1.0000 | 0.9722 |
| Hybrid Search + Rerank | 1.0000 | 1.0000 | 1.0000 |

这些指标来自合成评测文档，用于验证检索链路和排序策略，不代表真实业务数据。

### 项目源码语料评测

项目自身源码、迁移、测试和设计文档也已转换为 29 篇真实项目语料，并配套 30 条代码知识问题。

| Pipeline | HitRate@1 | HitRate@5 | MRR |
|---|---:|---:|---:|
| Hybrid Search | 0.2333 | 0.7667 | 0.4100 |
| Hybrid Search + Rerank | 0.3333 | 0.7667 | 0.5000 |

这组结果低于合成语料。结构感知分块和 Rerank 后，HitRate@1 从 0.3333 提升到 0.3667，HitRate@5 从 0.7667 提升到 0.8333。Rerank 在代码知识库上明显必要。

项目还实现了可选的 AST 函数级代码分块，通过 `AST_CHUNKING_ENABLED=true` 启用。单独使用 AST 分块时，HitRate@1 降到 0.2667，HitRate@5 降到 0.7000，因此默认关闭，保留作为后续多粒度检索实验能力。

Parent-child 多粒度检索也已实现，通过 `PARENT_CHILD_ENABLED=true` 启用。实测 HitRate@1 仍为 0.3667，HitRate@5 仍为 0.8333，MRR 从 0.5528 降到 0.5383，因此默认关闭。

同时开启 AST 和 parent-child 后，代码语料指标进一步降到 HitRate@1 = 0.2333、HitRate@5 = 0.7333、MRR = 0.4167。当前实验结果说明，单纯缩小检索粒度不能解决代码知识库的主要召回问题，后续需要改进查询改写、代码标识符提升或代码专用 Reranker。

该结果说明项目仍需要代码感知分块和代码检索优化，不应把当前代码知识库指标作为最终效果。

## 可观测性

Langfuse 中主要 Trace：

```text
search-query-embedding
embed-document-<document_id>
rerank-results
rag-chat
```

记录内容包括：

- 模型名称
- 输入和输出
- Token 使用量
- 调用耗时
- 错误信息
- Tags 和 metadata

## 项目结构

```text
app/
  api/          HTTP routes
  core/         Configuration and observability
  db/           SQLAlchemy engine and session
  models/       ORM models
  schemas/      Pydantic schemas
  services/     Parsing, embedding, search, rerank, chat
evaluation/
  corpus/       Evaluation documents
  results/      Evaluation reports
  qa_dataset*.jsonl
migrations/     Alembic migrations
scripts/        Evaluation and import utilities
tests/          Automated tests
```

## 自动化测试

安装测试依赖：

```powershell
python -m pip install -r requirements-dev.txt
```

运行测试：

```powershell
python -m pytest
```

当前测试覆盖：

- TXT 和 DOCX 文档解析
- 非法编码和格式校验
- 文本分块
- Rerank 成功排序
- Rerank 失败自动降级
- SSE 流式事件格式
- 评测数据加载与相关性判断
- FastAPI 健康检查和 OpenAPI 路由

GitHub Actions 配置位于 `.github/workflows/ci.yml`。
## 当前限制

- 扫描版 PDF 暂不支持 OCR。
- Rerank 依赖外部模型服务。
- 暂无用户认证和权限隔离。
- 暂无后台任务队列，长文档处理仍同步执行。
- RAGFlow 尚未接入。
- 当前评测集为合成数据，仍需补充真实业务文档。

## Roadmap

- 增加 pytest 接口测试和 CI。
- 增加 PDF 页码引用。
- 增加多轮对话。
- 增加流式回答。
- 增加真实文档评测集。
- 增加 Dockerize FastAPI 和部署文档。
- 评估 RAGFlow 接入。