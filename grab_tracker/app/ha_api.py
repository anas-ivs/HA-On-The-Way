import aiohttp
import logging
from zoneinfo import ZoneInfo

_LOGGER = logging.getLogger(__name__)

class HAApi:
    def __init__(self, ha_url: str, token: str):
        self.base = ha_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        self._timezone: ZoneInfo | None = None

    async def get_timezone(self) -> ZoneInfo:
        if self._timezone is not None:
            return self._timezone
        url = f"{self.base}/api/config"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers) as resp:
                    data = await resp.json()
            tz_name = data.get("time_zone", "UTC")
            self._timezone = ZoneInfo(tz_name)
            _LOGGER.info(f"HA timezone: {tz_name}")
        except Exception as e:
            # Don't cache the fallback — a transient HA hiccup shouldn't lock this order
            # to UTC for its whole lifetime; retry on the next call.
            _LOGGER.warning(f"Could not fetch HA timezone, using UTC for now: {e}")
            return ZoneInfo("UTC")
        return self._timezone

    # NOTE: Order state is published to HA via MQTT Discovery (see mqtt_client.py),
    # not the REST /api/states API. This class now only provides the HA timezone.
