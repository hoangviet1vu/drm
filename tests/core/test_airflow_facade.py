"""Tests for core/airflow_facade.py — Protocol registry."""

import pytest

import drm.core.airflow_facade as facade
from drm.core.airflow_facade import (
    AirflowAuthClient,
    AuthResult,
    get_default_client,
    register_client,
)


@pytest.fixture(autouse=True)
def _clean_registry(monkeypatch):
    """Reset module-level registry between tests."""
    monkeypatch.setattr(facade, "_registry", {})
    monkeypatch.setattr(facade, "_default_key", None)


class FakeClient:
    """A minimal implementation satisfying AirflowAuthClient protocol."""

    def authenticate(self, url: str, username: str, password: str) -> AuthResult:
        return AuthResult(token="fake-tok", expires_at="2026-01-01T00:00:00+00:00")


class AnotherClient:
    """A second implementation for multi-registration tests."""

    def authenticate(self, url: str, username: str, password: str) -> AuthResult:
        return AuthResult(token="alt-tok", expires_at="2027-01-01T00:00:00+00:00")


class TestAuthResult:
    def test_frozen_dataclass(self):
        result = AuthResult(token="abc", expires_at="2026-01-01T00:00:00+00:00")
        assert result.token == "abc"
        assert result.expires_at == "2026-01-01T00:00:00+00:00"

        with pytest.raises(AttributeError):
            result.token = "changed"  # type: ignore[misc]


class TestRegisterClient:
    def test_register_sets_default_when_first(self):
        client = FakeClient()
        register_client("test", client)
        assert get_default_client() is client

    def test_register_with_default_flag(self):
        first = FakeClient()
        second = AnotherClient()
        register_client("first", first)
        register_client("second", second, default=True)
        assert get_default_client() is second

    def test_first_registered_becomes_default(self):
        first = FakeClient()
        second = AnotherClient()
        register_client("first", first)
        register_client("second", second)
        # First registered is default when no explicit default=True
        assert get_default_client() is first

    def test_default_flag_overrides_previous_default(self):
        first = FakeClient()
        second = AnotherClient()
        register_client("first", first, default=True)
        register_client("second", second, default=True)
        assert get_default_client() is second


class TestGetDefaultClient:
    def test_raises_runtime_error_when_no_client_registered(self):
        with pytest.raises(RuntimeError, match="No Airflow auth client registered"):
            get_default_client()

    def test_returns_registered_client(self):
        client = FakeClient()
        register_client("fake", client)
        assert get_default_client() is client

    def test_protocol_compliance(self):
        """Verify FakeClient satisfies the Protocol structurally."""
        client: AirflowAuthClient = FakeClient()
        result = client.authenticate("https://airflow.example.com", "user", "pass")
        assert isinstance(result, AuthResult)
