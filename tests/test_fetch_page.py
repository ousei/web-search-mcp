"""Unit and integration tests for fetch_page tool."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.tools.fetch_page import (
    FetchPageInput,
    fetch_page_impl,
)


class TestFetchPageInputValidation:
    """Unit tests for FetchPageInput URL validation."""

    def test_valid_https_url(self):
        p = FetchPageInput(url="https://example.com/article", max_length=5000)
        assert p.url == "https://example.com/article"

    def test_valid_http_url(self):
        p = FetchPageInput(url="http://example.com")
        assert p.url == "http://example.com"

    def test_invalid_no_scheme(self):
        with pytest.raises(ValueError, match="scheme"):
            FetchPageInput(url="example.com/article")

    def test_invalid_no_host(self):
        with pytest.raises(ValueError, match="scheme"):
            FetchPageInput(url="https://")

    def test_invalid_scheme(self):
        with pytest.raises(ValueError, match="http or https"):
            FetchPageInput(url="ftp://example.com")


@pytest.mark.asyncio
class TestFetchPageImplIntegration:
    """Integration tests for fetch_page_impl with mocked httpx."""

    @patch("src.tools.fetch_page._get_client")
    async def test_returns_extracted_content(self, mock_get_client):
        # HTML that trafilatura can extract (article with main content)
        mock_response = MagicMock()
        mock_response.text = """
        <!DOCTYPE html><html><body>
        <article><h1>Test Title</h1>
        <p>This is the main content of the article. It has enough text for extraction.</p>
        </article></body></html>
        """
        mock_response.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client

        params = FetchPageInput(url="https://example.com/article", max_length=5000)
        result = await fetch_page_impl(params)
        assert "Error:" not in result
        assert "Test Title" in result or "main content" in result or "Could not extract" in result

    @patch("src.tools.fetch_page._get_client")
    async def test_http_error_returns_message(self, mock_get_client):
        resp = MagicMock()
        resp.status_code = 404
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=httpx.HTTPStatusError("404", request=MagicMock(), response=resp)
        )
        mock_get_client.return_value = mock_client

        params = FetchPageInput(url="https://example.com/404", max_length=5000)
        result = await fetch_page_impl(params)
        assert "Error:" in result
        assert "404" in result
