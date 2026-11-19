"""
Create all database tables (idempotent — existing tables are left alone).

Usage, from the backend/ folder:
    python -m scripts.init_db

Uses DATABASE_URL from your .env (SQLite by default, Neon/PostgreSQL in production).
For PostgreSQL you can alternatively run the raw SQL:
    psql "$DATABASE_URL" -f app/database/schema.sql
"""

from sqlalchemy import inspect

from app.database.connection import engine, init_db


def main() -> None:
    init_db()
    tables = sorted(inspect(engine).get_table_names())
    print(f"Database ready ({engine.dialect.name}): {', '.join(tables)}")


if __name__ == "__main__":
    main()
