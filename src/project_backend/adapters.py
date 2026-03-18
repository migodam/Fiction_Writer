from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class AdapterResponse:
    status: str
    detail: str
    payload: Dict[str, Any]


class EmbeddingProviderAdapter:
    def embed_documents(self, chunks: List[Dict[str, Any]]) -> AdapterResponse:
        return AdapterResponse(status="unsupported", detail="Embedding provider is not configured.", payload={"chunks": len(chunks)})

    def embed_query(self, query: str) -> AdapterResponse:
        return AdapterResponse(status="unsupported", detail="Embedding provider is not configured.", payload={"query": query})

    def index_vectors(self, vectors: List[Dict[str, Any]], metadata: Dict[str, Any]) -> AdapterResponse:
        return AdapterResponse(status="unsupported", detail="Vector indexing is not configured.", payload={"vectors": len(vectors), "metadata": metadata})


class LLMTaskExecutorAdapter:
    def submit(self, task_request: Dict[str, Any]) -> AdapterResponse:
        return AdapterResponse(status="not_configured", detail="LLM executor is a placeholder.", payload={"task_request": task_request})

    def poll(self, run_id: str) -> AdapterResponse:
        return AdapterResponse(status="not_configured", detail="LLM executor is a placeholder.", payload={"run_id": run_id})


class VideoProviderAdapter:
    def submit(self, prompt_package: Dict[str, Any]) -> AdapterResponse:
        return AdapterResponse(status="not_configured", detail="Video provider is a placeholder.", payload={"prompt_package": prompt_package})

    def poll(self, provider_task_id: str) -> AdapterResponse:
        return AdapterResponse(status="not_configured", detail="Video provider is a placeholder.", payload={"provider_task_id": provider_task_id})

    def cancel(self, provider_task_id: str) -> AdapterResponse:
        return AdapterResponse(status="not_configured", detail="Video provider is a placeholder.", payload={"provider_task_id": provider_task_id})
