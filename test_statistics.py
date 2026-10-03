import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from kyuden.statistics import StatisticsConfig, StatisticsReporter, StatisticsDeliveryError, build_statistics
from kyuden.storage import KyudenSQLite


class StatisticsTests(unittest.IsolatedAsyncioTestCase):
    def test_timezone_and_idempotent_replay_after_backfill(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"usage.sqlite"
            with KyudenSQLite(path) as db:
                db.init_schema()
                db.upsert_hourly([{"date": "2026-10-02", "hour": 22, "usage_kwh": 0.3},
                                  {"date": "2026-10-03", "hour": 0, "usage_kwh": 0.2}])
                before = build_statistics(path)
                self.assertEqual(before[1]["start"], "2026-10-02T13:00:00+00:00")
                self.assertEqual(before[-1]["sum"], 0.5)
                db.upsert_hourly([{"date": "2026-10-02", "hour": 23, "usage_kwh": 0.4}])
                after = build_statistics(path)
                self.assertEqual(after[-1]["sum"], 0.9)
                self.assertEqual(after, build_statistics(path))
                self.assertEqual(after[0]["sum"], 0)

    def test_disabled_or_incomplete_config_and_token_redaction(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(StatisticsConfig.from_env())
        with patch.dict(os.environ, {"KYUDEN_HA_URL": "http://ha.local"}, clear=True):
            with self.assertRaises(ValueError):
                StatisticsConfig.from_env()
        config = StatisticsConfig("https://ha.local", "private-token")
        self.assertEqual(config.websocket_url(), "wss://ha.local/api/websocket")
        self.assertNotIn("private-token", repr(config))

    async def test_import_uses_external_statistic_and_checks_result(self):
        ws = SimpleNamespace(recv=AsyncMock(side_effect=[json.dumps({"type":"auth_required"}),
                        json.dumps({"type":"auth_ok"}), json.dumps({"id":1,"success":True})]), send=AsyncMock())
        class Connection:
            async def __aenter__(self): return ws
            async def __aexit__(self, *_args): return None
        module = SimpleNamespace(connect=lambda *_args, **_kwargs: Connection())
        with patch.dict("sys.modules", {"websockets.asyncio.client": module}), \
                patch("kyuden.statistics.build_statistics", return_value=[{"start":"2026-10-02T13:00:00+00:00","sum":0.3}]):
            await StatisticsReporter(StatisticsConfig("http://ha.local", "token")).publish("unused")
        payload = json.loads(ws.send.call_args_list[-1].args[0])
        self.assertEqual(payload["metadata"]["statistic_id"], "kyuden:consumption")
        self.assertEqual(payload["metadata"]["mean_type"], 0)
        self.assertEqual(payload["metadata"]["unit_class"], "energy")

    async def test_auth_failure_is_not_silently_ignored(self):
        ws = SimpleNamespace(recv=AsyncMock(side_effect=[json.dumps({"type":"auth_required"}), json.dumps({"type":"auth_invalid"})]), send=AsyncMock())
        class Connection:
            async def __aenter__(self): return ws
            async def __aexit__(self, *_args): return None
        with patch.dict("sys.modules", {"websockets.asyncio.client": SimpleNamespace(connect=lambda *_args, **_kwargs: Connection())}), \
                patch("kyuden.statistics.build_statistics", return_value=[{"start":"2026-10-02T13:00:00+00:00","sum":0.3}]):
            with self.assertRaises(StatisticsDeliveryError):
                await StatisticsReporter(StatisticsConfig("http://ha.local", "token")).publish("unused")
