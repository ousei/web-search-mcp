"""Configuration constants for web-search-mcp."""

import atexit
import os
import threading
from datetime import datetime
from pathlib import Path

# Maximum response size in characters (MCP Best Practices)
CHARACTER_LIMIT = 25000

# Default values for tools
DEFAULT_NUM_RESULTS = 8
DEFAULT_MAX_CHARS = 8000
DEFAULT_MAX_LENGTH = 5000

# HTTP client timeout (seconds), overridable via env
HTTP_TIMEOUT = float(os.environ.get("WEB_SEARCH_HTTP_TIMEOUT", "30.0"))

# Retry config
RETRY_MAX_ATTEMPTS = int(os.environ.get("WEB_SEARCH_RETRY_ATTEMPTS", "3"))
RETRY_INITIAL_DELAY = 1.0  # seconds
RETRY_BACKOFF_FACTOR = 2.0

# Search cache TTL (seconds), 0 to disable
SEARCH_CACHE_TTL = int(os.environ.get("WEB_SEARCH_CACHE_TTL", "300"))

# Debug: print full request and response to stderr (for timeout troubleshooting)
def _debug_enabled() -> bool:
    return os.environ.get("WEB_SEARCH_DEBUG", "").lower() in ("1", "true", "yes")


DEBUG_VERBOSE = _debug_enabled()
DEBUG_RESPONSE_MAX_CHARS = 2000  # truncate long responses when printing


def set_debug(enabled: bool) -> None:
    """Enable/disable verbose debug output (e.g. from --debug flag)."""
    global DEBUG_VERBOSE
    DEBUG_VERBOSE = enabled


def _log_path() -> Path:
    base = Path(__file__).resolve().parent.parent
    return base / "web_search.log"


# Buffered logging: queue + background flusher
_log_buffer: list[str] = []
_log_lock = threading.Lock()


def _flush_log_buffer() -> None:
    """Flush buffered log entries to file."""
    with _log_lock:
        if not _log_buffer:
            return
        to_write = _log_buffer[:]
        _log_buffer.clear()
    try:
        path = _log_path()
        with open(path, "a", encoding="utf-8") as f:
            for line in to_write:
                f.write(line)
    except OSError:
        pass


def append_log(tool: str, message: str, duration_ms: float | None = None) -> None:
    """Append a timestamped log entry (buffered, flushed periodically)."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    suffix = f" duration_ms={duration_ms:.0f}" if duration_ms is not None else ""
    line = f"{ts} [{tool}] {message}{suffix}\n"
    to_flush: list[str] = []
    with _log_lock:
        _log_buffer.append(line)
        if len(_log_buffer) >= 10:  # Flush when 10 entries buffered
            to_flush = _log_buffer[:]
            _log_buffer.clear()
    if to_flush:
        try:
            path = _log_path()
            with open(path, "a", encoding="utf-8") as f:
                for l in to_flush:
                    f.write(l)
        except OSError:
            pass


def flush_log() -> None:
    """Force flush any buffered log entries."""
    _flush_log_buffer()


# Flush on exit
atexit.register(flush_log)
