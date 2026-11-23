"""Cognito access-token verification and fail-closed authorization."""

import secrets
from functools import lru_cache

import httpx
from typing import Any

import jwt
from fastapi import Depends, Header, HTTPException
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


async def _cognito_userinfo_email(settings, access_token: str) -> str | None:
    """Fetch the email claim when the access token does not carry it."""
    if not settings.cognito_domain:
        return None
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"https://{settings.cognito_domain}/oauth2/userInfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if resp.status_code != 200:
            return None
        email = str(resp.json().get("email") or "").strip().lower()
        return email or None
    except Exception:
        return None


async def require_authenticated_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="bearer token required")
    return verify_cognito_access_token(credentials.credentials)


async def require_admin(
    x_admin_token: str | None = Header(default=None),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    """Gate operational endpoints.

    Two independent paths are accepted:
      1. X-Admin-Token for CLI/ops use (compared in constant time).
      2. A Cognito access token whose verified email is in ADMIN_EMAILS, so the
         dashboard can trigger runs without a secret baked into the bundle.

    With neither ADMIN_TOKEN nor ADMIN_EMAILS configured (local development),
    admin endpoints stay open so the demo still works out of the box.
    """
    settings = get_settings()

    if settings.admin_token and x_admin_token:
        if secrets.compare_digest(x_admin_token, settings.admin_token):
            return

    allowed = settings.admin_email_set
    if allowed and credentials is not None and credentials.scheme.lower() == "bearer":
        try:
            claims = verify_cognito_access_token(credentials.credentials)
        except HTTPException as exc:
            # An invalid token is an authentication failure; a missing Cognito
            # configuration simply means this path is unavailable.
            if exc.status_code == 503:
                claims = None
            else:
                raise
        if claims:
            email = str(claims.get("email") or "").strip().lower()
            if not email:
                email = await _cognito_userinfo_email(settings, credentials.credentials) or ""
            if email and email in allowed:
                return

    if not settings.admin_token and not allowed:
        return  # development: no admin credentials configured

    raise HTTPException(
        status_code=403,
        detail="admin authorization required — sign in with an allowlisted account or use X-Admin-Token",
    )


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
