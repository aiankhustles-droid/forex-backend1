import os
import time
import json
import threading
import urllib.request
import urllib.parse
from datetime import datetime
from flask import Flask, jsonify, request

app = Flask(__name__)

API_KEY = "103109b9297f45a1a2875721dd1e9cc1"
TWELVE_BASE = "https://api.twelvedata.com"

@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

@app.route("/", methods=["OPTIONS"])
@app.route("/<path:path>", methods=["OPTIONS"])
def options(path=""):
    return jsonify({}), 200

_cache = {}

def get_cache(key):
    if key in _cache:
        e = _cache[key]
        if time.time() - e["ts"] < e["ttl"]:
            return e["data"]
        del _cache[key]
    return None

def set_cache(key, data, ttl):
    _cache[key] = {"data": data, "ts": time.time(), "ttl": ttl}

def fetch(endpoint, params):
    params["apikey"] = API_KEY
    url = f"{TWELVE_BASE}/{endpoint}?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ForexAI/1.0"})
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"status": "error", "message": str(e)}

_ping_count = 0
_last_ping = None

def keep_alive_loop():
    global _ping_count, _last_ping
    time.sleep(30)
    while True:
        try:
            port = int(os.environ.get("PORT", 10000))
            urllib.request.urlopen(f"http://localhost:{port}/ping", timeout=5)
            _ping_count += 1
            _last_ping = datetime.now().isoformat()
            print(f"[KEEP-ALIVE] Ping #{_ping_count} at {_last_ping}")
        except Exception as e:
            print(f"[KEEP-ALIVE] Failed: {e}")
        time.sleep(240)

@app.route("/")
@app.route("/health")
def health():
    return jsonify({
        "status": "online",
        "server": "NEXUS FX·AI — Render Backend",
        "time": datetime.now().isoformat(),
        "ping_count": _ping_count,
        "last_ping": _last_ping,
        "always_alive": True,
        "message": "Backend is live!"
    })

@app.route("/ping")
def ping():
    return jsonify({"alive": True, "time": datetime.now().isoformat()})

@app.route("/candles")
def candles():
    symbol = request.args.get("symbol", "EUR/USD")
    interval = request.args.get("interval", "5min")
    outputsize = int(request.args.get("outputsize", 150))
    ttl_map = {"1min":30,"5min":60,"15min":120,"1h":300,"4h":600,"1day":1800}
    key = f"c_{symbol}_{interval}_{outputsize}"
    cached = get_cache(key)
    if cached:
        return jsonify({**cached, "source":"cache"})

    data = fetch("time_series", {
        "symbol": symbol, "interval": interval,
        "outputsize": outputsize, "format": "JSON"
    })

    if data.get("status") == "error" or "values" not in data:
        return jsonify({"error": data.get("message","No data")}), 400

    result_candles = []
    for v in reversed(data["values"]):
        try:
            dt = v["datetime"]
            ts = int(datetime.strptime(dt, "%Y-%m-%d %H:%M:%S").timestamp()*1000) \
                 if " " in dt else \
                 int(datetime.strptime(dt, "%Y-%m-%d").timestamp()*1000)
            result_candles.append({
                "time": float(ts), "open": float(v["open"]),
                "high": float(v["high"]), "low": float(v["low"]),
                "close": float(v["close"]), "volume": float(v.get("volume",0))
            })
        except:
            continue

    result = {
        "symbol": symbol, "interval": interval,
        "count": len(result_candles), "candles": result_candles,
        "fetched_at": datetime.now().isoformat(), "source": "live"
    }
    set_cache(key, result, ttl_map.get(interval, 60))
    return jsonify(result)

@app.route("/quote")
def quote():
    symbol = request.args.get("symbol", "EUR/USD")
    key = f"q_{symbol}"
    cached = get_cache(key)
    if cached:
        return jsonify({**cached, "source":"cache"})

    data = fetch("quote", {"symbol": symbol})
    if data.get("status") == "error":
        return jsonify({"error": data.get("message","No quote")}), 400

    result = {
        "symbol": symbol, "price": float(data.get("close",0)),
        "change": float(data.get("change",0)),
        "percent_change": float(data.get("percent_change",0)),
        "name": data.get("name", symbol),
        "fetched_at": datetime.now().isoformat(), "source": "live"
    }
    set_cache(key, result, 15)
    return jsonify(result)

@app.route("/news")
def news():
    now_ms = int(time.time()*1000)
    h = 3600000
    events = [
        {"name":"USD Non-Farm Payrolls",    "impact":"HIGH",   "currency":"USD","time":now_ms+h*2},
        {"name":"EUR CPI Flash Estimate",   "impact":"HIGH",   "currency":"EUR","time":now_ms+h*5},
        {"name":"GBP Manufacturing PMI",    "impact":"MEDIUM", "currency":"GBP","time":now_ms-h},
        {"name":"USD Fed Interest Rate",    "impact":"HIGH",   "currency":"USD","time":now_ms+h*8},
        {"name":"EUR ECB Press Conference", "impact":"HIGH",   "currency":"EUR","time":now_ms+h*24},
        {"name":"GBP CPI y/y",             "impact":"HIGH",   "currency":"GBP","time":now_ms+h*12},
    ]
    return jsonify({"events": sorted(events, key=lambda e: e["time"]), "source":"simulated"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    threading.Thread(target=keep_alive_loop, daemon=True).start()
    print(f"\n✅ NEXUS FX·AI Backend running on port {port}\n")
    app.run(host="0.0.0.0", port=port)
