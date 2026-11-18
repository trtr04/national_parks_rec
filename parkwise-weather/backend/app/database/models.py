"""
ORM table definitions. These mirror app/database/schema.sql exactly.

Units (Open-Meteo defaults, stored as-is; the frontend converts for display):
    temperatures   °C
    precipitation  mm   (rain + showers + snowfall water equivalent)
    rainfall       mm
    snowfall       cm
    wind_speed_max km/h

Storing metric and converting at display time avoids rounding drift and keeps
the database consistent with the source API.
"""

import datetime as dt

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.connection import Base


class Park(Base):
    """One row per National Park. Filled from the NPS API in Phase 2."""

    __tablename__ = "parks"

    park_code: Mapped[str] = mapped_column(String(10), primary_key=True)  # NPS code, e.g. "yose"
    park_name: Mapped[str] = mapped_column(String(200), nullable=False)
    state: Mapped[str] = mapped_column(String(50), nullable=False)  # may list several, e.g. "CA,NV"
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # Large parks span huge areas and elevations; this says which point the weather describes.
    weather_location_note: Mapped[str | None] = mapped_column(Text)
    data_source: Mapped[str] = mapped_column(String(30), nullable=False, default="nps_api")
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_parks_latitude"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_parks_longitude"),
    )


class WeatherHistory(Base):
    """One row per park per day of observed (reanalysis) weather from Open-Meteo."""

    __tablename__ = "weather_history"

    park_code: Mapped[str] = mapped_column(
        String(10), ForeignKey("parks.park_code", ondelete="CASCADE"), primary_key=True
    )
    # Composite primary key (park_code, date) makes duplicate days impossible,
    # which is what lets the Phase 2 ETL re-run safely.
    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    temp_max: Mapped[float | None] = mapped_column(Float)
    temp_min: Mapped[float | None] = mapped_column(Float)
    precipitation: Mapped[float | None] = mapped_column(Float)
    rainfall: Mapped[float | None] = mapped_column(Float)
    snowfall: Mapped[float | None] = mapped_column(Float)
    wind_speed_max: Mapped[float | None] = mapped_column(Float)

    __table_args__ = (
        CheckConstraint("precipitation IS NULL OR precipitation >= 0", name="ck_wh_precip_nonneg"),
        CheckConstraint("rainfall IS NULL OR rainfall >= 0", name="ck_wh_rain_nonneg"),
        CheckConstraint("snowfall IS NULL OR snowfall >= 0", name="ck_wh_snow_nonneg"),
        CheckConstraint("wind_speed_max IS NULL OR wind_speed_max >= 0", name="ck_wh_wind_nonneg"),
        CheckConstraint(
            "temp_min IS NULL OR temp_max IS NULL OR temp_min <= temp_max",
            name="ck_wh_temp_order",
        ),
        # The PK already indexes (park_code, date). This one speeds up
        # cross-park queries filtered by date ("all parks in July 2024").
        Index("ix_weather_history_date", "date"),
    )


class WeatherPrediction(Base):
    """Every prediction the API serves gets logged here (Phase 3+), for auditing and evaluation."""

    __tablename__ = "weather_predictions"

    prediction_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    park_code: Mapped[str] = mapped_column(
        String(10), ForeignKey("parks.park_code", ondelete="CASCADE"), nullable=False
    )
    target_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    prediction_generated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # 'forecast' = real short-range weather forecast; 'climate_estimate' = historical-pattern estimate.
    prediction_type: Mapped[str] = mapped_column(String(20), nullable=False)
    model_name: Mapped[str] = mapped_column(String(60), nullable=False)
    activity: Mapped[str | None] = mapped_column(String(30))
    predicted_temp_max: Mapped[float | None] = mapped_column(Float)
    predicted_temp_min: Mapped[float | None] = mapped_column(Float)
    precipitation_probability: Mapped[float | None] = mapped_column(Float)  # 0.0–1.0
    weather_suitability_score: Mapped[float | None] = mapped_column(Float)  # 0–100

    __table_args__ = (
        CheckConstraint(
            "prediction_type IN ('forecast', 'climate_estimate')", name="ck_wp_prediction_type"
        ),
        CheckConstraint(
            "precipitation_probability IS NULL OR precipitation_probability BETWEEN 0 AND 1",
            name="ck_wp_precip_prob_range",
        ),
        CheckConstraint(
            "weather_suitability_score IS NULL OR weather_suitability_score BETWEEN 0 AND 100",
            name="ck_wp_score_range",
        ),
        Index("ix_weather_predictions_park_target", "park_code", "target_date"),
    )
