"""Small synchronous HTTP and retry utilities for official research APIs."""

import time
from typing import Callable, Optional

import httpx


class RateLimiter:
    """In-process delay limiter using configured delay and requests-per-minute."""

    def __init__(
        self,
        rpm_limit: int,
        request_delay: float,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ):
        self.interval = max(
            float(request_delay), 60.0 / float(rpm_limit) if rpm_limit > 0 else 0.0
        )
        self.sleep = sleep
        self.monotonic = monotonic
        self.last_request_at: Optional[float] = None

    def wait(self):
        now = self.monotonic()
        if self.last_request_at is not None:
            remaining = self.interval - (now - self.last_request_at)
            if remaining > 0:
                self.sleep(remaining)
                now = self.monotonic()
        self.last_request_at = now


class ResearchHttpClient:
    """HTTP client wrapper with bounded retries for transient failures."""

    def __init__(
        self,
        timeout: float,
        max_retries: int,
        rpm_limit: int,
        request_delay: float,
        http_client: Optional[httpx.Client] = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.client = http_client or httpx.Client(timeout=timeout)
        self._owns_client = http_client is None
        self.max_retries = max(0, max_retries)
        self.rate_limiter = RateLimiter(rpm_limit, request_delay, sleep=sleep)

    def get(self, url: str, params):
        """GET a URL, retrying only timeouts, connection errors, 429, and 5xx."""
        last_error = None
        for attempt in range(self.max_retries + 1):
            self.rate_limiter.wait()
            try:
                response = self.client.get(url, params=params)
                response.raise_for_status()
                return response
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
            except httpx.HTTPStatusError as exc:
                last_error = exc
                status_code = exc.response.status_code
                if status_code != 429 and status_code < 500:
                    raise
            if attempt < self.max_retries:
                continue
        raise last_error

    def close(self):
        if self._owns_client:
            self.client.close()

