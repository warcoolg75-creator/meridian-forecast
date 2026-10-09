from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Product
from app.schemas import Page, ProductRead

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
