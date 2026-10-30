"""Per-request RunZero credential storage.

The gateway serves many tenants through one running container, and each
request carries its own RunZero token in a header. The token is kept in a
contextvars.ContextVar - set at the start of a request, reset in a
`finally` - so two concurrent requests can never observe each other's
value. There is deliberately no module-level variable or cache here
(SOP Sec 3.3 "request-level isolation", Sec 3.4 "no cross-request cache").
"""

from __future__ import annotations

import contextvars

CREDENTIAL_HEADER = "X-Runzero-Api-Token"

_token: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "runzero_api_token", default=None
)


def set_token(value: str) -> contextvars.Token:
    """Store the current request's RunZero token; returns a reset handle."""
    return _token.set(value)


def reset_token(reset_handle: contextvars.Token) -> None:
    """Clear the current request's RunZero token."""
    _token.reset(reset_handle)


def get_token() -> str | None:
    """Return the current request's RunZero token, or None if unset."""
    return _token.get()
