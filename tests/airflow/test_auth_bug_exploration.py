"""Bug condition exploration test — HTTP 201 raises UnexpectedResponseError.

Validates: Requirements 1.1, 1.2

This test encodes the BUGGY behavior: on unfixed code, HTTP 201 with a valid token
body raises UnexpectedResponseError. The test PASSES on unfixed code (confirming the
bug exists). After the fix is applied, this test will FAIL — proving that 201 is now
accepted as a valid success response.
"""

from __future__ import annotations

import httpx
import respx
from hypothesis import given, settings
from hypothesis.strategies import datetimes, text

from drm.airflow.auth import Airflow3AuthClient
from drm.core.errors import UnexpectedResponseError

BASE_URL = "https://airflow.example.com"
TOKEN_ENDPOINT = f"{BASE_URL}/auth/token"


@settings(max_examples=50)
@given(
    access_token=text(min_size=1),
    expires_at=datetimes().map(lambda dt: dt.isoformat()),
)
def test_http_201_raises_unexpected_response_error(
    access_token: str, expires_at: str
) -> None:
    """Property 1: Bug Condition — HTTP 201 Raises UnexpectedResponseError.

    **Validates: Requirements 1.1, 1.2**

    On unfixed code, every generated (access_token, expires_at) pair that is returned
    in an HTTP 201 response triggers UnexpectedResponseError(201, ...).
    """
    client = Airflow3AuthClient()

    with respx.mock:
        respx.post(TOKEN_ENDPOINT).mock(
            return_value=httpx.Response(
                201,
                json={
                    "access_token": access_token,
                    "expires_at": expires_at,
                },
            )
        )

        try:
            client.authenticate(BASE_URL, "admin", "password")
            # If we reach here, the bug is NOT present (201 was accepted)
            raise AssertionError(
                f"Expected UnexpectedResponseError for 201 with "
                f"access_token={access_token!r}, expires_at={expires_at!r}, "
                f"but authenticate() returned successfully."
            )
        except UnexpectedResponseError as exc:
            # Bug IS present — 201 raises UnexpectedResponseError as expected
            assert exc.status_code == 201
            assert TOKEN_ENDPOINT in exc.url
