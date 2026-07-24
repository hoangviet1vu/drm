"""Bug condition exploration tests for optional expires_at.

These tests encode the BUGGY behavior and are expected to PASS on unfixed code.
After the fix is applied, they will FAIL (confirming the bug is fixed).

Validates: Requirements 1.1, 1.3, 1.4, 1.5
"""

from __future__ import annotations

import json
import os

import httpx
import pytest
import respx
from hypothesis import given, settings
from hypothesis.strategies import characters, text

from drm.airflow.auth import Airflow3AuthClient
from drm.core.airflow_facade import AuthResult
from drm.core.paths import TokenData, load_token, save_token

BASE_URL = "https://airflow.example.com"
TOKEN_ENDPOINT = f"{BASE_URL}/auth/token"

# Strategy: non-empty alphanumeric strings
access_token_strategy = text(min_size=1, alphabet=characters(categories=("L", "N")))


class TestBugConditionExploration:
    """Exploration tests that confirm buggy behavior exists on unfixed code."""

    @respx.mock
    @given(access_token=access_token_strategy)
    @settings(max_examples=30)
    def test_missing_expires_at_produces_empty_string(self, access_token: str) -> None:
        """**Validates: Requirements 1.1**

        Bug condition: when response has no expires_at field,
        authenticate() returns AuthResult with expires_at == "" (buggy).
        """
        respx.post(TOKEN_ENDPOINT).mock(
            return_value=httpx.Response(
                200,
                json={"access_token": access_token},
            )
        )

        client = Airflow3AuthClient()
        result = client.authenticate(BASE_URL, "user", "pass")

        assert isinstance(result, AuthResult)
        assert result.token == access_token
        # Buggy behavior: missing expires_at becomes empty string
        assert result.expires_at == ""

        respx.reset()

    @respx.mock
    @given(access_token=access_token_strategy)
    @settings(max_examples=30)
    def test_null_expires_at_produces_string_none(self, access_token: str) -> None:
        """**Validates: Requirements 1.5**

        Bug condition: when response has expires_at: null,
        authenticate() returns AuthResult with expires_at == "None" (buggy str coercion).
        """
        respx.post(TOKEN_ENDPOINT).mock(
            return_value=httpx.Response(
                200,
                json={"access_token": access_token, "expires_at": None},
            )
        )

        client = Airflow3AuthClient()
        result = client.authenticate(BASE_URL, "user", "pass")

        assert isinstance(result, AuthResult)
        assert result.token == access_token
        # Buggy behavior: None is coerced to string "None"
        assert result.expires_at == "None"

        respx.reset()

    @given(access_token=access_token_strategy)
    @settings(max_examples=30)
    def test_empty_expires_at_token_file_rejected(
        self, access_token: str, monkeypatch, tmp_path
    ) -> None:
        """**Validates: Requirements 1.3, 1.4**

        Bug condition: TokenData with expires_at="" is saved successfully,
        but load_token() rejects it and returns None (file treated as invalid).
        """
        token_path = tmp_path / "drm" / "token.json"
        monkeypatch.setattr("drm.core.paths.get_token_path", lambda: token_path)

        data = TokenData(token=access_token, server="https://a.com", expires_at="")
        save_token(data)

        # Verify the file was written with empty expires_at
        content = json.loads(token_path.read_text(encoding="utf-8"))
        assert content["expires_at"] == ""

        # Buggy behavior: load_token rejects file with empty expires_at
        loaded = load_token()
        assert loaded is None
