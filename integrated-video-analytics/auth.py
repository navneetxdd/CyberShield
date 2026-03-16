from __future__ import annotations

import hmac
import os

from fastapi import HTTPException, Request, WebSocket


def resolve_admin_token() -> str:
    return (os.getenv("ADMIN_API_TOKEN") or "").strip()


def admin_auth_enabled() -> bool:
    return bool(resolve_admin_token())


def extract_supplied_token(
    authorization: str | None = None,
    x_api_key: str | None = None,
    api_key: str | None = None,
) -> str:
    bearer = (authorization or "").strip()
    if bearer.lower().startswith("bearer "):
        bearer = bearer[7:].strip()
    for candidate in (bearer, (x_api_key or "").strip(), (api_key or "").strip()):
        if candidate:
            return candidate
    return ""


def extract_request_token(request: Request) -> str:
    return extract_supplied_token(
        authorization=request.headers.get("Authorization"),
        x_api_key=request.headers.get("X-API-Key"),
        api_key=request.query_params.get("api_key"),
    )


def extract_websocket_token(websocket: WebSocket) -> str:
    return extract_supplied_token(
        authorization=websocket.headers.get("Authorization"),
        x_api_key=websocket.headers.get("X-API-Key"),
        api_key=websocket.query_params.get("api_key"),
    )


def ensure_admin_access(
    authorization: str | None = None,
    x_api_key: str | None = None,
    api_key: str | None = None,
) -> None:
    configured_token = resolve_admin_token()
    if not configured_token:
        return
    supplied = extract_supplied_token(
        authorization=authorization,
        x_api_key=x_api_key,
        api_key=api_key,
    )
    if not supplied or not hmac.compare_digest(supplied, configured_token):
        raise HTTPException(status_code=401, detail="Invalid or missing admin token.")


def ensure_admin_request(request: Request) -> None:
    ensure_admin_access(
        authorization=request.headers.get("Authorization"),
        x_api_key=request.headers.get("X-API-Key"),
        api_key=request.query_params.get("api_key"),
    )


async def ensure_admin_websocket(websocket: WebSocket) -> bool:
    configured_token = resolve_admin_token()
    if not configured_token:
        return True
    supplied = extract_websocket_token(websocket)
    if supplied and hmac.compare_digest(supplied, configured_token):
        return True
    await websocket.close(code=1008, reason="Invalid or missing admin token.")
    return False
