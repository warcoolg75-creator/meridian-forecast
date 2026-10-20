"""Shared fixtures.

The suite runs on a temporary SQLite file unless PostgreSQL is asked for on the command
line: MERIDIAN_PG_TESTS=1 in the environment of the pytest process (`make test-pg`).
Then the whole suite runs on TEST_DATABASE_URL (environment or the repo-root .env) and
the cross-dialect tests compare the two. This project's tables in that database are
dropped and recreated, so it must not hold anything you want to keep in them.

The opt-in is never read from .env, which only supplies the URL: on 2026-10-20 a plain
`pytest` took the URL from .env and wiped the hosted copy of the pinned dataset. Without
the opt-in, the session also refuses every non-SQLite database connection and every
lookup of or connection to another machine, so nothing can reach PostgreSQL by accident.
"""

import os
import sys
from collections.abc import Callable, Iterator, Mapping
from datetime import date

# A fixed key for the test session, set before the app reads its settings, so no test
# ever writes backend/.jwt-secret.
os.environ.setdefault("JWT_SECRET", "test-only-jwt-signing-key-0123456789abcdef")

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.config import BACKEND_DIR, get_settings
from app.db import create_db_engine, get_db
from app.main import app
from app.models import (
    Base,
    Customer,
    DailySales,
    Product,
    Region,
    SalesOrder,
    SalesOrderLine,
    User,
    UserRole,
)
from app.models.base import utcnow
from app.seed.generate import wipe_all
from app.services.auth import create_access_token, hash_password
from app.services.rate_limit import login_limiter
from app.services.rollup import rebuild_period_rollups

PG_OPT_IN = "MERIDIAN_PG_TESTS"
LOOPBACK_HOSTS = {"", "localhost", "::1"}


def postgres_url_for_tests(environ: Mapping[str, str], dotenv_url: str) -> str:
    """The PostgreSQL URL this run may use, or "" to run on SQLite.

    Only the process environment can opt in, and only with exactly "1". `.env` supplies
    the URL once opted in, never the decision.
    """
    if environ.get(PG_OPT_IN) != "1":
        return ""
    url = environ.get("TEST_DATABASE_URL") or dotenv_url
    if not url.startswith("postgres"):
        raise pytest.UsageError(f"{PG_OPT_IN}=1 needs TEST_DATABASE_URL set to a PostgreSQL database")
    return url


PG_URL = postgres_url_for_tests(os.environ, get_settings().test_database_url)
HAS_PG = bool(PG_URL)
requires_pg = pytest.mark.skipif(not HAS_PG, reason=f"PostgreSQL tests need {PG_OPT_IN}=1")


def _is_loopback(host: str | bytes | None) -> bool:
    if host is None:  # getaddrinfo(None, port): this machine's wildcard address
        return True
    if isinstance(host, bytes):
        host = host.decode()
    return host in LOOPBACK_HOSTS or host.startswith("127.")


def _refuse_network(event: str, args: tuple) -> None:
    """Audit hook for a SQLite run: no lookup of, or connection to, another machine.

    psycopg resolves host names with socket.getaddrinfo, so this sees an attempt to
    reach PostgreSQL by name even though libpq opens the socket itself.
    """
    if event == "socket.getaddrinfo":
        host = args[0]
    elif event == "socket.connect" and isinstance(args[1], tuple):
        host = args[1][0]
    else:
        return
    if not _is_loopback(host):
        raise RuntimeError(f"Network access in a SQLite test run ({event}); PostgreSQL tests need {PG_OPT_IN}=1")


def _refuse_other_databases(dialect, _record, _cargs, _cparams) -> None:
    """Before any engine connects: a SQLite run connects to SQLite only (an IP address
    in a PostgreSQL URL would skip the lookup the audit hook sees)."""
    if dialect.name != "sqlite":
        raise RuntimeError(f"A {dialect.name} connection in a SQLite test run; PostgreSQL tests need {PG_OPT_IN}=1")


if not HAS_PG:
    sys.addaudithook(_refuse_network)
    sa.event.listen(Engine, "do_connect", _refuse_other_databases)


def migrate(engine: Engine) -> None:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.attributes["configure_logger"] = False
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


@pytest.fixture(scope="session")
def sqlite_engine(tmp_path_factory) -> Iterator[Engine]:
    engine = create_db_engine(f"sqlite:///{(tmp_path_factory.mktemp('db') / 'test.db').as_posix()}")
    migrate(engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def pg_engine() -> Iterator[Engine]:
    if not HAS_PG:
        pytest.skip(f"PostgreSQL tests need {PG_OPT_IN}=1")
    engine = create_db_engine(PG_URL)
    # Drop only this project's tables: hosted Postgres (Neon, Supabase) keeps its own
    # objects in the public schema, so dropping the schema itself would break it.
    with engine.begin() as connection:
        Base.metadata.drop_all(connection)
        connection.execute(sa.text("DROP TABLE IF EXISTS alembic_version"))
        connection.execute(sa.text("DROP TABLE IF EXISTS bucket_probe"))
    migrate(engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def engine(request) -> Engine:
    return request.getfixturevalue("pg_engine" if HAS_PG else "sqlite_engine")


def _clean_session(engine: Engine) -> Iterator[Session]:
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
    finally:
        session.rollback()
        wipe_all(session)
        session.commit()
        session.close()


@pytest.fixture
def db(engine) -> Iterator[Session]:
    yield from _clean_session(engine)


@pytest.fixture
def client(db) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db
    # https: the refresh cookie is Secure, and the client (rightly) only sends it back over https.
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _fresh_login_limiter() -> Iterator[None]:
    login_limiter.clear()
    yield
    login_limiter.clear()


TEST_PASSWORD = "correct horse battery staple"


@pytest.fixture
def make_user(db) -> Callable[..., User]:
    """Factory: an active user with TEST_PASSWORD unless told otherwise."""
    def make(email: str = "planner@example.com", role: UserRole = UserRole.PLANNER,
             password: str = TEST_PASSWORD, is_active: bool = True) -> User:
        user = User(email=email, full_name=f"Test {role.value}", role=role,
                    password_hash=hash_password(password), is_active=is_active)
        db.add(user)
        db.commit()
        return user
    return make


@pytest.fixture
def auth_headers(make_user) -> Callable[[UserRole], dict[str, str]]:
    """Factory: an Authorization header for a fresh user with the given role."""
    def headers(role: UserRole) -> dict[str, str]:
        user = make_user(email=f"{role.value}@example.com", role=role)
        return {"Authorization": f"Bearer {create_access_token(user, utcnow())}"}
    return headers


# --------------------------------------------------------------------------- data builders

REGION_ROWS = [
    # code, name, level, parent
    ("IN", "India", "country", None),
    ("IN-MH", "Maharashtra", "state", "IN"),
    ("IN-DL", "Delhi", "state", "IN"),
    ("IN-MH-MUM", "Mumbai", "city", "IN-MH"),
    ("IN-MH-PUN", "Pune", "city", "IN-MH"),
    ("IN-DL-NDL", "New Delhi", "city", "IN-DL"),
]
PRODUCT_ROWS = [
    # sku, name, category, launched_on, is_active
    ("FDS-GFB-1KG", "Dry Fruit Gift Box 1kg", "Packaged Foods", date(2019, 9, 1), True),
    ("IND-BRG-6205", "Ball Bearing 6205-2RS", "Industrial Components", date(2014, 5, 1), True),
    ("KIT-AFR-45", "Air Fryer 4.5L", "Kitchen Appliances", date(2026, 2, 8), True),
    ("COL-OLD-300", "Old Table Fan 300mm", "Cooling", date(2010, 1, 1), False),
]


def add_reference_data(session: Session) -> dict[str, dict[str, int]]:
    """A small catalog: 6 regions, 4 products, 3 customers. Returns code -> id maps."""
    ids: dict[str, dict[str, int]] = {"region": {}, "product": {}, "customer": {}}
    for code, name, level, parent in REGION_ROWS:
        region = Region(code=code, name=name, country="IN", level=level,
                        parent_region_id=ids["region"].get(parent))
        session.add(region)
        session.flush()
        ids["region"][code] = region.id
    for sku, name, category, launched_on, is_active in PRODUCT_ROWS:
        product = Product(sku=sku, name=name, category=category, subcategory="Test", unit_cost_minor=100,
                          unit_price_minor=1000, unit_of_measure="each", shelf_life_days=None,
                          is_active=is_active, launched_on=launched_on)
        session.add(product)
        session.flush()
        ids["product"][sku] = product.id
    for code, channel, city in [("C01", "distributor", "IN-MH-MUM"), ("C09", "retail", "IN-DL-NDL"),
                                ("C16", "ecommerce", "IN-MH-MUM")]:
        customer = Customer(code=code, name=f"Customer {code}", channel=channel, region_id=ids["region"][city])
        session.add(customer)
        session.flush()
        ids["customer"][code] = customer.id
    session.commit()
    return ids


def add_daily(session: Session, ids: dict, rows: list[tuple]) -> None:
    """rows: (date, sku, region_code, channel, units, revenue_minor[, source]).

    Rebuilds the weekly and monthly rollups for those dates too, as every real writer of
    daily_sales does, so analytics reads see the rows."""
    session.execute(sa.insert(DailySales), [
        dict(date=r[0], product_id=ids["product"][r[1]], region_id=ids["region"][r[2]], channel=r[3],
             units=r[4], revenue_minor=r[5], order_count=1 if len(r) < 7 or r[6] == "orders" else None,
             source=r[6] if len(r) > 6 else "orders")
        for r in rows
    ])
    if rows:
        rebuild_period_rollups(session, min(r[0] for r in rows), max(r[0] for r in rows))
    session.commit()


def add_order(session: Session, ids: dict, order_date: date, customer: str, region: str, channel: str,
              lines: list[tuple], currency: str = "INR") -> int:
    """lines: (sku, quantity, unit_price_minor, discount_minor). Returns the order id."""
    order = SalesOrder(order_date=order_date, customer_id=ids["customer"][customer],
                       region_id=ids["region"][region], channel=channel, currency=currency)
    session.add(order)
    session.flush()
    for sku, quantity, price, discount in lines:
        session.add(SalesOrderLine(sales_order_id=order.id, product_id=ids["product"][sku], quantity=quantity,
                                   unit_price_minor=price, discount_minor=discount, is_promotional=discount > 0))
    session.commit()
    return order.id


@pytest.fixture
def ids(db) -> dict[str, dict[str, int]]:
    return add_reference_data(db)


@pytest.fixture
def signed_in(client, db) -> TestClient:
    """The test client with a viewer's access token: sales data needs a signed-in user.
    The token is minted directly, so the password hash is never checked (and argon2's
    deliberate cost is not paid in every analytics test)."""
    user = User(email="viewer@example.com", full_name="Test viewer", role=UserRole.VIEWER,
                password_hash="not-used", is_active=True)
    db.add(user)
    db.commit()
    client.headers.update({"Authorization": f"Bearer {create_access_token(user, utcnow())}"})
    return client
