"""Desktop-shortcut entry point: start the server if it isn't running, then open the PC page.

The server runs in the background with no window, so there's nothing to keep
open or to close by accident. Stop it with the Stop button on the PC page
(running the shortcut again reopens that page). The log is on the PC page and
in ``%APPDATA%/nipulate/nipulate.log``.
"""

from __future__ import annotations

import ctypes
import json
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

from .cli import DEFAULT_PORT, default_log_path

PC_URL = f"http://localhost:{DEFAULT_PORT}/pc"
STARTUP_TIMEOUT_S = 15


def running() -> bool:
    try:
        # 127.0.0.1, not localhost: Windows takes ~2s to refuse the IPv6 attempt.
        with urllib.request.urlopen(f"http://127.0.0.1:{DEFAULT_PORT}/api/health", timeout=1) as resp:
            return json.load(resp).get("app") == "nipulate"
    except (OSError, ValueError):
        return False


def start_server() -> None:
    pythonw = Path(sys.executable).with_name("pythonw.exe")  # no console window
    subprocess.Popen([str(pythonw), "-m", "nipulate", "-v", "--log", str(default_log_path())],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)


def main() -> None:
    if not running():
        start_server()
        deadline = time.time() + STARTUP_TIMEOUT_S
        while not running():
            if time.time() > deadline:
                ctypes.windll.user32.MessageBoxW(
                    None, f"The server didn't start. Is port {DEFAULT_PORT} in use?\n\n"
                    f"See the log in {default_log_path()}, or run scripts\run.bat to watch it start.",
                    "nipulate", 0x10)
                sys.exit(1)
            time.sleep(0.3)
    webbrowser.open(PC_URL)


if __name__ == "__main__":
    main()
