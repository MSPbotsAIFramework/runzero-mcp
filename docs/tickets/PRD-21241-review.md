# PRD-21241 · Code review

Status: frozen @ 94064bf

## Round 1 · 2026-10-30 · reviewed f35d32b (base d935a8b)

Verdict: changes requested

### Findings

1. [must-fix] Dockerfile:9 (in combination with .dockerignore:12) — `docker build --platform linux/amd64` fails and cannot produce an image. `.dockerignore` excludes `README.md` from the build context, but `pyproject.toml:5` declares `readme = "README.md"` for the `hatchling` build backend. The builder stage's second `RUN uv sync --frozen --no-dev` (Dockerfile:9, after `COPY . .`) installs the project itself (no `--no-install-project` this time), which makes `hatchling` validate `[project].readme` and raise `OSError: Readme file does not exist: README.md` because the file was never copied into the build context. Reproduced directly: `sudo docker build --platform linux/amd64 -t runzero-mcp:dev .` on the review machine fails with this exact trace; temporarily removing the `README.md` line from `.dockerignore` and rebuilding succeeds end-to-end (image exports cleanly). This is a hard requirement, not a nice-to-have: `vendor-mcp-development-sop.md` §14 checklist requires "`docker build --platform linux/amd64` builds and starts cleanly", and the review leg's INT publish/register step builds this image — as submitted, that step cannot succeed. Fix needs either keeping `README.md` in the Docker build context (drop it from `.dockerignore`) or making the package buildable without it (e.g. a build-context-only readme, or switching the wheel target to not require `readme` at build time) — implementation detail is for the dev leg to pick, not prescribed here.

### Suggestions

1. [suggestion] app/tools/scans.py:40-44 — the tech design's contract for `runzero_start_scan` declares `site_id` as a required input (`Input: {"site_id": str}`, no default), but the implementation declares `site_id: Annotated[str | None, ...] = None` and enforces "required" manually inside the tool body. Functionally equivalent and covered by TC-RZ-005, but the tool's published JSON schema will not mark `site_id` as a required parameter, which is a minor discoverability mismatch for callers that introspect the schema rather than reading the description text. Not blocking — the self-test's "Deviations from the tech design" section already documents two other implementation-driven deviations; this one could be added there too, or simply made a required parameter if FastMCP/MCPServer's schema generation supports it cleanly.

### Fixes (round 1 rework)

1. [must-fix #1 — Dockerfile:9 / .dockerignore:12] Fixed by dropping the `README.md` line from `.dockerignore` (commit on `dev/PRD-21241`). `pyproject.toml:5` declares `readme = "README.md"` for the `hatchling` build backend, and the builder stage's second `RUN uv sync --frozen --no-dev` (Dockerfile:9, after `COPY . .`) installs the project itself, which requires that file to be present in the build context; only `README.md` was removed from the ignore list, `docs/` and `tests/` stay excluded. Chose "keep README.md in the build context" over "make the package buildable without it" — it is the smaller, more conventional change (the file is public documentation, not a secret) and does not touch `pyproject.toml` or the wheel target.
   - Verified: `docker build --platform linux/amd64 -t runzero-mcp:dev .` — `Successfully built f4e7084fe5e6`, `Successfully tagged runzero-mcp:dev`.
   - Verified: container started from that image answers `GET /health` with `200`; `initialize` → `tools/list` over `/mcp` with a placeholder `X-Runzero-Api-Token` header returns the same 5 tools as round 1 (`runzero_list_sites`, `runzero_list_assets`, `runzero_list_vulnerabilities`, `runzero_start_scan`, `runzero_list_scans`); the same request with the header omitted still gets `401`.
   - Re-ran the full gate suite on the resulting code: `uv run pytest -q` — 23 passed (unchanged from round 1); README Connector-section diff against `vendor-mcp-development/reference/readme-connector-section.md` — identical; Chinese-character scan (`grep -rnP '[\x{4e00}-\x{9fff}]' --exclude-dir=.git --exclude-dir=.venv .`) — no output. None of these were affected by the `.dockerignore` change, confirmed by rerunning rather than assuming.
2. [suggestion #1 — app/tools/scans.py:40-44] Not changed — the reviewer marked it non-blocking and the self-test's existing "Deviations from the tech design" section already documents it; revisiting it is out of scope for a must-fix-only rework round.

## Round 2 · 2026-10-30 · reviewed 94064bf (base d935a8b)

Verdict: approved

### Findings

None. Scope for this round: (a) verify round 1's "Fixes" entry against the actual code, (b) review the new diff `f65b151...94064bf` (one commit: `.dockerignore` — drops the `README.md` exclusion; plus the "Fixes" addendum to this file).

### Verification (independent, re-run on this machine rather than trusting the round-1-rework write-up)

- `docker build --platform linux/amd64 -t runzero-mcp:review-prd21241 .` on `94064bf` — succeeds (`Successfully built 454f8a64f167`). Confirms the `.dockerignore` fix resolves the exact failure mode recorded in round 1 (hatchling's `[project].readme = "README.md"` build-time check in the `uv sync --frozen --no-dev` step at Dockerfile:9, now satisfied because `README.md` is no longer excluded from the build context).
- Container from that image: `GET /health` → `200`; `POST /mcp` `initialize` with a placeholder `X-Runzero-Api-Token` header → `200`, returns server capabilities and the expected instructions string; the same request with the header omitted → `401` with the structured `unauthorized` envelope (`app/main.py:60-71`).
- `uv sync --frozen && uv run pytest -q` → 23 passed, matches the round-1-rework claim.
- Chinese-character scan (`grep -rnP '[\x{4e00}-\x{9fff}]' --exclude-dir=.git --exclude-dir=.venv .`) → no output.
- README `## MSPbots Connector` … `---` block (README.md:12-82) diffed byte-for-byte against `vendor-mcp-development/reference/readme-connector-section.md` → identical.
- Credential handling (SOP §3.3/3.4 iron rules): `app/credentials.py` stores the token in a `contextvars.ContextVar`, set in `CredentialHeaderMiddleware.dispatch` and reset in a `finally` (`app/main.py:73-77`) — no module-level or cross-request state. `grep -rn "log\|print("` over `app/` and `app/tools/` returns nothing, and the only occurrences of `token` in `app/runzero_client.py` / `app/tools/*.py` are the `get_token()` read and its use in the `Authorization: Bearer` header (`app/runzero_client.py:49`) — never written to a log, file, or module-level variable.
- Errors: `app/errors.py` maps RunZero HTTP statuses to a fixed `ErrorCode` vocabulary and serializes a structured `{"error": {"code", "message", "retryable"}}` envelope; `envelope_result()` catches all exceptions so tools never raise, per SOP §4.1.
- `docs/tickets/PRD-21241.ac.json`: 12/14 cases `pass`; TC-RZ-013/TC-RZ-014 are `untested` with an `evidence` field stating they need a real RunZero account/test org and are explicitly non-blocking per the ticket's completion criteria — consistent with `mcp-track.md` §3 ("missing a vendor test account is not a blocker").
- Suggestion #1 (`app/tools/scans.py:40-44`, `site_id` not marked required in the generated schema) — left open from round 1, confirmed still non-blocking (functionally covered by TC-RZ-005; documented in the self-test's "Deviations from the tech design" section).

Conclusion: the only must-fix from round 1 is fixed and independently reproduced as fixed; no new issues in the small round-2 diff; no must-fix remains. Approved.
