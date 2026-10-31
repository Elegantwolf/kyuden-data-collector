"""Opt-in display-only outlets. Never write encoded watts to energy history."""
import json
import math
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

from .parsing import JST

DISPLAYS = {
    "recent_hour": "Hour Avg",
    "yesterday": "Yesterday",
}

LEGACY_DISPLAY_NAMES = {
    "recent_hour": "Kyuden 最近小时均功率",
    "yesterday": "Kyuden 昨日用电〔W即度数〕",
}


def discovery_messages(base_topic, discovery_prefix):
    messages = []
    for key, name in DISPLAYS.items():
        prefix = f"{base_topic}/display/{key}"
        device = {
            "identifiers": [f"kyuden_display_{key}"], "name": name,
            "manufacturer": "Kyuden Collector", "model": "Display only — no physical relay",
            "suggested_area": "用电信息",
        }
        common = {"device": device, "availability_topic": f"{prefix}/availability"}
        switch = {
            **common, "name": None, "unique_id": f"kyuden_display_{key}_outlet",
            "default_entity_id": f"switch.kyuden_display_{key}",
            "device_class": "outlet", "state_topic": f"{prefix}/outlet/state",
            # Dedicated, unconsumed command topic: no connection to hardware.
            "command_topic": f"{prefix}/outlet/set", "optimistic": False,
            "payload_on": "ON", "payload_off": "OFF", "retain": False,
        }
        power = {
            **common, "name": "Display Power", "unique_id": f"kyuden_display_{key}_power",
            "default_entity_id": f"sensor.kyuden_display_{key}_power",
            "state_topic": f"{prefix}/power_w", "device_class": "power",
            "state_class": "measurement",
            "unit_of_measurement": "W", "expire_after": 10800,
            "json_attributes_topic": f"{prefix}/details",
            # Matterbridge-hass requires measurement to build the electrical
            # cluster. These isolated W histories are NOT kWh/energy statistics.
        }
        for component, suffix, payload in (("switch", "outlet", switch), ("sensor", "power", power)):
            messages.append((f"{discovery_prefix}/{component}/kyuden_display/{key}_{suffix}/config",
                             json.dumps(payload, ensure_ascii=False)))
    return messages


def _fresh(timestamp, now, max_age):
    try:
        fetched = datetime.fromisoformat(timestamp)
        if fetched.tzinfo is None:
            return False
        return -timedelta(minutes=5) <= now - fetched <= max_age
    except (ValueError, TypeError):
        return False


def state_messages(db_path, base_topic, now=None):
    now = (now or datetime.now(JST)).astimezone(JST)
    today, yesterday = now.date(), now.date() - timedelta(days=1)
    # A display refresh must never create or mutate the collection database.
    with closing(sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        hourly = conn.execute("""SELECT date,hour,usage_kwh,fetched_at FROM hourly_usage
            WHERE date < ? OR (date = ? AND hour < ?)
            ORDER BY date DESC,hour DESC LIMIT 1""",
            (today.isoformat(), today.isoformat(), now.hour)).fetchone()
        daily = conn.execute("SELECT usage_kwh,fetched_at FROM daily_usage WHERE date=?",
                             (yesterday.isoformat(),)).fetchone()
    values = {}
    if hourly:
        day, hour, kwh, fetched = hourly
        start = datetime.fromisoformat(day).replace(hour=hour, tzinfo=JST)
        end = start + timedelta(hours=1)
        available = (math.isfinite(kwh) and kwh >= 0 and
                     timedelta(0) <= now - end <= timedelta(hours=3) and
                     _fresh(fetched, now, timedelta(hours=3)))
        values["recent_hour"] = (round(kwh * 1000, 3), available, {
            "source_kwh": kwh, "period_start": start.isoformat(), "period_end": end.isoformat(),
            "source_fetched_at": fetched, "encoding": "hourly_kWh * 1000 = mean_W; not live power",
        })
    if daily:
        kwh, fetched = daily
        values["yesterday"] = (round(kwh, 3), math.isfinite(kwh) and kwh >= 0 and
                               _fresh(fetched, now, timedelta(hours=36)), {
            "source_kwh": kwh, "source_date": yesterday.isoformat(), "source_fetched_at": fetched,
            "encoding": "DISPLAY ONLY: 1 W represents 1 kWh; not physical power",
        })
    messages = []
    for key in DISPLAYS:
        prefix = f"{base_topic}/display/{key}"
        value, available, details = values.get(key, (None, False, {"reason": "source_missing"}))
        details.update({"display_only": True, "published_at": now.isoformat()})
        if not available:
            messages.append((f"{prefix}/availability", "offline"))
        messages += [(f"{prefix}/outlet/state", "ON"),
                     (f"{prefix}/details", json.dumps(details, ensure_ascii=False))]
        if available:
            messages += [(f"{prefix}/power_w", str(value)), (f"{prefix}/availability", "online")]
    return messages
