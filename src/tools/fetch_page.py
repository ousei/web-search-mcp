"""Fetch and extract main content from a web page."""

import asyncio
import sys
from typing import Annotated
from urllib.parse import urlparse

import httpx
import trafilatura
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src import config

# Module-level AsyncClient for connection reuse (lazy init)
_http_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """Get or create shared AsyncClient for connection reuse."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=config.HTTP_TIMEOUT,
            follow_redirects=True,
        )
    return _http_client


def _is_retryable(exc: BaseException) -> bool:
    """Whether the exception is retryable (timeout, 5xx, connection error)."""
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    if isinstance(exc, (httpx.ConnectError, httpx.ReadError)):
        return True
    return False


class FetchPageInput(BaseModel):
    """Input model for fetch_page."""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")

    url: str = Field(..., description="URL of the webpage to fetch (e.g. 'https://example.com/article')", min_length=5)
    max_length: Annotated[int, Field(ge=500, le=50000)] = Field(
        default=config.DEFAULT_MAX_LENGTH,
        description="Maximum characters to return (default: 5000)",
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        parsed = urlparse(v)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("URL must include scheme (http/https) and host")
        if parsed.scheme not in ("http", "https"):
            raise ValueError("URL scheme must be http or https")
        return v


async def fetch_page_impl(params: "FetchPageInput") -> str:
    """
    Fetch a webpage and extract main content as Markdown (async, with retry).

    Best for: reading article content for grounding, after finding URLs via web_search.
    Returns: Extracted main text in Markdown format.
    """
    url = params.url
    max_length = params.max_length
    html = ""
    delay = config.RETRY_INITIAL_DELAY

    for attempt in range(config.RETRY_MAX_ATTEMPTS):
        try:
            if config.DEBUG_VERBOSE:
                print(f"[fetch_page_impl] attempt={attempt+1} GET {url}", file=sys.stderr, flush=True)
            client = _get_client()
            response = await client.get(url)
            if config.DEBUG_VERBOSE:
                print(f"[fetch_page_impl] response status={response.status_code} len={len(response.text)}", file=sys.stderr, flush=True)
            response.raise_for_status()
            html = response.text
            break
        except httpx.HTTPStatusError as e:
            if config.DEBUG_VERBOSE:
                print(f"[fetch_page_impl] HTTPStatusError {e.response.status_code} attempt={attempt+1}", file=sys.stderr, flush=True)
            if not _is_retryable(e) or attempt == config.RETRY_MAX_ATTEMPTS - 1:
                return f"Error: Failed to fetch URL (HTTP {e.response.status_code}). The page may not exist or access was denied."
            await asyncio.sleep(delay)
            delay *= config.RETRY_BACKOFF_FACTOR
        except httpx.TimeoutException:
            if config.DEBUG_VERBOSE:
                print(f"[fetch_page_impl] TimeoutException attempt={attempt+1}", file=sys.stderr, flush=True)
            if attempt == config.RETRY_MAX_ATTEMPTS - 1:
                return "Error: Request timed out. The server took too long to respond. Try again later."
            await asyncio.sleep(delay)
            delay *= config.RETRY_BACKOFF_FACTOR
        except httpx.RequestError as e:
            if config.DEBUG_VERBOSE:
                print(f"[fetch_page_impl] RequestError {type(e).__name__}: {e} attempt={attempt+1}", file=sys.stderr, flush=True)
            if not _is_retryable(e) or attempt == config.RETRY_MAX_ATTEMPTS - 1:
                return f"Error: Request failed - {type(e).__name__}. Check the URL and network connectivity."
            await asyncio.sleep(delay)
            delay *= config.RETRY_BACKOFF_FACTOR

    if not html or len(html.strip()) < 100:
        return "Error: Received empty or minimal response from server. The page may be inaccessible."

    result = trafilatura.extract(
        html,
        output_format="markdown",
        with_metadata=True,
        include_comments=False,
        no_fallback=False,
    )

    if not result or not result.strip():
        return "Could not extract main content from this page. It may be a login wall, JavaScript-heavy SPA, or non-standard format. Try fetch_page with a different URL."

    if len(result) > max_length:
        result = result[:max_length].rsplit("\n", 1)[0] + "\n\n*[Content truncated due to max_length]*"

    if len(result) > config.CHARACTER_LIMIT:
        result = result[:config.CHARACTER_LIMIT - 80] + "\n\n*[Response truncated]*"

    return result
