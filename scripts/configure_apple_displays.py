"""Register ONLY Kyuden display outlets with the existing local Matterbridge.

Default: read-only inspection. --apply saves a mode-600 backup (contains the
existing HA credential), appends our two device names, then restarts ONLY the
HA plugin. Does not commission, reset nodes, toggle devices or alter Energy.
"""
import argparse
import copy
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from websockets.sync.client import connect

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kyuden.display_plugs import DISPLAYS, DISPLAY_LABELS


class RPC:
    def __init__(self, ws, ha=False):
        self.ws, self.ha, self.counter = ws, ha, 0

    def call(self, method, **params):
        self.counter += 1
        message = {"id": self.counter, "type": method, **params} if self.ha else {
            "id": self.counter, "sender": "KyudenDisplaySetup", "method": method,
            "src": "Frontend", "dst": "Matterbridge", "params": params,
        }
        self.ws.send(json.dumps(message))
        while True:
            response = json.loads(self.ws.recv(timeout=20))
            if response.get("id") != self.counter:
                continue
            if self.ha:
                if not response.get("success"):
                    raise RuntimeError(f"HA rejected {method}")
                return response.get("result")
            if response.get("method") != method:
                continue
            if response.get("error"):
                raise RuntimeError(f"Matterbridge rejected {method}")
            return response.get("response")


def whitelist_displays(config, entities):
    updated = copy.deepcopy(config)
    if config.get("filterByArea") or config.get("filterByLabel"):
        raise ValueError("Existing area/label filter requires manual review; nothing changed")
    # An empty whitelist means ALL existing devices; don't narrow it accidentally.
    if updated.get("whiteList"):
        # Retire the accidental English identity names; restore the original
        # stable names so Matter storage assigns the original endpoint numbers.
        kept = [name for name in updated["whiteList"] if name not in DISPLAY_LABELS.values()]
        updated["whiteList"] = list(dict.fromkeys([*kept, *DISPLAYS.values()]))
    if updated.get("entityWhiteList"):
        updated["entityWhiteList"] = list(dict.fromkeys([*updated["entityWhiteList"], *entities]))
    for name in DISPLAYS.values():
        if name in updated.get("blackList", []):
            raise ValueError("Display name is explicitly blacklisted; nothing changed")
    if any(entity in updated.get("entityBlackList", []) for entity in entities):
        raise ValueError("Display entity is explicitly blacklisted; nothing changed")
    return updated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matterbridge-url", required=True, help="Local http(s) URL, no embedded credentials")
    parser.add_argument("--ha-url", help="Reachable URL of the SAME HA instance if plugin uses add-on-internal DNS")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--no-restart", action="store_true", help="Save config only; use a normal service restart separately")
    parser.add_argument("--backup-dir", default="secrets/display-backups")
    args = parser.parse_args()
    parsed = urlparse(args.matterbridge_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username is not None:
        raise ValueError("Use an http(s) URL without embedded credentials")
    ws_url = urlunparse(("wss" if parsed.scheme == "https" else "ws", parsed.netloc, parsed.path, "", "", ""))
    with connect(ws_url, open_timeout=10) as ws:
        mb = RPC(ws)
        plugin = next(p for p in mb.call("/api/plugins") if p["name"] == "matterbridge-hass")
        config = plugin["configJson"]
        print("Matterbridge HA plugin:", plugin["version"], "loaded:", plugin.get("loaded"))
        # Reuse the existing HA connection in memory. Never log or copy its token
        # into arguments/environment/git, and do not create a new credential.
        ha_url = urlparse(args.ha_url or config["host"])
        if ha_url.scheme not in ("http", "https", "ws", "wss") or not ha_url.netloc or ha_url.username is not None:
            raise ValueError("Use --ha-url with the reachable URL of the same HA instance")
        ha_ws_url = urlunparse(("wss" if ha_url.scheme in ("https", "wss") else "ws",
                               ha_url.netloc, "/api/websocket", "", "", ""))
        with connect(ha_ws_url, open_timeout=10) as ha_ws:
            if json.loads(ha_ws.recv(timeout=10)).get("type") != "auth_required":
                raise RuntimeError("Unexpected HA handshake")
            ha_ws.send(json.dumps({"type": "auth", "access_token": config["token"]}))
            if json.loads(ha_ws.recv(timeout=10)).get("type") != "auth_ok":
                raise RuntimeError("Existing HA connection credential was rejected")
            ha = RPC(ha_ws, ha=True)
            registry = ha.call("config/entity_registry/list")
            expected = {f"kyuden_display_{key}_{suffix}" for key in DISPLAYS for suffix in ("outlet", "power")}
            entities = [e for e in registry if e.get("platform") == "mqtt" and e.get("unique_id") in expected]
            if {e["unique_id"] for e in entities} != expected:
                raise RuntimeError("Publish displays first; all four HA entities must exist")
            devices = {d["id"]: d for d in ha.call("config/device_registry/list")}
            for entity in entities:
                device = devices[entity["device_id"]]
                owned = any(i[0] == "mqtt" and i[1] in {f"kyuden_display_{k}" for k in DISPLAYS}
                            for i in device.get("identifiers", []))
                if not owned:
                    raise RuntimeError("Entity is not owned by a Kyuden display device; stopping")
            ids = [e["entity_id"] for e in entities]
            owned_ids = {e["device_id"] for e in entities}
            if any(device_id not in owned_ids and (device.get("name_by_user") or device.get("name")) in DISPLAYS.values()
                   for device_id, device in devices.items()):
                raise ValueError("Display name conflicts with another device; nothing changed")
            updated = whitelist_displays(config, ids)
            print("Display entities:", ids)
            print("Whitelist additions:", [n for n in updated.get("whiteList", []) if n not in config.get("whiteList", [])])
            if not args.apply:
                print("Inspection only; nothing changed")
                return
            backup_dir = Path(args.backup_dir)
            backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            backup = backup_dir / ("matterbridge-hass-" + datetime.now().strftime("%Y%m%dT%H%M%S%f") + ".json")
            with os.fdopen(os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as out:
                json.dump(config, out, ensure_ascii=False, indent=2)
            print("Protected configuration backup:", backup)
            areas = ha.call("config/area_registry/list")
            area = next((a for a in areas if a["name"] == "用电信息"), None)
            if area is None:
                area = ha.call("config/area_registry/create", name="用电信息")
            for device_id in {e["device_id"] for e in entities}:
                if not devices[device_id].get("area_id"):
                    ha.call("config/device_registry/update", device_id=device_id, area_id=area["area_id"])
            if updated != config:
                mb.call("/api/savepluginconfig", pluginName="matterbridge-hass", formData=updated)
                saved = next(p["configJson"] for p in mb.call("/api/plugins") if p["name"] == "matterbridge-hass")
                if any(saved.get(k) != v for k, v in updated.items()):
                    raise RuntimeError("Saved configuration differs; inspect backup before proceeding")
                if not args.no_restart:
                    mb.call("/api/restartplugin", pluginName="matterbridge-hass")
                    print("HA plugin restart requested; no bridge reset, no physical device commands")
                else:
                    print("Config saved; no restart requested")
            else:
                print("Whitelist already configured; plugin not restarted")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Third-party errors may contain URLs or auth frames: do not dump them.
        print(f"Display setup stopped ({type(exc).__name__}); no credentials printed", file=sys.stderr)
        sys.exit(1)
