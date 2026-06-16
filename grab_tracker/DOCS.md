# Grab Tracker

Track your Grab food and ride orders in Home Assistant and Telegram. Forward a Grab
"share" link to your Telegram bot (or paste it into the add-on's web UI) and the add-on
follows the order live — pushing status updates, ETA, and the driver's location to
Telegram, mirroring everything into Home Assistant sensors (via MQTT), and keeping a
history you can browse in the add-on's web UI.

## What you need

1. **A Telegram bot token** — create a bot with [@BotFather](https://t.me/BotFather) and
   copy the token.
2. **A Home Assistant long-lived access token** — Profile → Security → Long-lived access
   tokens. Used to read your HA timezone so times display correctly.
3. **An MQTT broker + the MQTT integration** — e.g. the Mosquitto broker add-on. Required
   for the Home Assistant sensors. Without one, Telegram tracking still works; only the HA
   entities are skipped.

## Setup

1. Install and open **Configuration**.
2. Fill in `telegram_bot_token` and `ha_token` (and `ha_url` if not the default).
3. Set `notify_chat_id` to your Telegram chat ID if you want a "started" message on boot,
   and so web-initiated tracking has somewhere to send updates (a bot cannot message a
   chat it has never seen).
4. Point the add-on at your broker with `mqtt_host` / `mqtt_port` / `mqtt_username` /
   `mqtt_password`. **Leave `mqtt_host` blank** to auto-discover the broker from the
   Supervisor (works with the Mosquitto add-on).
5. (Optional) Set `allowed_chat_ids` to lock the bot to specific chats.
6. **Start** the add-on.

## How to use it

**From Telegram:** send your bot a Grab share link (`https://app.grab.com/s/...`). The
add-on resolves it, confirms tracking has started, and updates you on every status change
plus periodic ETA/driver-location messages until the order is delivered, cancelled, or
times out.

**From the web UI:** open the add-on panel, paste a Grab link into *Track a New Order*,
and press **Track** (the button enables once the link looks like a Grab URL). Updates go
to your `notify_chat_id` if one is set.

You can track up to **`max_concurrent_orders`** orders at once (default 5). A further order
is politely rejected until a slot frees up. The same order sent twice is detected and not
double-tracked.

### Telegram commands

Type `/` in the chat to see the menu:

| Command | What it does |
|---------|--------------|
| `/list` | List active orders, each with **Refresh** and **Stop** buttons |
| `/poll` | Force an immediate status check (skip the wait) |
| `/config` | Toggle settings (debug messages, driver location pins) |
| `/restart` | Stop all tracking and clear the cache |
| `/help` | Show the command list |

## Home Assistant entities

All entities live under a single device named **Grab Tracker**:

- For each order slot (1–N): **Status**, **ETA** (min), **Delivery Time**, and a
  **Driver** device_tracker (shown on the map while en route).
- **Config controls** (editable from HA): *Debug messages* (switch), *Driver location
  pins* (switch), *Driver pin min move* (number, metres).

A slot's entities are **unavailable** while idle and become available only while that slot
is actively tracking an order. Changing a config control in HA, in `/config`, or in the
web UI keeps all three in sync.

## Web UI

Open the add-on's panel (sidebar) for a dashboard showing:

- **Track a New Order** — paste a Grab share link and press Track.
- **Active Tracking** — currently-tracked orders with Refresh / Stop.
- **Order history** — recent orders; click a row to expand its event timeline, or use 🗑
  to delete a record.
- **Settings** — the same toggles as `/config`.

## Configuration reference

| Option | Default | Description |
|--------|---------|-------------|
| `telegram_bot_token` | — | BotFather token (required) |
| `ha_token` | — | HA long-lived token, for timezone (required) |
| `ha_url` | `http://homeassistant:8123` | HA base URL |
| `notify_chat_id` | — | Chat ID for startup + web-initiated updates (optional) |
| `allowed_chat_ids` | — | Comma-separated chat IDs allowed to use the bot; blank = open to all |
| `poll_interval_prepare` | 120 | Poll seconds while preparing / driver assigned |
| `poll_interval_executing` | 30 | Poll seconds while the driver is en route |
| `poll_interval_default` | 180 | Poll seconds for other states |
| `max_tracking_timeout` | 7200 | Give up tracking after this many seconds (2h) |
| `max_concurrent_orders` | 5 | Max simultaneously-tracked orders |
| `history_limit` | 50 | Order history cap (oldest dropped first, FIFO) |
| `log_level` | `info` | `trace`/`debug`/`info`/`notice`/`warning`/`error`/`fatal` |
| `mqtt_host` | — | Broker host; blank = Supervisor auto-discovery |
| `mqtt_port` | 1883 | Broker port |
| `mqtt_username` / `mqtt_password` | — | Broker credentials |

## Good to know

- **A restart stops all tracking.** In-progress orders are not resumed after an add-on
  restart — they are marked stopped. Re-send the link to track again.
- **History is capped** at `history_limit` (FIFO) — the oldest record is removed once the
  cap is reached, no purge needed.
- **No broker?** The add-on still runs; Telegram works and HA sensors are simply skipped.

## Troubleshooting

- **No HA sensors:** check `mqtt_host`/credentials, that your broker is running, and that
  the MQTT integration points at the same broker. The log prints `MQTT connected to …` or
  a warning.
- **No startup message / web tracking is silent:** set `notify_chat_id`.
- **Command menu missing in Telegram:** reopen the chat — Telegram caches the menu.
- **Bot ignores me:** if `allowed_chat_ids` is set, your chat ID must be in the list.
- **Too much/too little logging:** adjust `log_level`.
