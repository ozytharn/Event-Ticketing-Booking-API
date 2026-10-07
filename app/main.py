import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes import auth, bookings, events, users
from app.core.config import settings
from app.core.errors import APIError

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Event discovery, organizer management, and seat booking API.",
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)
logger = logging.getLogger(__name__)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(events.router, prefix="/api/v1")
app.include_router(bookings.router, prefix="/api/v1")


@app.exception_handler(APIError)
async def api_error_handler(_: Request, exc: APIError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "Request validation failed",
                "details": jsonable_encoder(exc.errors()),
            }
        },
    )


@app.exception_handler(HTTPException)
async def http_error_handler(_: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "The request could not be completed"
    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
        content={
            "error": {
                "code": "http_error",
                "message": detail,
                "details": None if isinstance(exc.detail, str) else jsonable_encoder(exc.detail),
            }
        },
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled API error", exc_info=(type(exc), exc, exc.__traceback__))
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_server_error",
                "message": "An unexpected error occurred",
                "details": None,
            }
        },
    )


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}
