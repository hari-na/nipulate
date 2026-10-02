"""Command line entry point: ``nipulate`` or ``python -m nipulate``."""

from __future__ import annotations

import argparse
import os
import socket
import sys
from pathlib import Path

import qrcode
from aiohttp import web

from . import __version__
from .hub import Hub
from .input import select_backend
from .server import create_app

DEFAULT_PORT = 8787  # seidr-pad uses 8777, so both can run at once


def default_log_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / "nipulate" / "nipulate.log"


def lan_ip() -> str:
    """Best guess at the address phones on the same Wi-Fi can reach."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # picks the outgoing interface; no packet is sent
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="nipulate",
                                 description="Turn your phone into a TV remote for this PC, over Wi-Fi.")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"port to serve on (default {DEFAULT_PORT})")
    ap.add_argument("--fake", action="store_true", help="don't send input to Windows (for testing the phone page)")
    ap.add_argument("-v", "--verbose", action="store_true", help="also log every click and key (never typed text)")
    ap.add_argument("--log", type=Path, default=None,
                    help="write the log to this file instead of the console (the desktop shortcut does this)")
    ap.add_argument("--version", action="version", version=f"nipulate {__version__}")
    return ap.parse_args(argv)


def _print_qr(url: str) -> None:
    try:
        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.print_ascii(invert=True)
    except Exception:
        pass  # consoles that can't draw it; the PC page shows the QR code anyway


def main(argv=None) -> None:
    args = parse_args(argv)
    # Without a console (pythonw, as the desktop shortcut runs it) there's nowhere to print, so log to a file.
    log_path = args.log or (default_log_path() if sys.stdout is None else None)
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        sys.stdout = sys.stderr = open(log_path, "w", encoding="utf-8", buffering=1)
    else:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    def out(line: str) -> None:
        print(line, flush=True)

    backend, mode = select_backend(args.fake, out)
    url = f"http://{lan_ip()}:{args.port}/"
    hub = Hub(backend, mode, verbose=args.verbose, out=out)
    app = create_app(hub, url)

    if log_path is None:
        _print_qr(url)
    out(f"\nnipulate {__version__}: {mode}")
    out(f"Phones (same Wi-Fi): scan the QR code or open {url}")
    out(f"PC page (QR code, log, Stop): http://localhost:{args.port}/pc")
    out(f"Logging every click and key: {'on' if args.verbose else 'off (add -v)'}")
    out("Stop it from the PC page.\n" if log_path else "Ctrl+C to stop.\n")

    # Both IPv4 and IPv6, so "localhost" answers instantly whichever one it resolves to.
    web.run_app(app, host=["0.0.0.0", "::"], port=args.port, print=None)


if __name__ == "__main__":
    main()
