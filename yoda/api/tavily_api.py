"""Async facade for Tavily Search and Extract APIs."""

from typing import Any

from tavily import AsyncTavilyClient


class TavilyApi:
    """Thin wrapper around AsyncTavilyClient for search and URL extraction."""

    def __init__(self, api_key: str) -> None:
        self._client = AsyncTavilyClient(api_key=api_key)

    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        search_depth: str = "basic",
        topic: str = "general",
        include_domains: list[str] | None = None,
    ) -> dict[str, Any]:
        """Run a Tavily search; returns the raw API response dict."""
        kwargs: dict[str, Any] = {
            "query": query,
            "max_results": max_results,
            "search_depth": search_depth,
            "topic": topic,
        }
        if include_domains is not None:
            kwargs["include_domains"] = include_domains
        return await self._client.search(**kwargs)

    async def extract(self, urls: list[str]) -> dict[str, Any]:
        """Extract content from URLs; returns the raw API response dict."""
        return await self._client.extract(urls=urls)
