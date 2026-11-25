"""Apply db/migrations/*.sql in order. Requires psycopg and DATABASE_URL."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = sorted((ROOT / "db" / "migrations").glob("*.sql"))


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("Set DATABASE_URL", file=sys.stderr)
        return 1
    for path in MIGRATIONS:
        sql = path.read_text(encoding="utf-8")
        print(f"Applying {path.name}...")
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute(sql)
        print(f"OK {path.name}")
    print("Migrations done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())