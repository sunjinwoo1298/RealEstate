"""
Creates the demo accounts for a reviewer (idempotent):

    python -m backend.cli.seed_demo

Staff: demo-admin / demo-manager / demo-exec @estateflow.ai. Buyer: demo-buyer@estateflow.ai (already verified).
All share the password in DEMO_PASSWORD (default below -- change it for any public deployment).
Also seeds the three sample enquiries from the client's data. Works with EMAIL_PROVIDER=log (no email needed).
"""
import asyncio
import os

from sqlalchemy import select

from backend.cli import seed_leads
from backend.core.database import close_db_connection, get_session_factory
from backend.core.security import hash_password
from backend.models.user import User, UserRole
from backend.services.customer_auth_service import CustomerAuthService

PASSWORD = os.environ.get("DEMO_PASSWORD") or "Demo@12345"
STAFF = [
    ("demo-admin@estateflow.ai", "Demo Admin", UserRole.ADMIN),
    ("demo-manager@estateflow.ai", "Demo Sales Head", UserRole.MANAGER),
    ("demo-exec@estateflow.ai", "Demo Sales Executive", UserRole.SALES_EXECUTIVE),
]
BUYER = ("demo-buyer@estateflow.ai", "Demo Buyer", "+919800009999")


async def _seed() -> None:
    factory = get_session_factory()
    async with factory() as db:
        for email, name, role in STAFF:
            if (await db.execute(select(User).where(User.email == email))).scalar_one_or_none() is None:
                db.add(User(email=email, full_name=name, password_hash=hash_password(PASSWORD), role=role, is_active=True))
                print(f"created staff {email}")
        await db.commit()

        email, name, phone = BUYER
        registered = await CustomerAuthService.register(
            db, full_name=name, email=email, password=PASSWORD, phone=phone,
            accepted_privacy_policy=True, marketing_consent=False,
        )
        if registered is None:
            print(f"buyer {email} already exists")
        else:
            _, raw_token = registered
            await CustomerAuthService.verify_email(db, raw_token)
            print(f"created verified buyer {email}")
    await seed_leads._seed()


def main() -> None:
    try:
        asyncio.run(_seed())
    finally:
        asyncio.run(close_db_connection())


if __name__ == "__main__":
    main()
