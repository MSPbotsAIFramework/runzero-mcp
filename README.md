# runzero-mcp

MCP server for [RunZero](https://www.runzero.com/) asset discovery, network
scanning, and vulnerability-exposure data, built for the MSPbots Agent
platform.

- Transport: MCP Streamable HTTP (`POST /mcp`), stateless, no session
  affinity required.
- Stack: Python 3.12, `mcp[cli]` (FastMCP/`MCPServer`), `httpx`.
- License: Apache-2.0.

<div align="center">

## MSPbots Connector

**The MCP Gateway built for MSPs: visible, controlled, and your data stays where it belongs.**

[**Get started at connect.mspbots.ai →**](https://connect.mspbots.ai)

</div>

---

MSPbots Connector gives your AI clients one MCP URL to reach your entire MSP stack (RMM, PSA, documentation, security, finance), and gives you control over who can call which tool and a record of everything that was called.

**Hosted service: [connect.mspbots.ai](https://connect.mspbots.ai)** · Free to use.

### Why Connector

![MSPbots Connector](https://stgoss.mspbots.ai/files/mcp/mspbots-mcp.png)

| | |
|---|---|
| **Visible** | Every tool call is logged: who, which vendor, when. Usage dashboard, CSV export, SIEM streaming. |
| **Controlled** | Role-based, per-tool allowlist. Deny by default. |
| **Protected** | Credentials encrypted per record. AI clients never see your vendor passwords or tokens. |
| **MSP-native** | Built for the MSP stack only: RMM, PSA, documentation, security, finance. |

### Quick start

1. **Sign up** at [connect.mspbots.ai](https://connect.mspbots.ai).
2. **Connect your vendors.** Pick from 150+ connectors and authorize each one on the vendor's own page, or bring your own API keys. No extra vendor accounts needed.
3. **Set access.** Create roles and decide which tools each role may call. Nothing is allowed until you allow it.
4. **Add your MCP URL to your AI client.** Copy the URL from your Connector dashboard into Claude, ChatGPT, Cursor, VS Code, Gemini, Codex, or any MCP-capable client.
5. **Ask your AI to do real work**, and watch every call appear in the audit log.

### Features

**Unified gateway**
- One MCP URL for all your AI clients
- 150+ connectors across the MSP stack
- Custom MCP servers supported, free
- Authorization happens on each vendor's own page; the AI never sees passwords or tokens
- Bring your own credentials: use the vendor API keys you already have
- Multiple accounts per app; connect once, reuse across AI clients
- Tool search: finds the right action for the task
- One sign-in; vendor credentials are injected behind the scenes and OAuth tokens refresh automatically

**Visibility**
- Audit log for every tool call (who, which vendor, when)
- Usage dashboard: call volume, top vendors, error rate, per-user activity
- Export audit logs to CSV, or stream to Loki, Graylog, or LogScale (SIEM)
- Optional recording of tool arguments and result summaries (off by default, enabled per organization)

**Control**
- Per-role, per-tool allowlist, deny by default
- owner / admin / member roles
- SCIM provisioning with Entra ID, Okta, JumpCloud, and Google Workspace

**Security**
- Credentials encrypted one record at a time (AES-256-GCM, per-record key)
- AI clients authenticate with OAuth 2.1 + PKCE
- Vendor responses are scanned for prompt-injection patterns and returned as structured data. This is one layer of defense, not a guarantee against every attack.
- Static egress IP for customer firewall and API allowlisting

### Pricing

**Free.**

Links: [connect.mspbots.ai](https://connect.mspbots.ai) · [mspbots.ai](https://mspbots.ai)

---

## Authentication headers

| Header | Required | Type | Description |
|---|---|---|---|
| `X-Runzero-Api-Token` | yes | password | RunZero Bearer token (Export, Organization, or Account token) created in RunZero Console → Account → API |

The token is read only from this header on every request. It is never read
from an environment variable or a config file, never logged, and never
cached across requests (see `app/credentials.py`).

## Tools

| Tool | Read/Write | Description |
|---|---|---|
| `runzero_list_sites` | read-only | List the organization's RunZero sites (id, name). |
| `runzero_list_assets` | read-only | List inventory assets, optionally filtered by site or a RunZero search query. |
| `runzero_list_vulnerabilities` | read-only | List vulnerability-exposure findings, optionally scoped to an asset or site. |
| `runzero_start_scan` | write, non-idempotent | Start a network scan for one site (explicit `site_id` required). |
| `runzero_list_scans` | read-only | List recent scan tasks and their status, to poll a started scan. |

## Running locally

```bash
uv sync
uv run python -m app.main
```

The server listens on `0.0.0.0:8080` by default (override with
`MCP_HTTP_HOST` / `MCP_HTTP_PORT`). Try it with `curl`:

```bash
curl -s http://localhost:8080/health

curl -s -X POST http://localhost:8080/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -H 'X-Runzero-Api-Token: <your token>' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

## Testing

```bash
uv run pytest
```

Unit tests mock the RunZero HTTP client; no network access or real RunZero
account is required. See `docs/tickets/PRD-21241.md` for the full test-case
ledger, including the two manual cases that need a real RunZero account.

## Docker

```bash
docker build --platform linux/amd64 -t runzero-mcp:dev .
```
