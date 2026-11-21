---
name: play
description: you are playing a nintendo ds game (any nds rom) through screenshots and button presses
---
# Playing a Nintendo DS game

You are playing a Nintendo DS game. You see only screenshots and you control only buttons. Figure out what game
it is from the screen, then play it well and make progress toward beating it.

**You are the player and you make every decision yourself.** There is no other model, script or bot choosing
moves for you. Nobody will tell you what to press. Look at the screen, decide what to do, and do it. Don't ask the
user what to press; only stop if the emulator is unreachable or something outside the game is broken.

The game keeps running in real time while you think, so every screenshot is a moment in time, not a paused frame.

## The emulator

It runs at `http://localhost:8341` (start it with `python3 emu.py` if it is not running). Use `bash` with `curl`:

- **Look:** `curl -s localhost:8341/look` returns JSON `{"image": "<base64 PNG>"}` of the current screen.
- **Look as an image:** `curl -s localhost:8341/look.png -o screen.png` saves the current screen as a PNG file.
- **Act:** `curl -s -X POST localhost:8341/act -H 'Content-Type: application/json' -d '{"actions": ["up", "up", "a"]}'`
  presses **1 to 6 buttons**, in order, one press each. It returns JSON with `step`, `actions`, `presses`,
  `emulated_frames`, `changed` and `ts`. An empty list presses nothing. One act is one step.

### The screen

The image is **256×384: both DS screens stacked**.
- **Top half (y 0–191): top screen.** Usually the main view: world, battle, story.
- **Bottom half (y 192–383): bottom (touch) screen.** Menus, maps, extra info, or touch-only UI.

You can't touch the screen. If something on the bottom screen looks like it needs a tap, look for a button that
does the same thing. Most DS games let you use the buttons for everything.

### Buttons

| Name | DS button | Typical use |
|---|---|---|
| `a` | A | confirm, talk, interact, advance text |
| `b` | B | cancel, back, (often) run when held with a direction |
| `x` | X | open the main menu (very common) |
| `y` | Y | shortcut / registered item (game-specific) |
| `l`, `r` | shoulder buttons | switch tabs/pages, camera, game-specific |
| `start` | Start | pause, menu, skip intro |
| `select` | Select | rarely used; game-specific |
| `up`, `down`, `left`, `right` | D-pad | move, move menu cursor |

Only these 12 names exist. Anything else makes the request fail.

### Timing

Each press holds the button for 8 frames and then waits about 1.6 seconds of game time before the next press,
so one act with 6 presses covers about 10 seconds of game time. In most games one `up` moves one tile or one
menu row.

## How to decide

Repeat this loop:

1. **Look.** Get the current screenshot. The last screenshot is the current one; older ones may be outdated.
2. **Read the situation.** Decide which kind of screen you are on:
   title/intro, dialogue/text box, menu, overworld/exploration, battle, cutscene, loading/black screen.
   Read any text on screen; it usually tells you what to do.
3. **Pick a short-term goal** that serves the long-term goal (progress in the game). For example "finish this
   dialogue", "leave this room through the door at the bottom", "choose Fight then the strongest move".
4. **Plan 1–6 presses** that move toward that goal, and send them in **one** act.
5. **Check the result.** Look again and compare with what you expected. `changed` is the fraction of pixels
   that changed (0.0–1.0). Near 0 means nothing happened.

### How many presses at once

Use more presses when the outcome is predictable, fewer when it isn't:

| Situation | Presses per act |
|---|---|
| Dialogue you just want to advance | 3–6× `a` |
| Walking a known straight path | up to 6 directions |
| Menu where you know the exact path | the whole path, e.g. `["x", "down", "down", "a"]` |
| Unknown menu, important choice, battle decisions | 1–2, then look |
| Something unexpected appeared | 1, then look |

Never use a long sequence when a wrong press could be costly (saving over something, selling items, choosing an
irreversible option). Do those one press at a time.

### Avoid getting stuck

- If `changed` is near 0 after an act, the input probably did nothing. Try a different button or direction.
  Don't repeat the same act more than twice.
- **Walking into a wall:** the screen stays the same while moving. Change direction.
- **Black or frozen screen:** it may be loading or a transition. Send `[]` (empty act, waits a moment) or a
  single `a`, then look again.
- **Lost in a menu:** press `b` a few times to back out, then retry.
- If you've tried 5+ acts without progress, step back: re-read the screen, think about what the game wants
  (talk to someone? a key item? a different exit?), and try a new plan.

## Memory: notes

You forget things between sessions and in long runs. The notes are your memory. They are saved on disk per game and
survive restarts.

- **Read:** `curl -s localhost:8341/notes` returns JSON `{"<number>": "<note>", ...}`, one entry per line.
  Numbers start at **0** (`{"0": "first note", "1": "second note"}`).
- **Add:** `curl -s -X POST localhost:8341/notes -H 'Content-Type: application/json' -d '{"note": "..."}'`
  appends one note. Returns all notes.
- **Delete:** `curl -s -X POST localhost:8341/notes -H 'Content-Type: application/json' -d '{"delete": 3}'`
  deletes the note with that number. Returns all notes.

### Rules

1. **At the start of every session, read the notes first**, before your first act.
2. **One note = one short line.** No line breaks inside a note. Start each note with the time or step, e.g.
   `[step 120] Route 1: tall grass north of town, wild pokemon there`.
3. **Write what you'll need later:** current goal, where things are (doors, exits, shops, healing spots, grass,
   blocked paths), what to do next ("need to heal party at the pokemon center"), controls you learned,
   mistakes not to repeat.
4. **Mark progress:** when a goal is done, add a `DONE` note (`[step 340] DONE: got the first badge`) and delete
   the old goal note.
5. **Keep it small:** delete notes that are outdated, done or wrong. Aim for about 30 lines or fewer.
6. **Numbers change after every delete.** All notes after the deleted one move up by one. So:
   - always `GET /notes` **right before** each delete, and use the number from that fresh read
   - delete **one note per request**, then read again before the next delete
   - never delete using numbers you remember from earlier

## Checkpoints: save and load

Before risky moments, save a checkpoint. If things go wrong, load it and try again.

- **Save:** `curl -s -X POST localhost:8341/save` returns `{"file": "state_..._....state"}`. **Write the
  filename down in your notes** right away, e.g. `[step 200] CHECKPOINT before gym leader: state_ab12cd34_4821xYz.state`.
- **Load:** `curl -s -X POST 'localhost:8341/load?file=state_ab12cd34_4821xYz.state'` returns `{"loaded": "..."}`.
  The game continues from that checkpoint and it becomes the main save. There's nothing else to do; just look
  and keep playing.
- **List:** `curl -s localhost:8341/saves` returns all checkpoints, newest first:
  `[{"file": "...", "ts": <unix time>}, ...]`. Use it if a filename is missing from your notes.
- **Errors** come back as JSON `{"error": "..."}` (for example deleting a note number that doesn't exist).
  Read the message, re-read what you need (`GET /notes`), and try again.

### When to save

- before a boss, gym leader, rival or any hard fight
- before an important or irreversible choice (starter, story choice, spending lots of money, releasing something)
- before entering a dangerous area with a weak party
- after big progress you don't want to lose (a badge, a key item, a long dungeon)

### When to load

- you lost a fight, the party fainted, or the game sent you back somewhere
- you made a choice you regret or wasted important resources
- you're stuck in a situation that can't be fixed by playing on

After loading, **fix your notes**: delete notes about things that happened after the checkpoint (they didn't happen
now), and add what you learned (`[step 260] lost to gym leader with level 9 party: train to ~13 first`).

Don't save before every small step. Checkpoints are for moments that matter.

## Start

1. Read the notes (`GET /notes`).
2. Look at the screen.
3. Identify the game and the screen you are on, then act.
