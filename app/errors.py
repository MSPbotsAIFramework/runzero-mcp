"""Structured error envelope used by every tool.

Tools never raise. Success and failure both come back as a JSON string, so
the calling agent can parse `error.code` and decide whether to retry
(`retryable`) - see vendor-mcp-development-sop.md Sec 4. `code` is drawn
from the fixed, finite vocabulary in Sec 4.2; nothing here invents a new one.
"""

from __future__ import annotations

import json
from typing import Awaitable, Callable, Literal

ErrorCode = Literal[
    "not_configured",
    "unauthorized",
    "not_found",
    "invalid_argument",
    "rate_limited",
    "upstream_error",
]

_RETRYABLE: dict[str, bool] = {
    "not_configured": False,
    "unauthorized": False,
    "not_found": False,
    "invalid_argument": False,
    "rate_limited": True,
    "upstream_error": True,
}


class RunZeroApiError(Exception):
    """Carries an error-vocabulary code plus a human-readable message."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code: ErrorCode = code
        self.message = message


def error_envelope(code: ErrorCode, message: str) -> str:
    """Serialize the structured error envelope (SOP Sec 4.2)."""
    return json.dumps(
        {"error": {"code": code, "message": message, "retryable": _RETRYABLE[code]}},
        separators=(",", ":"),
        ensure_ascii=False,
    )


def code_for_status(status_code: int) -> ErrorCode:
    """Map a RunZero HTTP status code to the fixed error-code vocabulary."""
    if status_code in (401, 403):
        return "unauthorized"
    if status_code == 404:
        return "not_found"
    if status_code in (400, 422):
        return "invalid_argument"
    if status_code == 429:
        return "rate_limited"
    return "upstream_error"


async def envelope_result(call: Callable[[], Awaitable[str]]) -> str:
    """Run an async tool body and convert any error into the envelope.

    `call` must return the already-serialized success JSON string. A
    RunZeroApiError becomes its mapped envelope; any other exception is
    treated as an upstream error rather than propagating - the contract
    (Sec 4.1) requires tools to never raise.
    """
    try:
        return await call()
    except RunZeroApiError as exc:
        return error_envelope(exc.code, exc.message)
    except Exception as exc:  # defensive: tools must never raise
        return error_envelope(
            "upstream_error", f"unexpected error calling RunZero: {type(exc).__name__}"
        )
