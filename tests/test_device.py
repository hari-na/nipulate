import pytest

from nipulate.device import describe_device

IPHONE_SAFARI = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
                 "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1")
IPHONE_CHROME = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
                 "(KHTML, like Gecko) CriOS/128.0 Mobile/15E148 Safari/604.1")
ANDROID_CHROME = ("Mozilla/5.0 (Linux; Android 14; K) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/128.0 Mobile Safari/537.36")
ANDROID_SAMSUNG = ("Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) "
                   "SamsungBrowser/25.0 Chrome/121.0 Mobile Safari/537.36")
WINDOWS_EDGE = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/128.0 Safari/537.36 Edg/128.0")


@pytest.mark.parametrize("ua, expected", [
    (IPHONE_SAFARI, "iPhone Safari"),
    (IPHONE_CHROME, "iPhone Chrome"),
    (ANDROID_CHROME, "Android Chrome"),
    (ANDROID_SAMSUNG, "Android (SM-S918B) Samsung Internet"),
    (WINDOWS_EDGE, "Windows Edge"),
    ("", "Unknown device browser"),
])
def test_describe_device(ua, expected):
    assert describe_device(ua) == expected


def test_home_screen_app_is_marked():
    assert describe_device(IPHONE_SAFARI, standalone=True) == "iPhone Safari (Home Screen app)"
