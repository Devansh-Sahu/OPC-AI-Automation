"""
backend/core/security.py
────────────────────────
Authentication, authorisation, encryption, and audit-logging utilities.

Covers:
- Fernet symmetric encryption / decryption
- JWT creation & verification
- Bcrypt password hashing
- RBAC roles enum
- FastAPI dependency: get_current_user
- audit_log() function
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException, WebSocket, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.database import get_db

logger = logging.getLogger(__name__)

# ── Password hashing ──────────────────────────────────────────────────────────

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """Hash a plain-text password with bcrypt."""
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches the *hashed* password."""
    return _pwd_context.verify(plain, hashed)


# ── Fernet encryption ─────────────────────────────────────────────────────────

def _get_fernet() -> Fernet:
    key = settings.FERNET_KEY
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a plaintext string and return a URL-safe base64 token."""
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str) -> str:
    """Decrypt a Fernet token and return the plaintext string.

    Raises:
        ValueError: if the token is invalid or has been tampered with.
    """
    f = _get_fernet()
    try:
        return f.decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Invalid or corrupted encryption token") from exc


def encrypt_dict(data: dict) -> str:
    """Serialize *data* to JSON and then Fernet-encrypt it."""
    return encrypt_secret(json.dumps(data, default=str))


def decrypt_dict(token: str) -> dict:
    """Decrypt a Fernet token and deserialize the JSON payload."""
    return json.loads(decrypt_secret(token))


# ── RBAC ──────────────────────────────────────────────────────────────────────

class Role(str, Enum):
    """Application roles for role-based access control."""

    ADMIN = "admin"       # Full access: manage repos, trigger agents, view all
    OPERATOR = "operator" # Can trigger agent runs, approve PRs, view all
    VIEWER = "viewer"     # Read-only access to dashboards and logs


ROLE_PERMISSIONS: dict[Role, set[str]] = {
    Role.ADMIN: {
        "repo:read", "repo:write", "repo:delete",
        "issue:read", "issue:write",
        "pr:read", "pr:write", "pr:approve",
        "agent:read", "agent:write", "agent:cancel",
        "log:read",
        "user:read", "user:write",
        "settings:read", "settings:write",
    },
    Role.OPERATOR: {
        "repo:read", "repo:write",
        "issue:read", "issue:write",
        "pr:read", "pr:write", "pr:approve",
        "agent:read", "agent:write", "agent:cancel",
        "log:read",
        "user:read",
        "settings:read",
    },
    Role.VIEWER: {
        "repo:read",
        "issue:read",
        "pr:read",
        "agent:read",
        "log:read",
        "user:read",
    },
}


def has_permission(role: Role, permission: str) -> bool:
    """Check whether *role* has a specific *permission* string."""
    return permission in ROLE_PERMISSIONS.get(role, set())


def require_permission(role: Role, permission: str) -> None:
    """Raise HTTP 403 if the role lacks the required permission."""
    if not has_permission(role, permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{role}' lacks permission '{permission}'",
        )


# ── JWT ───────────────────────────────────────────────────────────────────────

class TokenData(BaseModel):
    sub: str                    # subject (user identifier / service name)
    role: Role = Role.VIEWER
    jti: str = ""               # JWT ID for revocation support
    exp: Optional[datetime] = None


def create_access_token(
    subject: str,
    role: Role = Role.VIEWER,
    expires_delta: Optional[timedelta] = None,
    extra_claims: Optional[dict] = None,
) -> str:
    """Create and sign a JWT access token.

    Args:
        subject:      Identifier encoded in the ``sub`` claim (e.g. user ID).
        role:         RBAC role to encode.
        expires_delta: Custom TTL; defaults to ``ACCESS_TOKEN_EXPIRE_MINUTES``.
        extra_claims:  Additional claims merged into the payload.

    Returns:
        Signed JWT string.
    """
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        if expires_delta
        else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload: dict = {
        "sub": str(subject),
        "role": role.value,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": expire,
        "iss": settings.APP_NAME,
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(subject: str, role: Role = Role.VIEWER) -> str:
    """Create a long-lived refresh token."""
    return create_access_token(
        subject=subject,
        role=role,
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        extra_claims={"type": "refresh"},
    )


def decode_token(token: str) -> TokenData:
    """Verify and decode a JWT token.

    Raises:
        HTTPException 401: if the token is invalid or expired.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        sub: str = payload.get("sub", "")
        role_str: str = payload.get("role", Role.VIEWER.value)
        jti: str = payload.get("jti", "")
        if not sub:
            raise credentials_exception

        return TokenData(sub=sub, role=Role(role_str), jti=jti)

    except JWTError as exc:
        logger.debug("JWT decode error: %s", exc)
        raise credentials_exception from exc


# ── FastAPI auth dependencies ─────────────────────────────────────────────────

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)


class CurrentUser(BaseModel):
    """Slim user context attached to every authenticated request."""

    model_config = {"arbitrary_types_allowed": True}

    sub: str
    role: Role
    jti: str


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
) -> CurrentUser:
    """FastAPI dependency – validate Bearer token and return CurrentUser.

    Returns:
        CurrentUser with sub, role, jti fields.

    Raises:
        HTTPException 401 if no valid token is provided.
    """
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = decode_token(token)
    return CurrentUser(sub=token_data.sub, role=token_data.role, jti=token_data.jti)


async def get_current_user_ws(websocket: WebSocket) -> Optional[CurrentUser]:
    """Extract and validate JWT from WebSocket query params or headers.

    Clients should pass the token as ``?token=<jwt>`` query parameter.
    """
    token = websocket.query_params.get("token")
    if not token:
        # Try Authorization header as fallback
        auth_header = websocket.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        return None

    try:
        token_data = decode_token(token)
        return CurrentUser(
            sub=token_data.sub, role=token_data.role, jti=token_data.jti
        )
    except HTTPException:
        return None


def require_role(*allowed_roles: Role):
    """Dependency factory – restrict endpoint to specific roles.

    Usage::

        @router.post("/admin-action")
        async def admin_action(user: CurrentUser = Depends(require_role(Role.ADMIN))):
            ...
    """
    async def _check(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Access denied. Required roles: "
                    f"{[r.value for r in allowed_roles]}"
                ),
            )
        return user

    return _check


# ── Audit logging ─────────────────────────────────────────────────────────────

_AUDIT_LOGGER = logging.getLogger("audit")


def audit_log(
    action: str,
    actor: str,
    resource_type: str,
    resource_id: str,
    details: Optional[dict] = None,
    success: bool = True,
) -> None:
    """Write a structured audit-log entry.

    All security-relevant events (login, token generation, data mutation) should
    call this function so they are captured in a dedicated audit log stream.

    Args:
        action:        Human-readable action label (e.g. "LOGIN", "PR_APPROVE").
        actor:         Subject identifier – user ID or service name.
        resource_type: Entity type being acted upon (e.g. "repository", "pr").
        resource_id:   ID of the affected entity.
        details:       Optional additional key-value context.
        success:       Whether the action succeeded.
    """
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "actor": actor,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "success": success,
        "details": details or {},
    }
    level = logging.INFO if success else logging.WARNING
    _AUDIT_LOGGER.log(level, json.dumps(entry))


# ── API Key auth (alternative to JWT) ────────────────────────────────────────

_STATIC_API_KEYS: dict[str, Role] = {}  # populated at startup from settings/db


def register_api_key(key: str, role: Role) -> None:
    """Register an API key with a given role (call during startup)."""
    _STATIC_API_KEYS[key] = role


def validate_api_key(key: str) -> Optional[Role]:
    """Return the Role associated with *key*, or None if not recognised."""
    return _STATIC_API_KEYS.get(key)


async def get_api_key_user(
    token: Optional[str] = Depends(oauth2_scheme),
) -> CurrentUser:
    """Dependency that accepts either a JWT Bearer token or a raw API key."""
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No credentials provided",
        )

    # First try JWT
    try:
        return await get_current_user(token)
    except HTTPException:
        pass

    # Then try raw API key
    role = validate_api_key(token)
    if role is not None:
        return CurrentUser(sub="api-key", role=role, jti="")

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
