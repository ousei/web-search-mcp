"""Unit and integration tests for web_search tool."""

import os
from unittest.mock import patch

import pytest

from src.tools.web_search import (
    WebSearchInput,
    format_search_results,
    web_search_impl,
)


class TestFormatSearchResults:
    """Unit tests for format_search_results."""

    def test_empty_results(self):
        assert format_search_results([], 1000) == ""

    def test_single_result(self):
        results = [{"title": "A", "url": "https://a.com", "snippet": "Snippet A"}]
        out = format_search_results(results, 1000)
        assert "## 1. A" in out
        assert "**URL**: https://a.com" in out
        assert "**Snippet**: Snippet A" in out

    def test_truncates_by_max_chars(self):
        results = [
            {"title": f"Title {i}", "url": f"https://{i}.com", "snippet": "x" * 50}
            for i in range(5)
        ]
        out = format_search_results(results, 200)
        assert "Truncated" in out or len(out) <= 250

    def test_handles_missing_fields(self):
        results = [{"title": "", "url": "", "snippet": ""}]
        out = format_search_results(results, 1000)
        assert "Untitled" in out or "## 1." in out


class TestWebSearchInput:
    """Unit tests for WebSearchInput validation."""

    def test_valid_input(self):
        p = WebSearchInput(query="test", num_results=5, max_chars=1000, region="us-en")
        assert p.query == "test"
        assert p.num_results == 5

    def test_strips_whitespace(self):
        p = WebSearchInput(query="  test  ", num_results=8)
        assert p.query == "test"


class TestWebSearchImplIntegration:
    """Integration tests for web_search_impl with mocked DDGS."""

    @pytest.fixture(autouse=True)
    def disable_cache(self, monkeypatch):
        monkeypatch.setenv("WEB_SEARCH_CACHE_TTL", "0")

    @patch("src.tools.web_search._search_sync")
    def test_returns_formatted_results(self, mock_search):
        mock_search.return_value = [
            {"title": "T1", "url": "https://1.com", "snippet": "S1"},
        ]
        params = WebSearchInput(query="test", num_results=1, max_chars=5000, region="jp-ja")
        result = web_search_impl(params)
        assert "Web Search Results" in result
        assert "T1" in result
        assert "https://1.com" in result

    @patch("src.tools.web_search._search_sync")
    def test_no_results_message(self, mock_search):
        mock_search.return_value = []
        params = WebSearchInput(query="xyznonexistent", num_results=5)
        result = web_search_impl(params)
        assert "No results found" in result
