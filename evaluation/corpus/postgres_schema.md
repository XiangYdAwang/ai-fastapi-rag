# PostgreSQL Schema

Synthetic evaluation fixture for retrieval testing.

The schema contains documents and document_chunks tables. Document identifiers use UUID values. Chunk metadata is stored in JSONB and deleting a document cascades to its chunks.
