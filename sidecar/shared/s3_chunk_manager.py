"""S3 — Chunk Manager

Splits text into overlapping chunks using one of three strategies:
  "chapter"   — split at chapter heading boundaries (preferred for Import)
  "paragraph" — split at paragraph breaks with soft size limit
  "fixed"     — hard character limit (for Metadata ingestion)

Default chunk_size: 500_000 chars
Default overlap:     50_000 chars (10%)

Each Chunk carries: chunk_id, char_start, char_end, content,
chapter_hint, entity_mentions (empty until extraction pass).
"""

import re
from typing import TypedDict


class ChunkConfig(TypedDict, total=False):
    strategy: str   # "chapter" | "paragraph" | "fixed"
    chunk_size: int
    overlap: int


class Chunk(TypedDict):
    chunk_id: int
    char_start: int
    char_end: int
    content: str
    chapter_hint: str | None
    entity_mentions: list[str]


# Regex matching common Chinese and English chapter headings at line start
_CHAPTER_RE = re.compile(
    r"^(第[一二三四五六七八九十百千\d○〇零]+[章节回幕]+|Chapter\s+\d+\b.*)",
    re.MULTILINE | re.IGNORECASE,
)

_DEFAULT_CHUNK_SIZE = 500_000
_DEFAULT_OVERLAP = 50_000


def chunk_text(text: str, config: ChunkConfig) -> list[Chunk]:
    strategy = config.get("strategy", "paragraph")
    chunk_size = config.get("chunk_size", _DEFAULT_CHUNK_SIZE)
    overlap = config.get("overlap", _DEFAULT_OVERLAP)

    if strategy == "chapter":
        return _split_by_chapter(text, chunk_size, overlap)
    elif strategy == "paragraph":
        return _split_by_paragraph(text, chunk_size, overlap)
    else:  # "fixed"
        return _split_fixed(text, chunk_size, overlap)


# ── Chapter strategy ──────────────────────────────────────────────────────────

def _split_by_chapter(text: str, chunk_size: int, overlap: int) -> list[Chunk]:
    """Split at chapter heading boundaries.

    Falls back to paragraph splitting if no headings are found.
    Overlap is applied by prepending the last `overlap` chars of the
    previous chunk's content to the current chunk's content.
    """
    matches = list(_CHAPTER_RE.finditer(text))
    if not matches:
        return _split_by_paragraph(text, chunk_size, overlap)

    # Build boundary start positions: each match start is a boundary
    boundaries = [m.start() for m in matches]
    headings = [m.group(0).strip() for m in matches]

    chunks: list[Chunk] = []
    chunk_id = 0

    for i, boundary_start in enumerate(boundaries):
        # Content from this boundary to next boundary (or end)
        content_start = boundary_start
        content_end = boundaries[i + 1] if i + 1 < len(boundaries) else len(text)
        raw_content = text[content_start:content_end]

        # If the chapter is large, sub-split with paragraph strategy
        if len(raw_content) > chunk_size:
            sub_chunks = _split_by_paragraph(raw_content, chunk_size, overlap)
            for j, sub in enumerate(sub_chunks):
                # Adjust absolute char offsets
                abs_start = content_start + sub["char_start"]
                abs_end = content_start + sub["char_end"]
                # Prepend overlap from previous chunk
                overlap_prefix = _get_overlap_prefix(chunks, overlap)
                final_content = overlap_prefix + sub["content"]
                chunks.append(
                    Chunk(
                        chunk_id=chunk_id,
                        char_start=abs_start,
                        char_end=abs_end,
                        content=final_content,
                        chapter_hint=headings[i],
                        entity_mentions=[],
                    )
                )
                chunk_id += 1
        else:
            overlap_prefix = _get_overlap_prefix(chunks, overlap)
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    char_start=content_start,
                    char_end=content_end,
                    content=overlap_prefix + raw_content,
                    chapter_hint=headings[i],
                    entity_mentions=[],
                )
            )
            chunk_id += 1

    return chunks


# ── Paragraph strategy ────────────────────────────────────────────────────────

def _split_by_paragraph(text: str, chunk_size: int, overlap: int) -> list[Chunk]:
    """Accumulate paragraphs until chunk_size is reached, then start new chunk."""
    paragraphs = re.split(r"\n{2,}", text)
    chunks: list[Chunk] = []
    chunk_id = 0
    current_parts: list[str] = []
    current_len = 0
    abs_pos = 0
    chunk_abs_start = 0

    for para in paragraphs:
        para_with_sep = para + "\n\n"
        para_len = len(para_with_sep)

        if current_len + para_len > chunk_size and current_parts:
            # Flush current chunk
            content = "".join(current_parts)
            overlap_prefix = _get_overlap_prefix(chunks, overlap)
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    char_start=chunk_abs_start,
                    char_end=abs_pos,
                    content=overlap_prefix + content,
                    chapter_hint=None,
                    entity_mentions=[],
                )
            )
            chunk_id += 1
            chunk_abs_start = abs_pos
            current_parts = []
            current_len = 0

        current_parts.append(para_with_sep)
        current_len += para_len
        abs_pos += para_len

    # Flush remainder
    if current_parts:
        content = "".join(current_parts)
        overlap_prefix = _get_overlap_prefix(chunks, overlap)
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                char_start=chunk_abs_start,
                char_end=abs_pos,
                content=overlap_prefix + content,
                chapter_hint=None,
                entity_mentions=[],
            )
        )

    return chunks if chunks else [
        Chunk(
            chunk_id=0,
            char_start=0,
            char_end=len(text),
            content=text,
            chapter_hint=None,
            entity_mentions=[],
        )
    ]


# ── Fixed strategy ────────────────────────────────────────────────────────────

def _split_fixed(text: str, chunk_size: int, overlap: int) -> list[Chunk]:
    """Hard-slice at chunk_size chars. Each chunk's content starts with overlap
    chars from the end of the previous chunk's raw content."""
    chunks: list[Chunk] = []
    chunk_id = 0
    pos = 0
    total = len(text)

    while pos < total:
        end = min(pos + chunk_size, total)
        raw_content = text[pos:end]
        overlap_prefix = text[max(0, pos - overlap):pos] if pos > 0 else ""
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                char_start=pos,
                char_end=end,
                content=overlap_prefix + raw_content,
                chapter_hint=None,
                entity_mentions=[],
            )
        )
        chunk_id += 1
        pos = end

    return chunks


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_overlap_prefix(chunks: list[Chunk], overlap: int) -> str:
    """Return the last `overlap` chars of the previous chunk's raw content
    (excluding any overlap prefix it already received)."""
    if not chunks:
        return ""
    prev_content = chunks[-1]["content"]
    return prev_content[-overlap:] if len(prev_content) > overlap else prev_content
