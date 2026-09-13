import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.observability import configure_observability, flush_observability
from app.db.session import AsyncSessionLocal, engine
from app.schemas.search import SearchRequest
from app.services.search_service import search_documents


def load_dataset(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()

            if not line:
                continue

            try:
                case = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON on line {line_number} of {path}"
                ) from exc

            required_fields = {"id", "question", "expected_document"}
            missing = required_fields - case.keys()

            if missing:
                raise ValueError(
                    f"Case {case.get('id', line_number)} is missing fields: "
                    f"{sorted(missing)}"
                )

            cases.append(case)

    return cases


def is_relevant(result: Any, case: dict[str, Any]) -> bool:
    if result.filename != case["expected_document"]:
        return False

    keywords = case.get("expected_keywords", [])

    if not keywords:
        return True

    content = result.content.casefold()

    return any(
        str(keyword).casefold() in content
        for keyword in keywords
    )


async def evaluate(
    dataset_path: Path,
    top_k: int,
) -> dict[str, Any]:
    cases = load_dataset(dataset_path)
    details: list[dict[str, Any]] = []

    hit_at_1 = 0
    hit_at_k = 0
    reciprocal_rank_sum = 0.0

    async with AsyncSessionLocal() as db:
        for case in cases:
            response = await search_documents(
                request=SearchRequest(
                    query=case["question"],
                    top_k=top_k,
                ),
                db=db,
            )

            first_relevant_rank: int | None = None

            for rank, result in enumerate(response.results, start=1):
                if is_relevant(result, case):
                    first_relevant_rank = rank
                    break

            if first_relevant_rank is not None:
                if first_relevant_rank <= 1:
                    hit_at_1 += 1

                if first_relevant_rank <= top_k:
                    hit_at_k += 1

                reciprocal_rank_sum += 1.0 / first_relevant_rank

            details.append(
                {
                    "id": case["id"],
                    "question": case["question"],
                    "expected_document": case["expected_document"],
                    "first_relevant_rank": first_relevant_rank,
                    "retrieved": [
                        {
                            "filename": result.filename,
                            "chunk_index": result.chunk_index,
                            "score": result.score,
                            "vector_score": result.vector_score,
                            "lexical_score": result.lexical_score,
                            "retrieval_score": result.retrieval_score,
                            "rerank_score": result.rerank_score,
                            "content": result.content,
                         }
                        for result in response.results
                    ],
                }
            )

    total = len(cases)
    metrics = {
        "cases": total,
        "top_k": top_k,
        "hit_rate_at_1": hit_at_1 / total if total else 0.0,
        f"hit_rate_at_{top_k}": hit_at_k / total if total else 0.0,
        "mrr": reciprocal_rank_sum / total if total else 0.0,
    }

    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset": str(dataset_path),
        "metrics": metrics,
        "details": details,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate vector retrieval using a JSONL QA dataset."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("evaluation/qa_dataset.jsonl"),
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("evaluation/results"),
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    configure_observability()

    try:
        report = await evaluate(
            dataset_path=args.dataset,
            top_k=args.top_k,
        )
    finally:
        await engine.dispose()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = args.output_dir / f"retrieval_{timestamp}.json"
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    metrics = report["metrics"]
    print(f"cases={metrics['cases']}")
    print(f"top_k={metrics['top_k']}")
    print(f"hit_rate_at_1={metrics['hit_rate_at_1']:.4f}")
    top_k_key = f"hit_rate_at_{metrics['top_k']}"
    print(f"{top_k_key}={metrics[top_k_key]:.4f}")
    print(f"mrr={metrics['mrr']:.4f}")
    print(f"report={output_path}")

    print("\nPer-case results:")

    for detail in report["details"]:
        rank = detail["first_relevant_rank"]
        status = f"rank={rank}" if rank is not None else "MISS"
        print(f"{detail['id']}: {status} | {detail['question']}")

    flush_observability()


if __name__ == "__main__":
    asyncio.run(main())