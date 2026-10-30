"""tools/list snapshot, per-tool success paths, and the error-mapping table.

Tools are exercised through a real MCPServer instance (`mcp.call_tool`), the
same call path main.py uses - only `RunZeroClient.get` / `.put` are mocked,
so the test covers field mapping, pagination, and the error envelope
end-to-end without hitting the network. `runzero_token` (conftest.py) stands
in for the credential middleware, which has its own tests in
test_middleware.py.
"""

from __future__ import annotations

import json

import pytest
from mcp.server.mcpserver import MCPServer

from app.errors import RunZeroApiError, code_for_status
from app.runzero_client import RunZeroClient
from app.tools import assets, scans, sites, vulnerabilities


def build_server() -> MCPServer:
    mcp = MCPServer(name="runzero-mcp-test")
    sites.register(mcp)
    assets.register(mcp)
    vulnerabilities.register(mcp)
    scans.register(mcp)
    return mcp


async def call(mcp: MCPServer, name: str, **arguments) -> dict:
    result = await mcp.call_tool(name, arguments)
    assert not result.is_error, result.content
    return json.loads(result.content[0].text)


# ---------------------------------------------------------------------------
# tools/list snapshot
# ---------------------------------------------------------------------------


async def test_tools_list_snapshot_has_five_tools_with_expected_names():
    mcp = build_server()
    tools = await mcp.list_tools()
    names = sorted(t.name for t in tools)
    assert names == sorted(
        [
            "runzero_list_sites",
            "runzero_list_assets",
            "runzero_list_vulnerabilities",
            "runzero_start_scan",
            "runzero_list_scans",
        ]
    )


async def test_start_scan_hints_are_non_readonly_non_idempotent():
    mcp = build_server()
    tools = await mcp.list_tools()
    start_scan = next(t for t in tools if t.name == "runzero_start_scan")
    assert start_scan.annotations.read_only_hint is False
    assert start_scan.annotations.idempotent_hint is False
    assert start_scan.annotations.destructive_hint is True

    for name in (
        "runzero_list_sites",
        "runzero_list_assets",
        "runzero_list_vulnerabilities",
        "runzero_list_scans",
    ):
        tool = next(t for t in tools if t.name == name)
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.idempotent_hint is True


# ---------------------------------------------------------------------------
# runzero_list_sites (TC-RZ-003 / AC2)
# ---------------------------------------------------------------------------


async def test_list_sites_returns_id_and_name(monkeypatch, runzero_token):
    async def fake_get(self, path, params=None):
        assert path == "/export/org/sites.json"
        return [{"id": "s1", "name": "HQ"}, {"id": "s2", "name": "Branch"}]

    monkeypatch.setattr(RunZeroClient, "get", fake_get)

    mcp = build_server()
    body = await call(mcp, "runzero_list_sites")
    assert body == {"sites": [{"id": "s1", "name": "HQ"}, {"id": "s2", "name": "Branch"}], "total": 2}


# ---------------------------------------------------------------------------
# runzero_list_assets (TC-RZ-001, TC-RZ-002 / AC1)
# ---------------------------------------------------------------------------


ASSET_FIXTURE = [
    {
        "id": "a1",
        "names": ["web-01"],
        "addresses": ["10.0.0.1"],
        "os": "Windows Server 2022",
        "risk": "high",
        "vulnerability_count": 3,
    },
    {
        "id": "a2",
        "names": ["db-01"],
        "addresses": ["10.0.0.2"],
        "os": "Ubuntu 24.04",
        "risk": "low",
        "vulnerability_count": 0,
    },
]


async def test_list_assets_returns_bounded_list_with_fields(monkeypatch, runzero_token):
    async def fake_get(self, path, params=None):
        assert path == "/export/org/assets.json"
        return ASSET_FIXTURE

    monkeypatch.setattr(RunZeroClient, "get", fake_get)

    mcp = build_server()
    body = await call(mcp, "runzero_list_assets")
    assert body["total"] == 2
    assert body["has_more"] is False
    assert {a["id"] for a in body["assets"]} == {"a1", "a2"}
    first = next(a for a in body["assets"] if a["id"] == "a1")
    assert first["names"] == ["web-01"]
    assert first["addresses"] == ["10.0.0.1"]
    assert first["os"] == "Windows Server 2022"
    assert first["risk"] == "high"
    assert first["vulnerability_count"] == 3


async def test_list_assets_search_filter_excludes_non_matching(monkeypatch, runzero_token):
    seen_params = {}

    async def fake_get(self, path, params=None):
        seen_params.update(params or {})
        # RunZero applies the search filter server-side; simulate that here
        # by only returning the Windows asset when asked for it.
        if params and "os:windows" in params.get("search", ""):
            return [ASSET_FIXTURE[0]]
        return ASSET_FIXTURE

    monkeypatch.setattr(RunZeroClient, "get", fake_get)

    mcp = build_server()
    body = await call(mcp, "runzero_list_assets", search="os:windows")
    assert seen_params["search"] == "os:windows"
    assert [a["id"] for a in body["assets"]] == ["a1"]
    assert body["total"] == 1


# ---------------------------------------------------------------------------
# runzero_start_scan / runzero_list_scans (TC-RZ-004, TC-RZ-005, TC-RZ-006 / AC3, AC4)
# ---------------------------------------------------------------------------


async def test_start_scan_returns_scan_id_and_status(monkeypatch, runzero_token):
    async def fake_put(self, path, json_body=None):
        assert path == "/org/sites/s1/scan"
        return {"id": "scan-123", "status": "queued"}

    monkeypatch.setattr(RunZeroClient, "put", fake_put)

    mcp = build_server()
    body = await call(mcp, "runzero_start_scan", site_id="s1")
    assert body == {"scan_id": "scan-123", "status": "queued"}


async def test_start_scan_without_site_id_is_rejected():
    mcp = build_server()
    result = await mcp.call_tool("runzero_start_scan", {})
    assert not result.is_error
    body = json.loads(result.content[0].text)
    assert body["error"]["code"] == "invalid_argument"
    assert body["error"]["retryable"] is False


async def test_list_scans_returns_status_field(monkeypatch, runzero_token):
    async def fake_get(self, path, params=None):
        assert path == "/export/org/scans.json"
        return [
            {"id": "scan-1", "site_id": "s1", "status": "running"},
            {"id": "scan-2", "site_id": "s1", "status": "complete"},
        ]

    monkeypatch.setattr(RunZeroClient, "get", fake_get)

    mcp = build_server()
    body = await call(mcp, "runzero_list_scans")
    statuses = {s["id"]: s["status"] for s in body["scans"]}
    assert statuses == {"scan-1": "running", "scan-2": "complete"}


# ---------------------------------------------------------------------------
# runzero_list_vulnerabilities (TC-RZ-007, TC-RZ-008 / AC5)
# ---------------------------------------------------------------------------


VULN_FIXTURE = [
    {"id": "v1", "cve": "CVE-2026-0001", "severity": "critical", "asset_id": "a1", "description": "RCE"},
    {"id": "v2", "cve": "CVE-2026-0002", "severity": "medium", "asset_id": "a2", "description": "XSS"},
]


async def test_list_vulnerabilities_returns_expected_fields(monkeypatch, runzero_token):
    async def fake_get(self, path, params=None):
        assert path == "/export/org/vulnerabilities.json"
        return VULN_FIXTURE

    monkeypatch.setattr(RunZeroClient, "get", fake_get)

    mcp = build_server()
    body = await call(mcp, "runzero_list_vulnerabilities")
    assert body["total"] == 2
    ids = {v["id"] for v in body["vulnerabilities"]}
    assert ids == {"v1", "v2"}
    first = next(v for v in body["vulnerabilities"] if v["id"] == "v1")
    assert first["cve"] == "CVE-2026-0001"
    assert first["severity"] == "critical"
    assert first["asset_id"] == "a1"


async def test_list_vulnerabilities_scoped_to_asset(monkeypatch, runzero_token):
    async def fake_get(self, path, params=None):
        return VULN_FIXTURE

    monkeypatch.setattr(RunZeroClient, "get", fake_get)

    mcp = build_server()
    body = await call(mcp, "runzero_list_vulnerabilities", asset_id="a2")
    assert [v["id"] for v in body["vulnerabilities"]] == ["v2"]
    assert body["total"] == 1


# ---------------------------------------------------------------------------
# Error mapping (TC-RZ-010, TC-RZ-011 / AC7)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status_code", "expected_code"),
    [
        (400, "invalid_argument"),
        (401, "unauthorized"),
        (403, "unauthorized"),
        (404, "not_found"),
        (422, "invalid_argument"),
        (429, "rate_limited"),
        (500, "upstream_error"),
        (503, "upstream_error"),
    ],
)
def test_code_for_status_mapping_table(status_code, expected_code):
    assert code_for_status(status_code) == expected_code


async def test_runzero_429_maps_to_rate_limited_retryable(monkeypatch, runzero_token):
    async def fake_get(self, path, params=None):
        raise RunZeroApiError("rate_limited", "RunZero returned 429 for GET /export/org/sites.json")

    monkeypatch.setattr(RunZeroClient, "get", fake_get)

    mcp = build_server()
    result = await mcp.call_tool("runzero_list_sites", {})
    body = json.loads(result.content[0].text)
    assert body == {
        "error": {
            "code": "rate_limited",
            "message": "RunZero returned 429 for GET /export/org/sites.json",
            "retryable": True,
        }
    }


async def test_runzero_401_maps_to_unauthorized_non_retryable(monkeypatch, runzero_token):
    async def fake_get(self, path, params=None):
        raise RunZeroApiError("unauthorized", "RunZero returned 401 for GET /export/org/sites.json")

    monkeypatch.setattr(RunZeroClient, "get", fake_get)

    mcp = build_server()
    result = await mcp.call_tool("runzero_list_sites", {})
    body = json.loads(result.content[0].text)
    assert body == {
        "error": {
            "code": "unauthorized",
            "message": "RunZero returned 401 for GET /export/org/sites.json",
            "retryable": False,
        }
    }
