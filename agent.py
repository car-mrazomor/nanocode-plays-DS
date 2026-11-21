import json
import os
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

import openai
from dotenv import load_dotenv

load_dotenv()


ROOT = Path.home() / ".nanocode" / "config.json"
KEY = os.environ.get("KEY", json.loads(ROOT.open("r").read())["api"]["key"])
URL = "http://127.0.0.1:8765/v1"
client = openai.OpenAI(base_url=URL, api_key=KEY)

START_PROMPT = """\
You are now playing a Nintendo DS game. Load and follow the `play` skill; it explains the emulator, the controls
and the rules.

Your goal: play the game well and keep making progress toward beating it. You make every decision yourself.
Don't ask me what to do.

Before your first move:
1. Read your notes with GET /notes. They are your memory from earlier sessions; continue from them.
2. Look at the screen, work out which game this is and what is happening.

Then play:
- Send 1 to 6 button presses per /act. Use more when the result is predictable (advancing dialogue, walking a
  known path, a menu path you know), and 1-2 when you're unsure or the choice matters.
- Keep your notes up to date: goals, locations, what to do next, what failed. Mark finished goals as DONE.
- Save a checkpoint (/save) before risky moments and write its filename in your notes. Load it (/load) if
  things go badly.

After each turn, reply in one or two short lines: what you see and what you did. Keep replies short.
"""

TURN_PROMPT = """\
Here is the current screen. Check what changed since your last move, decide your next move and act
(1-6 presses). Update your notes if you learned something. Reply in one or two short lines.
"""

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GRAY = "\033[90m"
CYAN = "\033[36m"


def act(message=None, image=None, chat="1"):
    messages = [{"type": "text", "text": message}]
    if image:
        messages.extend([{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image}"}}])
    
    r = client.chat.completions.create(
        model="nanocode",
        messages=[{"role": "user", "content": messages}],
        extra_headers={"X-Nanocode-Session-Id": chat},
    )

    return r


def look():
    req = urllib.request.Request(url="http://127.0.0.1:8341/look")
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            return json.loads(raw.decode())["image"]
    except urllib.error.HTTPError as e:
        return e


if __name__ == "__main__":
    response = act(START_PROMPT)
    while True:
        image = look()
        response = act(TURN_PROMPT, image=image)
        print(f"{GRAY}[{datetime.now().strftime('%d/%m/%Y, %H:%M:%S')}]{RESET} "
            f"{BOLD}{CYAN}nanocode Agent:{RESET} {response.choices[0].message.content}")
        print(f"{DIM}Tokens: {response.usage.completion_tokens}{RESET}")
        print(f"{DIM}Total tokens: {response.usage.total_tokens}{RESET}")
        print("-"*os.get_terminal_size()[0] + "\n\n")
