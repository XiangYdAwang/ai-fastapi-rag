# Architecture Overview

Synthetic evaluation fixture for retrieval testing.

The Orion RAG Platform exposes its FastAPI application on port 8000. PostgreSQL listens on container port 5432 and host port 5433. The request flow is API, retrieval, rerank, and generation.
