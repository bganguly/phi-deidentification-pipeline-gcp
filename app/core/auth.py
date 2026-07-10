import hashlib
import hmac
import time

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

_bearer = HTTPBearer(auto_error=False)


def _verify_hmac_token(token: str, secret: str) -> None:
    """
    Token format: {expiry_epoch}:{hmac_sha256(expiry_epoch, secret)}
    Raises HTTPException on invalid or expired tokens.
    """
    try:
        expiry_str, sig = token.split(":", 1)
        expected = hmac.new(secret.encode(), expiry_str.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            raise ValueError
        if int(expiry_str) < int(time.time()):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="access token expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid access token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def verify_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    if not settings.access_token:
        return  # auth disabled in local dev (no secret configured)
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing access token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    _verify_hmac_token(credentials.credentials, settings.access_token)
