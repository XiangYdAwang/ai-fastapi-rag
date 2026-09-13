import argparse
import sys
import asyncio
import json
from pathlib import Path

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run an end-to-end RAG demo."
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=Path("sample.pdf"),
    )
    parser.add_argument(
        "--query",
        default="What is pgvector?",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
    )
    return parser.parse_args()


def content_type_for(path: Path) -> str:
    return {
        ".pdf": "application/pdf",
        ".docx": (
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
        ".md": "text/markdown",
        ".txt": "text/plain",
    }.get(path.suffix.lower(), "application/octet-stream")


async def main() -> None:
    args = parse_args()

    if not args.file.exists():
        raise FileNotFoundError(args.file)

    async with httpx.AsyncClient(
        base_url=args.base_url.rstrip("/"),
        timeout=180.0,
    ) as client:
        health = await client.get("/health")
        health.raise_for_status()
        print("1. FastAPI health: ok")

        with args.file.open("rb") as file_handle:
            upload_response = await client.post(
                "/api/documents/upload",
                files={
                    "file": (
                        args.file.name,
                        file_handle,
                        content_type_for(args.file),
                    )
                },
            )
        upload_response.raise_for_status()
        upload = upload_response.json()
        document_id = upload["id"]
        print(
            "2. Uploaded: "
            f"{upload['filename']} "
            f"chunks={upload['chunks_created']} "
            f"id={document_id}"
        )

        embed_response = await client.post(
            f"/api/documents/{document_id}/embed"
        )
        embed_response.raise_for_status()
        embed = embed_response.json()
        print(
            "3. Embedded: "
            f"chunks={embed['embedded_chunks']} "
            f"status={embed['status']}"
        )

        search_response = await client.post(
            "/api/search",
            json={
                "query": args.query,
                "top_k": args.top_k,
                "document_id": document_id,
            },
        )
        search_response.raise_for_status()
        search = search_response.json()
        print(f"4. Search results: {len(search['results'])}")

        for index, result in enumerate(search["results"], start=1):
            print(
                f"   [{index}] {result['filename']} "
                f"score={result['score']:.4f}"
            )

        print("5. Streaming answer:")

        async with client.stream(
            "POST",
            "/api/chat/stream",
            json={
                "query": args.query,
                "top_k": args.top_k,
                "document_id": document_id,
            },
        ) as stream_response:
            stream_response.raise_for_status()
            current_event = None

            async for line in stream_response.aiter_lines():
                if line.startswith("event: "):
                    current_event = line.removeprefix("event: ")
                    continue

                if not line.startswith("data: "):
                    continue

                payload = json.loads(line.removeprefix("data: "))

                if current_event == "token":
                    print(payload["content"], end="", flush=True)
                elif current_event == "done":
                    print()
                    print("6. Stream complete")
                elif current_event == "error":
                    print()
                    raise RuntimeError(payload["detail"])


if __name__ == "__main__":
    asyncio.run(main())