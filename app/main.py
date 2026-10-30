"""Entry point: builds the Starlette app and runs it with uvicorn.

Composition note (deviates from the Mount()-based pattern in
vendor-mcp-development-sop.md Sec 7/Sec 9, which targets the v1
`mcp.server.fastmcp.FastMCP` API): this repo pins `mcp>=1.9,<3.0` and
resolved to mcp 2.x, where `FastMCP` was renamed `MCPServer` and
`streamable_http_app()` returns one complete Starlette app (with its own
lifespan already wired to the session manager) rather than a sub-app meant
to be `Mount()`-ed. Appending the /health route onto that same app object -
instead of mounting it inside a second outer app - sidesteps the "Mount()
does not run the child app's lifespan" pitfall entirely, because there is
only one app and one lifespan. Verified empirically: a stateless
`tools/list` call succeeds (200, not the 400 that a lost lifespan would
produce) and /health responds without needing /mcp - see
docs/tickets/PRD-21241.md Self-test.
"""

from __future__ import annotations

from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.types import ASGIApp

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from app.credentials import CREDENTIAL_HEADER, reset_token, set_token
from app.settings import settings
from app.tools import assets, scans, sites, vulnerabilities

MCP_PATH = "/mcp"

INSTRUCTIONS = (
    "RunZero asset discovery, network scanning, and vulnerability-exposure data. "
    "Typical flow: call runzero_list_sites to find a site id, then "
    "runzero_list_assets / runzero_list_vulnerabilities scoped to that site, "
    "or runzero_start_scan to trigger a new scan and runzero_list_scans to poll it."
)


class CredentialHeaderMiddleware(BaseHTTPMiddleware):
    """Enforces the RunZero credential header on /mcp; sets/resets the ContextVar.

    /health is exempt by design (SOP Sec 1.1: the health probe must not
    depend on anything tenant-specific, including whether a credential was
    sent).
    """

    def __init__(self, app: ASGIApp, *, protected_path: str) -> None:
        super().__init__(app)
        self._protected_path = protected_path

    async def dispatch(self, request: Request, call_next):
        if request.url.path != self._protected_path:
            return await call_next(request)

        token = request.headers.get(CREDENTIAL_HEADER)
        if not token:
            return JSONResponse(
                {
                    "error": {
                        "code": "unauthorized",
                        "message": f"Missing required header: {CREDENTIAL_HEADER}",
                        "retryable": False,
                    }
                },
                status_code=401,
            )

        reset_handle = set_token(token)
        try:
            return await call_next(request)
        finally:
            reset_token(reset_handle)


async def health(_request: Request) -> Response:
    """Pure local probe - must never depend on RunZero reachability."""
    return JSONResponse({"status": "ok"})


def build_app() -> Starlette:
    mcp = MCPServer(name="runzero-mcp", instructions=INSTRUCTIONS)

    sites.register(mcp)
    assets.register(mcp)
    vulnerabilities.register(mcp)
    scans.register(mcp)

    app = mcp.streamable_http_app(
        streamable_http_path=MCP_PATH,
        stateless_http=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        ),
        host=settings.mcp_http_host,
    )
    app.routes.append(Route("/health", health, methods=["GET"]))
    app.add_middleware(CredentialHeaderMiddleware, protected_path=MCP_PATH)
    return app


app = build_app()


def run() -> None:
    import uvicorn

    uvicorn.run(app, host=settings.mcp_http_host, port=settings.mcp_http_port)


if __name__ == "__main__":
    run()
