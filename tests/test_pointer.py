import pytest

from nipulate.pointer import MAX_GAIN, SCROLL_UNITS_PER_PX, Pointer, gain


def test_gain_is_one_when_slow_and_capped_when_fast():
    assert gain(0) == 1.0
    assert gain(0.05) == 1.0
    assert gain(10) == MAX_GAIN


def test_gain_rises_smoothly():
    speeds = [i / 20 for i in range(60)]
    gains = [gain(s) for s in speeds]
    assert gains == sorted(gains)
    assert max(b - a for a, b in zip(gains, gains[1:], strict=False)) < 0.35


def test_slow_movement_is_nearly_one_to_one():
    p = Pointer(sensitivity=1.0)
    assert p.move(1, 0, 16) == (1, 0)


def test_fast_flicks_travel_much_further_than_slow_drags():
    slow, fast = Pointer(1.0), Pointer(1.0)
    # The same 400 px of finger travel, once slowly and once as a quick flick.
    slow_total = sum(slow.move(1, 0, 16)[0] for _ in range(400))
    fast_total = sum(fast.move(40, 0, 16)[0] for _ in range(10))
    assert slow_total == 400
    assert fast_total > 3 * slow_total


def test_sub_pixel_movement_accumulates():
    p = Pointer(sensitivity=0.25)
    moves = [p.move(1, 0, 16)[0] for _ in range(8)]
    assert sum(moves) == 2  # 8 px * 0.25, not rounded down to zero every frame


def test_negative_movement_is_symmetric():
    a, b = Pointer(), Pointer()
    assert a.move(-7, -3, 16) == tuple(-v for v in b.move(7, 3, 16))


def test_sensitivity_scales_movement():
    low, high = Pointer(1.0), Pointer(2.0)
    assert high.move(10, 0, 100)[0] == 2 * low.move(10, 0, 100)[0]


def test_tiny_frame_times_do_not_explode():
    p = Pointer(1.0)
    dx, _ = p.move(5, 0, 0)
    assert dx <= 5 * MAX_GAIN


def test_scroll_down_is_a_negative_wheel_delta():
    v, h = Pointer().scroll(0, 10)
    assert v == -10 * SCROLL_UNITS_PER_PX
    assert h == 0


def test_scroll_right_is_a_positive_horizontal_delta():
    v, h = Pointer().scroll(4, 0)
    assert (v, h) == (0, 4 * SCROLL_UNITS_PER_PX)


def test_scroll_accumulates_fractions():
    p = Pointer()
    total = sum(p.scroll(0, 0.1)[0] for _ in range(40))
    assert total == pytest.approx(-40 * 0.1 * SCROLL_UNITS_PER_PX, abs=1)


def test_reset_drops_leftover_fractions():
    p = Pointer(sensitivity=0.5)
    p.move(1, 1, 16)
    p.reset()
    assert p.move(1, 1, 16) == (0, 0)
