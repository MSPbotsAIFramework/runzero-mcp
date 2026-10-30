"""Shared test fixtures.

Tests in test_tools.py call tools directly through a fresh MCPServer
instance, bypassing the Starlette credential middleware (that middleware
has its own dedicated tests in test_middleware.py). So here we set the
ContextVar the middleware would normally have set, mirroring a request that
already passed the 401 gate.
"""

from __future__ import annotations

import pytest

from app.credentials import reset_token, set_token


@pytest.fixture
def runzero_token():
    """Sets a fake per-request RunZero token for the duration of a test."""
    handle = set_token("test-token")
    try:
        yield "test-token"
    finally:
        reset_token(handle)
