import sqlite3
from pathlib import Path
from typing import Iterable, Dict, Any, Optional, List
from datetime import datetime, date

DEFAULT_DB_PATH = Path("kyuden_usage.db")

DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS daily_usage (
        date TEXT PRIMARY KEY,              -- ISO 日期（JST），YYYY-MM-DD
        usage_kwh REAL NOT NULL,
        fetched_at TEXT NOT NULL            -- ISO 时间戳
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS hourly_usage (
        date TEXT NOT NULL,                 -- ISO 日期（JST）
        hour INTEGER NOT NULL,              -- 0..23
        usage_kwh REAL NOT NULL,
        fetched_at TEXT NOT NULL,
        PRIMARY KEY (date, hour)
    );
    """,
    # 可选索引（主键已覆盖最常见查询）
]

def _to_iso_date(v: Any) -> str:
    if isinstance(v, date) and not isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, datetime):
        return v.date().isoformat()
    return str(v)

def _to_iso_ts(v: Optional[Any]) -> str:
    if isinstance(v, datetime):
        return v.isoformat()
    if v is None:
        return datetime.now().isoformat()
    return str(v)

class KyudenSQLite:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.conn: Optional[sqlite3.Connection] = None

    def connect(self):
        self.conn = sqlite3.connect(
            str(self.db_path),
            timeout=15,
            isolation_level=None,  # autocommit; 我们会显式用事务
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        self.conn.row_factory = sqlite3.Row
        cur = self.conn.cursor()
        # 推荐的运行参数
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA synchronous=NORMAL;")
        cur.execute("PRAGMA foreign_keys=ON;")
        cur.execute("PRAGMA busy_timeout=5000;")
        cur.close()

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def init_schema(self):
        assert self.conn, "Database not connected"
        cur = self.conn.cursor()
        try:
            for ddl in DDL_STATEMENTS:
                cur.execute(ddl)
        finally:
            cur.close()

    def upsert_daily(self, rows: Iterable[Dict[str, Any]]) -> int:
        """
        rows 中的每条记录至少包含:
        - date: date | str (YYYY-MM-DD)
        - usage_kwh: float
        - timestamp/fetched_at: datetime | str | None
        """
        assert self.conn, "Database not connected"
        rows_list: List[Dict[str, Any]] = list(rows)
        if not rows_list:
            return 0

        data = []
        for r in rows_list:
            d = _to_iso_date(r.get("date") or r.get("date_str"))
            u = float(r.get("usage_kwh"))
            ts = r.get("fetched_at", r.get("timestamp"))
            data.append((d, u, _to_iso_ts(ts)))

        sql = """
        INSERT INTO daily_usage (date, usage_kwh, fetched_at)
        VALUES (?, ?, ?)
        ON CONFLICT(date) DO UPDATE SET
            usage_kwh=excluded.usage_kwh,
            fetched_at=excluded.fetched_at;
        """
        cur = self.conn.cursor()
        try:
            cur.execute("BEGIN;")
            cur.executemany(sql, data)
            cur.execute("COMMIT;")
        except Exception:
            cur.execute("ROLLBACK;")
            raise
        finally:
            cur.close()
        return len(data)

    def upsert_hourly(self, rows: Iterable[Dict[str, Any]]) -> int:
        """
        rows 中的每条记录至少包含:
        - date: date | str (YYYY-MM-DD)
        - hour: int (0..23)
        - usage_kwh: float
        - timestamp/fetched_at: datetime | str | None
        """
        assert self.conn, "Database not connected"
        rows_list: List[Dict[str, Any]] = list(rows)
        if not rows_list:
            return 0

        data = []
        for r in rows_list:
            d = _to_iso_date(r.get("date") or r.get("date_str"))
            h = int(r.get("hour"))
            u = float(r.get("usage_kwh"))
            ts = r.get("fetched_at", r.get("timestamp"))
            data.append((d, h, u, _to_iso_ts(ts)))

        sql = """
        INSERT INTO hourly_usage (date, hour, usage_kwh, fetched_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(date, hour) DO UPDATE SET
            usage_kwh=excluded.usage_kwh,
            fetched_at=excluded.fetched_at;
        """
        cur = self.conn.cursor()
        try:
            cur.execute("BEGIN;")
            cur.executemany(sql, data)
            cur.execute("COMMIT;")
        except Exception:
            cur.execute("ROLLBACK;")
            raise
        finally:
            cur.close()
        return len(data)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Kyuden SQLite DB manager")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite 文件路径")
    parser.add_argument("--init", action="store_true", help="初始化数据库表结构")
    args = parser.parse_args()

    with KyudenSQLite(Path(args.db)) as db:
        if args.init:
            db.init_schema()
            print(f"Initialized schema in {db.db_path}")