"""Small HTTP policy shared by live evaluation clients."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import time


def _retry_after(value: str | None) -> float:
    """Return the server-requested wait, treating malformed values as no wait."""
    if not value:
        return 0.0
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            return max(0.0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError):
            return 0.0


async def post_with_retry(client, url, **kwargs):
    """POST once, retrying only rate limits up to three times."""
    request_seconds = 0.0
    retry_wait_seconds = 0.0
    for attempt in range(1, 5):
        started = time.perf_counter()
        response = await client.post(url, **kwargs)
        request_seconds += time.perf_counter() - started
        if response.status_code != 429 or attempt == 4:
            response.extensions["eval_timing"] = {
                "request_seconds": request_seconds,
                "retry_wait_seconds": retry_wait_seconds,
                "attempts": attempt,
            }
            return response
        delay = _retry_after(response.headers.get("Retry-After"))
        if delay:
            waited = time.perf_counter()
            await asyncio.sleep(delay)
            retry_wait_seconds += time.perf_counter() - waited
