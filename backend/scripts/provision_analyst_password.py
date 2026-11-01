import asyncio
import os
import sys
from getpass import getpass
from pathlib import Path

from argon2 import PasswordHasher
from sqlalchemy import select

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from api.database import SessionFactory  # noqa: E402
from api.models import Analyst  # noqa: E402


async def provision_password(analyst_code: str, password: str) -> bool:
    async with SessionFactory.begin() as session:
        analyst = await session.scalar(
            select(Analyst).where(Analyst.analyst_code == analyst_code)
        )
        if analyst is None:
            return False
        analyst.password_hash = PasswordHasher().hash(password)
    return True


async def main() -> None:
    analyst_code = os.getenv("SIMULATOR_ANALYST_CODE")
    password = os.getenv("SIMULATOR_ANALYST_PASSWORD")
    if analyst_code is None or password is None:
        analyst_code = input("Analyst code: ").strip()
        password = getpass("New password (minimum 12 characters): ")
        confirmation = getpass("Confirm password: ")
        if password != confirmation:
            raise SystemExit("Passwords do not match")
    if len(password) < 12:
        raise SystemExit("Password must be at least 12 characters")
    if not await provision_password(analyst_code, password):
        raise SystemExit(f"Analyst {analyst_code!r} does not exist")
    print(f"Password provisioned for {analyst_code}")


if __name__ == "__main__":
    asyncio.run(main())
