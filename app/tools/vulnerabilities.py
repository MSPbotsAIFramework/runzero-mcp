"""runzero_list_vulnerabilities tool.

Backed by GET /export/org/vulnerabilities.json. This path was not named in
RunZero's help-center page fetched during design (the linked SwaggerHub
spec 404'd); it was confirmed for this dev leg two ways: the OpenAPI spec
mirrored in the (reference-only) github.com/runZeroInc/runzero-api lists it
alongside the other `/export/org/*.json` endpoints, and an unauthenticated
probe against the live API returned 401 (a real, auth-gated path) rather
than 404 (checked 2026-10-30). The exact field names on each vulnerability
record were not independently confirmed, so the mapping below tolerates a
few plausible aliases - see docs/tickets/PRD-21241.md "Open questions" and
the Self-test section for what still needs a real account to verify.
"""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from app.errors import envelope_result
from app.paging import paginate_and_serialize
from app.runzero_client import RunZeroClient


def _vulnerability_asset_id(item: dict[str, Any]) -> str:
    if item.get("asset_id") is not None:
        return str(item["asset_id"])
    if item.get("assetID") is not None:
        return str(item["assetID"])
    asset = item.get("asset")
    if isinstance(asset, dict) and asset.get("id") is not None:
        return str(asset["id"])
    return ""


def _vulnerability_cve(item: dict[str, Any]) -> str | None:
    if item.get("cve"):
        return str(item["cve"])
    cves = item.get("cves")
    if isinstance(cves, list) and cves:
        return str(cves[0])
    return None


def _vulnerability_record(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id", "")),
        "cve": _vulnerability_cve(item),
        "severity": str(item.get("severity") or item.get("risk") or ""),
        "asset_id": _vulnerability_asset_id(item),
        "description": str(item.get("description") or item.get("name") or item.get("title") or ""),
    }


def register(mcp: MCPServer) -> None:
    @mcp.tool(
        name="runzero_list_vulnerabilities",
        description=(
            "List RunZero vulnerability-exposure findings, optionally scoped to one "
            "asset id or site id. Returns finding id, CVE (if any), severity, "
            "affected asset id, and a description."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True, destructiveHint=False, idempotentHint=True
        ),
    )
    async def runzero_list_vulnerabilities(
        asset_id: Annotated[
            str | None, Field(description="Restrict results to one RunZero asset id.")
        ] = None,
        site_id: Annotated[
            str | None, Field(description="Restrict results to one RunZero site id.")
        ] = None,
        limit: Annotated[
            int,
            Field(ge=1, le=200, description="Maximum findings to return (default 50, max 200)."),
        ] = 50,
        offset: Annotated[
            int, Field(ge=0, description="Number of matching findings to skip, for paging.")
        ] = 0,
    ) -> str:
        async def _run() -> str:
            search_parts = []
            if site_id:
                search_parts.append(f"site:{site_id}")
            params = {"search": " and ".join(search_parts)} if search_parts else None

            async with RunZeroClient() as client:
                raw = await client.get("/export/org/vulnerabilities.json", params=params)

            records = [_vulnerability_record(item) for item in (raw or [])]
            if asset_id:
                records = [r for r in records if r["asset_id"] == asset_id]
            return paginate_and_serialize("vulnerabilities", records, limit=limit, offset=offset)

        return await envelope_result(_run)
