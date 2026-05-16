from fastapi import Header, HTTPException, status

from .config import config


async def require_auth(authorization: str | None = Header(default=None)) -> None:
    if not config.auth_token:
        return
    expected = f"Bearer {config.auth_token}"
    if authorization != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing token",
        )
