import os
import aiohttp
import logging
from zoneinfo import ZoneInfo

_LOGGER = logging.getLogger(__name__)

class HAApi:
    """Provides the Home Assistant timezone. No HA token needed — the Supervisor sets the
    add-on's `TZ` env var to the system timezone; the Supervisor API is a fallback."""

    def __init__(self):
        self._timezone: ZoneInfo | None = None

    async def get_timezone(self) -> ZoneInfo:
        if self._timezone is not None:
            return self._timezone

        # 1) TZ env var — Supervisor sets it to the HA system timezone (no auth needed).
        name = (os.environ.get("TZ") or "").strip()

        # 2) Fallback: Supervisor API (uses SUPERVISOR_TOKEN, not a user token).
        if not name:
            name = await self._tz_from_supervisor()

        if name:
            try:
                self._timezone = ZoneInfo(name)
                _LOGGER.info(f"Timezone: {name}")
                return self._timezone
            except Exception as e:
                _LOGGER.warning(f"Invalid timezone '{name}', using UTC: {e}")

        # Don't cache the UTC fallback — retry on the next call.
        return ZoneInfo("UTC")

    async def _tz_from_supervisor(self):
        token = os.environ.get("SUPERVISOR_TOKEN")
        if not token:
            return None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "http://supervisor/info",
                    headers={"Authorization": f"Bearer {token}"},
                ) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
            return (data.get("data") or {}).get("timezone")
        except Exception as e:
            _LOGGER.warning(f"Could not get timezone from Supervisor: {e}")
            return None
