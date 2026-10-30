"""Client-side pagination and token-economical serialization for list tools.

RunZero's Export API endpoints document only a `search` query parameter -
no server-side limit/offset (help.runzero.com/docs/leveraging-the-api,
checked 2026-10-30). So every list tool fetches the (already
search-filtered) RunZero response once, then slices it here before
returning, bounded by both `limit` and the response-size cap
(vendor-mcp-development-sop.md Sec 2.5).
"""

from __future__ import annotations

import json
from typing import Any

MAX_RESPONSE_CHARS = 20_000


def paginate_and_serialize(
    envelope_key: str,
    items: list[dict[str, Any]],
    *,
    limit: int,
    offset: int,
) -> str:
    """Slice `items[offset:offset+limit]`, serialize, and enforce the size cap.

    `total` is the full search-filtered count (not the page size).
    `has_more` is true when the slice does not reach `total`, or when the
    character cap forced the page to shrink further.
    """
    total = len(items)
    page = items[offset : offset + limit]
    has_more = offset + len(page) < total

    while True:
        body = json.dumps(
            {envelope_key: page, "total": total, "has_more": has_more},
            separators=(",", ":"),
            ensure_ascii=False,
        )
        if len(body) <= MAX_RESPONSE_CHARS or len(page) <= 1:
            return body
        page = page[: len(page) // 2]
        has_more = True
