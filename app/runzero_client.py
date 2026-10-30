"""Thin httpx client for RunZero's REST API.

One instance is created per tool call and closed at the end of that call
(the `async with` block) - never a module-level client - so a tenant's
token can never outlive, or leak into, another request (SOP Sec 3.3/3.4,
Sec 5 "connection reuse" is satisfied within the single request's lifetime).
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.credentials import get_token
from app.errors import RunZeroApiError, code_for_status

BASE_URL = "https://console.runzero.com/api/v1.0"
CONNECT_TIMEOUT = 5.0
READ_TIMEOUT = 30.0
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = 1.0


class RunZeroClient:
    """Reads the current request's token from the ContextVar, not a param.

    Raising `not_configured` here would mean the credential middleware
    (app/main.py) failed to reject the request before it reached a tool -
    the middleware is the actual 401 gate (SOP Sec 3.2); this is a defensive
    backstop, not the primary check.
    """

    def __init__(self) -> None:
        token = get_token()
        if not token:
            raise RunZeroApiError(
                "not_configured", "RunZero credential is not set for this request"
            )
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=httpx.Timeout(
                connect=CONNECT_TIMEOUT,
                read=READ_TIMEOUT,
                write=READ_TIMEOUT,
                pool=READ_TIMEOUT,
            ),
            headers={"Authorization": f"Bearer {token}"},
        )

    async def __aenter__(self) -> "RunZeroClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self._client.aclose()

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return await self._request("GET", path, params=params)

    async def put(self, path: str, json_body: dict[str, Any] | None = None) -> Any:
        return await self._request("PUT", path, json_body=json_body)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        last_error: RunZeroApiError | None = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                response = await self._client.request(
                    method, path, params=params, json=json_body
                )
            except httpx.TimeoutException as exc:
                last_error = RunZeroApiError(
                    "upstream_error", f"RunZero request timed out: {exc}"
                )
                await asyncio.sleep(BACKOFF_SECONDS * (attempt + 1))
                continue
            except httpx.HTTPError as exc:
                last_error = RunZeroApiError(
                    "upstream_error", f"RunZero request failed: {type(exc).__name__}"
                )
                await asyncio.sleep(BACKOFF_SECONDS * (attempt + 1))
                continue

            if response.status_code < 400:
                return response.json() if response.content else None

            code = code_for_status(response.status_code)
            message = f"RunZero returned {response.status_code} for {method} {path}"
            if code not in ("rate_limited", "upstream_error"):
                raise RunZeroApiError(code, message)

            last_error = RunZeroApiError(code, message)
            if attempt + 1 >= MAX_ATTEMPTS:
                break
            delay = _retry_after_seconds(response.headers.get("Retry-After"))
            await asyncio.sleep(
                delay if delay is not None else BACKOFF_SECONDS * (attempt + 1)
            )

        assert last_error is not None
        raise last_error


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None
