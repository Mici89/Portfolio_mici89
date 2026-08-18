import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pymupdf


class DocumentParseError(ValueError):
    pass


@dataclass(frozen=True)
class ExtractedBlock:
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


def _flush_paragraph(
    paragraphs: list[ExtractedBlock],
    lines: list[str],
    heading_path: list[str],
) -> None:
    text = "\n".join(lines).strip()
    if text:
        paragraphs.append(
            ExtractedBlock(
                text=text,
                metadata={
                    "source_type": "text",
                    "heading_path": list(heading_path),
                },
            )
        )
    lines.clear()


def extract_markdown_blocks(text: str) -> list[ExtractedBlock]:
    blocks: list[ExtractedBlock] = []
    lines: list[str] = []
    heading_path: list[str] = []

    for line in text.splitlines():
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match:
            _flush_paragraph(blocks, lines, heading_path)
            level = len(match.group(1))
            heading = match.group(2)
            heading_path = heading_path[: level - 1]
            heading_path.append(heading)
            continue

        if not line.strip():
            _flush_paragraph(blocks, lines, heading_path)
        else:
            lines.append(line)

    _flush_paragraph(blocks, lines, heading_path)
    return blocks


def _rect_intersects(a: pymupdf.Rect, b: pymupdf.Rect) -> bool:
    return not (a & b).is_empty


def _normalise_table_rows(rows: list[list[str | None]]) -> tuple[list[str], list[list[str]]]:
    cleaned = [
        [(cell or "").strip().replace("\n", " ") for cell in row]
        for row in rows
    ]
    cleaned = [row for row in cleaned if any(row)]
    if not cleaned:
        return [], []

    width = max(len(row) for row in cleaned)
    padded = [row + [""] * (width - len(row)) for row in cleaned]
    headers = padded[0]
    data_rows: list[list[str]] = []
    last_values = [""] * width

    for row in padded[1:]:
        # PDF extraction often emits an empty cell for a vertically merged cell.
        row = [value or last_values[index] for index, value in enumerate(row)]
        last_values = row
        data_rows.append(row)

    return headers, data_rows


def _serialize_table(rows: list[list[str | None]]) -> tuple[str, list[str]]:
    headers, data_rows = _normalise_table_rows(rows)
    if not headers:
        return "", []

    lines = [f"表格字段：{'、'.join(headers)}"]
    for row in data_rows:
        pairs = [
            f"{headers[index]}={value}"
            for index, value in enumerate(row)
            if headers[index]
        ]
        if pairs:
            lines.append("；".join(pairs))
    return "\n".join(lines), headers


def extract_pdf_blocks(file_path: Path) -> list[ExtractedBlock]:
    blocks: list[ExtractedBlock] = []
    active_tables: dict[tuple[str, ...], tuple[int, str]] = {}
    table_sequence = 0

    try:
        with pymupdf.open(file_path) as document:
            for page_number, page in enumerate(document, start=1):
                tables = []
                try:
                    tables = list(page.find_tables().tables)
                except Exception:
                    # Some PDFs cannot be analysed for tables; plain text remains useful.
                    tables = []

                table_rects = [pymupdf.Rect(table.bbox) for table in tables]
                non_table_lines: list[str] = []
                for block in page.get_text("blocks", sort=True):
                    block_rect = pymupdf.Rect(block[:4])
                    if any(_rect_intersects(block_rect, rect) for rect in table_rects):
                        continue
                    value = block[4].strip()
                    if value:
                        non_table_lines.append(value)

                page_text = "\n".join(non_table_lines).strip()
                if page_text:
                    blocks.append(
                        ExtractedBlock(
                            text=page_text,
                            metadata={
                                "source_type": "text",
                                "page_start": page_number,
                                "page_end": page_number,
                            },
                        )
                    )

                for table_index, table in enumerate(tables, start=1):
                    table_text, headers = _serialize_table(table.extract())
                    if table_text:
                        signature = tuple(headers)
                        previous = active_tables.get(signature)
                        if previous and previous[0] == page_number - 1:
                            table_id = previous[1]
                        else:
                            table_sequence += 1
                            table_id = f"table-{table_sequence}"
                        active_tables[signature] = (page_number, table_id)
                        blocks.append(
                            ExtractedBlock(
                                text=table_text,
                                metadata={
                                    "source_type": "table",
                                    "table_id": table_id,
                                    "page_start": page_number,
                                    "page_end": page_number,
                                    "columns": headers,
                                },
                            )
                        )
    except Exception as error:
        raise DocumentParseError("Failed to parse PDF document") from error

    return blocks


def extract_document(file_path: Path) -> list[ExtractedBlock]:
    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        blocks = extract_pdf_blocks(file_path)
    elif suffix in {".txt", ".md"}:
        try:
            text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            raise DocumentParseError("Document must use UTF-8 encoding") from error
        blocks = extract_markdown_blocks(text)
    else:
        raise DocumentParseError(f"Unsupported document type: {suffix}")

    if not blocks or not any(block.text.strip() for block in blocks):
        raise DocumentParseError("Document contains no extractable text")
    return blocks


def extract_text(file_path: Path) -> str:
    """Backward-compatible plain text extraction for callers outside the pipeline."""
    return "\n\n".join(block.text for block in extract_document(file_path)).strip()
