"""runzero_list_assets tool."""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from app.errors import envelope_result
from app.paging import paginate_and_serialize
from app.runzero_client import RunZeroClient


def _asset_record(item: dict[str, Any]) -> dict[str, Any]:
    names = item.get("names")
    if not names and item.get("name"):
        names = [item["name"]]
    return {
        "id": str(item.get("id", "")),
        "names": names or [],
        "addresses": item.get("addresses") or [],
        "os": item.get("os"),
        "risk": item.get("risk") if item.get("risk") is not None else item.get("riskRating"),
        "vulnerability_count": item.get("vulnerability_count")
        if item.get("vulnerability_count") is not None
        else item.get("vulnerabilities"),
    }


def register(mcp: MCPServer) -> None:
    @mcp.tool(
        name="runzero_list_assets",
        description=(
            "List RunZero inventory assets, optionally filtered by site id "
            "and/or a RunZero search query (e.g. 'os:windows', 'alive:true'). "
            "Returns id, names, addresses, OS, and a risk/vulnerability summary per asset."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True, destructiveHint=False, idempotentHint=True
        ),
    )
    async def runzero_list_assets(
        site_id: Annotated[
            str | None, Field(description="Restrict results to one RunZero site id.")
        ] = None,
        search: Annotated[
            str | None,
            Field(description="RunZero search-query filter, e.g. 'os:windows'."),
        ] = None,
        limit: Annotated[
            int, Field(ge=1, le=200, description="Maximum assets to return (default 50, max 200).")
        ] = 50,
        offset: Annotated[
            int, Field(ge=0, description="Number of matching assets to skip, for paging.")
        ] = 0,
    ) -> str:
        async def _run() -> str:
            search_parts = []
            if search:
                search_parts.append(search)
            if site_id:
                search_parts.append(f"site:{site_id}")
            params = {"search": " and ".join(search_parts)} if search_parts else None

            async with RunZeroClient() as client:
                raw = await client.get("/export/org/assets.json", params=params)

            records = [_asset_record(item) for item in (raw or [])]
            return paginate_and_serialize("assets", records, limit=limit, offset=offset)

        return await envelope_result(_run)
