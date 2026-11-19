"""Park endpoints."""

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.models.schemas import ErrorResponse, ParkDetail, ParkListResponse
from app.services import park_service

router = APIRouter(prefix="/parks", tags=["parks"])

PARK_CODE = Path(min_length=2, max_length=10, examples=["yose"], description="NPS park code")


@router.get("", response_model=ParkListResponse, summary="List national parks")
def list_parks(
    search: str | None = Query(None, max_length=100, description="Filter by name, code or state"),
    db: Session = Depends(get_db),
) -> ParkListResponse:
    parks = park_service.list_parks(db, search)
    return ParkListResponse(count=len(parks), parks=parks)


@router.get(
    "/{park_code}",
    response_model=ParkDetail,
    responses={404: {"model": ErrorResponse}},
    summary="Get one park",
)
def get_park(park_code: str = PARK_CODE, db: Session = Depends(get_db)) -> ParkDetail:
    return ParkDetail.model_validate(park_service.get_park(db, park_code))
