import hmac

from fastapi import HTTPException, Request, status


async def require_api_key(request: Request) -> None:
    configured_key = request.app.state.settings.api_key
    if not configured_key:
        return

    supplied_key = request.headers.get("x-api-key", "")
    if not supplied_key or not hmac.compare_digest(supplied_key, configured_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid X-API-Key header is required.",
        )
