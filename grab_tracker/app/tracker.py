import asyncio
import logging
import math
from grab_api import resolve_token, fetch_order, POLL_INTERVALS
from database import DEFAULT_SETTINGS

_LOGGER = logging.getLogger(__name__)

# Poll-error backoff: start at 60s, double each consecutive failure up to a cap,
# and give up (with a Telegram notice) after this many failures in a row.
ERROR_BACKOFF_START = 60
ERROR_BACKOFF_CAP = 600
MAX_CONSECUTIVE_FAILURES = 5


def _haversine_m(lat1, lng1, lat2, lng2) -> float:
    """Great-circle distance in metres between two lat/lng points."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

STATUS_ICONS = {
    "QUEUEING": "📋", "ALLOCATING": "🔍",
    "PICKING_UP": "🛵", "IN_DELIVERY": "📦",
    "ORDER_IN_PREPARE": "🍳", "ORDER_EXECUTING": "🛵",
    "COMPLETED": "✅", "CANCELLED": "❌"
}
LOCATION_STATES = {"ORDER_IN_PREPARE", "ORDER_EXECUTING", "IN_DELIVERY", "PICKING_UP"}

class OrderTracker:
    def __init__(self, config, ha_api, bot, db, mqtt, slots):
        self.config = config
        self.ha_api = ha_api
        self.bot = bot
        self.db = db
        self.mqtt = mqtt
        self.slots = slots
        self.history_limit = int(config.get("history_limit") or 50)
        self.active = {}          # token -> {chat_id, last_state, poll_count, wake, task}
        self.booking_codes = {}   # booking_code -> token (dedup across share links)

    def _get_interval(self, state: str) -> int:
        interval_key = POLL_INTERVALS.get(state, "default")
        return self.config.get(f"poll_interval_{interval_key}", 180)

    async def start_tracking(self, short_url: str, chat_id: str):
        """Start tracking a Grab order. Returns (ok, message) so non-Telegram callers
        (web UI) can report the outcome; Telegram messages are still sent to chat_id when
        provided (skipped if chat_id is falsy)."""
        try:
            token = await resolve_token(short_url)
        except Exception as e:
            await self.bot.send_text(chat_id, f"❌ Tidak dapat menyelesaikan pautan Grab:\n{e}")
            return False, f"Tidak dapat menyelesaikan pautan Grab: {e}"

        if token in self.active:
            await self.bot.send_text(chat_id, "⚠️ Pesanan ini sedang dijejak.")
            return False, "Pesanan ini sedang dijejak."

        slot = self.slots.claim(token)
        if slot is None:
            msg = (f"Sudah menjejak maksimum {self.slots.size} pesanan. "
                   "Sila tunggu satu selesai sebelum menambah yang lain.")
            await self.bot.send_text(chat_id, f"⚠️ {msg}")
            return False, msg

        self.active[token] = {
            "chat_id": chat_id,
            "last_state": None,
            "poll_count": 0,
            "wake": asyncio.Event(),  # set by /poll to force an immediate check
        }
        self.mqtt.set_slot_availability(slot, True)
        await self.bot.send_text(
            chat_id,
            f"🛵 *Penjejakan pesanan Grab dimulakan!* _(slot {slot})_\n\n"
            "Saya akan kemas kini anda pada setiap perubahan status.",
            parse_mode="Markdown"
        )
        task = asyncio.create_task(self._poll_loop(token, chat_id))
        self.active[token]["task"] = task
        return True, f"Penjejakan dimulakan (slot {slot})."

    async def api_track(self, url: str):
        """Web-initiated tracking. Updates go to the configured notify_chat_id (if any)."""
        chat_id = self.config.get("notify_chat_id") or None
        return await self.start_tracking(url, chat_id)

    def force_poll(self, chat_id: str = None) -> int:
        """Wake matching poll loops so they fetch immediately instead of waiting out the
        timer. Returns how many active orders were nudged."""
        count = 0
        for entry in self.active.values():
            if chat_id is None or entry.get("chat_id") == chat_id:
                wake = entry.get("wake")
                if wake is not None:
                    wake.set()
                    count += 1
        return count

    async def restart_all(self) -> int:
        """Soft reset: cancel every active tracking task and clear in-memory caches +
        free all slots. Does NOT restart the add-on container."""
        tokens = list(self.active.keys())
        for entry in self.active.values():
            task = entry.get("task")
            if task is not None:
                task.cancel()
        self.active.clear()
        self.booking_codes.clear()
        for token in tokens:
            self.slots.release(token)
        for n in self.slots.all_slots():
            self.mqtt.set_slot_availability(n, False)
        return len(tokens)

    async def stop_all_on_startup(self) -> int:
        """EXPLICIT FEATURE: an add-on restart stops ALL in-flight tracking — nothing is
        resumed. Any order left non-terminal in SQLite is closed out, and every MQTT slot
        is set unavailable. Returns how many previously-open sessions were stopped."""
        try:
            closed = await self.db.close_open_orders()
        except Exception as e:
            _LOGGER.warning(f"Could not close open orders on startup: {e}")
            closed = 0
        for n in self.slots.all_slots():
            self.mqtt.set_slot_availability(n, False)
        if closed:
            _LOGGER.info(f"Restart: stopped {closed} previously-open tracking session(s); none resumed.")
        return closed

    # ---- introspection / control (used by /list, web UI) ----
    def list_active(self) -> list:
        """Snapshot of currently-tracked orders for the web UI / Telegram /list."""
        out = []
        for token, e in self.active.items():
            out.append({
                "token": token,
                "slot": self.slots.slot_for(token),
                "chat_id": e.get("chat_id"),
                "booking_code": e.get("booking_code"),
                "status": e.get("status") or e.get("last_state"),
                "dropoff": e.get("dropoff"),
                "poll_count": e.get("poll_count", 0),
            })
        out.sort(key=lambda x: (x["slot"] or 99))
        return out

    def force_poll_token(self, token: str) -> bool:
        """Wake one order's poll loop so it fetches immediately."""
        e = self.active.get(token)
        if e and e.get("wake") is not None:
            e["wake"].set()
            return True
        return False

    async def kill(self, token: str) -> bool:
        """Stop tracking one order: cancel its loop (the loop's finally frees the slot +
        MQTT availability) and mark it terminal in the DB."""
        e = self.active.get(token)
        if not e:
            return False
        task = e.get("task")
        if task is not None:
            task.cancel()
        try:
            await self.db.close_order(token)
        except Exception as ex:
            _LOGGER.warning(f"close_order({token}) failed: {ex}")
        return True

    async def update_setting(self, key: str, value) -> bool:
        """Single entry point for setting changes (web UI, /config, MQTT) so the DB and
        the MQTT config entity stay in sync."""
        if key not in DEFAULT_SETTINGS:
            return False
        await self.db.set_settings({key: str(value)})
        self.mqtt.publish_config_state(key, value)
        return True

    # async wrappers so the Flask thread can drive these via run_coroutine_threadsafe
    async def api_list_active(self):
        return self.list_active()

    async def api_refresh(self, token):
        return self.force_poll_token(token)

    async def api_kill(self, token):
        return await self.kill(token)

    async def api_update_setting(self, key, value):
        return await self.update_setting(key, value)

    async def _poll_loop(self, token: str, chat_id: str):
        slot = self.slots.slot_for(token)
        start = asyncio.get_event_loop().time()
        max_timeout = self.config.get("max_tracking_timeout", 7200)
        consecutive_failures = 0
        first_fetch = True

        try:
            while True:
                if asyncio.get_event_loop().time() - start > max_timeout:
                    await self.bot.send_text(chat_id, "⏰ Penjejakan tamat masa selepas 2 jam.")
                    break

                # Cached after first success; re-fetched cheaply until HA timezone resolves.
                tz = await self.ha_api.get_timezone()
                try:
                    order = await fetch_order(token, tz)
                    consecutive_failures = 0
                except Exception as e:
                    consecutive_failures += 1
                    _LOGGER.error(
                        f"Poll error for {token} "
                        f"({consecutive_failures}/{MAX_CONSECUTIVE_FAILURES}): {e}"
                    )
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        await self.bot.send_text(
                            chat_id,
                            "⚠️ Penjejakan dihentikan selepas ralat berulang semasa mendapatkan pesanan.",
                        )
                        break
                    backoff = min(
                        ERROR_BACKOFF_START * (2 ** (consecutive_failures - 1)),
                        ERROR_BACKOFF_CAP,
                    )
                    await asyncio.sleep(backoff)
                    continue

                # Dedup by booking code (catches the same order shared via a 2nd link).
                if first_fetch:
                    first_fetch = False
                    code = order.booking_code
                    if code:
                        owner = self.booking_codes.get(code)
                        if owner and owner != token and owner in self.active:
                            await self.bot.send_text(
                                chat_id, "⚠️ Pesanan ini sedang dijejak.")
                            break
                        self.booking_codes[code] = token

                entry = self.active.get(token, {})
                last_state = entry.get("last_state")
                poll_count = entry.get("poll_count", 0) + 1
                status_changed = order.booking_state != last_state

                self.active[token]["last_state"] = order.booking_state
                self.active[token]["poll_count"] = poll_count
                self.active[token]["booking_code"] = order.booking_code
                self.active[token]["status"] = order.friendly_status
                self.active[token]["dropoff"] = order.dropoff_name

                await self.db.upsert_order(token, chat_id, order, self.history_limit)

                if slot is not None:
                    self.mqtt.set_slot_availability(slot, True)
                    self.mqtt.publish_slot_state(slot, self._slot_state(order))

                settings = await self.db.get_settings()

                # Debug message to Telegram — toggled via /config or the web UI.
                if settings.get("debug_messages") == "1":
                    await self._send_debug(chat_id, order, poll_count)

                if status_changed:
                    await self._send_status_update(chat_id, order, poll_count)
                else:
                    await self._send_eta_update(chat_id, order, poll_count)

                if order.has_driver_loc and order.booking_state in LOCATION_STATES:
                    await self._maybe_send_driver_location(token, chat_id, order, settings)

                if order.is_terminal or order.session_status == "EXPIRED":
                    if order.dropoff_lat and order.dropoff_lat != 0:
                        await self.bot.send_location(chat_id, order.dropoff_lat, order.dropoff_lng)
                    break

                interval = self._get_interval(order.booking_state)
                await self._sleep_or_wake(token, interval)
        finally:
            self.active.pop(token, None)
            self._forget_booking(token)
            self.slots.release(token)
            if slot is not None:
                self.mqtt.set_slot_availability(slot, False)

    def _forget_booking(self, token: str):
        for code, owner in list(self.booking_codes.items()):
            if owner == token:
                del self.booking_codes[code]

    def _slot_state(self, order) -> dict:
        """Per-slot JSON state payload published to MQTT (consumed by all of that slot's
        HA entities via value_template / json_attributes)."""
        state = {
            "status": order.friendly_status,
            "booking_state": order.booking_state,
            "booking_code": order.booking_code,
            "eta_minutes": order.eta_minutes or 0,
            "eta_time": order.eta_time_str,
            "delivery_time": order.delivery_time_str,
            "driver_name": order.driver_name,
            "driver_rating": order.driver_rating,
            "vehicle": order.vehicle,
            "pickup": order.pickup_name,
            "dropoff": order.dropoff_name,
            "is_terminal": order.is_terminal,
            "tracker_state": "not_home",
        }
        if order.has_driver_loc:
            state["latitude"] = order.driver_lat
            state["longitude"] = order.driver_lng
            state["gps_accuracy"] = 50
        return state

    async def _sleep_or_wake(self, token: str, interval: int):
        """Sleep up to `interval` seconds, but return early if /poll wakes this order."""
        wake = self.active.get(token, {}).get("wake")
        if wake is None:
            await asyncio.sleep(interval)
            return
        try:
            await asyncio.wait_for(wake.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
        finally:
            wake.clear()

    async def _maybe_send_driver_location(self, token, chat_id, order, settings):
        """Send a driver location pin, honouring the configurable settings:
        `send_driver_location` (on/off) and `location_min_move_meters` (throttle by
        distance moved since the last pin)."""
        if settings.get("send_driver_location") != "1":
            return

        try:
            min_move = float(settings.get("location_min_move_meters") or 0)
        except (TypeError, ValueError):
            min_move = 0.0

        last = self.active.get(token, {}).get("last_sent_loc")
        if last and min_move > 0:
            moved = _haversine_m(last[0], last[1], order.driver_lat, order.driver_lng)
            if moved < min_move:
                return

        await self.bot.send_location(chat_id, order.driver_lat, order.driver_lng)
        if token in self.active:
            self.active[token]["last_sent_loc"] = (order.driver_lat, order.driver_lng)

    async def _send_debug(self, chat_id, order, poll_count):
        """Debug message — gated by the `debug_messages` setting."""
        text = f"🔍 *DEBUG Semakan #{poll_count}*\n"
        text += f"`bookingState: {order.booking_state}`\n"
        text += f"`sessionStatus: {order.session_status}`\n"
        text += f"`driverName: {order.driver_name or 'null'}`\n"
        text += f"`vehicleModel: {order.vehicle_model or 'null'}`\n"
        text += f"`vehiclePlate: {order.vehicle_plate or 'null'}`\n"
        text += f"`driverLat: {order.driver_lat or 'null'}`\n"
        text += f"`driverLng: {order.driver_lng or 'null'}`\n"
        text += f"`ETA unix: {order.eta_unix or 'null'}`\n"
        text += f"`ETA time: {order.eta_time_str or 'null'}`"
        await self.bot.send_text(chat_id, text, parse_mode="Markdown")

    async def _send_status_update(self, chat_id, order, poll_count):
        icon = STATUS_ICONS.get(order.booking_state, "📦")
        text = f"{icon} *{order.friendly_status}*\n\n"
        if order.driver_name:
            text += f"*Pemandu:* {order.driver_name}"
            if order.driver_rating:
                text += f" ⭐ {order.driver_rating}"
            text += "\n"
        if order.vehicle:
            text += f"*Kenderaan:* {order.vehicle}\n"
        if order.pickup_name:
            text += f"*Dari:* {order.pickup_name}\n"
        if order.dropoff_name:
            text += f"*Ke:* {order.dropoff_name}\n"
        if not order.is_terminal and order.eta_minutes and order.eta_minutes > 0:
            text += f"*Anggaran tiba:* {order.eta_minutes} min"
            if order.eta_time_str:
                text += f" ({order.eta_time_str})"
            text += "\n"
        if order.is_terminal:
            text += f"*Dihantar pada:* {order.delivery_time_str}\n"
        text += f"\n_Semakan #{poll_count}_"
        await self.bot.send_text(chat_id, text, parse_mode="Markdown")

    async def _send_eta_update(self, chat_id, order, poll_count):
        if order.is_terminal or not order.eta_minutes or order.eta_minutes <= 0:
            return
        icon = STATUS_ICONS.get(order.booking_state, "📦")
        text = f"{icon} *{order.friendly_status}*\n"
        text += f"⏱ *Anggaran tiba:* {order.eta_minutes} min"
        if order.eta_time_str:
            text += f" ({order.eta_time_str})"
        text += f"\n_Semakan #{poll_count}_"
        await self.bot.send_text(chat_id, text, parse_mode="Markdown")
