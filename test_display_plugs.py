import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

from kyuden.display_plugs import DISPLAYS, DISPLAY_LABELS, discovery_messages, state_messages
from kyuden.ha import HomeAssistantReporter, MQTTConfig
from kyuden.parsing import JST
from kyuden.storage import KyudenSQLite
from scripts.configure_apple_displays import whitelist_displays


class DisplayPlugTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/"usage.sqlite"
        self.now = datetime(2026, 11, 1, 2, 5, tzinfo=JST)
        with KyudenSQLite(self.path) as db:
            db.init_schema()

    def add_rows(self, hourly=(), daily=()):
        with KyudenSQLite(self.path) as db:
            db.upsert_hourly(hourly)
            db.upsert_daily(daily)

    def test_scale_and_midnight_dates(self):
        self.add_rows(hourly=[{"date":"2026-11-01","hour":0,"usage_kwh":0.35,
                              "timestamp":self.now.isoformat()}],
                      daily=[{"date":"2026-10-31","usage_kwh":6.7,"timestamp":self.now.isoformat()}])
        messages = dict(state_messages(self.path, "kyuden", self.now))
        self.assertEqual(float(messages["kyuden/display/recent_hour/power_w"]), 350)
        self.assertEqual(float(messages["kyuden/display/yesterday/power_w"]), 6.7)
        self.assertEqual(messages["kyuden/display/yesterday/availability"], "online")
        self.assertEqual(json.loads(messages["kyuden/display/yesterday/details"])["source_date"], "2026-10-31")

    def test_zero_is_a_valid_reading(self):
        self.add_rows(hourly=[{"date":"2026-11-01","hour":0,"usage_kwh":0,"timestamp":self.now.isoformat()}])
        messages = dict(state_messages(self.path,"kyuden",self.now))
        self.assertEqual(float(messages["kyuden/display/recent_hour/power_w"]),0)
        self.assertEqual(messages["kyuden/display/recent_hour/availability"],"online")

    def test_old_measurement_cannot_be_made_fresh_by_refetch(self):
        self.add_rows(hourly=[{"date":"2026-10-30","hour":23,"usage_kwh":1,"timestamp":self.now.isoformat()}],
                      daily=[{"date":"2026-10-30","usage_kwh":9,"timestamp":self.now.isoformat()}])
        messages = dict(state_messages(self.path,"kyuden",self.now))
        for key in ("recent_hour","yesterday"):
            self.assertEqual(messages[f"kyuden/display/{key}/availability"],"offline")
            self.assertNotIn(f"kyuden/display/{key}/power_w",messages)

    def test_current_hour_and_future_data_are_not_average_of_full_hour(self):
        self.add_rows(hourly=[{"date":"2026-11-01","hour":2,"usage_kwh":1,"timestamp":self.now.isoformat()}])
        self.assertEqual(dict(state_messages(self.path,"kyuden",self.now))["kyuden/display/recent_hour/availability"],"offline")

    def test_stale_collection_is_unavailable_even_if_period_is_recent(self):
        self.add_rows(hourly=[{"date":"2026-11-01","hour":0,"usage_kwh":1,"timestamp":"2026-10-30T00:00:00+09:00"}])
        self.assertEqual(dict(state_messages(self.path,"kyuden",self.now))["kyuden/display/recent_hour/availability"],"offline")

    def test_distinct_devices_no_energy_statistics_and_isolated_commands(self):
        configs = {k:json.loads(v) for k,v in discovery_messages("kyuden","homeassistant")}
        self.assertEqual(len(configs),4)
        ids = {tuple(v["device"]["identifiers"]) for v in configs.values()}
        self.assertEqual(len(ids),2)
        for topic,config in configs.items():
            self.assertNotIn("energy",topic)
            self.assertTrue(config["state_topic"].startswith("kyuden/display/"))
            if "/switch/" in topic:
                self.assertEqual(config["device_class"],"outlet")
                self.assertTrue(config["command_topic"].endswith("/outlet/set"))
                self.assertFalse(config["optimistic"])
            else:
                self.assertEqual(config["state_class"],"measurement")
                self.assertEqual(config["device_class"],"power")
                self.assertEqual(config["unit_of_measurement"],"W")

    def test_disabled_by_default(self):
        reporter = HomeAssistantReporter(MQTTConfig(host="unused"))
        self.assertFalse(any("kyuden_display" in topic for topic,_ in reporter.discovery_messages()))

    def test_read_only_missing_database_does_not_create_file(self):
        missing = Path(self.tmp.name)/"missing.sqlite"
        with self.assertRaises(Exception):
            state_messages(missing,"kyuden",self.now)
        self.assertFalse(missing.exists())

    def test_bridge_setup_preserves_existing_configuration_and_does_not_widen_entity_filters(self):
        config = {"whiteList":["Kyuden Data Collector"], "entityWhiteList":["sensor.existing"],
                  "blackList":["Bedroom Light"], "deviceEntityBlackList":{"Kyuden Data Collector":["sensor.old"]},
                  "token":"private", "controllerStrategy":"Merge"}
        updated = whitelist_displays(config,["switch.kyuden_display_recent_hour"])
        self.assertEqual(config["whiteList"],["Kyuden Data Collector"])
        self.assertEqual(updated["blackList"],config["blackList"])
        self.assertEqual(updated["deviceEntityBlackList"],config["deviceEntityBlackList"])
        self.assertEqual(updated["token"],"private")
        self.assertIn("sensor.existing",updated["entityWhiteList"])
        self.assertEqual(updated,whitelist_displays(updated,["switch.kyuden_display_recent_hour"]))

    def test_empty_whitelist_keeps_its_existing_all_devices_semantics(self):
        self.assertEqual(whitelist_displays({"whiteList":[]},[])["whiteList"],[])

    def test_restore_only_our_accidentally_renamed_bridge_identities(self):
        config = {"whiteList":["Kyuden Data Collector",*DISPLAY_LABELS.values(),"Bedroom Light"]}
        migrated = whitelist_displays(config,[])
        self.assertEqual(migrated["whiteList"],["Kyuden Data Collector","Bedroom Light",*DISPLAYS.values()])
        self.assertTrue(all(name.isascii() and len(name)<=9 for name in DISPLAY_LABELS.values()))

    def test_display_label_changes_never_change_bridge_identity_names(self):
        before = discovery_messages("kyuden","homeassistant")
        with patch.dict(DISPLAY_LABELS,{"recent_hour":"Another client label"}):
            self.assertEqual(before,discovery_messages("kyuden","homeassistant"))
        self.assertEqual(DISPLAYS,{"recent_hour":"Kyuden 最近小时均功率","yesterday":"Kyuden 昨日用电〔W即度数〕"})

    def test_setup_refuses_to_override_area_filter_or_explicit_blacklist(self):
        with self.assertRaises(ValueError):
            whitelist_displays({"filterByArea":"Bedroom"},[])
        with self.assertRaises(ValueError):
            whitelist_displays({"entityBlackList":["sensor.kyuden_display_yesterday_power"]},["sensor.kyuden_display_yesterday_power"])


class DisplayPublisherTests(unittest.IsolatedAsyncioTestCase):
    async def test_display_refresh_does_not_claim_collection_or_touch_other_devices(self):
        reporter = HomeAssistantReporter(MQTTConfig(host="unused", apple_display_plugs=True))
        reporter._publish_with_retry = AsyncMock()
        with patch("kyuden.display_plugs.state_messages",return_value=[("kyuden/display/recent_hour/power_w","350")]):
            await reporter.publish_displays("unused")
        messages = reporter._publish_with_retry.call_args.args[0]
        self.assertTrue(all("kyuden_display/" in topic or topic.startswith("kyuden/display/") for topic,_ in messages))
        self.assertFalse(any("health/" in topic or "energy/" in topic for topic,_ in messages))
