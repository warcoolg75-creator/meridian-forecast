from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.v1 import api_router
from app.schemas import ErrorResponse
from app.services.errors import NotFoundError

app = FastAPI(title="Meridian Forecast API", version="0.1.0")
app.include_router(api_router, prefix="/api/v1")


@app.exception_handler(NotFoundError)
def _not_found(_request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content=ErrorResponse(detail=str(exc)).model_dump())
