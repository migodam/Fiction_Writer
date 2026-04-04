from __future__ import annotations

from sidecar.shared.s3_chunk_manager import ChunkConfig, chunk_text


def text_chunker(text: str, config: ChunkConfig) -> list[dict]:
    return chunk_text(text, config)


def text_summarizer(text: str) -> str:
    raise NotImplementedError


def alias_resolver(text: str) -> dict:
    raise NotImplementedError
