"""Shared pytest fixtures."""

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app


@pytest.fixture
def client() -> TestClient:
    """A test client against a freshly created app."""
    return TestClient(create_app())


@pytest.fixture
def tmp_sandbox(tmp_path, monkeypatch):
    """Point the tool runtime's sandbox at a temp dir so agent-layer tests
    never write to the real ./sandbox."""
    from backend.app.config import get_settings
    from backend.app.data.runtime import get_runtime

    monkeypatch.setenv("SANDBOX_DIR", str(tmp_path))
    get_settings.cache_clear()
    get_runtime.cache_clear()
    yield tmp_path
    get_settings.cache_clear()
    get_runtime.cache_clear()
