import json

import pytest

from nipulate.pairing import (
    BAD,
    CODE_DIGITS,
    CODE_MAX_WRONG,
    CODE_TTL_S,
    FAILURE_WINDOW_S,
    LIMITED,
    MAX_DEVICES,
    MAX_FAILURES,
    OK,
    Pairing,
)

IP = "192.168.1.20"


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def pairing(tmp_path, clock):
    return Pairing(tmp_path / "nipulate" / "config.json", clock=clock)


def test_first_run_creates_a_128_bit_token_and_saves_it(pairing):
    assert len(pairing.token) == 22  # 16 random bytes, URL-safe base64
    saved = json.loads(pairing.path.read_text(encoding="utf-8"))
    assert saved["token"] == pairing.token


def test_token_survives_a_restart(pairing, clock):
    again = Pairing(pairing.path, clock=clock)
    assert again.token == pairing.token


def test_corrupt_config_is_replaced(tmp_path, clock):
    path = tmp_path / "config.json"
    path.write_text("{not json", encoding="utf-8")
    p = Pairing(path, clock=clock)
    assert len(p.token) == 22
    assert json.loads(path.read_text(encoding="utf-8"))["token"] == p.token


def test_short_token_in_config_is_replaced(tmp_path, clock):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"token": "abc"}), encoding="utf-8")
    assert Pairing(path, clock=clock).token != "abc"


def test_good_and_bad_tokens(pairing):
    assert pairing.check_token(IP, pairing.token) == OK
    assert pairing.check_token(IP, "wrong") == BAD
    assert pairing.check_token(IP, "") == BAD
    assert pairing.check_token(IP, "ünïcode") == BAD


def test_repeated_failures_are_rate_limited_per_ip(pairing, clock):
    for _ in range(MAX_FAILURES):
        assert pairing.check_token(IP, "wrong") == BAD
    # Even the right token is refused while limited.
    assert pairing.check_token(IP, pairing.token) == LIMITED
    assert pairing.retry_after(IP) > 0
    # Other phones are unaffected.
    assert pairing.check_token("192.168.1.21", pairing.token) == OK
    clock.now += FAILURE_WINDOW_S
    assert pairing.check_token(IP, pairing.token) == OK


def test_code_is_six_digits(pairing):
    assert len(pairing.code) == CODE_DIGITS and pairing.code.isdigit()


def test_right_code_works_once(pairing):
    code = pairing.code
    assert pairing.check_code(IP, code) == OK
    assert pairing.code != code
    assert pairing.check_code(IP, code) == BAD


def test_code_expires(pairing, clock):
    code = pairing.code
    clock.now += CODE_TTL_S
    assert pairing.check_code(IP, code) == BAD


def test_too_many_wrong_codes_replace_the_code(pairing):
    code = pairing.code
    wrong = "000000" if code != "000000" else "111111"
    for i in range(CODE_MAX_WRONG):
        pairing.check_code(f"10.0.0.{i}", wrong)  # spread over IPs to dodge the per-IP limit
    assert pairing.code != code


def test_wrong_codes_count_toward_the_rate_limit(pairing):
    for _ in range(MAX_FAILURES):
        pairing.check_code(IP, "999999" if pairing.code != "999999" else "888888")
    assert pairing.check_code(IP, pairing.code) == LIMITED


def test_reset_rotates_the_token_and_forgets_phones(pairing, clock):
    old = pairing.token
    pairing.remember("phone1", "iPhone Safari")
    pairing.reset()
    assert pairing.token != old
    assert pairing.devices == {}
    assert pairing.check_token(IP, old) == BAD
    assert Pairing(pairing.path, clock=clock).token == pairing.token


def test_remember_records_and_updates_devices(pairing):
    pairing.remember("phone1", "iPhone Safari")
    first = dict(pairing.devices["phone1"])
    pairing.remember("phone1", "iPhone Safari (Home Screen app)")
    entry = pairing.devices["phone1"]
    assert entry["paired"] == first["paired"]
    assert entry["label"] == "iPhone Safari (Home Screen app)"
    assert json.loads(pairing.path.read_text(encoding="utf-8"))["devices"]["phone1"]["label"] == entry["label"]


def test_device_list_is_capped(tmp_path, clock):
    now = [0]

    def wall():
        now[0] += 1
        return now[0]

    p = Pairing(tmp_path / "c.json", clock=clock, wall=wall)
    for i in range(MAX_DEVICES + 3):
        p.remember(f"phone{i}", "Android Chrome")
    assert len(p.devices) == MAX_DEVICES
    assert "phone0" not in p.devices
