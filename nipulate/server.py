"""The web server: the phone remote, its WebSocket, and the PC-only status page.

Phones must authenticate in their first WebSocket message, with the pairing
token or the short code. Nothing else is accepted until then.

The PC page and its endpoints (QR code, Stop, Reset pairing) carry or change
the pairing secrets, so they only answer requests from this PC, addressed to a
loopback host name, from the page's own origin.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
from importlib import resources

import qrcode
import qrcode.image.svg
from aiohttp import WSMsgType, web

from . import __version__
from .device import describe_device
from .hub import LOOPBACK, Hub, Phone
from .pairing import LIMITED, OK
from .protocol import MAX_MESSAGE_BYTES, Hello, Pair, Ping, parse_message

HUB = web.AppKey("hub", Hub)
_HOUSEKEEPING = web.AppKey("housekeeping", asyncio.Task)

STATIC = resources.files(__package__) / "static"
AUTH_TIMEOUT_S = 10
LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")


def _same_origin(request: web.Request) -> bool:
    """True when the Origin header is missing or names this server, as typed in the address bar."""
    origin = request.headers.get("Origin")
    return origin is None or origin == f"{request.scheme}://{request.host}"


def _is_pc(request: web.Request) -> bool:
    """A request from this PC, to a loopback name (not a DNS-rebound one), from our own pages."""
    return request.remote in LOOPBACK and request.url.host in LOCAL_HOSTS and _same_origin(request)


def _require_pc(request: web.Request) -> None:
    if not _is_pc(request):
        raise web.HTTPForbidden(text="Only the PC running nipulate can do this.")


# ---- phone ------------------------------------------------------------------


async def phone_socket(request: web.Request) -> web.WebSocketResponse:
    """One phone. First message: hello (token) or pair (code). Then input messages."""
    hub = request.app[HUB]
    if not _same_origin(request):
        hub.log(f"Refused a connection from {request.remote}: wrong Origin {request.headers.get('Origin')!r}")
        raise web.HTTPForbidden(text="Wrong origin.")
    ws = web.WebSocketResponse(heartbeat=5, max_msg_size=MAX_MESSAGE_BYTES)
    await ws.prepare(request)
    phone = await _authenticate(request, ws)
    if phone is None:
        await ws.close()
        return ws

    bad_logged_at = 0.0
    try:
        async for msg in ws:
            if msg.type != WSMsgType.TEXT:
                continue
            try:
                parsed = parse_message(json.loads(msg.data))
            except ValueError as e:  # includes JSON errors
                now = asyncio.get_running_loop().time()
                if now - bad_logged_at > 10:
                    hub.log(f"{phone.label}: ignored a bad message ({e})")
                    bad_logged_at = now
                continue
            if isinstance(parsed, Ping):
                if parsed.latency is not None:
                    phone.latency = round(parsed.latency)
                await ws.send_json({"t": "pong", "ping": parsed.ping})
            elif isinstance(parsed, (Hello, Pair)):
                continue
            else:
                hub.handle(phone, parsed)
    finally:
        hub.disconnect(phone, ws)
    return ws


async def _authenticate(request: web.Request, ws: web.WebSocketResponse) -> Phone | None:
    hub = request.app[HUB]
    ip = request.remote or "?"
    try:
        msg = await ws.receive(timeout=AUTH_TIMEOUT_S)
        hello = parse_message(json.loads(msg.data)) if msg.type == WSMsgType.TEXT else None
    except (asyncio.TimeoutError, ValueError, TypeError):
        hello = None
    if not isinstance(hello, (Hello, Pair)):
        await ws.send_json({"t": "denied", "reason": "hello"})
        return None

    pairing = hub.pairing
    if isinstance(hello, Hello):
        result = pairing.check_token(ip, hello.token)
    else:
        result = pairing.check_code(ip, hello.code)
    device = describe_device(request.headers.get("User-Agent", ""), hello.standalone)
    if result != OK:
        if result == LIMITED:
            reason = "limited"
            hub.log(f"Refused {device} at {ip}: too many failed attempts")
        else:
            reason = "token" if isinstance(hello, Hello) else "code"
            hub.log(f"Refused {device} at {ip}: wrong pairing {'token' if reason == 'token' else 'code'}")
        await ws.send_json({"t": "denied", "reason": reason, "retry": round(pairing.retry_after(ip))})
        if isinstance(hello, Pair):
            hub.broadcast_status()  # the code may have been replaced
        return None

    if hub.volume is None:
        hub.poll_volume()  # before connecting, so it arrives in the reply rather than as its own message
    phone = Phone(hello.client_id or f"anon-{ip}", ws, ip, device)
    if isinstance(hello, Pair):
        hub.log(f"{device} at {ip} paired with the code")
    old = hub.connect(phone)
    if old is not None and not old.ws.closed:
        hub.log(f"{phone.label}: closing its older tab")
        await old.ws.send_json({"t": "replaced"})  # stops it reconnecting and fighting the new one
        await old.ws.close()
    reply = {"t": "ok", "version": __version__}
    if isinstance(hello, Pair):
        reply["k"] = pairing.token
    if hub.volume is not None:
        reply["vol"] = {"level": hub.volume[0], "muted": hub.volume[1]}
    await ws.send_json(reply)
    return phone


# ---- PC page ------------------------------------------------------------------


async def pc_socket(request: web.Request) -> web.WebSocketResponse:
    """The PC status page: live status and log."""
    _require_pc(request)
    hub = request.app[HUB]
    ws = web.WebSocketResponse(heartbeat=10, max_msg_size=MAX_MESSAGE_BYTES)
    await ws.prepare(request)
    hub.monitors.add(ws)
    try:
        await ws.send_json({"t": "hello", "version": __version__, "log": list(hub.history), **hub.status()})
        async for _ in ws:
            pass  # the page only listens
    finally:
        hub.monitors.discard(ws)
    return ws


async def stop(request: web.Request) -> web.Response:
    _require_pc(request)
    hub = request.app[HUB]
    hub.log("Stop pressed on the PC page, shutting down")

    async def shutdown():
        await asyncio.sleep(0.3)  # let the response go out first
        hub.release_all()
        os._exit(0)

    asyncio.ensure_future(shutdown())
    return web.json_response({"ok": True})


async def reset_pairing(request: web.Request) -> web.Response:
    _require_pc(request)
    await request.app[HUB].reset_pairing()
    return web.json_response({"ok": True})


async def pc_status(request: web.Request) -> web.Response:
    _require_pc(request)
    return web.json_response(request.app[HUB].status())


async def health(request: web.Request) -> web.Response:
    """Public and secret-free: lets the launcher see that nipulate is running."""
    return web.json_response({"app": "nipulate", "version": __version__})


async def qr_code(request: web.Request) -> web.Response:
    _require_pc(request)
    img = qrcode.make(request.app[HUB].pair_url(), image_factory=qrcode.image.svg.SvgPathImage, box_size=20)
    buf = io.BytesIO()
    img.save(buf)
    return web.Response(body=buf.getvalue(), content_type="image/svg+xml")


def _page(name: str, pc_only: bool = False):
    async def handler(request: web.Request) -> web.Response:
        if pc_only:
            _require_pc(request)
        return web.Response(text=(STATIC / name).read_text(encoding="utf-8"), content_type="text/html")
    return handler


@web.middleware
async def no_cache(request: web.Request, handler):
    # Phones (iPhone Home Screen apps especially) otherwise keep running old copies after an update.
    resp = await handler(request)
    if not isinstance(resp, web.WebSocketResponse):
        resp.headers["Cache-Control"] = "no-cache"
        resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


async def _start_housekeeping(app: web.Application) -> None:
    hub = app[HUB]
    hub.log(f"nipulate {__version__} started, {hub.mode}")
    hub.log(f"Phones on the same Wi-Fi: {hub.url}")
    app[_HOUSEKEEPING] = asyncio.create_task(hub.run())


async def _cleanup(app: web.Application) -> None:
    app[_HOUSEKEEPING].cancel()
    app[HUB].release_all()


def create_app(hub: Hub, phone_url: str) -> web.Application:
    app = web.Application(middlewares=[no_cache], client_max_size=MAX_MESSAGE_BYTES)
    hub.url = phone_url
    app[HUB] = hub
    app.router.add_get("/", _page("index.html"))
    app.router.add_get("/pc", _page("pc.html", pc_only=True))
    app.router.add_get("/ws", phone_socket)
    app.router.add_get("/ws/pc", pc_socket)
    app.router.add_get("/api/health", health)
    app.router.add_get("/api/pc", pc_status)
    app.router.add_post("/api/stop", stop)
    app.router.add_post("/api/reset", reset_pairing)
    app.router.add_get("/qr.svg", qr_code)
    app.router.add_static("/static/", str(STATIC))
    app.on_startup.append(_start_housekeeping)
    app.on_cleanup.append(_cleanup)
    return app
