"""Web search tool using ddgs (DuckDuckGo metasearch)."""

import os
import sys
import time
from typing import Annotated

from ddgs import DDGS
from pydantic import BaseModel, ConfigDict, Field

from src import config

# Default region: jp-ja for Japanese content (国分寺不动产 etc), overridable via env
DEFAULT_REGION = os.environ.get("WEB_SEARCH_REGION", "jp-ja")

# TTL cache: (timestamp, result) per cache key
_search_cache: dict[str, tuple[float, str]] = {}


def _cache_key(query: str, num_results: int, region: str) -> str:
    return f"{query}|{num_results}|{region}"


def _get_cached(key: str) -> str | None:
    """Return cached result if valid, else None."""
    if config.SEARCH_CACHE_TTL <= 0:
        return None
    if key not in _search_cache:
        return None
    ts, result = _search_cache[key]
    if time.monotonic() - ts > config.SEARCH_CACHE_TTL:
        del _search_cache[key]
        return None
    return result


def _set_cache(key: str, result: str) -> None:
    if config.SEARCH_CACHE_TTL > 0:
        _search_cache[key] = (time.monotonic(), result)


class WebSearchInput(BaseModel):
    """Input model for web search."""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    query: str = Field(..., description="Search query (e.g. 'Python async tutorial', 'latest AI news')", min_length=1, max_length=500)
    num_results: Annotated[int, Field(ge=1, le=20)] = Field(
        default=config.DEFAULT_NUM_RESULTS,
        description="Maximum number of results to return (default: 8)",
    )
    max_chars: Annotated[int, Field(ge=500, le=25000)] = Field(
        default=config.DEFAULT_MAX_CHARS,
        description="Maximum total characters in response to control token usage (default: 8000)",
    )
    region: str = Field(
        default=DEFAULT_REGION,
        description="Search region e.g. jp-ja (Japan), us-en, zh-cn. Affects result locale.",
    )


def _search_sync(query: str, max_results: int, region: str = DEFAULT_REGION) -> list[dict[str, str]]:
    """Synchronous search using ddgs with retry - runs in thread pool."""
    results: list[dict[str, str]] = []
    last_exc: BaseException | None = None

    for attempt in range(config.RETRY_MAX_ATTEMPTS):
        try:
            if config.DEBUG_VERBOSE:
                print(f"[web_search_impl] attempt={attempt+1} DDGS.text query={query!r} max_results={max_results} region={region}", file=sys.stderr, flush=True)
            with DDGS() as ddgs:
                for r in ddgs.text(
                    query,
                    max_results=max_results,
                    region=region,
                    safesearch="on",
                    backend="bing",
                ):
                    results.append({
                        "title": r.get("title", ""),
                        "url": r.get("href", ""),
                        "snippet": r.get("body", ""),
                    })
            if config.DEBUG_VERBOSE:
                print(f"[web_search_impl] got {len(results)} results", file=sys.stderr, flush=True)
            return results
        except Exception as e:
            if config.DEBUG_VERBOSE:
                print(f"[web_search_impl] Exception {type(e).__name__}: {e} attempt={attempt+1}", file=sys.stderr, flush=True)
            last_exc = e
            if attempt < config.RETRY_MAX_ATTEMPTS - 1:
                time.sleep(config.RETRY_INITIAL_DELAY * (config.RETRY_BACKOFF_FACTOR ** attempt))
            else:
                raise RuntimeError(f"Search failed: {e}") from last_exc

    raise RuntimeError(f"Search failed: {last_exc}") from last_exc


def format_search_results(results: list[dict[str, str]], max_chars: int) -> str:
    """Format search results as readable Markdown, respecting max_chars."""
    lines: list[str] = []
    total_chars = 0
    for i, r in enumerate(results, 1):
        title = r.get("title", "Untitled")
        url = r.get("url", "")
        snippet = r.get("snippet", "")
        block = f"## {i}. {title}\n- **URL**: {url}\n- **Snippet**: {snippet}\n\n"
        if total_chars + len(block) > max_chars:
            remaining = max_chars - total_chars - 80
            if remaining > 50:
                block = block[:remaining] + "...\n\n"
            lines.append(block)
            lines.append(f"*[Truncated: {len(results) - i} more results omitted due to max_chars limit]*")
            break
        lines.append(block)
        total_chars += len(block)
    return "".join(lines).strip()


def web_search_impl(params: WebSearchInput) -> str:
    """
    Perform web search and return formatted results (with cache and retry).

    Best for: finding current information, news, facts, or answering questions.
    Returns: titles, URLs, and snippets ready for LLM context.
    """
    key = _cache_key(params.query, params.num_results, params.region)
    cached = _get_cached(key)
    if cached is not None:
        return cached

    results = _search_sync(params.query, params.num_results, params.region)

    if not results:
        msg = f"No results found for query: '{params.query}'. Try different keywords or check if the query is too specific."
        return msg

    output = f"# Web Search Results: '{params.query}'\n\n"
    output += f"Found {len(results)} results.\n\n"
    output += format_search_results(results, max(params.max_chars - len(output) - 100, 500))

    if len(output) > config.CHARACTER_LIMIT:
        output = output[:config.CHARACTER_LIMIT - 100] + "\n\n*[Response truncated]*"

    _set_cache(key, output)
    return output
