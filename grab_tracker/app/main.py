import asyncio
import json
import os
import threading
import logging
import aiohttp
from bot import TelegramBot
from tracker import OrderTracker
from ha_api import HAApi
from database import init_db
from web import run_web
from version import VERSION
from mqtt_client import MqttClient, NullMqttClient
from slots import SlotManager

logging.basicConfig(level=logging.INFO)
_LOGGER = logging.getLogger(__name__)

# Standard HA add-on log levels → Python logging levels.
LOG_LEVELS = {
    "trace": logging.DEBUG, "debug": logging.DEBUG, "info": logging.INFO,
    "notice": logging.INFO, "warning": logging.WARNING, "error": logging.ERROR,
    "fatal": logging.CRITICAL,
}

def load_config():
    with open("/data/options.json") as f:
        return json.load(f)

def apply_log_level(config):
    name = (config.get("log_level") or "info").lower()
    level = LOG_LEVELS.get(name, logging.INFO)
    logging.getLogger().setLevel(level)
    # The httpx/telegram pollers log every getUpdates at INFO — keep them quiet unless
    # the user explicitly asked for debug/trace.
    noisy = logging.DEBUG if name in ("trace", "debug") else logging.WARNING
    for lib in ("httpx", "httpcore", "telegram", "apscheduler"):
        logging.getLogger(lib).setLevel(noisy)
    _LOGGER.info(f"Log level set to '{name}'")

async def get_mqtt_config(config):
    """Prefer explicit mqtt_* options; otherwise discover the broker via the Supervisor
    services API (granted by `services: [mqtt:want]` in config.yaml)."""
    host = (config.get("mqtt_host") or "").strip()
    if host:
        return {
            "host": host,
            "port": int(config.get("mqtt_port") or 1883),
            "username": config.get("mqtt_username") or None,
            "password": config.get("mqtt_password") or None,
            "ssl": False,
        }
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        raise RuntimeError("no mqtt_host configured and SUPERVISOR_TOKEN is unavailable")
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "http://supervisor/services/mqtt",
            headers={"Authorization": f"Bearer {token}"},
        ) as resp:
            resp.raise_for_status()
            data = (await resp.json())["data"]
    return {
        "host": data["host"],
        "port": int(data.get("port") or 1883),
        "username": data.get("username") or None,
        "password": data.get("password") or None,
        "ssl": bool(data.get("ssl")),
    }

async def main():
    config = load_config()
    apply_log_level(config)

    await init_db()

    ha_api = HAApi()
    bot = TelegramBot(
        config["telegram_bot_token"],
        notify_chat_id=config.get("notify_chat_id") or None,
        version=VERSION,
        allowed_chat_ids=config.get("allowed_chat_ids") or None,
    )

    import database
    loop = asyncio.get_running_loop()
    slots = SlotManager(int(config.get("max_concurrent_orders") or 5))

    async def apply_config(key, value):
        # Driven by HA changing a config entity over MQTT; route through the tracker
        # so the DB + MQTT state stay in sync.
        await tracker.update_setting(key, value)

    try:
        mqtt_cfg = await get_mqtt_config(config)
        mqtt = MqttClient(slots=slots.size, version=VERSION, **mqtt_cfg)
        mqtt.set_command_handler(loop, apply_config)
        mqtt.start()
        _LOGGER.info(f"MQTT connected to {mqtt_cfg['host']}:{mqtt_cfg['port']}")
        try:
            mqtt.publish_all_config_states(await database.get_settings())
        except Exception as e:
            _LOGGER.warning(f"Could not publish initial config states: {e}")
    except Exception as e:
        _LOGGER.warning(f"MQTT unavailable ({e}); HA sensors disabled, Telegram still works")
        mqtt = NullMqttClient()

    tracker = OrderTracker(config, ha_api, bot, database, mqtt, slots)
    bot.set_tracker(tracker)

    threading.Thread(target=run_web, args=(tracker, loop), daemon=True).start()

    await bot.start()

    stopped = await tracker.stop_all_on_startup()
    if config.get("notify_chat_id"):
        msg = f"🛵 On the way v{VERSION} dimulakan."
        if stopped:
            msg += f"\n⏹ {stopped} sesi penjejakan terdahulu dihentikan semasa but semula (tidak disambung semula)."
        msg += "\nHantar pautan kongsi untuk mula menjejak."
        try:
            await bot.send_text(config["notify_chat_id"], msg)
        except Exception as e:
            _LOGGER.warning(f"Could not send startup notice: {e}")

    try:
        await asyncio.Event().wait()
    finally:
        await bot.stop()
        mqtt.stop()

if __name__ == "__main__":
    asyncio.run(main())
