from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.security import hash_password, verify_password
from app.models.user import User

router = APIRouter(prefix="/api/user", tags=["user"])


class ChangePasswordIn(BaseModel):
    currentPassword: str = Field(min_length=1, max_length=200)
    newPassword: str = Field(min_length=8, max_length=200)


@router.put("/password")
def change_password(
    payload: ChangePasswordIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not user.password_hash:
        raise HTTPException(
            status_code=400,
            detail="This account uses Google sign-in. Set a password via forgot-password if needed.",
        )
    if not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This account uses Google sign-in. Set a password via forgot-password if needed.",
        )
    if not verify_password(payload.currentPassword, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect")
    user.password_hash = hash_password(payload.newPassword)
    db.add(user)
    db.commit()
    return {"message": "Password updated successfully"}


@router.delete("")
def delete_account(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    db.delete(user)
    db.commit()
    return {"message": "Account deleted"}

