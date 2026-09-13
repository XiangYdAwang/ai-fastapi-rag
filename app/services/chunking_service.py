import ast
import re
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings

PYTHON_LANGUAGES = {"python", "py"}
CODE_FENCE_PATTERN = re.compile(
    r"```(?P<language>[A-Za-z0-9_+-]*)\s*\n"
    r"(?P<code>.*?)\n```",
    re.DOTALL,
)


@dataclass(frozen=True)
class TextChunk:
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


def split_text(
    text: str,
    chunk_size: int,
    overlap: int,
) -> list[str]:
    text = text.replace("\x00", "").replace("\r\n", "\n").strip()

    if not text:
        return []

    if chunk_size <= 0:
        raise ValueError("CHUNK_SIZE must be greater than 0")

    if overlap < 0:
        raise ValueError("CHUNK_OVERLAP must not be negative")

    if overlap >= chunk_size:
        raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")

    chunks: list[str] = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = min(start + chunk_size, text_length)
        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= text_length:
            break

        start = end - overlap

    return chunks


def _extract_source_path(text: str, fallback: str) -> str:
    match = re.search(
        r"<!--\s*source_path:\s*(.*?)\s*-->",
        text,
    )

    if match:
        return match.group(1).strip()

    return fallback


def _markdown_sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current_heading = "Document"
    current_lines: list[str] = []
    in_code_fence = False

    for line in text.splitlines():
        stripped = line.strip()

        if stripped.startswith("```"):
            in_code_fence = not in_code_fence
            current_lines.append(line)
            continue

        is_heading = (
            not in_code_fence
            and re.match(r"^#{1,6}\s+", line) is not None
        )

        if is_heading:
            if current_lines:
                content = "\n".join(current_lines).strip()

                if content:
                    sections.append((current_heading, content))

            current_heading = line.lstrip("#").strip()
            current_lines = [line]
            continue

        current_lines.append(line)

    if current_lines:
        content = "\n".join(current_lines).strip()

        if content:
            sections.append((current_heading, content))

    return sections


def _split_large_content(
    content: str,
    metadata: dict[str, Any],
) -> list[TextChunk]:
    if len(content) <= settings.structured_chunk_size:
        return [TextChunk(content=content, metadata=metadata)]

    return [
        TextChunk(
            content=chunk,
            metadata={
                **metadata,
                "part_index": part_index,
            },
        )
        for part_index, chunk in enumerate(
            split_text(
                text=content,
                chunk_size=settings.structured_chunk_size,
                overlap=settings.chunk_overlap,
            )
        )
    ]


def _chunk_python_code(
    code: str,
    source_path: str,
    heading: str,
    fence_index: int,
) -> list[TextChunk]:
    base_metadata = {
        "source_path": source_path,
        "chunk_type": "python_code",
        "heading": heading,
        "fence_index": fence_index,
    }

    normalized_code = code.replace("\r\n", "\n")

    try:
        tree = ast.parse(normalized_code)
    except SyntaxError:
        return _split_large_content(
            content=normalized_code.strip(),
            metadata={
                **base_metadata,
                "symbol_name": "python-block",
                "symbol_type": "fallback",
            },
        )

    lines = normalized_code.splitlines()
    covered_lines: set[int] = set()
    symbol_chunks: list[TextChunk] = []

    for node in tree.body:
        if not isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
            ),
        ):
            continue

        decorator_lines = [
            decorator.lineno
            for decorator in getattr(node, "decorator_list", [])
        ]
        start_line = min([node.lineno, *decorator_lines])
        end_line = getattr(node, "end_lineno", node.lineno)
        symbol_content = "\n".join(
            lines[start_line - 1 : end_line]
        ).strip()

        if not symbol_content:
            continue

        if isinstance(node, ast.ClassDef):
            symbol_type = "class"
        elif isinstance(node, ast.AsyncFunctionDef):
            symbol_type = "async_function"
        else:
            symbol_type = "function"

        symbol_chunks.extend(
            _split_large_content(
                content=symbol_content,
                metadata={
                    **base_metadata,
                    "symbol_name": node.name,
                    "symbol_type": symbol_type,
                    "start_line": start_line,
                    "end_line": end_line,
                },
            )
        )

        for line_number in range(start_line, end_line + 1):
            covered_lines.add(line_number)

    module_lines = [
        line
        for line_number, line in enumerate(lines, start=1)
        if line_number not in covered_lines
    ]
    module_content = "\n".join(module_lines).strip()

    chunks: list[TextChunk] = []

    if module_content:
        chunks.extend(
            _split_large_content(
                content=module_content,
                metadata={
                    **base_metadata,
                    "symbol_name": "module",
                    "symbol_type": "module",
                },
            )
        )

    chunks.extend(symbol_chunks)
    return chunks


def _chunk_markdown_section(
    section: str,
    heading: str,
    source_path: str,
) -> list[TextChunk]:
    matches = list(CODE_FENCE_PATTERN.finditer(section))

    if not matches:
        return _split_large_content(
            content=section,
            metadata={
                "source_path": source_path,
                "chunk_type": "markdown_section",
                "heading": heading,
            },
        )

    chunks: list[TextChunk] = []
    position = 0

    for fence_index, match in enumerate(matches):
        before = section[position : match.start()].strip()

        if before:
            chunks.extend(
                _split_large_content(
                    content=before,
                    metadata={
                        "source_path": source_path,
                        "chunk_type": "markdown_text",
                        "heading": heading,
                        "fence_index": fence_index,
                    },
                )
            )

        language = match.group("language").strip().lower()
        code = match.group("code").strip()

        if language in PYTHON_LANGUAGES and settings.ast_chunking_enabled:
            chunks.extend(
                _chunk_python_code(
                    code=code,
                    source_path=source_path,
                    heading=heading,
                    fence_index=fence_index,
                )
            )
        else:
            content = f"```{language}\n{code}\n```"
            chunks.extend(
                _split_large_content(
                    content=content,
                    metadata={
                        "source_path": source_path,
                        "chunk_type": "code_block",
                        "language": language,
                        "heading": heading,
                        "fence_index": fence_index,
                    },
                )
            )

        position = match.end()

    tail = section[position:].strip()

    if tail:
        chunks.extend(
            _split_large_content(
                content=tail,
                metadata={
                    "source_path": source_path,
                    "chunk_type": "markdown_text",
                    "heading": heading,
                },
            )
        )

    return chunks


def _chunk_markdown(
    text: str,
    source_path: str,
) -> list[TextChunk]:
    actual_source_path = _extract_source_path(text, source_path)
    chunks: list[TextChunk] = []

    for section_index, (heading, section) in enumerate(
        _markdown_sections(text)
    ):
        section_chunks = _chunk_markdown_section(
            section=section,
            heading=heading,
            source_path=actual_source_path,
        )

        for chunk in section_chunks:
            chunks.append(
                TextChunk(
                    content=chunk.content,
                    metadata={
                        **chunk.metadata,
                        "section_index": section_index,
                    },
                )
            )

    return chunks


def _expand_parent_chunks(
    parent_chunks: list[TextChunk],
) -> list[TextChunk]:
    child_chunks: list[TextChunk] = []

    for parent_index, parent in enumerate(parent_chunks):
        child_contents = split_text(
            text=parent.content,
            chunk_size=settings.child_chunk_size,
            overlap=settings.child_chunk_overlap,
        )

        for child_index, child_content in enumerate(child_contents):
            child_chunks.append(
                TextChunk(
                    content=child_content,
                    metadata={
                        **parent.metadata,
                        "chunk_role": "child",
                        "parent_index": parent_index,
                        "child_index": child_index,
                        "parent_content": parent.content,
                    },
                )
            )

    return child_chunks

def chunk_document(
    text: str,
    suffix: str,
    source_path: str,
) -> list[TextChunk]:
    text = text.replace("\x00", "").replace("\r\n", "\n").strip()

    if not text:
        return []

    if suffix == ".md":
        parent_chunks = _chunk_markdown(text, source_path)
    else:
        parent_chunks = [
            TextChunk(
                content=chunk,
                metadata={
                    "source_path": source_path,
                    "chunk_type": "text",
                },
            )
            for chunk in split_text(
                text=text,
                chunk_size=settings.chunk_size,
                overlap=settings.chunk_overlap,
            )
        ]

    if not settings.parent_child_enabled:
        return parent_chunks

    return _expand_parent_chunks(parent_chunks)