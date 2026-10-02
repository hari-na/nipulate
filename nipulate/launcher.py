"""Desktop-shortcut entry point: start the server if it isn't running, then open the PC page.

Run with pythonw (no console of its own). The server gets its own minimized
console window, so its log is still there if needed.
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

from .cli import DEFAULT_PORT

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
    python = Path(sys.executable).with_name("python.exe")  # console python, not pythonw
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 7  # SW_SHOWMINNOACTIVE: minimized, doesn't steal focus
    subprocess.Popen([str(python), "-m", "nipulate", "-v"],
                     startupinfo=si, creationflags=subprocess.CREATE_NEW_CONSOLE)


def main() -> None:
    if not running():
        start_server()
        deadline = time.time() + STARTUP_TIMEOUT_S
        while not running():
            if time.time() > deadline:
                ctypes.windll.user32.MessageBoxW(
                    None, f"The server didn't start. Is port {DEFAULT_PORT} in use? "
                    "Run scripts\\run.bat to see the error.", "nipulate", 0x10)
                sys.exit(1)
            time.sleep(0.3)
    webbrowser.open(PC_URL)


if __name__ == "__main__":
    main()
