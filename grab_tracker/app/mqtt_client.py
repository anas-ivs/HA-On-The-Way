import asyncio
import json
import logging
import paho.mqtt.client as mqtt

_LOGGER = logging.getLogger(__name__)

DISCOVERY_PREFIX = "homeassistant"   # HA MQTT discovery default
BASE = "grabtracker"
BRIDGE_AVAILABILITY = f"{BASE}/bridge/availability"
CONFIG_SET = f"{BASE}/config/+/set"   # subscription for config commands

DEVICE_ID = "grab_tracker"

# Settings exposed as controllable MQTT "config" entities (HA entity_category: config).
#   key -> (component, discovery payload extras)
CONFIG_ENTITIES = {
    "debug_messages": ("switch", {
        "name": "Mesej nyahpepijat", "icon": "mdi:bug",
        "payload_on": "1", "payload_off": "0", "state_on": "1", "state_off": "0",
    }),
    "send_driver_location": ("switch", {
        "name": "Pin lokasi pemandu", "icon": "mdi:map-marker",
        "payload_on": "1", "payload_off": "0", "state_on": "1", "state_off": "0",
    }),
    "location_min_move_meters": ("number", {
        "name": "Jarak min pin pemandu", "icon": "mdi:ruler",
        "min": 0, "max": 5000, "step": 10, "mode": "box", "unit_of_measurement": "m",
    }),
}


class MqttClient:
    """Publishes Grab order state to Home Assistant via MQTT Discovery.

    All entities live under ONE device ("Grab Tracker"): for each of the N slots a
    status / ETA / delivery-time sensor and a driver device_tracker, plus a set of
    controllable "config" entities mirroring the add-on settings. State + discovery are
    retained so entities survive HA restarts. Slot entities use dual availability
    (bridge + slot, mode `all`) so an idle slot reads unavailable.
    """

    def __init__(self, host, port=1883, username=None, password=None, ssl=False,
                 slots=5, version="unknown"):
        self.slots = int(slots)
        self.version = version
        self._host = host
        self._port = int(port)
        self._loop = None        # main asyncio loop (for config commands)
        self._apply = None       # async fn(key, value) applied on config command
        self._c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="grab_tracker")
        if username:
            self._c.username_pw_set(username, password)
        if ssl:
            self._c.tls_set()
        self._c.will_set(BRIDGE_AVAILABILITY, "offline", retain=True)
        self._c.reconnect_delay_set(min_delay=1, max_delay=60)
        self._c.on_connect = self._on_connect
        self._c.on_message = self._on_message

    # ---- lifecycle ----
    def set_command_handler(self, loop, apply_coro):
        """Register the main loop + an `async fn(key, value)` to run when HA changes a
        config entity. Must be called before start() so on_connect subscribes."""
        self._loop = loop
        self._apply = apply_coro

    def start(self):
        # Blocking connect so callers know the broker is reachable; loop_start() then
        # handles reconnects in a background thread.
        self._c.connect(self._host, self._port, keepalive=60)
        self._c.loop_start()

    def stop(self):
        try:
            self._c.publish(BRIDGE_AVAILABILITY, "offline", retain=True)
            self._c.loop_stop()
            self._c.disconnect()
        except Exception as e:
            _LOGGER.warning(f"MQTT stop error: {e}")

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        client.publish(BRIDGE_AVAILABILITY, "online", retain=True)
        self._clear_legacy_discovery()
        for n in range(1, self.slots + 1):
            self._publish_slot_discovery(n)
        self._publish_config_discovery()
        client.subscribe(CONFIG_SET)

    def _clear_legacy_discovery(self):
        """Remove the v1.3.0 per-slot devices: that release published one device per slot
        at `homeassistant/<comp>/grab_order_<n>/<obj>/config`. Those retained configs
        persist on the broker and would otherwise still show as separate devices, so we
        clear them with empty retained payloads. Clear a generous range in case the slot
        count was higher before."""
        legacy = [("sensor", "status"), ("sensor", "eta"),
                  ("sensor", "delivery_time"), ("device_tracker", "driver")]
        for n in range(1, max(self.slots, 10) + 1):
            for comp, obj in legacy:
                self._c.publish(
                    f"{DISCOVERY_PREFIX}/{comp}/grab_order_{n}/{obj}/config",
                    "", retain=True,
                )

    def _on_message(self, client, userdata, msg):
        # topic: grabtracker/config/<key>/set
        parts = msg.topic.split("/")
        if len(parts) < 4:
            return
        key = parts[-2]
        value = msg.payload.decode(errors="ignore").strip()
        if self._loop and self._apply and key in CONFIG_ENTITIES:
            asyncio.run_coroutine_threadsafe(self._apply(key, value), self._loop)

    # ---- topics / device ----
    def _state_topic(self, n):
        return f"{BASE}/slot{n}/state"

    def _avail_topic(self, n):
        return f"{BASE}/slot{n}/availability"

    def _config_state_topic(self, key):
        return f"{BASE}/config/{key}/state"

    def _config_set_topic(self, key):
        return f"{BASE}/config/{key}/set"

    def _device(self):
        return {
            "identifiers": [DEVICE_ID],
            "name": "On the way",
            "manufacturer": "On the way",
            "model": "Penjejak Pesanan",
            "sw_version": self.version,
        }

    # ---- discovery ----
    def _publish_slot_discovery(self, n):
        state = self._state_topic(n)
        common = {
            "availability": [
                {"topic": BRIDGE_AVAILABILITY},
                {"topic": self._avail_topic(n)},
            ],
            "availability_mode": "all",
            "device": self._device(),
        }
        self._pub_cfg("sensor", f"grab_order_{n}_status", {
            **common, "name": f"Pesanan {n} Status", "unique_id": f"grab_order_{n}_status",
            "object_id": f"grab_order_{n}_status",
            "state_topic": state, "value_template": "{{ value_json.status }}",
            "json_attributes_topic": state, "icon": "mdi:moped",
        })
        self._pub_cfg("sensor", f"grab_order_{n}_eta", {
            **common, "name": f"Pesanan {n} Anggaran Tiba", "unique_id": f"grab_order_{n}_eta",
            "object_id": f"grab_order_{n}_eta",
            "state_topic": state, "value_template": "{{ value_json.eta_minutes | default(0) }}",
            "unit_of_measurement": "min", "icon": "mdi:timer-outline",
        })
        self._pub_cfg("sensor", f"grab_order_{n}_delivery_time", {
            **common, "name": f"Pesanan {n} Masa Penghantaran",
            "unique_id": f"grab_order_{n}_delivery_time",
            "object_id": f"grab_order_{n}_delivery_time",
            "state_topic": state, "value_template": "{{ value_json.delivery_time }}",
            "icon": "mdi:clock-check-outline",
        })
        self._pub_cfg("device_tracker", f"grab_order_{n}_driver", {
            **common, "name": f"Pesanan {n} Pemandu", "unique_id": f"grab_order_{n}_driver",
            "object_id": f"grab_order_{n}_driver",
            "state_topic": state, "value_template": "{{ value_json.tracker_state }}",
            "json_attributes_topic": state, "source_type": "gps",
        })

    def _publish_config_discovery(self):
        for key, (component, extras) in CONFIG_ENTITIES.items():
            payload = {
                **extras,
                "unique_id": f"{DEVICE_ID}_{key}",
                "object_id": f"{DEVICE_ID}_{key}",
                "device": self._device(),
                "availability": [{"topic": BRIDGE_AVAILABILITY}],
                "entity_category": "config",
                "state_topic": self._config_state_topic(key),
                "command_topic": self._config_set_topic(key),
            }
            self._pub_cfg(component, f"{DEVICE_ID}_{key}", payload)

    def _pub_cfg(self, component, node, payload):
        topic = f"{DISCOVERY_PREFIX}/{component}/{node}/config"
        self._c.publish(topic, json.dumps(payload), retain=True)

    # ---- runtime ----
    def set_slot_availability(self, n, online: bool):
        self._c.publish(self._avail_topic(n), "online" if online else "offline", retain=True)

    def publish_slot_state(self, n, state: dict):
        self._c.publish(self._state_topic(n), json.dumps(state), retain=True)

    def publish_config_state(self, key, value):
        self._c.publish(self._config_state_topic(key), str(value), retain=True)

    def publish_all_config_states(self, settings: dict):
        for key in CONFIG_ENTITIES:
            if key in settings:
                self.publish_config_state(key, settings[key])


class NullMqttClient:
    """No-op fallback used when no broker is reachable — tracking/Telegram still work,
    HA sensors are simply not published."""

    def set_command_handler(self, *a, **k): pass
    def start(self): pass
    def stop(self): pass
    def set_slot_availability(self, *a, **k): pass
    def publish_slot_state(self, *a, **k): pass
    def publish_config_state(self, *a, **k): pass
    def publish_all_config_states(self, *a, **k): pass
