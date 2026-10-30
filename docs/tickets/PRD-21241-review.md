# PRD-21241 · Code review

## Round 1 · 2026-10-30 · reviewed f35d32b (base d935a8b)

Verdict: changes requested

### Findings

1. [must-fix] Dockerfile:9 (in combination with .dockerignore:12) — `docker build --platform linux/amd64` fails and cannot produce an image. `.dockerignore` excludes `README.md` from the build context, but `pyproject.toml:5` declares `readme = "README.md"` for the `hatchling` build backend. The builder stage's second `RUN uv sync --frozen --no-dev` (Dockerfile:9, after `COPY . .`) installs the project itself (no `--no-install-project` this time), which makes `hatchling` validate `[project].readme` and raise `OSError: Readme file does not exist: README.md` because the file was never copied into the build context. Reproduced directly: `sudo docker build --platform linux/amd64 -t runzero-mcp:dev .` on the review machine fails with this exact trace; temporarily removing the `README.md` line from `.dockerignore` and rebuilding succeeds end-to-end (image exports cleanly). This is a hard requirement, not a nice-to-have: `vendor-mcp-development-sop.md` §14 checklist requires "`docker build --platform linux/amd64` builds and starts cleanly", and the review leg's INT publish/register step builds this image — as submitted, that step cannot succeed. Fix needs either keeping `README.md` in the Docker build context (drop it from `.dockerignore`) or making the package buildable without it (e.g. a build-context-only readme, or switching the wheel target to not require `readme` at build time) — implementation detail is for the dev leg to pick, not prescribed here.

### Suggestions

1. [suggestion] app/tools/scans.py:40-44 — the tech design's contract for `runzero_start_scan` declares `site_id` as a required input (`Input: {"site_id": str}`, no default), but the implementation declares `site_id: Annotated[str | None, ...] = None` and enforces "required" manually inside the tool body. Functionally equivalent and covered by TC-RZ-005, but the tool's published JSON schema will not mark `site_id` as a required parameter, which is a minor discoverability mismatch for callers that introspect the schema rather than reading the description text. Not blocking — the self-test's "Deviations from the tech design" section already documents two other implementation-driven deviations; this one could be added there too, or simply made a required parameter if FastMCP/MCPServer's schema generation supports it cleanly.
