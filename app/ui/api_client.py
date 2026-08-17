"""Small HTTP client for the approved CuraPharm backend API."""

import os
from typing import Any, Dict, Optional

import httpx


class ApiError(RuntimeError):
    """User-safe error raised for backend connectivity or API failures."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class CuraPharmApi:
    """Call only the approved process read and workflow endpoints."""

    def __init__(self, base_url: Optional[str] = None, client=None):
        self.base_url = (
            base_url or os.getenv("API_BASE_URL", "http://127.0.0.1:8000/api")
        ).rstrip("/")
        self.client = client or httpx.Client(timeout=120.0, trust_env=False)

    def close(self):
        self.client.close()

    def list_processes(self, search=None, domain=None, sort_by="process_code", sort_order="asc"):
        return self._request(
            "GET", "/processes", params={"search": search or "", "domain": domain or "", "sort_by": sort_by, "sort_order": sort_order}
        )

    def get_process(self, process_code: str) -> Dict[str, Any]:
        return self._request("GET", "/processes/{}".format(process_code))

    def analyze_process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", "/processes/analyze", json=payload)

    def analyze_all_processes(self) -> Dict[str, Any]:
        """Trigger background batch analysis across baseline processes."""
        return self._request("POST", "/processes/analyze-all")

    def start_batch_analysis(self) -> Dict[str, Any]:
        """Alias for analyze_all_processes that starts an asynchronous batch job."""
        return self.analyze_all_processes()

    def get_batch_status(self, job_id: int) -> Dict[str, Any]:
        """Retrieve real-time persistent status for a specific batch job."""
        return self._request("GET", "/processes/batch/{}".format(job_id))

    def get_active_batch(self) -> Optional[Dict[str, Any]]:
        """Retrieve the currently active or most recent batch job."""
        return self._request("GET", "/processes/batch/active")

    def health_check(self) -> Dict[str, Any]:
        """Check backend health status."""
        return self._request("GET", "/health")

    def _request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        if path.startswith("/health"):
            url = self.base_url.rsplit("/api", 1)[0] + path
        else:
            url = self.base_url + path

        import time
        max_connect_retries = 3
        for attempt in range(max_connect_retries):
            try:
                response = self.client.request(method, url, **kwargs)
                break
            except httpx.ConnectError as exc:
                if attempt < max_connect_retries - 1 and method in ("GET", "HEAD"):
                    time.sleep(1.0)
                    continue
                raise ApiError("Unable to connect to CuraPharm backend. Ensure the backend service is running.") from exc
            except httpx.ReadTimeout as exc:
                raise ApiError("The backend request timed out while waiting for a response.") from exc
            except httpx.ConnectTimeout as exc:
                raise ApiError("Connection to the CuraPharm backend timed out.") from exc
            except httpx.HTTPStatusError as exc:
                raise ApiError("The backend returned an HTTP error (HTTP {}).".format(exc.response.status_code), exc.response.status_code) from exc
            except httpx.HTTPError as exc:
                raise ApiError("The CuraPharm backend communication error: {}".format(exc)) from exc


        if response.is_success:
            return response.json()
        detail = self._detail(response)
        if response.status_code == 404:
            raise ApiError("The requested process was not found.", response.status_code)
        if response.status_code == 409:
            raise ApiError("That process code already exists. Use a new code or open the existing process.", response.status_code)
        if response.status_code == 422:
            raise ApiError("Please check the process fields and use an approved domain.{}".format(" " + detail if detail else ""), response.status_code)
        raise ApiError("The backend could not complete the request.{}".format(" " + detail if detail else ""), response.status_code)

    @staticmethod
    def _detail(response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return ""
        detail = payload.get("detail") if isinstance(payload, dict) else None
        if isinstance(detail, dict):
            return str(detail.get("message") or detail.get("stage") or "")
        return str(detail or "")


__all__ = ["ApiError", "CuraPharmApi"]

