import aiosqlite
from datetime import datetime, timezone

DB_PATH = "/data/grab_tracker.db"

# Runtime settings editable from the web UI. Stored as TEXT in the settings table.
DEFAULT_SETTINGS = {
    "send_driver_location": "1",      # "1"/"0" — send Telegram driver location pins
    "location_min_move_meters": "0",  # only send a pin once the driver moves >= N metres (0 = every poll)
    "debug_messages": "0",            # "1"/"0" — send raw per-poll debug messages to Telegram
}

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT NOT NULL UNIQUE,
                chat_id TEXT NOT NULL,
                booking_code TEXT,
                current_state TEXT,
                friendly_status TEXT,
                driver_name TEXT,
                vehicle TEXT,
                pickup_name TEXT,
                dropoff_name TEXT,
                started_at TEXT,
                completed_at TEXT,
                is_terminal INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS order_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER,
                booking_state TEXT,
                friendly_status TEXT,
                eta_minutes INTEGER,
                eta_time_str TEXT,
                driver_lat REAL,
                driver_lng REAL,
                recorded_at TEXT,
                FOREIGN KEY(order_id) REFERENCES orders(id)
            )
        """)
        await db.commit()

async def _trim_history(db, limit: int):
    """FIFO cap: keep only the newest `limit` orders, deleting older ones + their events."""
    if not limit or limit <= 0:
        return
    await db.execute(
        "DELETE FROM order_events WHERE order_id IN ("
        "  SELECT id FROM orders ORDER BY started_at DESC LIMIT -1 OFFSET ?)",
        (limit,),
    )
    await db.execute(
        "DELETE FROM orders WHERE id IN ("
        "  SELECT id FROM orders ORDER BY started_at DESC LIMIT -1 OFFSET ?)",
        (limit,),
    )

async def upsert_order(token, chat_id, order, history_limit: int = 50) -> int:
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT id FROM orders WHERE token=?", (token,))
        row = await cursor.fetchone()
        is_new = row is None
        if row:
            order_id = row[0]
            await db.execute("""
                UPDATE orders SET current_state=?, friendly_status=?, driver_name=?,
                vehicle=?, is_terminal=?, completed_at=? WHERE id=?
            """, (
                order.booking_state, order.friendly_status, order.driver_name,
                order.vehicle, 1 if order.is_terminal else 0,
                now if order.is_terminal else None, order_id
            ))
        else:
            cursor = await db.execute("""
                INSERT INTO orders (token, chat_id, booking_code, current_state,
                friendly_status, driver_name, vehicle, pickup_name, dropoff_name, started_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                token, chat_id, order.booking_code, order.booking_state,
                order.friendly_status, order.driver_name, order.vehicle,
                order.pickup_name, order.dropoff_name, now
            ))
            order_id = cursor.lastrowid

        await db.execute("""
            INSERT INTO order_events
            (order_id, booking_state, friendly_status, eta_minutes, eta_time_str,
             driver_lat, driver_lng, recorded_at)
            VALUES (?,?,?,?,?,?,?,?)
        """, (
            order_id, order.booking_state, order.friendly_status,
            order.eta_minutes, order.eta_time_str,
            order.driver_lat, order.driver_lng, now
        ))
        if is_new:
            await _trim_history(db, history_limit)
        await db.commit()
        return order_id

async def get_recent_orders(limit=20):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM orders ORDER BY started_at DESC LIMIT ?", (limit,)
        )
        return [dict(r) for r in await cursor.fetchall()]

async def close_open_orders() -> int:
    """Mark all non-terminal orders as stopped. Called on startup: an add-on restart
    explicitly ENDS all in-flight tracking — nothing is resumed. Returns rows closed."""
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE orders SET is_terminal=1, completed_at=? WHERE is_terminal=0",
            (now,),
        )
        await db.commit()
        return cursor.rowcount

async def close_order(token: str) -> int:
    """Mark a single order terminal (used by kill/stop)."""
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE orders SET is_terminal=1, completed_at=? WHERE token=? AND is_terminal=0",
            (now, token),
        )
        await db.commit()
        return cursor.rowcount

async def get_order_token(order_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT token FROM orders WHERE id=?", (order_id,))
        row = await cursor.fetchone()
        return row[0] if row else None

async def delete_order(order_id) -> int:
    """Delete an order and its event history. Returns rows deleted from `orders`."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM order_events WHERE order_id=?", (order_id,))
        cursor = await db.execute("DELETE FROM orders WHERE id=?", (order_id,))
        await db.commit()
        return cursor.rowcount

async def get_order_events(order_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM order_events WHERE order_id=? ORDER BY recorded_at ASC", (order_id,)
        )
        return [dict(r) for r in await cursor.fetchall()]

async def get_settings() -> dict:
    """Return all settings, merged over defaults so callers always get every key."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT key, value FROM settings")
        stored = {k: v for k, v in await cursor.fetchall()}
    return {**DEFAULT_SETTINGS, **stored}

async def set_settings(updates: dict):
    """Upsert only known setting keys; ignore anything else the client sends."""
    async with aiosqlite.connect(DB_PATH) as db:
        for key, value in updates.items():
            if key not in DEFAULT_SETTINGS:
                continue
            await db.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value)),
            )
        await db.commit()
