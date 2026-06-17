# Changelog

All notable changes to **On the way** are documented here.
Format loosely follows [Keep a Changelog](https://keepachangelog.com/).

## [1.0.0] — 2026-06-17

First public release. A Home Assistant add-on that tracks delivery/ride orders live and
relays them to Telegram + Home Assistant (via MQTT). Currently supports **Grab** share
links; foodpanda / ShopeeFood / others are planned.

### Features
- **Live order tracking** from a share link — via Telegram or the web UI.
- **Up to 5 simultaneous orders** (configurable), each a slot under one MQTT device,
  with reject-the-6th and duplicate detection.
- **MQTT Discovery entities** per slot: status, ETA, delivery time, **service** label,
  and a GPS **`device_tracker`** (Home Assistant resolves home/away + map from the
  coordinates).
- **Telegram bot:** status/ETA/driver-location updates; commands `/list`, `/poll`,
  `/config`, `/restart`, `/help` (shown via the "/" menu); optional chat allowlist;
  polite "not supported yet" reply for non-Grab links.
- **Web UI (ingress):** track new orders, manage/stop active ones, browse & delete
  history, collapsible settings, mobile-responsive.
- **Config controls exposed as HA entities** (debug toggle, driver-pin toggle, min-move).
- **Bahasa Melayu (Malaysia)** throughout the UI, Telegram and docs.
- **No HA token required** — timezone read from the add-on environment; broker via
  `mqtt_*` options or Supervisor auto-discovery.
- **History capped at 50** (FIFO); standard `log_level` option.
- Unofficial / personal-use disclaimer, privacy note, and non-Grab-brand styling.

### Notes
- Unofficial and not affiliated with or endorsed by Grab Holdings. For personal,
  non-profit use only.

---

## Pre-1.0 development (internal milestones)

Condensed history of the iterative build before the public 1.0.0 baseline:

- **Foundations** — Telegram link intake, adaptive polling, SQLite history, ingress web
  UI, HA timezone handling.
- **Reliability** — Grab API status/error handling, exponential backoff, configurable
  driver-location pins, `device_tracker` state correctness, ingress-relative web fetches.
- **Telegram UX** — startup hello, version surfacing, `/poll` `/restart` `/config`,
  `debug_messages` toggle, `setMyCommands` menu, `/help`.
- **Multi-order + MQTT** — fixed 5-slot pool, MQTT Discovery grouped under one device,
  bidirectional config entities, restart-stops-all semantics, booking-code dedup,
  graceful no-broker fallback.
- **Web UI** — active-tracking management, delete-from-history, "track from web" input
  with link validation, collapsible sections, mobile-responsive layout.
- **Localisation & branding** — full Malaysian Bahasa Melayu; rebranded from "Grab
  Tracker" → "On the way"; scooter/OTW logo; multi-service framing.
- **Hardening for release** — removed the HA long-lived token dependency; per-slot
  Service sensor; GPS `device_tracker` that HA auto-zones; unofficial/personal-use
  disclaimer + privacy note; recoloured off Grab's brand green.
