import base64
import hashlib
import io
import os
import random
import string
import threading
import time
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request
from src.melonds_python import PymelonDS

load_dotenv()


GAME_ROM = os.environ.get("GAME_ROM", "pokemon_white.nds")
ROOT = Path(__file__).parent / "roms" / GAME_ROM
STATES = Path(__file__).parent / "runs"
STATES.mkdir(exist_ok=True)

BUTTONS = ("up", "down", "left", "right", "a", "b",
           "start", "select", "x", "y", "l", "r")
TICK_FRAMES = 6
GB_FPS = 59.8261
PRESS_FRAMES = 8

_lock = threading.Lock()
_emu = None
_step = 0
_actions = []
_tick_thread = None
_tick_stop = threading.Event()


def start_ticker():
    global _tick_thread
    if _tick_thread is not None:
        return
    _tick_stop.clear()

    def run():
        next_at = time.monotonic()
        while not _tick_stop.is_set():
            try:
                with _lock:
                    if _emu is not None:
                        _emu.tick(TICK_FRAMES, render=True)
            except Exception as exc:
                print(f"[ticker] {exc}", flush=True)
                if _tick_stop.wait(0.1):
                    break
                continue
            next_at += TICK_FRAMES / GB_FPS
            if _tick_stop.wait(max(0.0, next_at - time.monotonic())):
                break
            next_at = time.monotonic()

    _tick_thread = threading.Thread(target=run, name="ticker", daemon=True)
    _tick_thread.start()


def stop_ticker():
    global _tick_thread
    _tick_stop.set()
    thread, _tick_thread = _tick_thread, None
    if thread is not None:
        thread.join(timeout=2)


_rom_cache = None


def _rom_bytes():
    global _rom_cache
    if _rom_cache is None:
        _rom_cache = ROOT.read_bytes()
    return _rom_cache


def _new_emulator():
    """For manual testing using window not null"""
    emu = PymelonDS(io.BytesIO(_rom_bytes()), window="null")
    emu.set_emulation_speed(0)

    return emu


def _frame():
    return _emu.screen.image.convert("RGB").copy()


def _changed(a, b):
    x = np.asarray(a, dtype=np.int16)
    y = np.asarray(b, dtype=np.int16)

    return float(np.mean(np.max(abs(x - y), axis=2) > 20))


def look(scale=1):
    buf = io.BytesIO()
    image = _emu.screen.image
    image = image.resize(size=(int(image.width*scale), int(image.height*scale)))

    with buf:
        image.save(buf, format="PNG")
        buf.seek(0) 
        out = buf.read()

    return base64.b64encode(out).decode()


def _state_run():
    sha = hashlib.sha256(_rom_bytes()).hexdigest()[:8]
    return STATES / f"state_{sha}.state"


def _save():
    sha = hashlib.sha256(_rom_bytes()).hexdigest()[:8]
    part = "".join(random.choice(string.ascii_letters) for _ in range(3))
    state = STATES / f"state_{sha}_{random.randint(1000,9999)}{part}.state"
    with state.open("wb") as ss:
        _emu.save_state(ss)

    return state


def _load(filename: Path):
    if filename.exists():
        with filename.open("rb") as ss:
            with _state_run().open("wb") as ss2:
                ss2.write(ss.read())

        with _state_run().open("rb") as ss:
            _emu.load_state(ss)
        
        return True

    return False


def _notes_file():
    sha = hashlib.sha256(_rom_bytes()).hexdigest()[:8]
    return STATES / f"notes_{sha}.txt"


def notes_get(*args):
    notes_dict = {}
    if not _notes_file().exists():
        return notes_dict
    with _notes_file().open("r") as n:
        notes = n.read().split("\n")
        for i,note in enumerate(notes):
            if note is None or note == "":
                continue
            notes_dict[str(i)] = note

    return notes_dict


def notes_post(note):
    if note == "" or note is None:
        return notes_get()

    array = [v for v in notes_get().values()]
    array.append(note)
    with _notes_file().open("w") as f:
        for i,n in enumerate(array):
            f.write(n)
            if i != len(array)-1:
                f.write("\n")

    return notes_get()
    


def notes_delete(note_num):
    notes_dict = notes_get()
    try:
        notes_dict.pop(str(note_num))
    except (BaseException, KeyError):
        raise KeyError("doesn't exist")
    with _notes_file().open("w") as f:
        for i,note in enumerate(notes_dict.values()):
            f.write(note)
            if i != len(notes_dict.values())-1:
                f.write("\n")


ACTIONS = {
    "get": notes_get,
    "post": notes_post,
    "delete": notes_delete
}


def _notes(action="get", note=None):
    """Action can be get, post, delete"""
    return ACTIONS[action](note)


def act(actions):
    if not isinstance(actions, list):
        raise ValueError("Actions needs to be list")
    if len(actions) > 6:
        actions = actions[:6]
    if not all([action in BUTTONS for action in actions]):
        raise ValueError("Some of actions is not supported")

    global _step, _actions
    with _lock:
        before = _frame()
        held = 0
        for action in actions:
            _emu.button_press(action)
            try:
                _emu.tick(PRESS_FRAMES, render=True)
                held += PRESS_FRAMES
            finally:
                _emu.button_release(action)
            _emu.tick(PRESS_FRAMES*12, render=True)
            held += PRESS_FRAMES*12

        after = _frame()
        _step += 1
        entry = {"step": _step, "actions": list(actions), "presses": len(actions),
            "emulated_frames": held, "changed": round(_changed(before, after), 4),
            "ts": time.time()}
        with _state_run().open("wb") as ss:
            _emu.save_state(ss)

    return entry


def init():
    global _emu
    with _lock:
        _emu = _new_emulator()
        if _state_run().exists():
            with _state_run().open("rb") as ss:
                _emu.load_state(ss)


# ---------------- web ----------------

app = Flask(__name__)
_web_log = []

PAGE = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>nanocode plays DS</title>
<style>
  body { font-family: monospace; background: #111; color: #ddd; display: flex; gap: 24px; padding: 16px; margin: 0; align-items: flex-start; }
  #screen { height: var(--h); aspect-ratio: 256 / 384; image-rendering: pixelated; background: #000;
            border: 6px solid #0b0b0d; border-radius: 4px; display: block; }
  button { background: #333; color: #ddd; border: 1px solid #555; cursor: pointer; font-family: monospace; }
  button:hover { background: #444; }
  button:active { background: #555; transform: translateY(1px); }

  /* DS body */
  .ds { background: #1d1d22; border: 1px solid #2f2f36; border-radius: 22px; padding: 12px 20px 22px; }
  .shoulders { display: flex; justify-content: space-between; margin-bottom: 12px; }
  .shoulders button { width: 110px; height: 30px; border-radius: 14px 14px 4px 4px; }
  .console { display: flex; align-items: flex-end; gap: 22px; }
  .side { height: calc(var(--h) / 2); display: flex; flex-direction: column; align-items: center;
          justify-content: center; gap: 28px; }
  .dpad, .face { display: grid; grid-template-columns: repeat(3, 44px); grid-template-rows: repeat(3, 44px); gap: 3px; }
  .dpad button { border-radius: 6px; font-size: 16px; }
  .face button { border-radius: 50%; font-size: 15px; font-weight: bold; }
  .small { display: flex; flex-direction: column; gap: 10px; }
  .small button { width: 70px; height: 22px; border-radius: 11px; font-size: 11px; }
  .sys { display: flex; justify-content: center; align-items: center; gap: 10px; margin-top: 16px; }
  .sys button { width: 70px; height: 22px; border-radius: 11px; font-size: 11px; }
  .sys select { height: 22px; max-width: 230px; background: #26262c; color: #ddd; border: 1px solid #555;
                border-radius: 11px; padding: 0 8px; font-family: monospace; font-size: 11px; }
  #sysmsg { text-align: center; font-size: 11px; color: #888; margin-top: 6px; min-height: 14px; }

  #logwrap { width: 440px; }
  #logwrap h2 { margin: 0 0 10px; font-size: 14px; color: #aaa; letter-spacing: 1px; text-transform: uppercase; }
  #log { height: calc(100vh - 70px); overflow-y: auto; display: flex; flex-direction: column; gap: 8px; padding-right: 6px; }
  #log::-webkit-scrollbar { width: 6px; }
  #log::-webkit-scrollbar-thumb { background: #444; border-radius: 3px; }
  .entry { background: #1b1b1f; border: 1px solid #2a2a30; border-radius: 6px; padding: 8px 10px; }
  .entry.empty { border-left-color: #555; opacity: 0.7; }
  .head { display: flex; justify-content: space-between; font-size: 12px; color: #888; margin-bottom: 6px; }
  .step { color: #6c8cff; font-weight: bold; }
  .chips { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 6px; }
  .chip { background: #2b2f45; color: #cfd6ff; border-radius: 10px; padding: 2px 8px; font-size: 12px; }
  .chip.a, .chip.b, .chip.x, .chip.y { background: #45302b; color: #ffd6cf; }
  .chip.l, .chip.r { background: #3f2b45; color: #f0cfff; }
  .chip.start, .chip.select { background: #2b4532; color: #cfffd9; }
  .chip.none { background: #333; color: #999; }
  .meta { display: flex; gap: 12px; align-items: center; font-size: 11px; color: #999; }
  .bar { flex: 1; height: 5px; background: #2a2a30; border-radius: 3px; overflow: hidden; }
  .bar > div { height: 100%; background: linear-gradient(90deg, #6c8cff, #b46cff); }
</style>
</head>
<body>
<div class="ds">
  <div class="shoulders">
    <button onclick="act('l')" title="l">L</button>
    <button onclick="act('r')" title="r">R</button>
  </div>
  <div class="console">
    <div class="side">
      <div class="dpad">
        <span></span><button onclick="act('up')" title="up">&#9650;</button><span></span>
        <button onclick="act('left')" title="left">&#9664;</button><span></span><button onclick="act('right')" title="right">&#9654;</button>
        <span></span><button onclick="act('down')" title="down">&#9660;</button><span></span>
      </div>
    </div>
    <img id="screen">
    <div class="side">
      <div class="face">
        <span></span><button onclick="act('x')">X</button><span></span>
        <button onclick="act('y')">Y</button><span></span><button onclick="act('a')">A</button>
        <span></span><button onclick="act('b')">B</button><span></span>
      </div>
      <div class="small">
        <button onclick="act('start')">START</button>
        <button onclick="act('select')">SELECT</button>
      </div>
    </div>
  </div>
  <div class="sys">
    <button onclick="saveState()" title="save a checkpoint">SAVE</button>
    <select id="saves"><option value="">no checkpoints</option></select>
    <button onclick="loadState()" title="load the selected checkpoint">LOAD</button>
    <select id="viewfps" onchange="setViewFps(this.value)" title="how often this page refreshes the screen (only for you, the agent is not affected)">
      <option value="1">view 1 fps</option>
      <option value="2">view 2 fps</option>
      <option value="5">view 5 fps</option>
      <option value="10">view 10 fps</option>
      <option value="20">view 20 fps</option>
      <option value="30">view 30 fps</option>
    </select>
  </div>
  <div id="sysmsg"></div>
</div>
<div id="logwrap"><h2>Action log</h2><div id="log"></div></div>
<script>
let screenBusy = false;
async function refreshScreen() {
  if (screenBusy) return;          // skip if the previous frame is still loading
  screenBusy = true;
  try {
    const r = await fetch('/look');
    const d = await r.json();
    document.getElementById('screen').src = 'data:image/png;base64,' + d.image;
  } catch (e) {}
  screenBusy = false;
}
let screenTimer = null;
function setViewFps(fps) {
  fps = Number(fps) || 2;
  clearInterval(screenTimer);
  screenTimer = setInterval(refreshScreen, 1000 / fps);
  localStorage.setItem('viewFps', fps);
  document.getElementById('viewfps').value = String(fps);
}
function renderEntry(e) {
  const acts = e.actions || [];
  const chips = acts.length
    ? acts.map(a => `<span class="chip ${a}">${a}</span>`).join('')
    : '<span class="chip none">no press</span>';
  const time = e.ts ? new Date(e.ts * 1000).toLocaleTimeString() : '';
  const changed = typeof e.changed === 'number' ? e.changed : 0;
  const pct = Math.max(0, Math.min(100, changed * 100));
  return `<div class="entry ${acts.length ? '' : 'empty'}">
    <div class="head"><span class="step">#${e.step ?? '?'}</span><span>${time}</span></div>
    <div class="chips">${chips}</div>
    <div class="meta">
      <span>${e.emulated_frames ?? 0} frames</span>
      <span>changed ${(changed * 100).toFixed(1)}%</span>
      <div class="bar"><div style="width:${pct}%"></div></div>
    </div>
  </div>`;
}
async function refreshLog() {
  try {
    const r = await fetch('/log');
    const d = await r.json();
    const el = document.getElementById('log');
    el.innerHTML = d.filter(Boolean).slice().reverse().map(renderEntry).join('');
  } catch (e) {}
}
async function act(button) {
  await fetch('/act', {method: 'POST', headers: {'Content-Type': 'application/json'},
                       body: JSON.stringify({actions: [button]})});
  refreshScreen(); refreshLog();
}
function sysmsg(text) { document.getElementById('sysmsg').textContent = text; }
async function refreshSaves(selected) {
  try {
    const r = await fetch('/saves');
    const d = await r.json();
    const el = document.getElementById('saves');
    const keep = selected || el.value;
    el.innerHTML = d.length
      ? d.map(s => `<option value="${s.file}">${new Date(s.ts * 1000).toLocaleString()}  ${s.file}</option>`).join('')
      : '<option value="">no checkpoints</option>';
    if (keep && d.some(s => s.file === keep)) el.value = keep;
  } catch (e) {}
}
async function saveState() {
  try {
    const r = await fetch('/save', {method: 'POST'});
    const d = await r.json();
    if (!r.ok) { sysmsg('save failed: ' + (d.error || r.status)); return; }
    sysmsg('saved ' + d.file);
    refreshSaves(d.file);
  } catch (e) { sysmsg('save failed'); }
}
async function loadState() {
  const file = document.getElementById('saves').value;
  if (!file) { sysmsg('no checkpoint selected'); return; }
  if (!confirm('Load checkpoint ' + file + '? Current progress after it is lost.')) return;
  try {
    const r = await fetch('/load?file=' + encodeURIComponent(file), {method: 'POST'});
    const d = await r.json();
    if (!r.ok) { sysmsg('load failed: ' + (d.error || r.status)); return; }
    sysmsg('loaded ' + d.loaded);
    refreshScreen();
  } catch (e) { sysmsg('load failed'); }
}
setViewFps(localStorage.getItem('viewFps') || 2);
setInterval(refreshLog, 1000);
setInterval(refreshSaves, 5000);
refreshScreen(); refreshLog(); refreshSaves();
</script>
</body>
</html>
"""


@app.get("/")
def index():
    return PAGE


@app.get("/look")
def look_route():
    return jsonify({"image": look()})


@app.get("/look.png")
def look_png_route():
    png = base64.b64decode(look())
    return Response(png, mimetype="image/png",
                    headers={"Cache-Control": "no-store"})


@app.post("/act")
def act_route():
    data = request.get_json(force=True) or {}
    try:
        entry = act(data.get("actions", []))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
    _web_log.append(entry)
    return jsonify(entry)


@app.get("/log")
def log_route():
    return jsonify(_web_log[-200:])


@app.get("/notes")
def notes_get_route():
    return jsonify(_notes("get"))


@app.post("/notes")
def notes_post_route():
    data = request.get_json(force=True) or {}
    try:
        if "delete" in data:
            _notes("delete", data["delete"])
        elif "note" in data:
            _notes("post", data["note"])
        else:
            return jsonify({"error": "send {\"note\": \"...\"} or {\"delete\": <number>}"}), 400
    except KeyError as exc:
        return jsonify({"error": f"note {data.get('delete')}: {exc.args[0] if exc.args else 'not found'}"}), 404
    return jsonify(_notes("get"))


@app.get("/saves")
def saves_route():
    sha = hashlib.sha256(_rom_bytes()).hexdigest()[:8]
    files = sorted(STATES.glob(f"state_{sha}_*.state"), key=lambda f: f.stat().st_mtime, reverse=True)
    return jsonify([{"file": f.name, "ts": f.stat().st_mtime} for f in files])


@app.post("/save")
def save_route():
    with _lock:
        state = _save()
    return jsonify({"file": state.name})


@app.post("/load")
def load_route():
    name = request.args.get("file", "")
    sha = hashlib.sha256(_rom_bytes()).hexdigest()[:8]
    if Path(name).name != name or not name.startswith(f"state_{sha}_") or not name.endswith(".state"):
        return jsonify({"error": "unknown state file"}), 400
    with _lock:
        loaded = _load(STATES / name)
    if not loaded:
        return jsonify({"error": "state file not found"}), 404
    return jsonify({"loaded": name})


if __name__ == "__main__":
    init()
    start_ticker()
    app.run(host="0.0.0.0", port=8341, threaded=True)
