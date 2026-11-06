"""
Secure CLI command to bootstrap the first admin account.

Usage:
    conda activate minor
    python -m backend.cli.bootstrap_admin

Credentials are read from the INITIAL_ADMIN_EMAIL / INITIAL_ADMIN_PASSWORD
environment variables (or backend/.env.local). If either is missing, the
command falls back to secure interactive prompts (password input is hidden).

Refuses to create a duplicate admin: if an account with the given email
already exists, or if any ADMIN account already exists, the command exits
without making changes.
"""
import asyncio
import getpass
import sys

from sqlalchemy import select

from backend.core.config import settings
from backend.core.database import close_db_connection, get_session_factory
from backend.core.security import hash_password
from backend.models.user import User, UserRole


def _resolve_credentials() -> tuple[str, str, str]:
    email = settings.INITIAL_ADMIN_EMAIL or input("Admin email: ").strip()
    full_name = input("Admin full name: ").strip()
    password = settings.INITIAL_ADMIN_PASSWORD or getpass.getpass("Admin password: ")

    if not email or not full_name or not password:
        print("Email, full name and password are all required.", file=sys.stderr)
        sys.exit(1)

    if len(password) < 8:
        print("Password must be at least 8 characters.", file=sys.stderr)
        sys.exit(1)

    return email.strip().lower(), full_name, password


async def _bootstrap() -> None:
    email, full_name, password = _resolve_credentials()

    session_factory = get_session_factory()
    async with session_factory() as db:
        existing_email = await db.execute(select(User).where(User.email == email))
        if existing_email.scalar_one_or_none() is not None:
            print(f"A staff account with email '{email}' already exists. Aborting.", file=sys.stderr)
            sys.exit(1)

        existing_admin = await db.execute(select(User).where(User.role == UserRole.ADMIN))
        if existing_admin.scalar_one_or_none() is not None:
            print("An admin account already exists. Aborting to prevent duplicate admin creation.", file=sys.stderr)
            sys.exit(1)

        admin = User(
            email=email,
            full_name=full_name,
            password_hash=hash_password(password),
            role=UserRole.ADMIN,
            is_active=True,
        )
        db.add(admin)
        await db.commit()

    print(f"Admin account created successfully for {email}.")


def main() -> None:
    try:
        asyncio.run(_bootstrap())
    finally:
        asyncio.run(close_db_connection())


if __name__ == "__main__":
    main()
