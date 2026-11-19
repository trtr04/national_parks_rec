# Weather data validation report

Generated 2026-11-01 15:36.

- Rows in weather_history: **253,134**
- Parks in parks table: **63**
- Date range: 2015-01-01 to 2025-12-31

## Coverage

- Parks with any weather data: 63 of 63
- Years stored per park: 11
- Every stored park-year is complete.

## Gaps inside each park's history

No gaps: every park's stored days are consecutive.

## Missing values

| Column | NULL rows | Share |
| --- | --- | --- |
| temp_max | 0 | 0.00% |
| temp_min | 0 | 0.00% |
| precipitation | 0 | 0.00% |
| rainfall | 0 | 0.00% |
| snowfall | 0 | 0.00% |
| wind_speed_max | 0 | 0.00% |

## Rule checks (must be zero)

| Rule | Violations |
| --- | --- |
| negative precipitation | 0 |
| negative rainfall | 0 |
| negative snowfall | 0 |
| negative wind speed | 0 |
| temp_min above temp_max | 0 |

## Plausibility (flagged for review, not errors)

| Column | Range | Outside |
| --- | --- | --- |
| temp_max | -60.0 to 58.0 | 0 |
| temp_min | -70.0 to 45.0 | 0 |
| precipitation | 0.0 to 600.0 | 0 |
| snowfall | 0.0 to 250.0 | 0 |
| wind_speed_max | 0.0 to 250.0 | 0 |

**Result: PASS**
