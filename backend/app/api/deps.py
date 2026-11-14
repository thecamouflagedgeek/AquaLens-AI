"""
AquaLens AI - FastAPI Dependencies
Database session injection, JWT authentication, and Role-Based Access Control (RBAC).
"""

from typing import Optional
from fastapi import Depends, HTTPException, status, Request
import hashlib
from ..core.config import settings
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from ..core.security import decode_access_token
from ..db.session import get_db
from ..db.models import User, RevokedAccessToken

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def get_current_user_optional(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Optional[User]:
    token = token or request.cookies.get(settings.SESSION_COOKIE)
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload or "sub" not in payload or db.get(RevokedAccessToken, hashlib.sha256(token.encode()).hexdigest()):
        return None
    user = db.query(User).filter(User.username == payload["sub"]).first()
    return user if user and user.is_active else None


def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    token = token or request.cookies.get(settings.SESSION_COOKIE)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(token)
    if not payload or "sub" not in payload or db.get(RevokedAccessToken, hashlib.sha256(token.encode()).hexdigest()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.query(User).filter(User.username == payload["sub"]).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_role(*roles: str):
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles and current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access forbidden: role '{current_user.role}' lacks required permission.",
            )
        return current_user
    return role_checker
