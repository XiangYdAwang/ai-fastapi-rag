# Performance Tuning

Synthetic evaluation fixture for retrieval testing.

Embedding requests are processed in batches of 32. Hybrid search initially retrieves up to 20 candidates. The API limits top_k to a maximum value of 20.
