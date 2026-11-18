"""
Insert-or-update ("upsert") that works on both SQLite and PostgreSQL.

Both databases support `INSERT ... ON CONFLICT (pk) DO UPDATE`, but SQLAlchemy
exposes it through dialect-specific insert() functions. This picks the right one,
so the ETL scripts can be re-run safely: existing rows are updated, never duplicated.
"""

from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session


def upsert_rows(db: Session, model, rows: list[dict], conflict_columns: list[str]) -> int:
    """Upsert `rows` into `model`'s table. Returns the number of rows sent."""
    if not rows:
        return 0

    dialect = db.get_bind().dialect.name
    insert = postgresql.insert if dialect == "postgresql" else sqlite.insert
    table = model.__table__

    stmt = insert(table).values(rows)
    update_columns = {
        col.name: stmt.excluded[col.name]
        for col in table.columns
        if col.name not in conflict_columns and col.name in rows[0]
    }
    stmt = stmt.on_conflict_do_update(index_elements=conflict_columns, set_=update_columns)
    db.execute(stmt)
    return len(rows)
