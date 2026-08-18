import re
from dataclasses import dataclass, field
from typing import Any

from app.services.document_parser import ExtractedBlock


@dataclass(frozen=True)
class StructuredChunk:
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


def _sentences(text: str) -> list[str]:
    return [
        value.strip()
        for value in re.split(r"(?<=[。！？；.!?;])\s*|\n+", text)
        if value.strip()
    ]


def _merge_metadata(blocks: list[ExtractedBlock]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for block in blocks:
        for key, value in block.metadata.items():
            if value in (None, "", []):
                continue
            if key in {"page_start", "page_end"} and key in metadata:
                metadata[key] = min(metadata[key], value) if key == "page_start" else max(metadata[key], value)
            elif key == "heading_path":
                metadata[key] = value
            else:
                metadata.setdefault(key, value)
    return metadata


def split_document(
    blocks: list[ExtractedBlock],
    *,
    max_chars: int = 1200,
    overlap_sentences: int = 1,
) -> list[StructuredChunk]:
    if max_chars <= 0:
        raise ValueError("max_chars must be greater than zero")
    if overlap_sentences < 0:
        raise ValueError("overlap_sentences must not be negative")

    chunks: list[StructuredChunk] = []
    current_blocks: list[ExtractedBlock] = []
    current_text = ""

    def flush() -> None:
        nonlocal current_blocks, current_text
        content = current_text.strip()
        if content:
            chunks.append(
                StructuredChunk(
                    content=content,
                    metadata=_merge_metadata(current_blocks),
                )
            )
        current_blocks = []
        current_text = ""

    for block in blocks:
        block_text = block.text.strip()
        if not block_text:
            continue

        if len(block_text) <= max_chars:
            candidate = f"{current_text}\n\n{block_text}".strip()
            if current_text and len(candidate) > max_chars:
                flush()
            current_blocks.append(block)
            current_text = f"{current_text}\n\n{block_text}".strip()
            continue

        # Long paragraphs or tables are split only at sentence/row boundaries.
        flush()
        pieces = _sentences(block_text)
        if not pieces:
            pieces = [block_text[index:index + max_chars] for index in range(0, len(block_text), max_chars)]

        piece_buffer: list[str] = []
        for piece in pieces:
            candidate = "".join(piece_buffer + [piece])
            if piece_buffer and len(candidate) > max_chars:
                chunks.append(StructuredChunk("".join(piece_buffer).strip(), dict(block.metadata)))
                piece_buffer = piece_buffer[-overlap_sentences:] if overlap_sentences else []
            piece_buffer.append(piece)
        if piece_buffer:
            chunks.append(StructuredChunk("".join(piece_buffer).strip(), dict(block.metadata)))

    flush()
    return chunks


def split_text(
    text: str,
    *,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> list[str]:
    """Backward-compatible fixed splitter kept for external callers."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be between zero and chunk_size")

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(text):
            break
        start = end - chunk_overlap
    return chunks
