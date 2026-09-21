"""Optional JSON webhook adapter."""
import asyncio
import json
import logging
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


def combine_alert_handlers(*handlers):
    enabled = [handler for handler in handlers if handler]
    if not enabled:
        return None

    async def send_alert(message: str, context: dict):
        for handler in enabled:
            await handler(message, context)

    return send_alert

def build_alert_handler(webhook_url: str | None):
    """Build a generic JSON webhook callback; no-op when no URL is configured."""
    if not webhook_url:
        return None

    async def send_alert(message: str, context: dict):
        payload = json.dumps(
            {"message": message, "context": context},
            ensure_ascii=False,
        ).encode("utf-8")

        def post():
            request = Request(
                webhook_url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=10) as response:
                response.read()

        try:
            await asyncio.to_thread(post)
        except Exception as exc:
            logger.error("通知 webhook 调用失败: %s", exc)

    return send_alert
