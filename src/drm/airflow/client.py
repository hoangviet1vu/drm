"""HTTP client wrapper for Airflow API calls."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from drm.core.errors import NetworkError, TimeoutError


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """Structured HTTP response."""

    status_code: int
    json_body: dict[str, object] | None


class AirflowHttpClient:
    """Thin httpx wrapper that translates transport errors to DrmError subclasses."""

    def __init__(self, *, timeout: float = 30.0) -> None:
        self._timeout = timeout

    def post_json(self, url: str, body: dict[str, str]) -> HttpResponse:
        """POST JSON to the given URL.

        Returns an HttpResponse with the status code and parsed JSON body.

        Raises:
            TimeoutError: on httpx.TimeoutException
            NetworkError: on httpx.ConnectError or other transport errors
        """
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(url, json=body)
        except httpx.TimeoutException:
            raise TimeoutError(url) from None
        except httpx.TransportError:
            raise NetworkError(f"Server unreachable: {url}") from None

        try:
            json_body = response.json()
        except (ValueError, TypeError):
            json_body = None

        return HttpResponse(status_code=response.status_code, json_body=json_body)
