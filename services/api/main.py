"""
FastAPI 진입점.
실행: uvicorn services.api.main:app --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException as FastAPIHTTPException, RequestValidationError
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


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """쿼리 파라미터 검증 실패(422) 등도 공통 에러 포맷을 따르도록 통일.

    FastAPI 기본 포맷({"detail": [...]})은 API_SPEC.md의 공통 에러 형식과
    다르기 때문에, HTTPException 핸들러와 별개로 하나 더 등록해야 한다.
    """
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(p) for p in first.get("loc", []) if p != "query")
    message = f"{field}: {first.get('msg', 'invalid request')}" if field else first.get("msg", "invalid request")
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "VALIDATION_ERROR", "message": message}},
    )


@app.get("/health")
def health():
    return {"status": "ok"}