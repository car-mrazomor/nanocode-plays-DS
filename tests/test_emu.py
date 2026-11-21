import time

import pytest

from conftest import decode_png, square_pos

START = (72, 64)
TILE = 8


def screen(emu):
    return decode_png(emu.look())


# ---------------- look ----------------

def test_look_returns_base64_png(emu):
    img = screen(emu)
    assert img.format == "PNG"
    assert img.size == (160, 144)


def test_look_scale(emu):
    img = decode_png(emu.look(scale=3))
    assert img.size == (480, 432)


def test_look_shows_toy_square(emu):
    assert square_pos(screen(emu)) == START


# ---------------- act ----------------

def test_act_entry_fields(emu):
    entry = emu.act(["right"])
    for key in ("step", "actions", "presses", "emulated_frames", "changed", "ts"):
        assert key in entry
    assert entry["actions"] == ["right"]
    assert entry["presses"] == 1
    assert abs(entry["ts"] - time.time()) < 5


def test_act_moves_square(emu):
    emu.act(["right"])
    assert square_pos(screen(emu)) == (START[0] + TILE, START[1])


def test_act_presses_in_order(emu):
    emu.act(["right", "right", "down"])
    assert square_pos(screen(emu)) == (START[0] + 2 * TILE, START[1] + TILE)


def test_act_each_entry_is_one_press(emu):
    emu.act(["left", "left", "left"])
    assert square_pos(screen(emu)) == (START[0] - 3 * TILE, START[1])


def test_act_max_six_presses(emu):
    entry = emu.act(["up"] * 8)
    assert entry["presses"] == 6
    assert len(entry["actions"]) == 6
    assert square_pos(screen(emu)) == (START[0], START[1] - 6 * TILE)


def test_act_empty_presses_nothing(emu):
    entry = emu.act([])
    assert entry["presses"] == 0
    assert entry["actions"] == []
    assert entry["emulated_frames"] == 0
    assert square_pos(screen(emu)) == START


def test_act_step_increments(emu):
    steps = [emu.act([])["step"] for _ in range(3)]
    assert steps == [1, 2, 3]


def test_act_emulated_frames_matches_emulator(emu):
    before = emu._emu.frame_count
    entry = emu.act(["right", "a"])
    assert entry["emulated_frames"] == emu._emu.frame_count - before


def test_act_changed_small_for_move(emu):
    entry = emu.act(["right"])
    assert 0 < entry["changed"] < 0.05


def test_act_changed_large_for_flash(emu):
    entry = emu.act(["a"])
    assert entry["changed"] > 0.9
    assert square_pos(screen(emu), inverted=True) == START


def test_act_changed_zero_when_nothing_happens(emu):
    entry = emu.act(["b"])
    assert entry["changed"] == 0


@pytest.mark.parametrize("bad", [["jump"], ["up", "fly"], ["A"]])
def test_act_rejects_unknown_buttons(emu, bad):
    with pytest.raises(Exception):
        emu.act(bad)
    assert square_pos(screen(emu)) == START


@pytest.mark.parametrize("bad", ["right", ("right",), None])
def test_act_rejects_non_list(emu, bad):
    with pytest.raises(Exception):
        emu.act(bad)


# ---------------- campaign state ----------------

def test_act_saves_state(emu):
    emu.act(["right"])
    assert emu._state_run().exists()
    assert emu._state_run().parent == emu.STATES


def test_state_name_keyed_to_rom(emu):
    name = emu._state_run().name
    assert name.startswith("state-") and name.endswith(".state")
    assert emu._state_run() == emu._state_run()


def test_init_resumes_saved_state(emu):
    emu.act(["right", "right"])
    emu._emu.stop(save=False)
    emu._emu = None

    emu.init()
    emu._emu.tick(2, True, False)
    assert square_pos(screen(emu)) == (START[0] + 2 * TILE, START[1])


def test_init_fresh_without_state(emu):
    emu._emu.stop(save=False)
    emu._emu = None
    assert not emu._state_run().exists()

    emu.init()
    emu._emu.tick(300, True, False)
    assert square_pos(screen(emu)) == START


# ---------------- ticker ----------------

def test_ticker_advances_time(emu):
    before = emu._emu.frame_count
    emu.start_ticker()
    time.sleep(0.5)
    assert emu._emu.frame_count > before


def test_ticker_stops(emu):
    emu.start_ticker()
    time.sleep(0.3)
    emu.stop_ticker()
    frozen = emu._emu.frame_count
    time.sleep(0.3)
    assert emu._emu.frame_count == frozen


def test_ticker_start_twice_is_noop(emu):
    emu.start_ticker()
    first = emu._tick_thread
    emu.start_ticker()
    assert emu._tick_thread is first


def test_ticker_runs_near_real_time(emu):
    emu.start_ticker()
    before = emu._emu.frame_count
    time.sleep(1.0)
    frames = emu._emu.frame_count - before
    assert 30 <= frames <= 90


def test_act_works_while_ticker_runs(emu):
    emu.start_ticker()
    emu.act(["down"])
    assert square_pos(screen(emu)) == (START[0], START[1] + TILE)
