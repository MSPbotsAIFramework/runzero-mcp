"""runzero_start_scan and runzero_list_scans tools."""

from __future__ import annotations

import json
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from app.errors import envelope_result, error_envelope
from app.paging import paginate_and_serialize
from app.runzero_client import RunZeroClient


def _scan_record(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id", "")),
        "site_id": str(item.get("site_id", item.get("siteID", ""))),
        "status": str(item.get("status", "")),
        "started_at": item.get("started_at") or item.get("startedAt"),
        "completed_at": item.get("completed_at") or item.get("completedAt"),
    }


def register(mcp: MCPServer) -> None:
    @mcp.tool(
        name="runzero_start_scan",
        description=(
            "Start a RunZero network scan for one site. Requires an explicit "
            "site_id - there is no 'scan everything' option. Returns the new "
            "scan's id and status; poll it with runzero_list_scans."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=False, destructiveHint=True, idempotentHint=False
        ),
    )
    async def runzero_start_scan(
        site_id: Annotated[
            str | None,
            Field(description="RunZero site id to scan (required; from runzero_list_sites)."),
        ] = None,
    ) -> str:
        if not site_id:
            return error_envelope(
                "invalid_argument", "site_id is required; there is no scan-all-sites option"
            )

        async def _run() -> str:
            async with RunZeroClient() as client:
                raw = await client.put(f"/org/sites/{site_id}/scan")
            raw = raw or {}
            return json.dumps(
                {
                    "scan_id": str(raw.get("id", raw.get("scan_id", ""))),
                    "status": str(raw.get("status", "queued")),
                },
                separators=(",", ":"),
                ensure_ascii=False,
            )

        return await envelope_result(_run)

    @mcp.tool(
        name="runzero_list_scans",
        description=(
            "List recent RunZero scan tasks, optionally filtered by site id. "
            "Each entry has a status (queued/running/complete/failed) so a "
            "scan started by runzero_start_scan can be polled."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True, destructiveHint=False, idempotentHint=True
        ),
    )
    async def runzero_list_scans(
        site_id: Annotated[
            str | None, Field(description="Restrict results to one RunZero site id.")
        ] = None,
        limit: Annotated[
            int, Field(ge=1, le=200, description="Maximum scans to return (default 50, max 200).")
        ] = 50,
        offset: Annotated[
            int, Field(ge=0, description="Number of matching scans to skip, for paging.")
        ] = 0,
    ) -> str:
        async def _run() -> str:
            params = {"search": f"site:{site_id}"} if site_id else None
            async with RunZeroClient() as client:
                raw = await client.get("/export/org/scans.json", params=params)
            records = [_scan_record(item) for item in (raw or [])]
            return paginate_and_serialize("scans", records, limit=limit, offset=offset)

        return await envelope_result(_run)
