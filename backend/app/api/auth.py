"""
AquaLens AI - Authentication API Endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
import hashlib
from datetime import datetime, timezone
from ..core.config import settings
from ..core.security import decode_access_token
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from ..core.security import verify_password, hash_password, create_access_token
from ..db.session import get_db
from ..db.models import User, AuditLog, RevokedAccessToken
from ..schemas.schemas import Token, UserLogin, UserCreate, UserOut
from .deps import get_current_user, oauth2_scheme, require_role

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=Token)
def login(login_data: UserLogin, response: Response, db: Session = Depends(get_db)):
    """Authenticates user with username & password; returns signed JWT access token."""
    user = db.query(User).filter(User.username == login_data.username).first()
    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account is deactivated.",
        )

    db.query(RevokedAccessToken).filter(RevokedAccessToken.expires_at <= datetime.now(timezone.utc)).delete(synchronize_session=False)
    db.commit()
    access_token = create_access_token(subject=user.username, role=user.role)
    response.set_cookie(
        settings.SESSION_COOKIE, access_token,
        httponly=True, secure=settings.SECURE_COOKIES, samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60, path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user.role,
        "username": user.username,
    }


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_role("admin"))])
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    """Creates a new user account with specified role."""
    existing_user = db.query(User).filter(
        (User.username == user_in.username) | (User.email == user_in.email)
    ).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already registered.",
        )

    # Validate role
    valid_roles = ["admin", "officer", "researcher", "viewer"]
    role = user_in.role if user_in.role in valid_roles else "viewer"

    new_user = User(
        username=user_in.username,
        email=user_in.email,
        hashed_password=hash_password(user_in.password),
        role=role,
        is_active=True,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    """Returns profile information for the authenticated user."""
    return current_user


@router.post("/logout")
def logout(request: Request, response: Response, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    token = token or request.cookies.get(settings.SESSION_COOKIE)
    payload = decode_access_token(token) if token else None
    if payload and payload.get("exp"):
        digest = hashlib.sha256(token.encode()).hexdigest()
        if not db.get(RevokedAccessToken, digest):
            db.add(RevokedAccessToken(token_hash=digest, expires_at=datetime.fromtimestamp(payload["exp"], timezone.utc)))
            db.commit()
    response.delete_cookie(settings.SESSION_COOKIE, path="/", httponly=True, secure=settings.SECURE_COOKIES, samesite="lax")
    response.headers["Cache-Control"] = "no-store"
    return {"authenticated": False}
