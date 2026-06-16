import aiohttp
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

# Known-but-not-yet-supported services → friendly label (substring match on the URL/text).
UNSUPPORTED_SERVICES = {
    "foodpanda": "foodpanda",
    "panda.link": "foodpanda",
    "shopee": "Shopee",
    "shp.ee": "Shopee",
    "lalamove": "Lalamove",
    "maxim": "Maxim",
    "deliveroo": "Deliveroo",
}

def detect_service(text: str):
    """Classify a pasted link/text. Returns ('grab', None) | ('unsupported', label) |
    ('invalid', None). Grab takes priority (covers grabfood/grabexpress share links)."""
    t = (text or "").lower()
    if "grab" in t:
        return ("grab", None)
    for kw, label in UNSUPPORTED_SERVICES.items():
        if kw in t:
            return ("unsupported", label)
    return ("invalid", None)

API_URL = "https://api.grab.com/api/v1/safety/sharemyride/{token}/bookingdetails?fullData=true"
HEADERS = {
    "accept": "application/json, text/plain, */*",
    "origin": "https://sharelocation.grab.com",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
}

STATUS_MAP = {
    "QUEUEING":         "Pesanan Dibuat",
    "ALLOCATING":       "Mencari Pemandu",
    "PICKING_UP":       "Pemandu Dalam Perjalanan",
    "IN_DELIVERY":      "Pesanan Diambil",
    "ORDER_IN_PREPARE": "Menyediakan Pesanan Anda",
    "ORDER_EXECUTING":  "Pemandu Dalam Perjalanan",
    "COMPLETED":        "Telah Dihantar",
    "CANCELLED":        "Dibatalkan",
}

TERMINAL_STATES = {"COMPLETED", "CANCELLED"}

POLL_INTERVALS = {
    "ORDER_IN_PREPARE": "prepare",
    "PICKING_UP":       "prepare",
    "ORDER_EXECUTING":  "executing",
    "IN_DELIVERY":      "executing",
}

@dataclass
class OrderData:
    token: str
    booking_code: str
    booking_state: str
    friendly_status: str
    is_terminal: bool
    session_status: str
    driver_name: Optional[str]
    driver_rating: Optional[float]
    driver_lat: Optional[float]
    driver_lng: Optional[float]
    has_driver_loc: bool
    vehicle_model: Optional[str]
    vehicle_plate: Optional[str]
    vehicle: Optional[str]
    pickup_name: Optional[str]
    dropoff_name: Optional[str]
    dropoff_lat: Optional[float]
    dropoff_lng: Optional[float]
    eta_unix: Optional[int]
    eta_minutes: Optional[int]
    eta_time_str: Optional[str]
    delivery_time_str: str
    complete_time: Optional[str]
    raw_response: dict

async def resolve_token(short_url: str) -> str:
    async with aiohttp.ClientSession() as session:
        async with session.get(short_url, allow_redirects=True) as resp:
            final_url = str(resp.url)
    match = re.search(r'shareOrderLink=([^&]+)', final_url)
    if not match:
        raise ValueError(f"shareOrderLink not found in: {final_url}")
    return match.group(1)

def fmt_time(unix_ts: int, tz: ZoneInfo) -> str:
    """Format unix timestamp to local 12hr time using the provided timezone."""
    dt = datetime.fromtimestamp(unix_ts, tz=tz)
    return dt.strftime("%I:%M %p").lstrip("0").lower()

async def fetch_order(token: str, tz: ZoneInfo) -> OrderData:
    url = API_URL.format(token=token)
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=HEADERS) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"Grab API HTTP {resp.status}: {body[:200]}")
            ctype = resp.headers.get("Content-Type", "")
            if "json" not in ctype.lower():
                body = await resp.text()
                raise RuntimeError(f"Grab API returned non-JSON ({ctype}): {body[:200]}")
            data = await resp.json()

    b = data.get("booking", {})
    d = data.get("driver", {})
    pickup = b.get("pickup", {})
    dropoff_b = b.get("dropOff", {})
    driver_loc = d.get("location", {})
    dropoff_loc = dropoff_b.get("location", {})
    route = data.get("route", {})

    state = b.get("bookingState", "UNKNOWN")
    is_terminal = state in TERMINAL_STATES

    driver_lat = driver_loc.get("latitude")
    driver_lng = driver_loc.get("longitude")
    has_driver_loc = bool(driver_lat and driver_lat != 0 and driver_lng and driver_lng != 0)

    eta_unix = route.get("ETA")
    now_ms = time.time() * 1000
    eta_minutes = None
    eta_time_str = None
    if eta_unix:
        eta_minutes = max(0, round((eta_unix * 1000 - now_ms) / 60000))
        eta_time_str = fmt_time(eta_unix, tz)

    raw_complete = b.get("completeTime") or b.get("driverArrivalTime")
    if is_terminal and raw_complete:
        ts = int(datetime.fromisoformat(raw_complete.replace("Z", "+00:00")).timestamp())
        delivery_time_str = fmt_time(ts, tz)
    elif eta_time_str:
        delivery_time_str = eta_time_str
    else:
        delivery_time_str = "N/A"

    vehicle_model = d.get("vehicleModel")
    vehicle_plate = d.get("vehiclePlateNumber")
    vehicle = f"{vehicle_model} {vehicle_plate}" if vehicle_model and vehicle_plate else None

    return OrderData(
        token=token,
        booking_code=b.get("bookingCode", ""),
        booking_state=state,
        friendly_status=STATUS_MAP.get(state, state),
        is_terminal=is_terminal,
        session_status=data.get("sessionStatus", "UNKNOWN"),
        driver_name=d.get("name"),
        driver_rating=d.get("rating"),
        driver_lat=driver_lat if has_driver_loc else None,
        driver_lng=driver_lng if has_driver_loc else None,
        has_driver_loc=has_driver_loc,
        vehicle_model=vehicle_model,
        vehicle_plate=vehicle_plate,
        vehicle=vehicle,
        pickup_name=pickup.get("keywords"),
        dropoff_name=dropoff_b.get("keywords"),
        dropoff_lat=dropoff_loc.get("latitude"),
        dropoff_lng=dropoff_loc.get("longitude"),
        eta_unix=eta_unix,
        eta_minutes=eta_minutes if not is_terminal else 0,
        eta_time_str=eta_time_str,
        delivery_time_str=delivery_time_str,
        complete_time=raw_complete,
        raw_response=data
    )
