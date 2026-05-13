"""Tavily web search for corroborating document claims with online sources."""

from typing import Any

import httpx

from app.core.config import settings


TAVILY_SEARCH_URL = "https://api.tavily.com/search"


def search_web(*, query: str, max_results: int = 5, search_depth: str = "basic") -> dict[str, Any]:
    """
    Run a Tavily search. Returns raw API JSON (includes results[].title, url, content).
    """
    key = (settings.tavily_api_key or "").strip()
    if not key:
        raise RuntimeError("TAVILY_API_KEY is not set")

    payload = {
        "api_key": key,
        "query": query,
        "max_results": max_results,
        "search_depth": search_depth,
        "include_answer": False,
    }
    with httpx.Client(timeout=45.0) as client:
        resp = client.post(TAVILY_SEARCH_URL, json=payload)
        resp.raise_for_status()
        return resp.json()


def format_results_for_llm(data: dict[str, Any], *, max_chars_per_snippet: int = 600) -> list[dict[str, str]]:
    """Flatten Tavily response into title/url/snippet for prompt injection."""
    out: list[dict[str, str]] = []
    for r in data.get("results") or []:
        title = (r.get("title") or "").strip()
        url = (r.get("url") or "").strip()
        content = (r.get("content") or "").strip()
        if len(content) > max_chars_per_snippet:
            content = content[:max_chars_per_snippet] + "…"
        if title or content:
            out.append({"title": title, "url": url, "snippet": content})
    return out


def run_queries(queries: list[str], *, per_query_max_results: int = 5) -> tuple[list[str], list[dict[str, Any]]]:
    """
    Run multiple searches. Returns (queries_used, list of {query, raw_response, snippets}).
    """
    used: list[str] = []
    blocks: list[dict[str, Any]] = []
    for q in queries:
        q = q.strip()
        if not q or len(q) < 4:
            continue
        raw = search_web(query=q, max_results=per_query_max_results)
        snippets = format_results_for_llm(raw)
        used.append(q)
        blocks.append({"query": q, "snippets": snippets, "response_keys": list(raw.keys())})
    return used, blocks
