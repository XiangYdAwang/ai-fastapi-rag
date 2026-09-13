# Retrieval Evaluation

## Purpose

The evaluation script measures whether the correct source appears in the retrieved results and how early it appears.

This allows retrieval changes to be compared instead of relying only on manual inspection.

## Metrics

### HitRate@1

The percentage of queries where the first retrieved result is relevant.

### HitRate@K

The percentage of queries where at least one of the first K results is relevant.

### MRR

Mean Reciprocal Rank.

For each query:

```text
reciprocal_rank = 1 / rank_of_first_relevant_result
```

If no relevant result is retrieved, the reciprocal rank is zero.

## Dataset Format

Each JSONL line contains:

```json
{
  "id": "corpus-01-q1",
  "question": "Which port does the API expose?",
  "expected_document": "architecture_overview.md",
  "expected_keywords": ["8000"]
}
```

Fields:

- `id`: unique question identifier.
- `question`: query sent to retrieval.
- `expected_document`: filename that should be retrieved.
- `expected_keywords`: phrases that should occur in the matching chunk.

## Running

Import the corpus:

```powershell
python -m scripts.import_evaluation_corpus
```

Run evaluation:

```powershell
python -m scripts.evaluate_retrieval `
  --dataset evaluation/qa_dataset_corpus.jsonl `
  --top-k 5
```

Reports are written to:

```text
evaluation/results
```

## Current Synthetic Benchmark

The current benchmark uses 18 synthetic Markdown documents and 36 questions.

| Pipeline | HitRate@1 | HitRate@5 | MRR |
|---|---:|---:|---:|
| Hybrid Search | 0.9444 | 1.0000 | 0.9722 |
| Hybrid Search + Rerank | 1.0000 | 1.0000 | 1.0000 |

Rerank improved Top-1 ranking on this benchmark.

These results are useful for regression testing and implementation validation. They should not be presented as real-world production results.

## Project Code Corpus

A second benchmark was built from the project's own source code, migrations, tests, and design documents.

- 29 real project files.
- 30 unique code-knowledge questions.

| Pipeline | HitRate@1 | HitRate@5 | MRR |
|---|---:|---:|---:|
| Hybrid Search | 0.2333 | 0.7667 | 0.4100 |
| Hybrid Search + Rerank | 0.3333 | 0.7667 | 0.5000 |

The structural chunking experiment improved the reranked pipeline: HitRate@1 increased from 0.3333 to 0.3667, and HitRate@5 increased from 0.7667 to 0.8333. The result also shows that Rerank is essential on this code corpus.

An optional AST function-level chunking mode was also implemented behind `AST_CHUNKING_ENABLED`. Used alone, it reduced HitRate@1 to 0.2667 and HitRate@5 to 0.7000. It is therefore disabled by default and retained for future multi-granularity retrieval experiments.

A parent-child mode is available behind `PARENT_CHILD_ENABLED`. It searches child chunks and expands the result to parent context. On the project code corpus it produced HitRate@1 = 0.3667, HitRate@5 = 0.8333, and MRR = 0.5383. This did not improve over the structural baseline and is disabled by default.

Combining AST child chunking with parent-child expansion performed worse: HitRate@1 = 0.2333, HitRate@5 = 0.7333, and MRR = 0.4167. The combined mode is therefore also disabled by default.

The next optimization target is code-aware chunking:

- Split Markdown by headings.
- Split Python by top-level classes and functions using `ast`.
- Store `source_path`, `symbol_name`, `start_line`, and `end_line`.
- Evaluate again against the same questions.

## Next Evaluation Step

Replace the synthetic corpus with real documents while keeping the same evaluation format.

Recommended target:

- At least 30 distinct documents.
- At least 30 to 50 questions.
- Multiple question types: factual, comparison, numeric, acronym, and multi-chunk.
- A held-out set not used while tuning retrieval parameters.