from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user
from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import LoginIn, MeOut, RegisterIn, TokenOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", status_code=201)
def register(payload: RegisterIn, db: Session = Depends(get_db)) -> dict:
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(
        name=payload.name,
        organisation=payload.organisation,
        email=payload.email,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"message": "Account created successfully", "credits": user.credits}


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)) -> TokenOut:
    user = db.scalar(select(User).where(User.email == payload.email))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return TokenOut(access_token=create_access_token(str(user.id)), refresh_token=create_refresh_token(str(user.id)))


@router.post("/refresh", response_model=TokenOut)
def refresh(refresh_token: str, db: Session = Depends(get_db)) -> TokenOut:
    try:
        payload = jwt.decode(refresh_token, settings.jwt_secret, algorithms=["HS256"])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    user_id = payload.get("sub")
    if not user_id or not db.get(User, user_id):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    return TokenOut(access_token=create_access_token(user_id), refresh_token=create_refresh_token(user_id))


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)) -> MeOut:
    return MeOut(
        id=user.id,
        name=user.name,
        organisation=user.organisation,
        email=user.email,
        credits=user.credits,
    )

