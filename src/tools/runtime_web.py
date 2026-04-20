from __future__ import annotations

import io
import json
import os
import re
from dataclasses import dataclass
from typing import Protocol

import httpx
import fitz
import pdfplumber
from pypdf import PdfReader

from src.contracts_runtime import FetchResult, SearchResult, SearchResults

try:
    from openai import OpenAI
except Exception:
    OpenAI = None


class SearchAdapter(Protocol):
    def search(self, query: str, limit: int = 5) -> SearchResults: ...


class FetchAdapter(Protocol):
    def fetch(self, url: str, timeout: float = 20.0) -> FetchResult: ...


@dataclass
class StaticSearchAdapter:
    fixtures: dict[str, list[dict]]

    def search(self, query: str, limit: int = 5) -> SearchResults:
        raw = self.fixtures.get(query, [])[:limit]
        return SearchResults(
            query=query,
            results=[SearchResult.model_validate(item) for item in raw],
        )


class OpenAIWebSearchAdapter:
    def __init__(self, api_key: str | None = None, model: str = "gpt-5.4-mini"):
        if OpenAI is None:
            raise RuntimeError("openai package is unavailable")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        self.client = OpenAI(api_key=self.api_key)
        self.model = model

    def search(self, query: str, limit: int = 5) -> SearchResults:
        response = self.client.responses.create(
            model=self.model,
            input=query,
            tools=[{"type": "web_search_preview", "search_context_size": "medium"}],
        )
        payload = response.model_dump() if hasattr(response, "model_dump") else {}
        results: list[SearchResult] = []
        seen_urls: set[str] = set()
        for item in payload.get("output", []):
            if item.get("type") == "web_search_call":
                for result in item.get("results", [])[:limit]:
                    url = result.get("url", "")
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    results.append(
                        SearchResult(
                            title=result.get("title", ""),
                            url=url,
                            snippet=result.get("snippet", ""),
                            source=result.get("source"),
                        )
                    )
            elif item.get("type") == "message":
                for content in item.get("content", []) or []:
                    for ann in content.get("annotations", []) or []:
                        if ann.get("type") != "url_citation":
                            continue
                        url = ann.get("url", "")
                        if not url or url in seen_urls:
                            continue
                        seen_urls.add(url)
                        results.append(
                            SearchResult(
                                title=ann.get("title", url),
                                url=url,
                                snippet=content.get("text", ""),
                                source="openai_web_search_annotation",
                            )
                        )
                        if len(results) >= limit:
                            break
                    if len(results) >= limit:
                        break
            if len(results) >= limit:
                break
        return SearchResults(query=query, results=results[:limit])


class HttpFetchAdapter:
    def fetch(self, url: str, timeout: float = 20.0) -> FetchResult:
        try:
            response = httpx.get(url, timeout=timeout, follow_redirects=True)
            content_type = response.headers.get("content-type", "text/plain")
            if _is_pdf(url, content_type):
                extracted_text = _extract_pdf_text(response.content)
                return FetchResult(
                    url=str(response.url),
                    status_code=response.status_code,
                    content_type=content_type,
                    text=extracted_text,
                )
            return FetchResult(
                url=str(response.url),
                status_code=response.status_code,
                content_type=content_type,
                text=response.text,
            )
        except Exception as exc:
            return FetchResult(
                url=url,
                status_code=599,
                content_type="text/plain",
                text=f"FETCH_ERROR: {type(exc).__name__}: {exc}",
            )


@dataclass
class StaticFetchAdapter:
    fixtures: dict[str, dict]

    def fetch(self, url: str, timeout: float = 20.0) -> FetchResult:
        if url not in self.fixtures:
            raise KeyError(f"No fetch fixture for {url}")
        return FetchResult.model_validate({"url": url, **self.fixtures[url]})


class WebSearchTool:
    def __init__(self, adapter: SearchAdapter):
        self.adapter = adapter

    def __call__(self, query: str, limit: int = 5) -> SearchResults:
        return self.adapter.search(query=query, limit=limit)


class WebFetchTool:
    def __init__(self, adapter: FetchAdapter):
        self.adapter = adapter

    def __call__(self, url: str, timeout: float = 20.0) -> FetchResult:
        return self.adapter.fetch(url=url, timeout=timeout)


def dump_search_results(results: SearchResults) -> str:
    return json.dumps(results.model_dump(mode="json"), indent=2, ensure_ascii=False)


def _is_pdf(url: str, content_type: str) -> bool:
    lowered_type = (content_type or '').lower()
    lowered_url = (url or '').lower()
    return 'pdf' in lowered_type or lowered_url.endswith('.pdf')


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    extraction_attempts: list[tuple[str, str]] = []

    extraction_attempts.append(('pymupdf', _extract_pdf_text_pymupdf(pdf_bytes)))
    if _pdf_text_quality_ok(extraction_attempts[-1][1]):
        return extraction_attempts[-1][1]

    extraction_attempts.append(('pdfplumber', _extract_pdf_text_pdfplumber(pdf_bytes)))
    if _pdf_text_quality_ok(extraction_attempts[-1][1]):
        return extraction_attempts[-1][1]

    extraction_attempts.append(('pypdf', _extract_pdf_text_pypdf(pdf_bytes)))
    if _pdf_text_quality_ok(extraction_attempts[-1][1]):
        return extraction_attempts[-1][1]

    best_name, best_text = max(extraction_attempts, key=lambda item: _pdf_text_score(item[1]))
    return f"PDF_EXTRACTION_QUALITY: low\nPDF_EXTRACTION_METHOD: {best_name}\n\n{best_text[:4000]}"


def _extract_pdf_text_pymupdf(pdf_bytes: bytes) -> str:
    try:
        with fitz.open(stream=pdf_bytes, filetype='pdf') as doc:
            return '\n'.join(page.get_text('text') for page in doc)
    except Exception:
        return ''


def _extract_pdf_text_pdfplumber(pdf_bytes: bytes) -> str:
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            return '\n'.join((page.extract_text() or '') for page in pdf.pages)
    except Exception:
        return ''


def _extract_pdf_text_pypdf(pdf_bytes: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        return '\n'.join((page.extract_text() or '') for page in reader.pages)
    except Exception:
        return ''


def _pdf_text_quality_ok(text: str) -> bool:
    return _pdf_text_score(text) >= 3


def _pdf_text_score(text: str) -> int:
    normalized = re.sub(r'\s+', ' ', text or '').strip()
    if not normalized:
        return 0
    score = 0
    if len(normalized) >= 80:
        score += 1
    alpha_num_ratio = sum(ch.isalnum() for ch in normalized) / max(len(normalized), 1)
    if alpha_num_ratio >= 0.55:
        score += 1
    lowered = normalized.lower()
    if any(token in lowered for token in ('revenue', 'cash', 'assets', 'annual report', 'financial', 'income')):
        score += 1
    return score
