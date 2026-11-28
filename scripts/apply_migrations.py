"""Apply db/migrations/*.sql in order. Loads DATABASE_URL from repo .env when unset."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = sorted((ROOT / "db" / "migrations").glob("*.sql"))


def _strip_quotes(value: str) -> str:
    return value.strip().strip('"').strip("'")


def resolve_database_url() -> str | None:
    raw = os.environ.get("DATABASE_URL")
    if raw:
        return _strip_quotes(raw)
    for rel in (".env", "apps/web/.env.local"):
        path = ROOT / rel
        if not path.is_file():
            continue
        last: str | None = None
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("DATABASE_URL="):
                last = _strip_quotes(line.split("=", 1)[1])
        if last:
            return last
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply SQL migrations in db/migrations/")
    parser.add_argument(
        "--from",
        dest="from_name",
        default="0001",
        metavar="PREFIX",
        help="Skip files before this prefix (e.g. 0002 for existing Liara DB)",
    )
    args = parser.parse_args()
    url = resolve_database_url()
    if not url:
        print("Set DATABASE_URL in .env or the environment", file=sys.stderr)
        return 1

    connect_timeout = int(os.environ.get("MIGRATE_CONNECT_TIMEOUT", "30"))
    from_prefix = args.from_name.split("_", 1)[0]
    applied = 0
    for path in MIGRATIONS:
        file_prefix = path.name.split("_", 1)[0]
        if file_prefix < from_prefix:
            continue
        sql = path.read_text(encoding="utf-8")
        print(f"Applying {path.name}...")
        with psycopg.connect(url, connect_timeout=connect_timeout, autocommit=True) as conn:
            conn.execute(sql)
        print(f"OK {path.name}")
        applied += 1
    if applied == 0:
        print("No migrations matched the filter.", file=sys.stderr)
        return 1
    print("Migrations done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())