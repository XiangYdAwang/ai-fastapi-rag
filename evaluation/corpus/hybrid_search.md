# Hybrid Search

Synthetic evaluation fixture for retrieval testing.

Hybrid search combines pgvector and pg_trgm results. Reciprocal Rank Fusion uses RRF_K equal to 60. The candidate limit is the maximum of 20 and four times top_k.
