from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db import get_db
from app.models import Product
from app.schemas import ErrorResponse, Page, ProductRead
from app.schemas.analytics import ProductDetail
from app.services.analytics.events import product_events
from app.services.errors import NotFoundError
from app.services.sales_source import Window, data_bounds

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=Page[ProductRead])
def list_products(
    db: Annotated[Session, Depends(get_db)],
    category: str | None = None,
    is_active: bool | None = None,
    q: Annotated[str | None, Query(min_length=1, max_length=64, description="Substring of sku or name")] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ProductRead]:
    stmt = select(Product)
    if category is not None:
        stmt = stmt.where(Product.category == category)
    if is_active is not None:
        stmt = stmt.where(Product.is_active == is_active)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(or_(Product.sku.ilike(pattern), Product.name.ilike(pattern)))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    products = db.scalars(stmt.order_by(Product.sku).limit(limit).offset(offset)).all()
    return Page[ProductRead](
        items=[ProductRead.model_validate(p) for p in products], total=total, limit=limit, offset=offset
    )


@router.get(
    "/{sku}",
    response_model=ProductDetail,
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse, "description": "Not signed in"},
               404: {"model": ErrorResponse, "description": "Unknown sku"}},
)
def product_detail(
    sku: str,
    db: Annotated[Session, Depends(get_db)],
    date_from: Annotated[date | None, Query(description="Events from; default the first day with data")] = None,
    date_to: Annotated[date | None, Query(description="Events to; default 26 weeks after the last day with "
                                                      "data, so upcoming events show too")] = None,
) -> ProductDetail:
    """Master data plus the calendar events touching this product in range: its
    promotions, holidays and festivals, and shutdowns at plants that make it."""
    product = db.scalar(select(Product).where(Product.sku == sku))
    if product is None:
        raise NotFoundError(f"Unknown sku: {sku}")
    bounds = data_bounds(db)
    events_from = date_from or (bounds[0] if bounds else None)
    events_to = date_to or (bounds[1] + timedelta(weeks=26) if bounds else None)
    if events_from and events_to and events_from > events_to:
        raise HTTPException(status_code=422, detail="date_from must be on or before date_to")
    events = product_events(db, product, Window(events_from, events_to)) if events_from and events_to else []
    return ProductDetail(**ProductRead.model_validate(product).model_dump(), events=events,
                         events_from=events_from, events_to=events_to)
