"""
Shared HTTP helper for the ETL scripts: one requests.Session with retries.

Transient failures (timeouts, connection resets, 500/502/503/504) are retried with
exponential backoff. Rate limits (429) are NOT retried here, because the right wait
depends on which limit was hit; callers get a RateLimitedError and decide.
"""

import logging
import time

import requests

logger = logging.getLogger("parkwise.etl")

RETRY_STATUSES = {500, 502, 503, 504}


class RateLimitedError(Exception):
    """The API answered 429. `reason` is the API's own explanation, if it gave one."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def get_json(
    session: requests.Session,
    url: str,
    params: dict | None = None,
    headers: dict | None = None,
    attempts: int = 5,
    timeout: float = 60,
) -> dict:
    """GET a JSON document, retrying transient errors with backoff (2, 4, 8, 16 s)."""
    for attempt in range(1, attempts + 1):
        try:
            response = session.get(url, params=params, headers=headers, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt == attempts:
                raise
            wait = 2**attempt
            logger.warning("%s (attempt %d/%d), retrying in %ds", type(exc).__name__, attempt, attempts, wait)
            time.sleep(wait)
            continue

        if response.status_code == 429:
            try:
                reason = response.json().get("reason", "")
            except ValueError:
                reason = response.text[:200]
            raise RateLimitedError(reason or "Too many requests")

        if response.status_code in RETRY_STATUSES and attempt < attempts:
            wait = 2**attempt
            logger.warning("HTTP %d (attempt %d/%d), retrying in %ds", response.status_code, attempt, attempts, wait)
            time.sleep(wait)
            continue

        response.raise_for_status()
        return response.json()

    raise RuntimeError("unreachable")
