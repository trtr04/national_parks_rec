"""
ParkWise Weather API — FastAPI entry point.

Run locally (from the backend/ folder):
    uvicorn app.main:app --reload --port 8000
Then open http://127.0.0.1:8000/docs for interactive API documentation.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import API_VERSION
from app.api import health, model_performance, parks, weather
from app.config import get_settings
from app.database.connection import init_db
from app.services.errors import ParkWiseError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("parkwise")
settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Create any missing tables on startup so a fresh clone "just works".
    init_db()
    logger.info("ParkWise Weather API %s started (%s)", API_VERSION, settings.environment)
    yield


app = FastAPI(
    title="ParkWise Weather API",
    version=API_VERSION,
    description=(
        "Weather forecasts, historical climate estimates and weather suitability scores "
        "for U.S. National Parks. Part of the ParkWise travel planner.\n\n"
        "All errors use the shape `{\"error\": {\"code\", \"message\", \"details\"}}`."
    ),
    lifespan=lifespan,
)

# CORS: browsers block a page on one origin (the React app) from calling an API on
# another origin (this server) unless the API explicitly allows it.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


# ---------- Consistent error responses ----------

def _error(status: int, code: str, message: str, details=None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details}},
    )


@app.exception_handler(ParkWiseError)
async def handle_parkwise_error(_request: Request, exc: ParkWiseError):
    return _error(exc.status_code, exc.code, exc.message, exc.details)


@app.exception_handler(RequestValidationError)
async def handle_validation_error(_request: Request, exc: RequestValidationError):
    # Turn Pydantic's error list into one readable sentence plus the raw details.
    problems = [
        f"{'.'.join(str(p) for p in err['loc'] if p not in ('query', 'body', 'path'))}: {err['msg']}"
        for err in exc.errors()
    ]
    details = [{"loc": list(err["loc"]), "msg": err["msg"]} for err in exc.errors()]
    return _error(422, "validation_error", "; ".join(problems), details)


@app.exception_handler(StarletteHTTPException)
async def handle_http_error(_request: Request, exc: StarletteHTTPException):
    code = "not_found" if exc.status_code == 404 else "http_error"
    return _error(exc.status_code, code, str(exc.detail))


@app.exception_handler(Exception)
async def handle_unexpected_error(_request: Request, exc: Exception):
    logger.exception("Unhandled error")
    message = "Internal server error." if settings.is_production else f"{type(exc).__name__}: {exc}"
    return _error(500, "internal_error", message)


# ---------- Routes ----------

app.include_router(health.router, prefix="/api")
app.include_router(parks.router, prefix="/api")
app.include_router(weather.router, prefix="/api")
app.include_router(model_performance.router, prefix="/api")


@app.get("/", include_in_schema=False)
def root():
    return {"name": "ParkWise Weather API", "version": API_VERSION, "docs": "/docs", "health": "/api/health"}
