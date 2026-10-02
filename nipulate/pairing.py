"""Pairing: which phones may control this PC.

A random 128-bit token is created on first run and stored in
``%APPDATA%\\nipulate\\config.json``. The PC page's QR code carries it in the
URL fragment; the phone keeps it and sends it in every WebSocket hello.

Phones that can't use the QR link (an iPhone Home Screen app has its own
storage) can type the short pairing code shown on the PC instead, and get the
token in return. The code expires after a few minutes, changes after each
use, and changes after too many wrong guesses.

Failed attempts are rate-limited per IP. Resetting pairing makes a new token,
which signs every phone out.
"""

from __future__ import annotations

import hmac
import json
import os
import secrets
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path

CODE_DIGITS = 6
CODE_TTL_S = 300
MAX_FAILURES = 5  # per IP, within FAILURE_WINDOW_S
FAILURE_WINDOW_S = 60
CODE_MAX_WRONG = 10  # wrong codes from anyone before the code is replaced
MAX_DEVICES = 20
LABEL_MAX = 64

OK, BAD, LIMITED = "ok", "bad", "limited"


def default_config_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / "nipulate" / "config.json"


def new_token() -> str:
    return secrets.token_urlsafe(16)  # 128 bits, 22 URL-safe characters


def _same(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


class Pairing:
    def __init__(self, path: Path, *, clock: Callable[[], float] = time.monotonic,
                 wall: Callable[[], float] = time.time):
        self.path = Path(path)
        self.clock = clock
        self.wall = wall
        self.token, self.devices = self._load()
        self._failures: dict[str, deque[float]] = {}
        self._wrong_codes = 0
        self._code = ""
        self._code_made = 0.0
        self.new_code()

    # ---- storage -----------------------------------------------------------

    def _load(self) -> tuple[str, dict[str, dict]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            token = data["token"]
            devices = data.get("devices", {})
            if not isinstance(token, str) or len(token) < 16 or not isinstance(devices, dict):
                raise ValueError("invalid config")
            return token, devices
        except (OSError, ValueError, KeyError, TypeError):
            token = new_token()
            self.token, self.devices = token, {}
            self.save()
            return token, {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps({"token": self.token, "devices": self.devices}, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    # ---- the short code ------------------------------------------------------

    def new_code(self) -> str:
        self._code = f"{secrets.randbelow(10 ** CODE_DIGITS):0{CODE_DIGITS}d}"
        self._code_made = self.clock()
        self._wrong_codes = 0
        return self._code

    @property
    def code(self) -> str:
        if self.clock() - self._code_made >= CODE_TTL_S:
            self.new_code()
        return self._code

    @property
    def code_expires_in(self) -> float:
        return max(0.0, CODE_TTL_S - (self.clock() - self._code_made))

    # ---- checks --------------------------------------------------------------

    def limited(self, ip: str) -> bool:
        q = self._failures.get(ip)
        if not q:
            return False
        now = self.clock()
        while q and now - q[0] >= FAILURE_WINDOW_S:
            q.popleft()
        if not q:
            del self._failures[ip]
            return False
        return len(q) >= MAX_FAILURES

    def retry_after(self, ip: str) -> float:
        q = self._failures.get(ip)
        return max(0.0, FAILURE_WINDOW_S - (self.clock() - q[0])) if q else 0.0

    def _fail(self, ip: str) -> None:
        self._failures.setdefault(ip, deque()).append(self.clock())

    def check_token(self, ip: str, token: str) -> str:
        if self.limited(ip):
            return LIMITED
        if token and _same(token, self.token):
            return OK
        self._fail(ip)
        return BAD

    def check_code(self, ip: str, code: str) -> str:
        """Check a typed pairing code. On success the code is used up and replaced."""
        if self.limited(ip):
            return LIMITED
        if code and _same(code, self.code):
            self.new_code()
            return OK
        self._fail(ip)
        self._wrong_codes += 1
        if self._wrong_codes >= CODE_MAX_WRONG:
            self.new_code()
        return BAD

    # ---- devices ---------------------------------------------------------------

    def remember(self, client_id: str, label: str) -> None:
        """Record a phone that authenticated, for the PC page's list."""
        now = round(self.wall())
        entry = self.devices.get(client_id) or {"paired": now}
        entry.update(label=label[:LABEL_MAX], last_seen=now)
        self.devices[client_id] = entry
        if len(self.devices) > MAX_DEVICES:
            oldest = min(self.devices, key=lambda k: self.devices[k].get("last_seen", 0))
            del self.devices[oldest]
        self.save()

    def reset(self) -> None:
        """New token, new code, no paired phones."""
        self.token = new_token()
        self.devices = {}
        self._failures.clear()
        self.new_code()
        self.save()
