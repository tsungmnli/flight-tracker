"""
FastAPI 진입점.
실행: uvicorn services.api.main:app --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from fastapi.responses import JSONResponse

from services.api.routers import routes, itineraries, flights, market_context, admin

app = FastAPI(title="Flight Price Tracker API", version="1.0.0")

app.include_router(routes.router, prefix="/v1/routes", tags=["routes"])
app.include_router(itineraries.router, prefix="/v1/itineraries", tags=["itineraries"])
app.include_router(flights.router, prefix="/v1/flights", tags=["flights"])
app.include_router(market_context.router, prefix="/v1/market-context", tags=["market-context"])
app.include_router(admin.router, prefix="/v1/admin", tags=["admin"])


@app.exception_handler(FastAPIHTTPException)
async def http_exception_handler(request: Request, exc: FastAPIHTTPException):
    """API_SPEC.md 공통 에러 포맷: {"error": {"code": ..., "message": ...}}"""
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "HTTP_ERROR", "message": str(exc.detail)}},
    )


@app.get("/health")
def health():
    return {"status": "ok"}