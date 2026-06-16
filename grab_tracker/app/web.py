from flask import Flask, render_template, jsonify, request
import asyncio
import database
from version import VERSION

app = Flask(__name__)

_tracker = None   # set by run_web()
_loop = None      # main asyncio loop, for cross-thread calls into the tracker


def _call(coro):
    """Run a tracker coroutine on the main asyncio loop from the Flask thread."""
    return asyncio.run_coroutine_threadsafe(coro, _loop).result(timeout=30)


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/version")
def version():
    return jsonify({"version": VERSION})

@app.route("/api/orders")
def orders():
    return jsonify(asyncio.run(database.get_recent_orders()))

@app.route("/api/orders/<int:order_id>/events")
def events(order_id):
    return jsonify(asyncio.run(database.get_order_events(order_id)))

@app.route("/api/orders/<int:order_id>", methods=["DELETE"])
def delete_order(order_id):
    # Stop tracking first (if active) so the poll loop can't re-insert the row.
    token = asyncio.run(database.get_order_token(order_id))
    if token and _tracker is not None:
        try:
            _call(_tracker.api_kill(token))
        except Exception:
            pass
    deleted = asyncio.run(database.delete_order(order_id))
    return jsonify({"ok": deleted > 0})

@app.route("/api/track", methods=["POST"])
def track():
    data = request.get_json(force=True, silent=True) or {}
    url = (data.get("url") or "").strip()
    if "grab" not in url.lower():
        return jsonify({"ok": False, "message": "URL mesti pautan kongsi Grab."}), 400
    if _tracker is None:
        return jsonify({"ok": False, "message": "Penjejak tidak tersedia."}), 503
    ok, message = _call(_tracker.api_track(url))
    return jsonify({"ok": ok, "message": message})

@app.route("/api/active")
def active():
    if _tracker is None:
        return jsonify([])
    return jsonify(_call(_tracker.api_list_active()))

@app.route("/api/active/<path:token>/refresh", methods=["POST"])
def refresh_active(token):
    ok = _call(_tracker.api_refresh(token)) if _tracker else False
    return jsonify({"ok": bool(ok)})

@app.route("/api/active/<path:token>/kill", methods=["POST"])
def kill_active(token):
    ok = _call(_tracker.api_kill(token)) if _tracker else False
    return jsonify({"ok": bool(ok)})

@app.route("/api/settings", methods=["GET"])
def get_settings():
    return jsonify(asyncio.run(database.get_settings()))

@app.route("/api/settings", methods=["POST"])
def update_settings():
    data = request.get_json(force=True, silent=True) or {}
    if _tracker is not None:
        for key, value in data.items():
            _call(_tracker.api_update_setting(key, str(value)))
    else:
        asyncio.run(database.set_settings(data))
    return jsonify(asyncio.run(database.get_settings()))

def run_web(tracker=None, loop=None):
    global _tracker, _loop
    _tracker = tracker
    _loop = loop
    app.run(host="0.0.0.0", port=8099, debug=False)
