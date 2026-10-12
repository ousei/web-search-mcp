#!/usr/bin/env python3
"""
Web Search MCP Server - Local web search for LLM (OpenClaw, etc.).

Exposes web_search and fetch_page tools. Uses ddgs (no Docker, minimal resources).
Run with: python -m src.server
HTTP mode (for testing with mcporter, see logs in terminal):
  python -m src.server --http
"""

import argparse
import asyncio
import sys
import time

from mcp.server.fastmcp import FastMCP

from src.config import DEBUG_RESPONSE_MAX_CHARS, append_log, set_debug
from src.tools.fetch_page import FetchPageInput, fetch_page_impl
from src.tools.web_search import WebSearchInput, web_search_impl

mcp = FastMCP(
    name="web_search_mcp",
    json_response=True,  # JSON 响应更稳定，与 MCP Python client 兼容性更好
)


def _print_debug(tool: str, request: str, response: str, duration_ms: float, error: str | None = None) -> None:
    """Print request and response for timeout debugging."""
    from src.config import DEBUG_VERBOSE
    if not DEBUG_VERBOSE:
        return
    sep = "-" * 60
    print(f"\n[{tool}] REQUEST:\n{request}", file=sys.stderr, flush=True)
    if error:
        print(f"[{tool}] ERROR: {error}", file=sys.stderr, flush=True)
    else:
        preview = response if len(response) <= DEBUG_RESPONSE_MAX_CHARS else response[:DEBUG_RESPONSE_MAX_CHARS] + f"\n\n...[truncated, total {len(response)} chars]"
        print(f"[{tool}] RESPONSE ({len(response)} chars, {duration_ms:.0f}ms):\n{preview}\n{sep}", file=sys.stderr, flush=True)


def _format_error(e: BaseException) -> str:
    """Unified error message format for tool responses."""
    return f"Error: {type(e).__name__} - {e}"


@mcp.tool(
    name="web_search",
    annotations={
        "title": "Web Search",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def web_search(
    query: str,
    num_results: int = 8,
    max_chars: int = 8000,
    region: str = "jp-ja",
) -> str:
    """Search the web for any topic and get titles, URLs, and snippets.

    Best for: finding current information, news, facts, or answering questions.
    Returns: Clean formatted results (title, URL, snippet) ready for LLM use.

    Args:
        query: Search query (e.g. 'Python async tutorial', '国分寺 不動産').
        num_results: Maximum results to return (default: 8).
        max_chars: Maximum total characters to control token usage (default: 8000).
        region: Search region (default: jp-ja for Japanese). Options: jp-ja, us-en, zh-cn.

    Returns:
        Formatted Markdown with search results. Empty string on failure.
    """
    request_str = f"query={query!r} num_results={num_results} max_chars={max_chars} region={region}"
    print(f"[web_search] {request_str}", file=sys.stderr, flush=True)
    t0 = time.perf_counter()
    try:
        params = WebSearchInput(query=query, num_results=num_results, max_chars=max_chars, region=region)
    except Exception as e:
        append_log("web_search", request_str)
        return f"Error: Invalid parameters - {e}"

    try:
        result = await asyncio.to_thread(web_search_impl, params)
        duration_ms = (time.perf_counter() - t0) * 1000
        append_log("web_search", request_str, duration_ms=duration_ms)
        _print_debug("web_search", request_str, result, duration_ms)
        return result
    except RuntimeError as e:
        duration_ms = (time.perf_counter() - t0) * 1000
        append_log("web_search", request_str, duration_ms=duration_ms)
        _print_debug("web_search", request_str, "", duration_ms, error=str(e))
        return _format_error(e)


@mcp.tool(
    name="fetch_page",
    annotations={
        "title": "Fetch Web Page",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def fetch_page(url: str, max_length: int = 5000) -> str:
    """Fetch a webpage and extract its main content as Markdown.

    Best for: reading article content after finding URLs via web_search.
    Use for grounding: get full page text to answer detailed questions.

    Args:
        url: Full URL to fetch (must be http or https).
        max_length: Maximum characters to return (default: 5000).

    Returns:
        Extracted main content in Markdown, or error message.
    """
    request_str = f"url={url} max_length={max_length}"
    url_preview = url[:60] + "..." if len(url) > 60 else url
    print(f"[fetch_page] {request_str}", file=sys.stderr, flush=True)
    t0 = time.perf_counter()
    try:
        params = FetchPageInput(url=url, max_length=max_length)
    except Exception as e:
        append_log("fetch_page", f"url={url}")
        return f"Error: Invalid parameters - {e}"

    try:
        result = await fetch_page_impl(params)
        duration_ms = (time.perf_counter() - t0) * 1000
        append_log("fetch_page", f"url={url}", duration_ms=duration_ms)
        _print_debug("fetch_page", request_str, result, duration_ms)
        return result
    except Exception as e:
        duration_ms = (time.perf_counter() - t0) * 1000
        append_log("fetch_page", f"url={url}", duration_ms=duration_ms)
        _print_debug("fetch_page", request_str, "", duration_ms, error=str(e))
        return _format_error(e)


def main() -> None:
    """Run MCP server. Default: stdio (OpenClaw, Cursor). --http: HTTP mode for testing."""
    import uvicorn

    parser = argparse.ArgumentParser(description="Web Search MCP Server")
    parser.add_argument("--http", action="store_true", help="Run HTTP server (port 8765) to see logs when testing with mcporter")
    parser.add_argument("--port", type=int, default=8765, help="HTTP port when using --http")
    parser.add_argument("--debug", action="store_true", help="Print full request and response to stderr for timeout debugging")
    args = parser.parse_args()
    if args.debug:
        set_debug(True)
        print("[web_search_mcp] DEBUG: request/response logging enabled", file=sys.stderr, flush=True)

    if args.http:
        mcp.settings.host = "127.0.0.1"
        mcp.settings.port = args.port
        print(f"[web_search_mcp] HTTP server on http://localhost:{args.port}/mcp (logs below)", file=sys.stderr, flush=True)

        # Wrap with request logging when debug: see if tool calls reach us
        base_app = mcp.streamable_http_app()

        if args.debug:
            # Wrap at ASGI level to log all requests + body (helps debug when tool calls don't reach handlers)
            async def asgi_wrapper(scope, receive, send):
                if scope["type"] == "http":
                    path = scope.get("path", "")
                    method = scope.get("method", "")
                    print(f"[MCP] ASGI {method} {path}", file=sys.stderr, flush=True)

                    # Wrap receive to capture and log request body (first chunk usually has all for MCP)
                    _body_logged: list[bool] = [False]  # mutable to allow assignment in closure

                    async def logged_receive():
                        msg = await receive()
                        if msg.get("type") == "http.request" and not _body_logged[0]:
                            _body_logged[0] = True
                            body = msg.get("body", b"")
                            if body:
                                try:
                                    import json

                                    txt = body.decode("utf-8", errors="replace")
                                    j = json.loads(txt)
                                    method_name = j.get("method", "?")
                                    print(f"[MCP] JSON-RPC method={method_name!r} body_len={len(body)}", file=sys.stderr, flush=True)
                                except json.JSONDecodeError:
                                    print(f"[MCP] body len={len(body)} (not JSON)", file=sys.stderr, flush=True)
                                except Exception as e:
                                    print(f"[MCP] body log err: {e}", file=sys.stderr, flush=True)
                        return msg

                    await base_app(scope, logged_receive, send)
                else:
                    await base_app(scope, receive, send)

            config = uvicorn.Config(
                asgi_wrapper,
                host=mcp.settings.host,
                port=mcp.settings.port,
                log_level="info",
            )
        else:
            config = uvicorn.Config(
                base_app,
                host=mcp.settings.host,
                port=mcp.settings.port,
                log_level="info",
            )

        server = uvicorn.Server(config)
        asyncio.run(server.serve())
    else:
        print("[web_search_mcp] Stdio mode, waiting for connections... (logs on stderr)", file=sys.stderr, flush=True)
        mcp.run()


if __name__ == "__main__":
    main()
