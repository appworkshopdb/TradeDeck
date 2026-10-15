"""Trading-Tool Backend: Login, Marktdaten, Live-Relay und Strategie-Analyse."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
import websockets
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from strategies import backtest, sma_cross

# --------------------------------------------------------------------------
# Konfiguration (aus .env / Umgebung)
# --------------------------------------------------------------------------
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
APP_SECRET = os.environ.get("APP_SECRET", "")
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "1") == "1"

if len(APP_PASSWORD) < 8 or len(APP_SECRET) < 16:
    raise RuntimeError(
        "APP_PASSWORD (min. 8 Zeichen) und APP_SECRET (min. 16 Zeichen) müssen gesetzt sein."
    )

STATIC_DIR = Path(__file__).parent / "static"
SESSION_DAYS = 7

# Gold: Binance bietet kein XAU/USD, aber PAXG (tokenisiertes Gold, 1 Token = 1 Feinunze).
# Der Kurs folgt dem Goldpreis eng, ist aber kein offizieller Spotpreis.
MARKETS = {
    "BTCUSDT": "Bitcoin (BTC/USDT)",
    "ETHUSDT": "Ethereum (ETH/USDT)",
    "SOLUSDT": "Solana (SOL/USDT)",
    "PAXGUSDT": "Gold (PAXG/USDT, tokenisiert)",
}
INTERVALS = ["1m", "5m", "15m", "1h", "4h", "1d"]

app = FastAPI(title="Trading-Tool", docs_url=None, redoc_url=None, openapi_url=None)


# --------------------------------------------------------------------------
# Login (Passwort + signiertes Cookie, ohne Zusatzbibliotheken)
# --------------------------------------------------------------------------
def make_token() -> str:
    exp = str(int(time.time()) + SESSION_DAYS * 86400)
    sig = hmac.new(APP_SECRET.encode(), exp.encode(), hashlib.sha256).hexdigest()
    return f"{exp}.{sig}"


def valid_token(token: str) -> bool:
    try:
        exp, sig = token.split(".", 1)
        expected = hmac.new(APP_SECRET.encode(), exp.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected) and int(exp) > time.time()
    except (ValueError, AttributeError):
        return False


_failed_logins: dict[str, list[float]] = {}


def client_ip(request: Request) -> str:
    # Die App ist nur über Caddy erreichbar; Caddy setzt X-Forwarded-For selbst.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def locked_out(ip: str) -> bool:
    now = time.time()
    recent = [t for t in _failed_logins.get(ip, []) if now - t < 60]
    _failed_logins[ip] = recent
    return len(recent) >= 5


PUBLIC_PATHS = {"/login", "/api/login", "/health"}


@app.middleware("http")
async def require_login(request: Request, call_next):
    path = request.url.path
    if path in PUBLIC_PATHS or valid_token(request.cookies.get("session", "")):
        return await call_next(request)
    if path.startswith("/api/"):
        return JSONResponse({"detail": "Nicht angemeldet"}, status_code=401)
    return RedirectResponse("/login")


@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/login")
async def login_page():
    return FileResponse(STATIC_DIR / "login.html")


@app.post("/api/login")
async def login(request: Request):
    ip = client_ip(request)
    if locked_out(ip):
        raise HTTPException(429, "Zu viele Versuche. Bitte eine Minute warten.")
    try:
        body = await request.json()
        password = str(body.get("password", ""))
    except Exception:
        raise HTTPException(400, "Ungültige Anfrage")
    if not hmac.compare_digest(password.encode(), APP_PASSWORD.encode()):
        _failed_logins.setdefault(ip, []).append(time.time())
        raise HTTPException(401, "Falsches Passwort")
    response = JSONResponse({"ok": True})
    response.set_cookie(
        "session",
        make_token(),
        max_age=SESSION_DAYS * 86400,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="strict",
    )
    return response


@app.post("/api/logout")
async def logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie("session")
    return response


# --------------------------------------------------------------------------
# Marktdaten
# --------------------------------------------------------------------------
@app.get("/api/markets")
async def markets():
    return {
        "markets": [{"symbol": s, "name": n} for s, n in MARKETS.items()],
        "intervals": INTERVALS,
    }


async def fetch_candles(symbol: str, interval: str, limit: int = 1000) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://api.binance.com/api/v3/klines",
                params={"symbol": symbol, "interval": interval, "limit": limit},
            )
        r.raise_for_status()
    except httpx.HTTPError:
        raise HTTPException(502, "Datenquelle (Binance) nicht erreichbar")
    return [
        {
            "time": int(k[0]) // 1000,
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
        }
        for k in r.json()
    ]


def check_market(symbol: str, interval: str) -> None:
    if symbol not in MARKETS:
        raise HTTPException(400, "Unbekannter Markt")
    if interval not in INTERVALS:
        raise HTTPException(400, "Unbekanntes Intervall")


@app.get("/api/data")
async def data(
    symbol: str,
    interval: str,
    fast: int = Query(20, ge=2, le=200),
    slow: int = Query(50, ge=3, le=400),
):
    check_market(symbol, interval)
    if fast >= slow:
        raise HTTPException(400, "Der schnelle SMA muss kleiner sein als der langsame.")

    candles = await fetch_candles(symbol, interval)
    signals, f, s = sma_cross(candles, fast, slow)

    def line(values):
        return [
            {"time": c["time"], "value": v}
            for c, v in zip(candles, values)
            if v is not None
        ]

    return {
        "symbol": symbol,
        "interval": interval,
        "candles": candles,
        "fast": line(f),
        "slow": line(s),
        "markers": signals,
        "stats": backtest(candles, signals),
    }


@app.websocket("/ws/live")
async def live(ws: WebSocket, symbol: str, interval: str):
    """Reicht den Binance-Kerzenstream an den Browser weiter."""
    origin = ws.headers.get("origin")
    same_origin = origin is None or urlparse(origin).netloc == ws.headers.get("host")
    if (
        not same_origin
        or not valid_token(ws.cookies.get("session", ""))
        or symbol not in MARKETS
        or interval not in INTERVALS
    ):
        await ws.close(code=1008)
        return

    await ws.accept()
    url = f"wss://stream.binance.com:9443/ws/{symbol.lower()}@kline_{interval}"
    try:
        async with websockets.connect(url, ping_interval=20, open_timeout=10) as upstream:
            async for raw in upstream:
                k = json.loads(raw)["k"]
                await ws.send_json(
                    {
                        "time": int(k["t"]) // 1000,
                        "open": float(k["o"]),
                        "high": float(k["h"]),
                        "low": float(k["l"]),
                        "close": float(k["c"]),
                        "volume": float(k["v"]),
                        "closed": bool(k["x"]),
                    }
                )
    except Exception:
        pass  # Browser oder Binance hat getrennt; der Browser verbindet sich neu.
    finally:
        try:
            await ws.close()
        except Exception:
            pass


# Muss als Letztes stehen: liefert das Frontend aus (index.html unter "/").
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
