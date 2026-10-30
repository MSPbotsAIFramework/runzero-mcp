"""runzero_list_sites tool."""

from __future__ import annotations

import json

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from app.errors import envelope_result
from app.runzero_client import RunZeroClient


def register(mcp: MCPServer) -> None:
    @mcp.tool(
        name="runzero_list_sites",
        description=(
            "List the RunZero sites in this organization. Use a returned "
            "site id to scope runzero_list_assets, runzero_list_vulnerabilities, "
            "runzero_list_scans, or runzero_start_scan."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True, destructiveHint=False, idempotentHint=True
        ),
    )
    async def runzero_list_sites() -> str:
        async def _run() -> str:
            async with RunZeroClient() as client:
                raw = await client.get("/export/org/sites.json")
            sites = [
                {"id": str(item.get("id", "")), "name": str(item.get("name", ""))}
                for item in (raw or [])
            ]
            return json.dumps(
                {"sites": sites, "total": len(sites)},
                separators=(",", ":"),
                ensure_ascii=False,
            )

        return await envelope_result(_run)
