import argparse
import asyncio
import json
from pathlib import Path

import httpx
from sqlalchemy import delete, select

from app.db.session import AsyncSessionLocal, engine
from app.models.document import Document


async def load_existing_documents() -> dict[str, tuple[str, str]]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(
                Document.filename,
                Document.id,
                Document.status,
            ).order_by(Document.created_at.desc())
        )

        existing: dict[str, tuple[str, str]] = {}

        for row in result.all():
            existing.setdefault(
                row.filename,
                (str(row.id), row.status),
            )

        return existing


async def delete_documents_by_filename(
    filenames: set[str],
) -> None:
    if not filenames:
        return

    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(Document).where(
                Document.filename.in_(filenames)
            )
        )
        await db.commit()


async def import_file(
    client: httpx.AsyncClient,
    path: Path,
    existing: dict[str, tuple[str, str]],
) -> tuple[str, bool]:
    if path.name in existing:
        document_id, status = existing[path.name]

        if status != "completed":
            response = await client.post(
                f"/api/documents/{document_id}/embed"
            )
            response.raise_for_status()

        return document_id, True

    with path.open("rb") as file_handle:
        response = await client.post(
            "/api/documents/upload",
            files={
                "file": (
                    path.name,
                    file_handle,
                    "text/markdown",
                )
            },
        )
        response.raise_for_status()

    document_id = response.json()["id"]

    response = await client.post(
        f"/api/documents/{document_id}/embed"
    )
    response.raise_for_status()

    return document_id, False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import the evaluation Markdown corpus through FastAPI."
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
    )
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=Path("evaluation/corpus"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/corpus_document_ids.json"),
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Delete existing documents with matching filenames before import.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    paths = sorted(args.corpus_dir.glob("*.md"))

    existing = await load_existing_documents()

    if args.replace:
        filenames = {path.name for path in paths}
        await delete_documents_by_filename(filenames)
        existing = {
            filename: value
            for filename, value in existing.items()
            if filename not in filenames
        }

    document_ids: dict[str, str] = {}

    async with httpx.AsyncClient(
        base_url=args.base_url.rstrip("/"),
        timeout=180.0,
    ) as client:
        health = await client.get("/health")
        health.raise_for_status()

        for index, path in enumerate(paths, start=1):
            document_id, reused = await import_file(
                client=client,
                path=path,
                existing=existing,
            )
            document_ids[path.name] = document_id
            action = "reused" if reused else "imported"
            print(
                f"[{index}/{len(paths)}] {action} "
                f"{path.name} -> {document_id}"
            )

    args.output.write_text(
        json.dumps(document_ids, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    await engine.dispose()

    print(f"documents={len(document_ids)}")
    print(f"mapping={args.output}")


if __name__ == "__main__":
    asyncio.run(main())