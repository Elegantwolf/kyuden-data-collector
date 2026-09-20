"""Compatibility imports for the existing SQLite API."""
from kyuden.storage import KyudenSQLite, DEFAULT_DB_PATH

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--init", action="store_true")
    args = parser.parse_args()
    if args.init:
        with KyudenSQLite(args.db) as db:
            db.init_schema()
