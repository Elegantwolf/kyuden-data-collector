import tempfile
import unittest
from pathlib import Path
from kyuden.storage import KyudenSQLite


class StorageTests(unittest.TestCase):
    def test_parent_creation_and_idempotent_upsert(self):
        with tempfile.TemporaryDirectory() as directory:
            with KyudenSQLite(Path(directory) / "nested" / "usage.sqlite") as db:
                db.init_schema()
                for usage in (1, 2):
                    db.upsert_daily([dict(date="2026-09-01", usage_kwh=usage)])
                    db.upsert_hourly([dict(date="2026-09-01", hour=3, usage_kwh=usage)])
                for table in ("daily_usage", "hourly_usage"):
                    rows = db.conn.execute(f"SELECT * FROM {table}").fetchall()
                    self.assertEqual(len(rows), 1)
                    self.assertEqual(rows[0]["usage_kwh"], 2)


if __name__ == "__main__":
    unittest.main()
