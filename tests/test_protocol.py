import pytest

from nipulate.protocol import (
    DELTA_MAX,
    KEYS,
    SENSITIVITY_MAX,
    TEXT_MAX,
    Button,
    Hello,
    Key,
    Lock,
    Move,
    Ping,
    Release,
    Scroll,
    Settings,
    Text,
    clean_text,
    parse_message,
)


def test_move_passes_valid_values_through():
    assert parse_message({"t": "m", "dx": 3.5, "dy": -2, "dt": 16}) == Move(3.5, -2.0, 16.0)


def test_move_clamps_huge_deltas_and_frame_times():
    msg = parse_message({"t": "m", "dx": 1e9, "dy": -1e9, "dt": 99999})
    assert msg == Move(DELTA_MAX, -DELTA_MAX, 250.0)


def test_scroll_defaults_missing_axes_to_zero():
    assert parse_message({"t": "scroll", "dy": 12}) == Scroll(0.0, 12.0)


@pytest.mark.parametrize("bad", [None, "5", True, float("nan"), float("inf"), [1]])
def test_numbers_must_be_real_numbers(bad):
    with pytest.raises(ValueError):
        parse_message({"t": "m", "dx": bad, "dy": 0})


def test_button_click_is_the_default_action():
    assert parse_message({"t": "button", "b": "right"}) == Button("right", "click")
    assert parse_message({"t": "button", "b": "left", "a": "down"}) == Button("left", "down")


@pytest.mark.parametrize("msg", [{"t": "button", "b": "x1"}, {"t": "button", "b": "left", "a": "smash"}])
def test_unknown_buttons_are_rejected(msg):
    with pytest.raises(ValueError):
        parse_message(msg)


def test_every_named_key_parses():
    for name in KEYS:
        assert parse_message({"t": "key", "k": name}) == Key(name)


@pytest.mark.parametrize("bad", ["VK_F4", "0x41", 65, None, "__class__"])
def test_keys_outside_the_allowlist_are_rejected(bad):
    with pytest.raises(ValueError):
        parse_message({"t": "key", "k": bad})


def test_key_combos_are_well_formed():
    for label, combo in KEYS.values():
        assert label and combo
        assert all(isinstance(vk, int) and 0 < vk < 0xFF for vk in combo)


def test_text_keeps_unicode_and_emoji():
    assert parse_message({"t": "text", "s": "héllo 世界 👨‍👩‍👧"}) == Text("héllo 世界 👨‍👩‍👧")


def test_text_drops_control_characters_but_keeps_newlines():
    assert clean_text("a\x00b\x1bc\nd\te") == "abc\nde"


def test_text_is_truncated():
    assert len(parse_message({"t": "text", "s": "x" * 5000}).text) == TEXT_MAX


def test_text_must_be_a_string():
    with pytest.raises(ValueError):
        parse_message({"t": "text", "s": ["a"]})


def test_sensitivity_is_clamped():
    assert parse_message({"t": "set", "sens": 50}) == Settings(SENSITIVITY_MAX)


def test_ping_with_and_without_latency():
    assert parse_message({"t": "ping", "ping": 123}) == Ping(123.0, None)
    assert parse_message({"t": "ping", "ping": 1, "lat": 42}) == Ping(1.0, 42.0)


def test_simple_messages():
    assert parse_message({"t": "lock"}) == Lock()
    assert parse_message({"t": "release"}) == Release()


def test_hello_cleans_the_client_id():
    msg = parse_message({"t": "hello", "id": "phone\n1" + "x" * 100, "standalone": True})
    assert msg.client_id.startswith("phone1") and len(msg.client_id) <= 64
    assert msg.standalone is True
    assert isinstance(msg, Hello)


def test_hello_ignores_an_old_pairing_key():
    assert parse_message({"t": "hello", "k": "old-key", "id": "b"}) == Hello("b", False)


def test_hello_standalone_must_be_exactly_true():
    assert parse_message({"t": "hello", "id": "b", "standalone": "yes"}).standalone is False


def test_pairing_messages_no_longer_exist():
    with pytest.raises(ValueError):
        parse_message({"t": "pair", "code": "123456", "id": "p"})


@pytest.mark.parametrize("bad", ["hello", [1, 2], None, {"t": "exec", "cmd": "calc"}, {"no": "type"}])
def test_malformed_messages_are_rejected(bad):
    with pytest.raises(ValueError):
        parse_message(bad)
