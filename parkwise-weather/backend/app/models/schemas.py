"""
Pydantic schemas: the exact JSON shapes the API accepts and returns.

FastAPI uses these to
  * validate incoming query params / bodies (bad input -> 422 with a clear message),
  * serialize responses (only declared fields go out),
  * generate the interactive docs at /docs, which teammates can use as the contract.
"""

import datetime as dt
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

# Units used in every weather payload. Sent with responses so clients never have to guess.
WEATHER_UNITS: dict[str, str] = {
    "temperature": "celsius",
    "precipitation": "mm",
    "rainfall": "mm",
    "snowfall": "cm",
    "wind_speed": "km/h",
}


class Activity(str, Enum):
    """Activities the suitability score supports (see app/services/suitability.py)."""

    hiking = "hiking"
    camping = "camping"
    sightseeing = "sightseeing"
    wildlife = "wildlife"


# ---------- Errors ----------

class ErrorBody(BaseModel):
    code: str = Field(examples=["not_found"])
    message: str = Field(examples=["No park with code 'xyz'."])
    details: object | None = None


class ErrorResponse(BaseModel):
    """Every error from this API has this shape: {"error": {"code", "message", "details"}}."""

    error: ErrorBody


# ---------- Health ----------

class DatabaseStatus(BaseModel):
    connected: bool
    dialect: str | None = None
    park_count: int | None = None
    weather_rows: int | None = None


class HealthResponse(BaseModel):
    status: str = Field(examples=["ok"])
    api_version: str
    environment: str
    database: DatabaseStatus


# ---------- Parks ----------

class ParkSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # lets us build this straight from an ORM row

    park_code: str
    park_name: str
    state: str
    latitude: float
    longitude: float


class ParkDetail(ParkSummary):
    description: str | None = None
    weather_location_note: str | None = None
    data_source: str


class ParkListResponse(BaseModel):
    count: int
    parks: list[ParkSummary]


# ---------- Weather history ----------

class WeatherDay(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: dt.date
    temp_max: float | None = None
    temp_min: float | None = None
    precipitation: float | None = None
    rainfall: float | None = None
    snowfall: float | None = None
    wind_speed_max: float | None = None


class WeatherHistoryResponse(BaseModel):
    park_code: str
    start_date: dt.date | None
    end_date: dt.date | None
    units: dict[str, str] = WEATHER_UNITS
    count: int
    observations: list[WeatherDay]


class MonthlyClimate(BaseModel):
    month: int = Field(ge=1, le=12)
    avg_temp_max: float | None
    avg_temp_min: float | None
    avg_precipitation: float | None
    wet_day_frequency: float | None = Field(
        description="Share of days with at least 1 mm of precipitation (0–1)."
    )
    days_observed: int


class SeasonalResponse(BaseModel):
    park_code: str
    wet_day_threshold_mm: float
    first_date: dt.date | None
    last_date: dt.date | None
    units: dict[str, str] = WEATHER_UNITS
    months: list[MonthlyClimate]


# ---------- Comparison request ----------

class CompareRequest(BaseModel):
    park_codes: list[str] = Field(min_length=2, max_length=5, examples=[["yose", "zion"]])
    date: dt.date
    activity: Activity = Activity.hiking


# ---------- Park recommendation request ----------

class ParkRecommendRequest(BaseModel):
    """What the traveller wants. Every preference except month is optional."""

    month: int = Field(ge=1, le=12, examples=[7], description="Travel month, 1–12")
    activity: Activity = Activity.hiking
    origin: str | None = Field(None, examples=["Seattle, WA"], description="A city from /recommend/options")
    max_miles: float | None = Field(None, gt=0, le=10000, description="Straight-line miles from origin")
    temperature: str | None = Field(None, examples=["mild"], description="cool, mild or warm")
    scenery: list[str] = Field(default_factory=list, max_length=13, examples=[["mountains", "lakes_rivers"]])
    wildlife: list[str] = Field(default_factory=list, max_length=10, examples=[["elk"]])
    amenities: list[str] = Field(default_factory=list, max_length=7, examples=[["campground"]])
    include_poor_weather: bool = Field(False, description="Also rank parks whose weather that month is Poor")
    limit: int = Field(6, ge=1, le=63)
