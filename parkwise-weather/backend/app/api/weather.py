"""Weather endpoints: history, seasonal climate, prediction and comparison."""

import datetime as dt

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.schemas import (
    Activity,
    CompareRequest,
    ErrorResponse,
    SeasonalResponse,
    WeatherHistoryResponse,
)
from app.services import weather_service

router = APIRouter(prefix="/weather", tags=["weather"])

PARK_CODE = Path(min_length=2, max_length=10, examples=["yose"], description="NPS park code")
ERRORS = {400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}
MODEL_ERRORS = {**ERRORS, 503: {"model": ErrorResponse}}


@router.get(
    "/history/{park_code}",
    response_model=WeatherHistoryResponse,
    responses=ERRORS,
    summary="Daily weather history for one park",
)
def weather_history(
    park_code: str = PARK_CODE,
    start_date: dt.date | None = Query(None, description="YYYY-MM-DD, inclusive"),
    end_date: dt.date | None = Query(None, description="YYYY-MM-DD, inclusive"),
    db: Session = Depends(get_db),
):
    """Defaults to the most recent 365 stored days. Returns count 0 if no history is loaded yet."""
    return weather_service.get_history(db, park_code, start_date, end_date)


@router.get(
    "/seasonal/{park_code}",
    response_model=SeasonalResponse,
    responses=ERRORS,
    summary="Monthly climate summary for one park",
)
def weather_seasonal(park_code: str = PARK_CODE, db: Session = Depends(get_db)):
    """Average highs/lows, average precipitation and wet-day frequency for each calendar month."""
    return weather_service.get_seasonal(db, park_code)


@router.get(
    "/predict",
    responses=MODEL_ERRORS,
    summary="Weather outlook for a park on a travel date",
)
def weather_predict(
    park_code: str = Query(..., min_length=2, max_length=10, examples=["yose"]),
    date: dt.date = Query(..., description="Travel date, YYYY-MM-DD", examples=["2027-04-15"]),
    activity: Activity = Query(Activity.hiking),
    db: Session = Depends(get_db),
):
    """
    Today through today + 15 days: the live Open-Meteo forecast. Later dates: a climate
    estimate from the trained model, with 80% ranges. Both include a 0–100 suitability
    score for the activity. 503 `model_not_ready` means the model hasn't been trained yet.
    """
    return weather_service.predict_weather(db, park_code, date, activity)


@router.get(
    "/best-time/{park_code}",
    responses=MODEL_ERRORS,
    summary="Month-by-month climate outlook and suitability for one park",
)
def weather_best_time(park_code: str = PARK_CODE, db: Session = Depends(get_db)):
    """
    For each month: typical high and low, chance of a wet or snowy day, typical wind,
    the 0–100 suitability score for every activity, and how much the month has varied
    between years. Also the three best months per activity.
    """
    return weather_service.best_time(db, park_code)


@router.post(
    "/compare",
    responses=MODEL_ERRORS,
    summary="Compare 2–5 parks for the same travel date",
)
def weather_compare(body: CompareRequest, db: Session = Depends(get_db)):
    """The same outlook as /predict for each park, ranked best suitability first."""
    return weather_service.compare_parks(db, body.park_codes, body.date, body.activity)
