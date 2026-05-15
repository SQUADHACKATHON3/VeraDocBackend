"""Tavily web search for corroborating document claims with online sources."""

from typing import Any

import httpx

from app.core.config import settings


TAVILY_SEARCH_URL = "https://api.tavily.com/search"

# Contact pages need more text for the regex extractor to find emails/phones reliably.
_SNIPPET_DEFAULT = 1200
_SNIPPET_CONTACT = 2000


def search_web(*, query: str, max_results: int = 5, search_depth: str = "basic") -> dict[str, Any]:
    """
    Run a Tavily search. Returns raw API JSON (includes results[].title, url, content).
    search_depth: "basic" (fast preview) or "advanced" (full-page crawl — use for contact queries).
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
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(TAVILY_SEARCH_URL, json=payload)
        resp.raise_for_status()
        return resp.json()


def format_results_for_llm(data: dict[str, Any], *, max_chars_per_snippet: int = _SNIPPET_DEFAULT) -> list[dict[str, str]]:
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


# QuerySpec lets callers override depth and snippet size per-query.
# Accepts either a plain string or a dict:
#   {"query": str, "search_depth": "basic"|"advanced", "max_chars_per_snippet": int}
QuerySpec = str | dict[str, Any]


def run_queries(
    queries: list[QuerySpec],
    *,
    per_query_max_results: int = 5,
) -> tuple[list[str], list[dict[str, Any]]]:
    """
    Run multiple searches. Each entry in `queries` is either:
      - a plain string (uses basic depth, default snippet size), or
      - a dict with keys: query (str), search_depth (str), max_chars_per_snippet (int)

    Returns (queries_used, list of {query, snippets, response_keys}).
    """
    used: list[str] = []
    blocks: list[dict[str, Any]] = []
    for spec in queries:
        if isinstance(spec, dict):
            q = (spec.get("query") or "").strip()
            depth = spec.get("search_depth", "basic")
            snippet_size = int(spec.get("max_chars_per_snippet", _SNIPPET_DEFAULT))
        else:
            q = (spec or "").strip()
            depth = "basic"
            snippet_size = _SNIPPET_DEFAULT

        if not q or len(q) < 4:
            continue
        raw = search_web(query=q, max_results=per_query_max_results, search_depth=depth)
        snippets = format_results_for_llm(raw, max_chars_per_snippet=snippet_size)
        used.append(q)
        blocks.append({"query": q, "snippets": snippets, "response_keys": list(raw.keys())})
    return used, blocks
