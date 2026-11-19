"""Служебные команды.

  python -m app.cli create-user admin@example.kz --role admin   # пароль спросит без отображения
"""

from __future__ import annotations

import argparse
import asyncio
import getpass

from sqlalchemy import select

from app.core.security import hash_password
from app.db.models.users import User, UserRole
from app.db.session import SessionLocal, engine


async def create_user(email: str, password: str, role: UserRole, full_name: str | None) -> str:
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == email.lower()))
        if user is None:
            user = User(email=email.lower())
            session.add(user)
        user.password_hash, user.role, user.full_name = hash_password(password), role, full_name or user.full_name
        await session.commit()
        uid = str(user.id)
    await engine.dispose()
    return uid


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("create-user")
    p.add_argument("email")
    p.add_argument("--role", choices=["admin", "lawyer"], default="admin")
    p.add_argument("--name")
    p.add_argument("--password-env", help="взять пароль из переменной окружения (для скриптов)")
    args = ap.parse_args()
    import os

    password = os.environ.get(args.password_env, "") if args.password_env else getpass.getpass("Пароль: ")
    if len(password) < 8:
        raise SystemExit("Пароль должен быть не короче 8 символов")
    uid = asyncio.run(create_user(args.email, password, UserRole(args.role), args.name))
    print(f"Пользователь {args.email} ({args.role}) готов, id {uid}")


if __name__ == "__main__":
    main()
