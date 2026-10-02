"""Turn a browser User-Agent into a short label for logs, e.g. "iPhone Safari"."""

from __future__ import annotations

import re

# Checked in order: several browsers also claim to be Chrome or Safari.
_BROWSERS = [
    ("SamsungBrowser", "Samsung Internet"),
    ("CriOS", "Chrome"),
    ("FxiOS", "Firefox"),
    ("EdgA|EdgiOS|Edg/", "Edge"),
    ("Firefox", "Firefox"),
    ("Chrome", "Chrome"),
    ("Safari", "Safari"),
]


def _os_name(ua: str) -> str:
    if re.search(r"iPhone|iPod", ua):
        return "iPhone"
    if "iPad" in ua:
        return "iPad"
    if "Android" in ua:
        # Most Android browsers now send "K" instead of the real model name.
        m = re.search(r"Android [\d.]+; ([^;)]+)", ua)
        model = m.group(1).strip() if m else "K"
        return f"Android ({model})" if model != "K" else "Android"
    if "Windows" in ua:
        return "Windows"
    if "Mac OS" in ua:
        return "Mac"
    return "Unknown device"


def describe_device(ua: str, standalone: bool = False) -> str:
    browser = next((name for pattern, name in _BROWSERS if re.search(pattern, ua)), "browser")
    label = f"{_os_name(ua)} {browser}"
    return label + " (Home Screen app)" if standalone else label
