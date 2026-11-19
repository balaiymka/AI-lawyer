"""Вход сотрудников (админ, юрист)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.security import current_user, find_user_by_email, issue_token, verify_password
from app.db.models.users import User, UserRole

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


def _public(u: User) -> dict:
    return {"id": str(u.id), "email": u.email, "full_name": u.full_name, "role": u.role.value}


@router.post("/login")
async def login(body: LoginIn) -> dict:
    user = await find_user_by_email(body.email)
    if user is None or not verify_password(body.password, user.password_hash) or user.deleted_at is not None:
        raise HTTPException(401, "Неверный email или пароль")
    if user.role not in (UserRole.admin, UserRole.lawyer):
        raise HTTPException(403, "Вход в админку — только для сотрудников")
    return {"token": issue_token(user), "user": _public(user)}


@router.get("/me")
async def me(user: User = Depends(current_user)) -> dict:
    return _public(user)
