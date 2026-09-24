"""Cognito access-token verification and fail-closed trading authorization."""

from functools import lru_cache
from typing import Any

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError, PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError, PyJWKClientError

from app.core.config import get_settings

_bearer = HTTPBearer(auto_error=False)


@lru_cache(maxsize=4)
def _jwks_client(issuer: str) -> PyJWKClient:
    return PyJWKClient(f"{issuer}/.well-known/jwks.json", cache_keys=True)


def verify_cognito_access_token(token: str) -> dict[str, Any]:
    """Verify signature, issuer, expiry, access-token use, and configured client."""
    settings = get_settings()
    if not (settings.cognito_region and settings.cognito_user_pool_id and settings.cognito_app_client_id):
        raise HTTPException(status_code=503, detail="authentication is not configured")

    issuer = (
        f"https://cognito-idp.{settings.cognito_region}.amazonaws.com/"
        f"{settings.cognito_user_pool_id}"
    )
    try:
        signing_key = _jwks_client(issuer).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=issuer,
            options={"require": ["exp", "iss", "sub", "token_use", "client_id"]},
        )
    except PyJWKClientConnectionError as exc:
        raise HTTPException(status_code=503, detail="identity provider is temporarily unavailable") from exc
    except (InvalidTokenError, PyJWKClientError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="invalid or expired access token") from exc

    if claims.get("token_use") != "access" or claims.get("client_id") != settings.cognito_app_client_id:
        raise HTTPException(status_code=401, detail="invalid access token audience")
    return claims


async def require_authenticated_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="bearer token required")
    return verify_cognito_access_token(credentials.credentials)


async def require_trading_user(
    claims: dict[str, Any] = Depends(require_authenticated_user),
) -> dict[str, Any]:
    """Trading is unavailable unless globally enabled and caller has a verified identity."""
    settings = get_settings()
    if not settings.trading_enabled:
        raise HTTPException(status_code=503, detail="trading is disabled")
    if not claims.get("sub"):
        raise HTTPException(status_code=403, detail="trading identity is not authorized")
    return claims
