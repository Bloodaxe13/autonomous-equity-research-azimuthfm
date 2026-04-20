from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Protocol

import httpx

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
    def __init__(self, api_key: str | None = None, model: str = "gpt-5"):
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
        for item in payload.get("output", []):
            if item.get("type") != "web_search_call":
                continue
            for result in item.get("results", [])[:limit]:
                results.append(
                    SearchResult(
                        title=result.get("title", ""),
                        url=result.get("url", ""),
                        snippet=result.get("snippet", ""),
                        source=result.get("source"),
                    )
                )
        return SearchResults(query=query, results=results)


class HttpFetchAdapter:
    def fetch(self, url: str, timeout: float = 20.0) -> FetchResult:
        response = httpx.get(url, timeout=timeout, follow_redirects=True)
        return FetchResult(
            url=str(response.url),
            status_code=response.status_code,
            content_type=response.headers.get("content-type", "text/plain"),
            text=response.text,
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
