"""Web lookup for facts the model cannot know.

Two backends:

* **duckduckgo** (default) - the keyless Instant Answer API. It only returns
  results for entities and definitions, not general queries, so it is honest
  about coming up empty rather than pretending.
* **tavily** - a search API built for LLMs; needs ``TAVILY_API_KEY`` but gives
  far better coverage.

Both are normalised to one short, speakable string, because a voice agent cannot
read out a list of ten blue links.
"""

from __future__ import annotations

from typing import Any

from ..errors import ToolError
from ..http_client import AsyncHttpClient

DUCKDUCKGO_URL = "https://api.duckduckgo.com/"
TAVILY_URL = "https://api.tavily.com/search"

#: Voice replies should be a couple of sentences, not a page.
MAX_SPOKEN_CHARS = 600


def _truncate(text: str, limit: int = MAX_SPOKEN_CHARS) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    # Prefer cutting at a sentence boundary so the reply does not end mid-word.
    clipped = text[:limit]
    for stop in (". ", "! ", "? "):
        idx = clipped.rfind(stop)
        if idx > limit * 0.5:
            return clipped[: idx + 1].strip()
    return clipped.rsplit(" ", 1)[0].strip() + "…"


async def search_duckduckgo(query: str, client: AsyncHttpClient) -> str:
    """Query the DuckDuckGo Instant Answer API."""
    payload = await client.get_json(
        DUCKDUCKGO_URL,
        params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1, "t": "nina"},
    )
    payload = payload or {}

    abstract = (payload.get("AbstractText") or "").strip()
    if abstract:
        source = (payload.get("AbstractSource") or "").strip()
        return _truncate(f"{abstract}" + (f" (source: {source})" if source else ""))

    answer = (payload.get("Answer") or "").strip()
    if answer:
        return _truncate(answer)

    definition = (payload.get("Definition") or "").strip()
    if definition:
        return _truncate(definition)

    for topic in payload.get("RelatedTopics") or []:
        text = (topic or {}).get("Text")
        if text:
            return _truncate(str(text))

    raise ToolError(f"I found nothing solid for {query}")


async def search_tavily(query: str, client: AsyncHttpClient, api_key: str) -> str:
    """Query Tavily, preferring its synthesised answer over raw results."""
    if not api_key:
        raise ToolError("web search is not configured")

    payload = await client.post_json(
        TAVILY_URL,
        json={
            "query": query,
            "max_results": 3,
            "include_answer": True,
            "search_depth": "basic",
        },
        headers={"Authorization": f"Bearer {api_key}"},
    )
    payload = payload or {}

    answer = (payload.get("answer") or "").strip()
    if answer:
        return _truncate(answer)

    results: list[dict[str, Any]] = payload.get("results") or []
    snippets = [" ".join(str(r.get("content", "")).split()) for r in results if r.get("content")]
    if snippets:
        return _truncate(" ".join(snippets))

    raise ToolError(f"I found nothing solid for {query}")


async def search(
    query: str,
    client: AsyncHttpClient,
    *,
    provider: str = "duckduckgo",
    api_key: str = "",
) -> str:
    """Run a web search with the configured backend.

    Raises:
        ToolError: if the query is empty, search is disabled, or nothing useful
            comes back.
    """
    query = " ".join(query.strip().split())
    if not query:
        raise ToolError("I need something to search for")

    if provider == "none":
        raise ToolError("web search is turned off in this deployment")
    if provider == "tavily":
        return await search_tavily(query, client, api_key)
    if provider == "duckduckgo":
        return await search_duckduckgo(query, client)
    raise ToolError(f"unknown search provider {provider!r}")
