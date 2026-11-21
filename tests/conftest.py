import base64
import io
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

PROJECT = Path(__file__).resolve().parent.parent
TOY_DIR = PROJECT / "toy"
TOY_ROM = TOY_DIR / "toy.gb"

sys.path.insert(0, str(PROJECT))

BOOT_FRAMES = 300


def _build_toy():
    if TOY_ROM.exists():
        return True
    if not all(shutil.which(t) for t in ("rgbasm", "rgblink", "rgbfix")):
        return False
    subprocess.run(["rgbasm", "-o", "toy.o", "toy.asm"], cwd=TOY_DIR, check=True)
    subprocess.run(["rgblink", "-o", "toy.gb", "toy.o"], cwd=TOY_DIR, check=True)
    subprocess.run(["rgbfix", "-v", "-p", "0xFF", "-t", "TOY", "toy.gb"], cwd=TOY_DIR, check=True)
    return True


def decode_png(b64):
    return Image.open(io.BytesIO(base64.b64decode(b64)))


def square_pos(image, inverted=False):
    """Top-left (x, y) in pixels of the toy square, or None."""
    a = np.asarray(image.convert("RGB"), dtype=int).sum(axis=2)
    target = 255 * 3 if inverted else 0
    ys, xs = np.where(a == target)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min())


@pytest.fixture
def emu(tmp_path, monkeypatch):
    if not _build_toy():
        pytest.skip("toy.gb not built and rgbds not installed")

    import emu as emu_mod

    monkeypatch.setattr(emu_mod, "ROOT", TOY_ROM)
    monkeypatch.setattr(emu_mod, "STATES", tmp_path)
    monkeypatch.setattr(emu_mod, "_rom_cache", None)
    monkeypatch.setattr(emu_mod, "_emu", None)
    monkeypatch.setattr(emu_mod, "_step", 0)
    monkeypatch.setattr(emu_mod, "_web_log", [])

    emu_mod.init()
    emu_mod._emu.tick(BOOT_FRAMES, True, False)
    yield emu_mod

    emu_mod.stop_ticker()
    if emu_mod._emu is not None:
        emu_mod._emu.stop(save=False)


@pytest.fixture
def client(emu):
    return emu.app.test_client()
