from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - exercised via injected client in tests
    OpenAI = None


@dataclass
class ResolvedDocument:
    source: str
    local_path: Path
    sha256: str
    filename: str
    content_type: str
    is_pdf: bool


class OpenAIDocumentToolkit:
    DIRECT_TASK_TYPES = {"summarize", "extract", "critique", "qa"}

    def __init__(
        self,
        *,
        client: Any | None = None,
        api_key: str | None = None,
        cache_dir: str | Path | None = None,
        direct_model: str = "gpt-5.4",
        retrieval_model: str = "gpt-5.4-mini",
    ):
        self.client = client or self._build_default_client(api_key=api_key)
        self.direct_model = direct_model
        self.retrieval_model = retrieval_model
        self.cache_dir = Path(cache_dir or Path.cwd() / ".document_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.cache_dir / "files").mkdir(parents=True, exist_ok=True)
        self._uploads_cache_path = self.cache_dir / "uploads.json"
        self._vector_store_cache_path = self.cache_dir / "vector_stores.json"

    def analyze(
        self,
        *,
        question: str,
        document_urls: list[str] | None = None,
        document_paths: list[str] | None = None,
        mode: str = "auto",
        task_type: str = "qa",
        max_num_results: int = 5,
        debug: bool = False,
    ) -> dict[str, Any]:
        resolved = self._resolve_documents(document_urls=document_urls or [], document_paths=document_paths or [])
        if not resolved:
            raise ValueError("document_query requires at least one document_url or document_path")
        mode_used = self._select_mode(mode=mode, task_type=task_type, documents=resolved)
        if mode_used == "direct_pdf":
            return self._analyze_direct(question=question, documents=resolved)
        return self._analyze_file_search(
            question=question,
            documents=resolved,
            max_num_results=max_num_results,
            debug=debug,
        )

    def _select_mode(self, *, mode: str, task_type: str, documents: list[ResolvedDocument]) -> str:
        normalized_mode = (mode or "auto").strip().lower()
        if normalized_mode in {"direct_pdf", "file_search"}:
            return normalized_mode
        if len(documents) == 1 and documents[0].is_pdf and task_type in self.DIRECT_TASK_TYPES:
            return "direct_pdf"
        return "file_search"

    def _analyze_direct(self, *, question: str, documents: list[ResolvedDocument]) -> dict[str, Any]:
        document = documents[0]
        file_id = self._upload(resolved=document, purpose="user_data")
        response = self.client.responses.create(
            model=self.direct_model,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_file", "file_id": file_id},
                        {"type": "input_text", "text": question},
                    ],
                }
            ],
        )
        return {
            "mode_used": "direct_pdf",
            "answer": getattr(response, "output_text", "") or self._payload_text(response),
            "document_count": 1,
            "document_sources": [document.source],
            "document_file_ids": [file_id],
            "response_id": getattr(response, "id", None),
        }

    def _analyze_file_search(
        self,
        *,
        question: str,
        documents: list[ResolvedDocument],
        max_num_results: int,
        debug: bool,
    ) -> dict[str, Any]:
        file_ids = [self._upload(resolved=document, purpose="assistants") for document in documents]
        vector_store_id = self._ensure_vector_store(file_ids=file_ids)
        request: dict[str, Any] = {
            "model": self.retrieval_model,
            "input": question,
            "tools": [
                {
                    "type": "file_search",
                    "vector_store_ids": [vector_store_id],
                    "max_num_results": max_num_results,
                }
            ],
        }
        if debug:
            request["include"] = ["file_search_call.results"]
        response = self.client.responses.create(**request)
        result = {
            "mode_used": "file_search",
            "answer": getattr(response, "output_text", "") or self._payload_text(response),
            "document_count": len(documents),
            "document_sources": [document.source for document in documents],
            "document_file_ids": file_ids,
            "vector_store_id": vector_store_id,
            "response_id": getattr(response, "id", None),
        }
        if debug:
            result["raw_response"] = self._payload(response)
        return result

    def _resolve_documents(self, *, document_urls: list[str], document_paths: list[str]) -> list[ResolvedDocument]:
        resolved: list[ResolvedDocument] = []
        for url in document_urls:
            response = httpx.get(url, timeout=30.0, follow_redirects=True)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "application/octet-stream")
            content = response.content
            resolved.append(self._materialize(source=url, content=content, content_type=content_type, suggested_name=self._filename_from_url(url)))
        for raw_path in document_paths:
            path = Path(raw_path).expanduser().resolve()
            content = path.read_bytes()
            content_type = "application/pdf" if path.suffix.lower() == ".pdf" else "application/octet-stream"
            resolved.append(self._materialize(source=str(path), content=content, content_type=content_type, suggested_name=path.name))
        return resolved

    def _materialize(self, *, source: str, content: bytes, content_type: str, suggested_name: str) -> ResolvedDocument:
        sha256 = hashlib.sha256(content).hexdigest()
        suffix = Path(suggested_name).suffix or (".pdf" if "pdf" in content_type.lower() else "")
        safe_name = Path(suggested_name or f"document{suffix}").name
        local_path = self.cache_dir / "files" / f"{sha256[:16]}-{safe_name}"
        if not local_path.exists():
            local_path.write_bytes(content)
        is_pdf = suffix.lower() == ".pdf" or "pdf" in (content_type or "").lower()
        return ResolvedDocument(
            source=source,
            local_path=local_path,
            sha256=sha256,
            filename=local_path.name,
            content_type=content_type,
            is_pdf=is_pdf,
        )

    def _upload(self, *, resolved: ResolvedDocument, purpose: str) -> str:
        cache = self._read_json(self._uploads_cache_path)
        key = f"{purpose}:{resolved.sha256}"
        cached = cache.get(key)
        if cached:
            return str(cached["file_id"])
        with resolved.local_path.open("rb") as f:
            uploaded = self.client.files.create(file=f, purpose=purpose)
        file_id = str(uploaded.id)
        cache[key] = {
            "file_id": file_id,
            "source": resolved.source,
            "filename": resolved.filename,
            "sha256": resolved.sha256,
            "purpose": purpose,
        }
        self._write_json(self._uploads_cache_path, cache)
        return file_id

    def _ensure_vector_store(self, *, file_ids: list[str]) -> str:
        cache = self._read_json(self._vector_store_cache_path)
        key = "|".join(sorted(file_ids))
        cached = cache.get(key)
        if cached:
            return str(cached["vector_store_id"])
        store = self.client.vector_stores.create(name=f"pdf-kb-{hashlib.sha256(key.encode()).hexdigest()[:12]}")
        vector_store_id = str(store.id)
        for file_id in file_ids:
            self.client.vector_stores.files.create(vector_store_id=vector_store_id, file_id=file_id)
        self._wait_until_ready(vector_store_id)
        cache[key] = {"vector_store_id": vector_store_id, "file_ids": sorted(file_ids)}
        self._write_json(self._vector_store_cache_path, cache)
        return vector_store_id

    def _wait_until_ready(self, vector_store_id: str, *, timeout_seconds: float = 300.0, poll_seconds: float = 2.0) -> None:
        started = time.time()
        while True:
            listing = self.client.vector_stores.files.list(vector_store_id=vector_store_id)
            data = getattr(listing, "data", []) or []
            statuses = [getattr(item, "status", None) for item in data]
            if data and all(status == "completed" for status in statuses):
                return
            terminal_failures = [status for status in statuses if status in {"failed", "cancelled", "expired"}]
            if terminal_failures:
                raise RuntimeError(f"Vector store file processing failed with statuses: {', '.join(sorted(set(str(s) for s in terminal_failures)))}")
            if time.time() - started > timeout_seconds:
                raise TimeoutError("Vector store files did not reach completed status in time.")
            time.sleep(poll_seconds)

    @staticmethod
    def _filename_from_url(url: str) -> str:
        path = urlparse(url).path
        name = Path(path).name
        return name or "document.pdf"

    @staticmethod
    def _payload(response: Any) -> dict[str, Any]:
        if hasattr(response, "model_dump"):
            dumped = response.model_dump()
            if isinstance(dumped, dict):
                return dumped
        if isinstance(response, dict):
            return response
        return {}

    def _payload_text(self, response: Any) -> str:
        payload = self._payload(response)
        texts: list[str] = []
        for item in payload.get("output", []) or []:
            if item.get("type") == "message":
                for content in item.get("content", []) or []:
                    text = (content.get("text") or "").strip()
                    if text:
                        texts.append(text)
        return "\n".join(texts).strip()

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _build_default_client(*, api_key: str | None = None) -> Any:
        if OpenAI is None:
            raise RuntimeError("openai package is unavailable")
        resolved_key = api_key or os.getenv("OPENAI_API_KEY")
        if not resolved_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        return OpenAI(api_key=resolved_key)
