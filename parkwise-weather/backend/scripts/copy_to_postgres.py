"""
Copy parks and weather history from one database to another, e.g. local SQLite -> Neon.

Re-downloading eleven years of weather from Open-Meteo would take hours and hit the free
rate limits; copying what's already stored locally takes about a minute.

Usage, from the backend/ folder:
    python -m scripts.copy_to_postgres --target "postgresql://USER:PASSWORD@HOST/DB?sslmode=require"

    --source   database to read (default: DATABASE_URL from .env, normally local SQLite)
    --target   database to write (required). Tables are created if missing.

Rows are upserted, so the copy can be re-run safely; existing rows are updated, never
duplicated. weather_predictions is not copied: it is a log of answers served locally.
"""

import argparse
import logging
import sys

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database.connection import Base, build_engine, normalize_database_url
from app.database.models import Park, WeatherHistory
from app.database.upsert import upsert_rows

logger = logging.getLogger("parkwise.copy")

# 5,000 rows x 8 columns stays well under PostgreSQL's 65,535 parameters per statement.
BATCH_ROWS = 5000
TABLES = [(Park, ["park_code"]), (WeatherHistory, ["park_code", "date"])]


def redact(url: str) -> str:
    """Hide the password when a URL is printed."""
    if "@" not in url or "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    credentials, host = rest.rsplit("@", 1)
    user = credentials.split(":", 1)[0]
    return f"{scheme}://{user}:***@{host}"


def copy_table(source: Session, target: Session, model, conflict_columns: list[str]) -> int:
    columns = [c.name for c in model.__table__.columns]
    total = source.scalar(select(func.count()).select_from(model))
    copied = 0
    result = source.execute(select(model.__table__).order_by(*model.__table__.primary_key.columns))
    while batch := result.fetchmany(BATCH_ROWS):
        upsert_rows(target, model, [dict(zip(columns, row)) for row in batch], conflict_columns)
        target.commit()
        copied += len(batch)
        logger.info("%s: %d / %d", model.__tablename__, copied, total)
    return copied


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", default=get_settings().database_url)
    parser.add_argument("--target", required=True)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if normalize_database_url(args.source) == normalize_database_url(args.target):
        logger.error("Source and target are the same database.")
        return 1

    source_engine, target_engine = build_engine(args.source), build_engine(args.target)
    logger.info("Copying %s -> %s", redact(args.source), redact(args.target))
    Base.metadata.create_all(bind=target_engine)

    with Session(source_engine) as source, Session(target_engine) as target:
        for model, keys in TABLES:
            copied = copy_table(source, target, model, keys)
            stored = target.scalar(select(func.count()).select_from(model))
            logger.info("%s: copied %d rows; target now has %d", model.__tablename__, copied, stored)
    return 0


if __name__ == "__main__":
    sys.exit(main())
