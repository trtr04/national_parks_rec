"""Park recommendation endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.schemas import ErrorResponse, ParkRecommendRequest
from app.services import park_recommender as rec
from app.services.errors import InvalidRequestError

router = APIRouter(prefix="/recommend", tags=["recommend"])


@router.get("/options", summary="Choices the park recommender understands")
def recommend_options():
    """Starting cities, temperature bands, scenery, wildlife and amenity keys, with labels."""
    return rec.options()


def _check(values: list[str], allowed: dict, name: str) -> tuple[str, ...]:
    unknown = [v for v in values if v not in allowed]
    if unknown:
        raise InvalidRequestError(f"Unknown {name}: {', '.join(unknown)}.", {"allowed": list(allowed)})
    return tuple(dict.fromkeys(values))  # drop duplicates, keep order


@router.post(
    "/parks",
    responses={400: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    summary="Recommend national parks for a month and set of preferences",
)
def recommend_parks(body: ParkRecommendRequest, db: Session = Depends(get_db)):
    """
    Filters out parks that are too far, lack a must-have amenity or don't offer the
    activity, then ranks the rest by weather for the month plus any temperature, scenery,
    wildlife and distance preferences. Parks whose weather that month is Poor are left out
    unless `include_poor_weather` is true. Each result explains why it matched and warns
    about access or seasonal limits; `excluded` names each other park and why it was left
    out; `nearest_beyond_limit` is the closest park the distance limit removed.
    """
    if body.origin is not None and body.origin not in rec.START_CITIES:
        raise InvalidRequestError(f"Unknown starting city: {body.origin}.", {"allowed": list(rec.START_CITIES)})
    if body.temperature is not None and body.temperature not in rec.TEMPERATURE_BANDS:
        raise InvalidRequestError(f"Unknown temperature: {body.temperature}.", {"allowed": list(rec.TEMPERATURE_BANDS)})
    if body.max_miles is not None and body.origin is None:
        raise InvalidRequestError("max_miles needs an origin city.")
    prefs = rec.ParkPreferences(
        month=body.month,
        activity=body.activity,
        origin=body.origin,
        max_miles=body.max_miles,
        temperature=body.temperature,
        scenery=_check(body.scenery, rec.SCENERY, "scenery"),
        wildlife=_check(body.wildlife, rec.WILDLIFE, "wildlife"),
        amenities=_check(body.amenities, rec.AMENITIES, "amenities"),
        include_poor_weather=body.include_poor_weather,
        limit=body.limit,
    )
    return rec.recommend_parks(db, prefs)
