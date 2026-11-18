"""
Analytical SQL over weather_history: CTEs and window functions.

Written with SQLAlchemy Core so the same code runs on SQLite (local) and PostgreSQL
(Neon). Each function's docstring shows the equivalent PostgreSQL.

    driest_parks_for_month()   CTE + RANK()                 which parks stay driest in a month
    annual_trend()             CTE + LAG() + rolling AVG()   year-by-year change for one park
    date_gaps()                LAG() over each park's days   missing days, for the validation report
"""

from sqlalchemy import Date, case, extract, func, literal, select
from sqlalchemy.orm import Session

from app.database.models import Park, WeatherHistory
from app.services.park_service import get_park
from app.services.weather_service import WET_DAY_THRESHOLD_MM


def _wet_day():
    """1.0 for a wet day, 0.0 for a dry day, NULL when precipitation is unknown."""
    return case(
        (WeatherHistory.precipitation.is_(None), None),
        (WeatherHistory.precipitation >= WET_DAY_THRESHOLD_MM, 1.0),
        else_=0.0,
    )


def _days_between(db: Session, later, earlier):
    """Whole days between two DATE expressions, for either database."""
    if db.get_bind().dialect.name == "postgresql":
        return later - earlier
    return func.julianday(later) - func.julianday(earlier)


def driest_parks_for_month(db: Session, month: int, limit: int = 10) -> list[dict]:
    """
    Parks ranked from driest to wettest for one calendar month.

        WITH monthly AS (
            SELECT park_code,
                   AVG(CASE WHEN precipitation >= 1.0 THEN 1.0 ELSE 0.0 END) AS wet_day_frequency,
                   AVG(temp_max) AS avg_temp_max,
                   COUNT(*)      AS days_observed
            FROM weather_history
            WHERE EXTRACT(MONTH FROM date) = :month
            GROUP BY park_code
        )
        SELECT m.*, p.park_name,
               RANK() OVER (ORDER BY wet_day_frequency) AS dryness_rank
        FROM monthly m JOIN parks p USING (park_code)
        ORDER BY dryness_rank
        LIMIT :limit;
    """
    monthly = (
        select(
            WeatherHistory.park_code,
            func.avg(_wet_day()).label("wet_day_frequency"),
            func.avg(WeatherHistory.temp_max).label("avg_temp_max"),
            func.count().label("days_observed"),
        )
        .where(extract("month", WeatherHistory.date) == month)
        .group_by(WeatherHistory.park_code)
        .cte("monthly")
    )
    stmt = (
        select(
            monthly.c.park_code,
            Park.park_name,
            monthly.c.wet_day_frequency,
            monthly.c.avg_temp_max,
            monthly.c.days_observed,
            func.rank().over(order_by=monthly.c.wet_day_frequency).label("dryness_rank"),
        )
        .join(Park, Park.park_code == monthly.c.park_code)
        .order_by("dryness_rank", monthly.c.park_code)
        .limit(limit)
    )
    return [
        {
            "rank": row.dryness_rank,
            "park_code": row.park_code,
            "park_name": row.park_name,
            "wet_day_frequency": round(float(row.wet_day_frequency), 3),
            "avg_temp_max": round(float(row.avg_temp_max), 2),
            "days_observed": row.days_observed,
        }
        for row in db.execute(stmt)
    ]


def annual_trend(db: Session, park_code: str) -> list[dict]:
    """
    One park's yearly averages, the change from the year before, and a 3-year rolling mean.

        WITH yearly AS (
            SELECT EXTRACT(YEAR FROM date) AS year,
                   AVG(temp_max) AS avg_temp_max, AVG(temp_min) AS avg_temp_min,
                   SUM(precipitation) AS total_precipitation, COUNT(*) AS days_observed
            FROM weather_history WHERE park_code = :park_code
            GROUP BY 1
        )
        SELECT *,
               avg_temp_max - LAG(avg_temp_max) OVER (ORDER BY year) AS temp_max_change,
               AVG(avg_temp_max) OVER (ORDER BY year ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)
                   AS temp_max_rolling_3yr
        FROM yearly ORDER BY year;
    """
    park = get_park(db, park_code)
    year = extract("year", WeatherHistory.date)
    yearly = (
        select(
            year.label("year"),
            func.avg(WeatherHistory.temp_max).label("avg_temp_max"),
            func.avg(WeatherHistory.temp_min).label("avg_temp_min"),
            func.sum(WeatherHistory.precipitation).label("total_precipitation"),
            func.count().label("days_observed"),
        )
        .where(WeatherHistory.park_code == park.park_code)
        .group_by(year)
        .cte("yearly")
    )
    by_year = {"order_by": yearly.c.year}
    stmt = select(
        yearly,
        (yearly.c.avg_temp_max - func.lag(yearly.c.avg_temp_max).over(**by_year)).label("temp_max_change"),
        func.avg(yearly.c.avg_temp_max).over(**by_year, rows=(-2, 0)).label("temp_max_rolling_3yr"),
    ).order_by(yearly.c.year)

    def r(value, digits=2):
        return None if value is None else round(float(value), digits)

    return [
        {
            "year": int(row.year),
            "avg_temp_max": r(row.avg_temp_max),
            "avg_temp_min": r(row.avg_temp_min),
            "total_precipitation": r(row.total_precipitation, 1),
            "days_observed": row.days_observed,
            "temp_max_change": r(row.temp_max_change),
            "temp_max_rolling_3yr": r(row.temp_max_rolling_3yr),
        }
        for row in db.execute(stmt)
    ]


def date_gaps(db: Session) -> list[dict]:
    """
    Every place where a park's stored days skip one or more dates.

        SELECT park_code, previous_date, date, date - previous_date - 1 AS missing_days
        FROM (
            SELECT park_code, date,
                   LAG(date) OVER (PARTITION BY park_code ORDER BY date) AS previous_date
            FROM weather_history
        ) d
        WHERE date - previous_date > 1;
    """
    ordered = select(
        WeatherHistory.park_code,
        WeatherHistory.date,
        func.lag(WeatherHistory.date, type_=Date)
        .over(partition_by=WeatherHistory.park_code, order_by=WeatherHistory.date)
        .label("previous_date"),
    ).subquery("d")
    gap = _days_between(db, ordered.c.date, ordered.c.previous_date)
    stmt = (
        select(ordered.c.park_code, ordered.c.previous_date, ordered.c.date, (gap - literal(1)).label("missing"))
        .where(gap > 1)
        .order_by(ordered.c.park_code, ordered.c.date)
    )
    return [
        {
            "park_code": row.park_code,
            "after": row.previous_date,
            "before": row.date,
            "missing_days": int(row.missing),
        }
        for row in db.execute(stmt)
    ]
