"""Shared fixtures.

The suite runs on a temporary SQLite file. If TEST_DATABASE_URL points at PostgreSQL
the whole suite runs there instead, and the cross-dialect tests compare the two.
The PostgreSQL database must be disposable: every table in it is dropped first.
"""

import os
from collections.abc import Iterator
from datetime import date

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.config import BACKEND_DIR
from app.db import create_db_engine, get_db
from app.main import app
from app.models import (
    Customer,
    DailySales,
    Product,
    Region,
    SalesOrder,
    SalesOrderLine,
)
from app.seed.generate import wipe_all

PG_URL = os.environ.get("TEST_DATABASE_URL", "")
HAS_PG = PG_URL.startswith("postgresql")
requires_pg = pytest.mark.skipif(not HAS_PG, reason="TEST_DATABASE_URL is not set to a PostgreSQL database")


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
        pytest.skip("TEST_DATABASE_URL is not set to a PostgreSQL database")
    engine = create_db_engine(PG_URL)
    with engine.begin() as connection:
        connection.execute(sa.text("DROP SCHEMA public CASCADE"))
        connection.execute(sa.text("CREATE SCHEMA public"))
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
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


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
    """rows: (date, sku, region_code, channel, units, revenue_minor[, source])."""
    session.execute(sa.insert(DailySales), [
        dict(date=r[0], product_id=ids["product"][r[1]], region_id=ids["region"][r[2]], channel=r[3],
             units=r[4], revenue_minor=r[5], order_count=1 if len(r) < 7 or r[6] == "orders" else None,
             source=r[6] if len(r) > 6 else "orders")
        for r in rows
    ])
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
