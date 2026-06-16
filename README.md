# Grab Tracker — Home Assistant Add-on

Track your Grab food and ride orders in Home Assistant and Telegram. Forward a Grab
"share" link to your Telegram bot (or paste it into the add-on's web UI) and the add-on
follows the order live — pushing status updates, ETA, and the driver's location to
Telegram, mirroring everything into Home Assistant entities via MQTT, and keeping a
browsable history.

## Features

- 🛵 Live order tracking from a Grab share link (Telegram **or** web UI)
- 📦 Up to 5 simultaneous orders (configurable), each a slot under one HA MQTT device
- 🗺️ Driver location pushed to Telegram and a HA `device_tracker`
- 🔔 Status, ETA and delivery-time entities via MQTT Discovery
- 🤖 Telegram commands (`/list`, `/poll`, `/config`, `/restart`, `/help`) + optional
  chat allowlist
- 🌐 Ingress web UI: track new orders, manage active ones, browse/delete history,
  toggle settings
- ⚙️ Config controls exposed as HA entities; FIFO history cap; standard log levels

## Installation

1. In Home Assistant: **Settings → Add-ons → Add-on Store → ⋮ → Repositories**.
2. Add this repository URL:
   ```
   https://github.com/anas-ivs/HA-Grab-Tracker
   ```
3. Install **Grab Tracker** from the store, configure it, and start.

## Requirements

- A Telegram bot token ([@BotFather](https://t.me/BotFather))
- A Home Assistant long-lived access token (for timezone)
- An MQTT broker + the MQTT integration (e.g. the Mosquitto add-on) — optional; without
  it, Telegram tracking still works and HA entities are skipped.

## Configuration & usage

See the add-on's **Documentation** tab (rendered from
[`grab_tracker/DOCS.md`](grab_tracker/DOCS.md)) for the full option reference, Telegram
commands, entity list, and troubleshooting.

## License

[MIT](LICENSE)
