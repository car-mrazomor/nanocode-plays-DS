import base64
import io

from PIL import Image

from conftest import decode_png, square_pos

START = (72, 64)
TILE = 8
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def post_act(client, actions):
    return client.post("/act", json={"actions": actions})


def test_index_serves_ui(client):
    r = client.get("/")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "<html" in html
    assert "Action log" in html
    for b in ("up", "down", "left", "right", "a", "b", "start", "select"):
        assert f"act('{b}')" in html


def test_look_json_base64(client):
    r = client.get("/look")
    assert r.status_code == 200
    assert r.is_json
    img = decode_png(r.get_json()["image"])
    assert img.size == (160, 144)
    assert square_pos(img) == START


def test_look_png_is_real_image(client):
    r = client.get("/look.png")
    assert r.status_code == 200
    assert r.mimetype == "image/png"
    assert r.data.startswith(PNG_MAGIC)
    assert "no-store" in r.headers.get("Cache-Control", "")
    img = Image.open(io.BytesIO(r.data))
    assert img.size == (160, 144)
    assert square_pos(img) == START


def test_look_and_look_png_match(client):
    b64 = client.get("/look").get_json()["image"]
    png = client.get("/look.png").data
    assert base64.b64decode(b64) == png


def test_act_endpoint_moves_square(client):
    r = post_act(client, ["right", "down"])
    assert r.status_code == 200
    entry = r.get_json()
    assert entry["actions"] == ["right", "down"]
    assert entry["presses"] == 2
    img = Image.open(io.BytesIO(client.get("/look.png").data))
    assert square_pos(img) == (START[0] + TILE, START[1] + TILE)


def test_act_endpoint_empty_list(client):
    r = post_act(client, [])
    assert r.status_code == 200
    assert r.get_json()["presses"] == 0


def test_act_endpoint_missing_actions_presses_nothing(client):
    r = client.post("/act", json={})
    assert r.status_code == 200
    assert r.get_json()["presses"] == 0


def test_act_endpoint_caps_at_six(client):
    r = post_act(client, ["left"] * 9)
    assert r.status_code == 200
    assert r.get_json()["presses"] == 6


def test_act_endpoint_bad_button_is_error(client):
    r = post_act(client, ["jump"])
    assert r.status_code >= 400


def test_act_endpoint_bad_type_is_error(client):
    r = client.post("/act", json={"actions": "right"})
    assert r.status_code >= 400


def test_log_empty_at_start(client):
    r = client.get("/log")
    assert r.status_code == 200
    assert r.get_json() == []


def test_log_records_acts_in_order(client):
    post_act(client, ["up"])
    post_act(client, ["a", "b"])
    log = client.get("/log").get_json()
    assert [e["actions"] for e in log] == [["up"], ["a", "b"]]
    assert [e["step"] for e in log] == [1, 2]


def test_log_ignores_failed_acts(client):
    post_act(client, ["jump"])
    post_act(client, ["up"])
    log = client.get("/log").get_json()
    assert [e["actions"] for e in log] == [["up"]]


def test_log_keeps_last_200(emu, client):
    emu._web_log.extend({"step": i, "actions": []} for i in range(250))
    log = client.get("/log").get_json()
    assert len(log) == 200
    assert log[0]["step"] == 50
    assert log[-1]["step"] == 249
