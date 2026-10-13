"""Demo users, one per role, created by `make seed` and nowhere else.

The password is public on purpose: it is printed by `make seed`, listed in the
README's demo-credentials block and prefilled by the login page's demo buttons (which
exist in development builds only). Never seed these into a deployed database.
"""

from sqlalchemy.orm import Session

from app.models import User, UserRole
from app.services.auth import hash_password

DEMO_PASSWORD = "meridian-demo-2026"
DEMO_USERS: list[tuple[str, str, UserRole]] = [
    ("admin@meridian.demo", "Demo Admin", UserRole.ADMIN),
    ("planner@meridian.demo", "Demo Planner", UserRole.PLANNER),
    ("analyst@meridian.demo", "Demo Analyst", UserRole.ANALYST),
    ("viewer@meridian.demo", "Demo Viewer", UserRole.VIEWER),
]


def add_demo_users(session: Session) -> list[User]:
    """Insert the four demo users (the caller has wiped the table and commits)."""
    password_hash = hash_password(DEMO_PASSWORD)
    users = [User(email=email, full_name=name, role=role, password_hash=password_hash, is_active=True)
             for email, name, role in DEMO_USERS]
    session.add_all(users)
    session.flush()
    return users
