from fastapi import APIRouter

from app.api.v1 import analytics, auth, backtest, forecasts, imports, market, products, regions, sales

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(products.router)
api_router.include_router(regions.router)
api_router.include_router(sales.router)
api_router.include_router(imports.router)
api_router.include_router(analytics.router)
api_router.include_router(forecasts.router)
api_router.include_router(backtest.router)
api_router.include_router(market.router)
