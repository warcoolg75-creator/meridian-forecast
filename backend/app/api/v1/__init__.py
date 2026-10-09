from fastapi import APIRouter

from app.api.v1 import imports, products, regions, sales

api_router = APIRouter()
api_router.include_router(products.router)
api_router.include_router(regions.router)
api_router.include_router(sales.router)
api_router.include_router(imports.router)
