"""Command line entry point: ``nipulate`` or ``python -m nipulate``."""

from __future__ import annotations

import argparse
import socket
import sys
from pathlib import Path

import qrcode
from aiohttp import web

from . import __version__
from .hub import Hub
from .input import select_backend
from .pairing import Pairing, default_config_path
from .server import create_app

DEFAULT_PORT = 8787  # seidr-pad uses 8777, so both can run at once


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
    ap.add_argument("--config", type=Path, default=None,
                    help=f"pairing file (default {default_config_path()})")
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
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    def out(line: str) -> None:
        print(line, flush=True)

    backend, mode = select_backend(args.fake, out)
    pairing = Pairing(args.config or default_config_path())
    url = f"http://{lan_ip()}:{args.port}/"
    hub = Hub(backend, pairing, mode, verbose=args.verbose, out=out)
    app = create_app(hub, url)

    _print_qr(hub.pair_url())
    out(f"\nnipulate {__version__}: {mode}")
    out("First time: scan the QR code with your phone (it holds the pairing key; keep it private).")
    out(f"Phones already paired: open {url}")
    out(f"PC page (QR code, pairing code, log): http://localhost:{args.port}/pc")
    out(f"Pairing file: {pairing.path}")
    out(f"Logging every click and key: {'on' if args.verbose else 'off (add -v)'}")
    out("Ctrl+C to stop.\n")

    # Both IPv4 and IPv6, so "localhost" answers instantly whichever one it resolves to.
    web.run_app(app, host=["0.0.0.0", "::"], port=args.port, print=None)


if __name__ == "__main__":
    main()
