"""GET /api/health — is the API up, and can it reach the database?"""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import API_VERSION
from app.config import get_settings
from app.database.connection import get_db
from app.database.models import Park, WeatherHistory
from app.models.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="API and database status")
def health(db: Session = Depends(get_db)) -> HealthResponse:
    settings = get_settings()
    database = {"connected": False}
    try:
        db.execute(text("SELECT 1"))
        database = {
            "connected": True,
            "dialect": db.get_bind().dialect.name,  # 'sqlite' or 'postgresql'
            "park_count": db.scalar(select(func.count()).select_from(Park)),
            "weather_rows": db.scalar(select(func.count()).select_from(WeatherHistory)),
        }
    except SQLAlchemyError:
        pass  # report connected=False rather than crashing the health check

    return HealthResponse(
        status="ok" if database["connected"] else "degraded",
        api_version=API_VERSION,
        environment=settings.environment,
        database=database,
    )
