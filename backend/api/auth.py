from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import get_settings
from api.database import get_session
from api.models import Analyst, AuditLog
from shared.schemas import AnalystLogin, AnalystLogoutResponse, AnalystToken

router = APIRouter(prefix="/auth", tags=["authentication"])
password_hasher = PasswordHasher()
bearer_scheme = HTTPBearer(auto_error=False)
JWT_ISSUER = "underlock-api"
REVOCATION_KEY_PREFIX = "auth:revoked:"
SessionDependency = Annotated[AsyncSession, Depends(get_session)]


@dataclass(frozen=True)
class AnalystPrincipal:
    analyst_code: str
    token_id: str
    expires_at: int


def _secret_key() -> str:
    secret = get_settings().jwt_secret_key
    if len(secret) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT_SECRET_KEY must be configured with at least 32 characters",
        )
    return secret


def _verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


async def require_analyst(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> AnalystPrincipal:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer authentication is required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = jwt.decode(
            credentials.credentials,
            _secret_key(),
            algorithms=["HS256"],
            issuer=JWT_ISSUER,
            options={"require": ["exp", "iat", "iss", "jti", "sub"]},
        )
        analyst_code = claims.get("sub")
        token_id = claims.get("jti")
        expires_at = claims.get("exp")
        if (
            not isinstance(analyst_code, str)
            or not isinstance(token_id, str)
            or not isinstance(expires_at, int)
        ):
            raise InvalidTokenError("Invalid analyst token claims")
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(status_code=503, detail="Authentication revocation service unavailable")
    try:
        revoked = await redis.get(f"{REVOCATION_KEY_PREFIX}{token_id}")
    except (RedisError, TimeoutError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Authentication revocation service unavailable",
        ) from exc
    if revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return AnalystPrincipal(analyst_code, token_id, expires_at)


CurrentAnalyst = Annotated[AnalystPrincipal, Depends(require_analyst)]


@router.post("/login", response_model=AnalystToken)
async def login(payload: AnalystLogin, db: SessionDependency) -> AnalystToken:
    _secret_key()
    analyst = await db.scalar(
        select(Analyst).where(Analyst.analyst_code == payload.analyst_code.strip())
    )
    if analyst is None or not _verify_password(payload.password, analyst.password_hash):
        raise HTTPException(status_code=401, detail="Invalid analyst code or password")

    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=get_settings().jwt_access_token_minutes)
    token_id = str(uuid4())
    access_token = jwt.encode(
        {
            "sub": analyst.analyst_code,
            "analyst_id": analyst.analyst_code,
            "jti": token_id,
            "iat": now,
            "exp": expires_at,
            "iss": JWT_ISSUER,
        },
        _secret_key(),
        algorithm="HS256",
    )
    db.add(
        AuditLog(
            actor_id=analyst.id,
            action="analyst_login",
            entity_type="analyst",
            entity_id=analyst.id,
            details={"analyst_code": analyst.analyst_code, "token_id": token_id},
        )
    )
    await db.commit()
    return AnalystToken(
        access_token=access_token,
        expires_at=expires_at,
        analyst_id=analyst.analyst_code,
    )


@router.post("/logout", response_model=AnalystLogoutResponse)
async def logout(
    request: Request,
    principal: CurrentAnalyst,
    db: SessionDependency,
) -> AnalystLogoutResponse:
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(status_code=503, detail="Authentication revocation service unavailable")
    ttl = max(1, principal.expires_at - int(datetime.now(UTC).timestamp()))
    try:
        await redis.set(f"{REVOCATION_KEY_PREFIX}{principal.token_id}", "1", ex=ttl)
    except (RedisError, TimeoutError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Authentication revocation service unavailable",
        ) from exc

    analyst = await db.scalar(select(Analyst).where(Analyst.analyst_code == principal.analyst_code))
    if analyst is None:
        raise HTTPException(status_code=401, detail="Analyst no longer exists")
    db.add(
        AuditLog(
            actor_id=analyst.id,
            action="analyst_logout",
            entity_type="analyst",
            entity_id=analyst.id,
            details={"analyst_code": analyst.analyst_code, "token_id": principal.token_id},
        )
    )
    await db.commit()
    return AnalystLogoutResponse()
