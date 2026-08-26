"""Tiny stdlib-only JSON/HTTP helper shared by all provider adapters.

Kept deliberately dependency-free (``urllib`` instead of ``requests``/``httpx``)
so the tool has no third-party runtime dependencies, matching the rest of the
toolchain this ships alongside.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from .base import ProviderError


def post_json(
    provider: str,
    url: str,
    *,
    headers: dict[str, str],
    payload: dict,
    timeout_seconds: float,
) -> dict:
    """POST ``payload`` as JSON and return the parsed JSON response.

    Raises ``ProviderError`` for every failure mode (timeout, connection
    error, non-2xx status, malformed JSON) so callers never need to catch
    ``urllib`` or ``json`` exceptions directly.
    """
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", **headers},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        retryable = exc.code == 429 or exc.code >= 500
        raise ProviderError(
            provider,
            f"HTTP {exc.code} from {url}: {detail}",
            retryable=retryable,
        ) from exc
    except urllib.error.URLError as exc:
        raise ProviderError(provider, f"connection error to {url}: {exc.reason}", retryable=True) from exc
    except TimeoutError as exc:
        raise ProviderError(provider, f"timed out after {timeout_seconds}s calling {url}", retryable=True) from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProviderError(provider, f"non-JSON response from {url}: {exc}") from exc
