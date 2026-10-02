"""Connected phones: turns their messages into input, and feeds the PC page.

Each authenticated phone gets a ``Phone`` with its own pointer state and the
mouse buttons it's holding. Held buttons are released whenever a phone
disconnects, loses focus or locks the PC, so nothing stays stuck down.

Typed text is never logged, only how many characters were typed.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from collections.abc import Callable

from .input import Backend
from .pairing import Pairing
from .pointer import Pointer
from .protocol import KEYS, Button, Key, Lock, Message, Move, Release, Scroll, Settings, Text

LOOPBACK = ("127.0.0.1", "::1")
VOLUME_KEYS = ("vol_up", "vol_down", "mute")
LOG_HISTORY = 200
TYPING_IDLE_S = 1.5  # typing is logged as one line once the phone pauses this long

CLOSE_REASONS = {
    1000: "page closed",
    1001: "page closed or app switched",
    1006: "connection lost (Wi-Fi drop or phone locked)",
}


class Phone:
    def __init__(self, client_id: str, ws, ip: str, device: str):
        self.client_id = client_id
        self.ws = ws
        self.ip = ip
        self.device = device
        self.pointer = Pointer()
        self.held: set[str] = set()
        self.latency: int | None = None
        self.msgs = 0
        self.typed = 0
        self.last_typed = 0.0
        self.last_key: tuple[str, float] = ("", 0.0)
        self.connected_at = time.time()

    @property
    def label(self) -> str:
        return f"{self.device} ({self.ip})"

    def send(self, obj: dict) -> None:
        if self.ws is not None and not self.ws.closed:
            asyncio.ensure_future(self.ws.send_json(obj))


class Hub:
    def __init__(self, backend: Backend, pairing: Pairing, mode: str, *, verbose: bool = False,
                 stats_every_s: float = 10, out: Callable[[str], None] = print):
        self.backend = backend
        self.pairing = pairing
        self.mode = mode
        self.verbose = verbose
        self.stats_every_s = stats_every_s
        self.out = out
        self.phones: dict[str, Phone] = {}  # connected phones by client id
        self.monitors: set = set()  # WebSockets of open PC pages
        self.history: deque[str] = deque(maxlen=LOG_HISTORY)
        self.volume: tuple[int, bool] | None = None
        self.url = ""  # the phone page address, set by the server
        self._last_stats = time.monotonic()
        self._shown_code = ""

    # ---- logging and PC page updates ---------------------------------------

    def log(self, msg: str) -> None:
        line = f"{time.strftime('%H:%M:%S')}  {msg}"
        self.out(line)
        self.history.append(line)
        self.broadcast({"t": "log", "msg": line})

    def broadcast(self, obj: dict) -> None:
        if not self.monitors:
            return
        data = json.dumps(obj)
        for ws in list(self.monitors):
            if not ws.closed:
                asyncio.ensure_future(ws.send_str(data))

    def broadcast_status(self) -> None:
        self.broadcast({"t": "status", **self.status()})

    def pair_url(self) -> str:
        return f"{self.url}#k={self.pairing.token}"

    def status(self) -> dict:
        """Everything the PC page shows. Contains the pairing secrets: only ever send it to the PC itself."""
        by_id = {p.client_id: p for p in self.phones.values()}
        paired = []
        for client_id, info in self.pairing.devices.items():
            phone = by_id.get(client_id)
            paired.append({
                "label": info.get("label", ""), "last_seen": info.get("last_seen"),
                "connected": phone is not None,
                "ip": phone.ip if phone else None,
                "latency": phone.latency if phone else None,
            })
        paired.sort(key=lambda d: (not d["connected"], -(d["last_seen"] or 0)))
        return {
            "mode": self.mode, "url": self.url, "pair_url": self.pair_url(),
            "code": self.pairing.code, "code_ttl": round(self.pairing.code_expires_in),
            "connected": len(self.phones), "paired": paired,
            "volume": self.volume,
        }

    # ---- connections ---------------------------------------------------------

    def connect(self, phone: Phone) -> Phone | None:
        """Register an authenticated phone. Returns the older connection of the same phone, if any."""
        old = self.phones.get(phone.client_id)
        self.phones[phone.client_id] = phone
        self.pairing.remember(phone.client_id, phone.device)
        self.log(f"{phone.label} connected")
        self.broadcast_status()
        return old

    def disconnect(self, phone: Phone, ws) -> None:
        self.release(phone)
        if self.phones.get(phone.client_id) is not phone:
            return  # a newer connection of the same phone already took over
        del self.phones[phone.client_id]
        self._flush_typing(phone)
        reason = CLOSE_REASONS.get(ws.close_code, f"closed (code {ws.close_code})")
        self.log(f"{phone.label} disconnected: {reason}")
        self.broadcast_status()

    def release(self, phone: Phone) -> None:
        """Let go of every mouse button this phone is holding."""
        for name in list(phone.held):
            self.backend.button(name, False)
        if phone.held and self.verbose:
            self.log(f"{phone.label}: released {', '.join(sorted(phone.held))} button")
        phone.held.clear()
        phone.pointer.reset()

    async def reset_pairing(self) -> None:
        """New token: every phone is signed out and must scan the new QR code."""
        self.pairing.reset()
        self.log("Pairing reset: every phone has to pair again")
        for phone in list(self.phones.values()):
            self.release(phone)
            if not phone.ws.closed:
                await phone.ws.send_json({"t": "reset"})
                await phone.ws.close()
        self.broadcast_status()

    # ---- input ---------------------------------------------------------------

    def handle(self, phone: Phone, msg: Message) -> None:
        phone.msgs += 1
        b = self.backend
        if isinstance(msg, Move):
            dx, dy = phone.pointer.move(msg.dx, msg.dy, msg.dt)
            if dx or dy:
                b.move(dx, dy)
        elif isinstance(msg, Scroll):
            v, h = phone.pointer.scroll(msg.dx, msg.dy)
            if v or h:
                b.scroll(v, h)
        elif isinstance(msg, Button):
            self._button(phone, msg)
        elif isinstance(msg, Key):
            self._key(phone, msg.name)
        elif isinstance(msg, Text):
            if msg.text:
                b.text(msg.text)
                phone.typed += len(msg.text)
                phone.last_typed = time.monotonic()
        elif isinstance(msg, Settings):
            phone.pointer.sensitivity = msg.sensitivity
        elif isinstance(msg, Release):
            self.release(phone)
        elif isinstance(msg, Lock):
            self.release(phone)
            self.log(f"{phone.label} locked the PC")
            b.lock()

    def _button(self, phone: Phone, msg: Button) -> None:
        b = self.backend
        if msg.action == "click":
            if msg.button in phone.held:  # finishing a drag
                phone.held.discard(msg.button)
            else:
                b.button(msg.button, True)
            b.button(msg.button, False)
        elif msg.action == "down" and msg.button not in phone.held:
            phone.held.add(msg.button)
            b.button(msg.button, True)
        elif msg.action == "up" and msg.button in phone.held:
            phone.held.discard(msg.button)
            b.button(msg.button, False)
        else:
            return
        if self.verbose:
            self.log(f"{phone.label}: {msg.button} {msg.action}")

    def _key(self, phone: Phone, name: str) -> None:
        label, combo = KEYS[name]
        self.backend.keys(combo)
        now = time.monotonic()
        last_name, last_at = phone.last_key
        phone.last_key = (name, now)
        if self.verbose and (name != last_name or now - last_at > 1.0):  # one line per held-down repeat
            self.log(f"{phone.label}: {label}")
        if name in VOLUME_KEYS:
            asyncio.get_running_loop().call_later(0.08, self.poll_volume)

    def _flush_typing(self, phone: Phone) -> None:
        if phone.typed:
            if self.verbose:
                self.log(f"{phone.label}: typed {phone.typed} character{'s' if phone.typed != 1 else ''}")
            phone.typed = 0

    # ---- volume ----------------------------------------------------------------

    def poll_volume(self) -> None:
        vol = self.backend.volume()
        if vol is None or vol == self.volume:
            return
        self.volume = vol
        for phone in self.phones.values():
            phone.send({"t": "vol", "level": vol[0], "muted": vol[1]})

    # ---- housekeeping ------------------------------------------------------------

    def tick(self, now: float) -> None:
        """Called about once a second."""
        if self.phones:
            self.poll_volume()
        for phone in self.phones.values():
            if phone.typed and now - phone.last_typed >= TYPING_IDLE_S:
                self._flush_typing(phone)
        code = self.pairing.code  # also replaces an expired code
        if code != self._shown_code or self.phones:
            self._shown_code = code
            self.broadcast_status()
        if now - self._last_stats >= self.stats_every_s:
            self._log_stats(now - self._last_stats)
            self._last_stats = now

    def _log_stats(self, elapsed: float) -> None:
        parts = []
        for p in self.phones.values():
            if p.msgs:
                lat = f"{p.latency} ms" if p.latency is not None else "? ms"
                parts.append(f"{p.label} {p.msgs / elapsed:.1f} msg/s {lat}")
            p.msgs = 0
        if parts and self.verbose:
            self.log("stats: " + " | ".join(parts))

    async def run(self) -> None:
        while True:
            await asyncio.sleep(1)
            self.tick(time.monotonic())

    def release_all(self) -> None:
        for phone in self.phones.values():
            self.release(phone)
