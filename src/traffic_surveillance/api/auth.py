import hmac

from fastapi import HTTPException, Request, status


async def require_api_key(request: Request) -> None:
    expected = request.app.state.settings.api_key
    if expected is None:
        return
    supplied = request.headers.get("x-api-key", "")
    if not supplied or not hmac.compare_digest(expected, supplied):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid X-API-Key header is required.",
        )
