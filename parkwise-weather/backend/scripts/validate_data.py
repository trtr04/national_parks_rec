"""
Phase 2 data validation report for weather_history.

Usage, from the backend/ folder:
    python -m scripts.validate_data            # writes data/validation_report.md

Checks
    coverage      every park has a row for every day of 2015–2025 (the ETL's default years)
    gaps          runs of missing dates inside a park's history (LAG window function)
    nulls         missing values per column
    rules         the table's CHECK rules hold (non-negative values, temp_min <= temp_max)
    plausibility  values outside physically sensible ranges, flagged for a human to look at

Exit code 0 when no rule is broken and nothing is missing, 1 otherwise.
"""

import calendar
import datetime as dt
import sys

from sqlalchemy import extract, func, or_, select

from app.config import PROJECT_DIR
from app.database.connection import SessionLocal
from app.database.models import Park, WeatherHistory
from app.services.analytics_service import date_gaps
from scripts.load_weather_history import DEFAULT_END_YEAR, DEFAULT_START_YEAR

W = WeatherHistory
COLUMNS = ["temp_max", "temp_min", "precipitation", "rainfall", "snowfall", "wind_speed_max"]

# Outside these, a value is almost certainly an error (world records are about -68 / 57 °C).
PLAUSIBLE = {
    "temp_max": (-60.0, 58.0),
    "temp_min": (-70.0, 45.0),
    "precipitation": (0.0, 600.0),
    "snowfall": (0.0, 250.0),
    "wind_speed_max": (0.0, 250.0),
}

RULES = {
    "negative precipitation": W.precipitation < 0,
    "negative rainfall": W.rainfall < 0,
    "negative snowfall": W.snowfall < 0,
    "negative wind speed": W.wind_speed_max < 0,
    "temp_min above temp_max": W.temp_min > W.temp_max,
}


def build_report(db) -> tuple[str, bool]:
    lines: list[str] = []
    ok = True
    total = db.scalar(select(func.count()).select_from(W))
    parks = db.scalar(select(func.count()).select_from(Park))
    first, last = db.execute(select(func.min(W.date), func.max(W.date))).one()

    lines += [
        "# Weather data validation report",
        "",
        f"Generated {dt.datetime.now():%Y-%m-%d %H:%M}.",
        "",
        f"- Rows in weather_history: **{total:,}**",
        f"- Parks in parks table: **{parks}**",
        f"- Date range: {first} to {last}",
        "",
    ]

    # ---- coverage: stored days per park-year vs days in that year
    year = extract("year", W.date)
    per_year = db.execute(
        select(W.park_code, year.label("year"), func.count().label("n")).group_by(W.park_code, year)
    ).all()
    incomplete = [
        (r.park_code, int(r.year), r.n)
        for r in per_year
        if r.n < (366 if calendar.isleap(int(r.year)) else 365)
    ]
    years_by_park: dict[str, int] = {}
    for r in per_year:
        years_by_park[r.park_code] = years_by_park.get(r.park_code, 0) + 1
    all_codes = list(db.scalars(select(Park.park_code).order_by(Park.park_code)))
    no_data = [c for c in all_codes if c not in years_by_park]

    lines += ["## Coverage", ""]
    lines.append(f"- Parks with any weather data: {len(years_by_park)} of {len(all_codes)}")
    if years_by_park:
        counts = sorted(set(years_by_park.values()))
        lines.append(f"- Years stored per park: {', '.join(map(str, counts))}")
    if no_data:
        ok = False
        lines.append(f"- **No data yet:** {', '.join(no_data)}")
    stored = {(r.park_code, int(r.year)) for r in per_year}
    missing_years = [
        (code, year) for year in range(DEFAULT_START_YEAR, DEFAULT_END_YEAR + 1)
        for code in all_codes if (code, year) not in stored
    ]
    if missing_years:
        ok = False
        by_year: dict[int, list[str]] = {}
        for code, year in missing_years:
            by_year.setdefault(year, []).append(code)
        lines.append(f"- **Park-years not loaded yet ({len(missing_years)}):** "
                     + "; ".join(f"{year}: {'all parks' if len(codes) == len(all_codes) else ', '.join(codes)}"
                                 for year, codes in sorted(by_year.items()))
                     + ". Run `python -m scripts.load_weather_history` to fill them.")
    if incomplete:
        ok = False
        lines.append(f"- **Incomplete park-years ({len(incomplete)}):** "
                     + ", ".join(f"{c} {y} ({n} days)" for c, y, n in incomplete[:30]))
    else:
        lines.append("- Every stored park-year is complete.")
    lines.append("")

    # ---- gaps
    gaps = date_gaps(db)
    lines += ["## Gaps inside each park's history", ""]
    if gaps:
        lines.append("Gaps are expected while the ETL is still running (it loads newest years first).")
        lines.append("")
        lines.append("| Park | After | Before | Missing days |")
        lines.append("| --- | --- | --- | --- |")
        lines += [f"| {g['park_code']} | {g['after']} | {g['before']} | {g['missing_days']} |" for g in gaps[:50]]
        if len(gaps) > 50:
            lines.append(f"| … | | | {len(gaps) - 50} more |")
    else:
        lines.append("No gaps: every park's stored days are consecutive.")
    lines.append("")

    # ---- nulls
    lines += ["## Missing values", "", "| Column | NULL rows | Share |", "| --- | --- | --- |"]
    for col in COLUMNS:
        n = db.scalar(select(func.count()).select_from(W).where(getattr(W, col).is_(None)))
        lines.append(f"| {col} | {n:,} | {n / total:.2%} |" if total else f"| {col} | 0 | – |")
    lines.append("")

    # ---- rules
    lines += ["## Rule checks (must be zero)", "", "| Rule | Violations |", "| --- | --- |"]
    for name, condition in RULES.items():
        n = db.scalar(select(func.count()).select_from(W).where(condition))
        ok &= n == 0
        lines.append(f"| {name} | {n} |")
    lines.append("")

    # ---- plausibility
    lines += ["## Plausibility (flagged for review, not errors)", "", "| Column | Range | Outside |", "| --- | --- | --- |"]
    for col, (lo, hi) in PLAUSIBLE.items():
        c = getattr(W, col)
        n = db.scalar(select(func.count()).select_from(W).where(or_(c < lo, c > hi)))
        lines.append(f"| {col} | {lo} to {hi} | {n} |")
    lines.append("")

    lines.append(f"**Result: {'PASS' if ok else 'ATTENTION NEEDED'}**")
    return "\n".join(lines) + "\n", ok


def main() -> int:
    with SessionLocal() as db:
        report, ok = build_report(db)
    path = PROJECT_DIR / "data" / "validation_report.md"
    path.write_text(report, encoding="utf-8")
    print(report)
    print(f"Written to {path}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
