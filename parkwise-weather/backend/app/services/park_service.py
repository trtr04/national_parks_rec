"""Park lookups."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Park
from app.services.errors import NotFoundError


def list_parks(db: Session, search: str | None = None) -> list[Park]:
    """All parks, alphabetical. Optional case-insensitive search on name, code or state."""
    stmt = select(Park).order_by(Park.park_name)
    if search:
        pattern = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            Park.park_name.ilike(pattern) | Park.park_code.ilike(pattern) | Park.state.ilike(pattern)
        )
    return list(db.scalars(stmt))


def get_park(db: Session, park_code: str) -> Park:
    """One park by NPS code (case-insensitive). Raises NotFoundError if missing."""
    park = db.get(Park, park_code.strip().lower())
    if park is None:
        raise NotFoundError(f"No park with code '{park_code}'.")
    return park
