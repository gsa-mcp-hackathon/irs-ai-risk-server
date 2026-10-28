"""Shared helpers: HTTP client, URL validation, pagination.

Keep all outbound I/O here. Tool modules import these helpers and never
instantiate their own HTTP clients.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import unquote, urlsplit

import httpx2 as httpx

from irs_risk.config import settings

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = settings.http_timeout
MAX_RESPONSE_BYTES = 2_000_000  # 2 MB guard

# Allowed outbound origins — operator-controlled; never a tool argument.
_ALLOWED_ORIGINS: frozenset[str] = frozenset({
    "https://data.irs.gov",
})


class UpstreamServiceError(RuntimeError):
    """Sanitized external-service failure safe to return to an MCP client."""


def _validate_url(url: str) -> str:
    """
    Validate that a URL targets one of the allowed origins.

    Raises ValueError for any URL that is not an https:// URL pointing at a
    known-safe origin. This prevents SSRF and open-redirect bugs.
    """
    parsed = urlsplit(url)
    # Require https scheme
    if parsed.scheme != "https":
        raise ValueError(f"Only https URLs are allowed. Got scheme: {parsed.scheme!r}")
    origin = f"https://{parsed.netloc}"
    if origin not in _ALLOWED_ORIGINS:
        raise ValueError(
            f"URL origin {origin!r} is not in the allowed list. "
            f"Allowed: {sorted(_ALLOWED_ORIGINS)}"
        )
    # Reject double-encoding / path traversal
    path = parsed.path
    for _ in range(3):
        decoded = unquote(path)
        if decoded == path:
            break
        path = decoded
    segments = path.replace("\\", "/").split("/")
    if any(seg in {".", ".."} for seg in segments):
        raise ValueError("Path traversal sequences are not allowed in the URL path.")
    return url


async def fetch_json(
    url: str,
    params: dict[str, Any] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Any:
    """
    GET a validated URL and return parsed JSON.

    Raises
    ------
    ValueError            : URL failed origin/scheme validation.
    UpstreamServiceError  : Sanitized message for any external-service failure.
    """
    safe_url = _validate_url(url)
    try:
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=timeout,
            trust_env=False,
        ) as client:
            async with client.stream("GET", safe_url, params=params) as response:
                response.raise_for_status()
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > MAX_RESPONSE_BYTES:
                        raise UpstreamServiceError(
                            "Upstream response exceeded the size limit."
                        )
                return json.loads(content)
    except UpstreamServiceError:
        raise
    except httpx.HTTPStatusError as exc:
        log.warning("upstream HTTP %d for %s", exc.response.status_code, safe_url)
        raise UpstreamServiceError(
            f"Upstream service returned status {exc.response.status_code}."
        ) from None
    except (httpx.DecodingError, json.JSONDecodeError, UnicodeDecodeError):
        log.warning("upstream returned invalid JSON for %s", safe_url)
        raise UpstreamServiceError("Upstream service returned invalid JSON.") from None
    except httpx.RequestError:
        log.warning("upstream request failed for %s", safe_url)
        raise UpstreamServiceError("Upstream service request failed.") from None


def paginate(items: list[Any], limit: int, offset: int) -> dict[str, Any]:
    """Return a standard pagination envelope."""
    total = len(items)
    window = items[offset: offset + limit]
    next_offset = offset + len(window)
    return {
        "total": total,
        "count": len(window),
        "offset": offset,
        "items": window,
        "has_more": next_offset < total,
        "next_offset": next_offset if next_offset < total else None,
    }
