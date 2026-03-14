"""Autenticación JWT para la API REST del agente."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

security = HTTPBearer(auto_error=False)


def create_token(subject: str = "agent-admin") -> str:
    """Genera un JWT token."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


async def verify_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> str:
    """Dependency de FastAPI que verifica el JWT.

    En modo SIMULATION, permite acceso sin token.
    En modo LIVE, requiere token JWT válido.
    """
    # En modo SIMULATION, permitir acceso sin token
    if settings.agent_mode == "SIMULATION":
        if credentials is None:
            return "simulation-user"
        # Si envía token, validarlo igual
        try:
            payload = jwt.decode(
                credentials.credentials,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
            )
            return payload.get("sub", "unknown")
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return "simulation-user"

    # En modo LIVE, requiere token válido
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token requerido",
        )
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload.get("sub", "unknown")
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido",
        )
