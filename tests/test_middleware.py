"""Credential middleware: missing-header 401, and per-request ContextVar isolation.

Exercised through a real Starlette app built by app.main.build_app(), with
stateless_http=True so no MCP session handshake is needed. Each test builds
its own app instance rather than sharing the module-level `app.main.app`
singleton: the underlying StreamableHTTPSessionManager can only run its
lifespan once per instance, and TestClient's `with` block runs it on enter -
reusing one instance across tests raises
"StreamableHTTPSessionManager .run() can only be called once per instance".
"""

from __future__ import annotations

from starlette.testclient import TestClient

from app.credentials import CREDENTIAL_HEADER, get_token
from app.main import build_app
from app.runzero_client import RunZeroClient

MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


def test_missing_credential_header_returns_401_with_header_name():
    with TestClient(build_app()) as client:
        response = client.post(
            "/mcp",
            headers=MCP_HEADERS,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "unauthorized"
    assert CREDENTIAL_HEADER in body["error"]["message"]


def test_health_does_not_require_the_credential_header():
    with TestClient(build_app()) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_context_var_isolated_and_reset_between_requests(monkeypatch):
    """Two sequential requests with different tokens never see each other's value.

    `runzero_list_sites` calls RunZeroClient.get() exactly once; patching it
    to record `get_token()` lets this test observe, from inside a real tool
    call reached through the real middleware, which token that request saw.
    """
    observed: list[str | None] = []

    async def recording_get(self, path, params=None):
        observed.append(get_token())
        return []

    monkeypatch.setattr(RunZeroClient, "get", recording_get)

    with TestClient(build_app()) as client:
        r1 = client.post(
            "/mcp",
            headers={**MCP_HEADERS, CREDENTIAL_HEADER: "token-tenant-a"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "runzero_list_sites", "arguments": {}},
            },
        )
        assert r1.status_code == 200

        r2 = client.post(
            "/mcp",
            headers={**MCP_HEADERS, CREDENTIAL_HEADER: "token-tenant-b"},
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "runzero_list_sites", "arguments": {}},
            },
        )
        assert r2.status_code == 200

    assert observed == ["token-tenant-a", "token-tenant-b"]
    # The ContextVar in this (test) context was never touched by the
    # request-scoped set/reset inside the middleware - it remains unset here.
    assert get_token() is None
