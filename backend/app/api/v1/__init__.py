from fastapi import APIRouter

from app.api.v1 import analytics, auth, imports, products, regions, sales

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(products.router)
api_router.include_router(regions.router)
api_router.include_router(sales.router)
api_router.include_router(imports.router)
api_router.include_router(analytics.router)
