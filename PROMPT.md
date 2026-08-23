Hi Claude! I want to install a tamagotchi pet in my Claude Code statusline. Follow these steps exactly:

1. Create the file `~/.claude/claude_pet_tama.py` with EXACTLY this content (do not change anything):

```python
#!/usr/bin/env python3
"""
claude_pet_tama.py — tamagotchi v2: pixel-art edition of the Claude Code
statusline pet.

- Half-block pixel-art sprite (2 pixels per character cell, Catppuccin Mocha
  palette), animated at 1 fps (requires "refreshInterval": 1 in settings).
- Species evolve during each session, from lines of code written:
  egg -> chick (50) -> bird (400) -> phoenix (2500). Every chat hatches anew.
- Each mood has its own animation: breathing, wing stretches, bobbing,
  excited flapping, shivering with a sweat drop, panicked shaking.
- Mood detection reads the tail of the session transcript and reacts when
  your last message sounds frustrated (swearing, CAPS, screams — pt/en/es)
  or when tools keep erroring in a row. Moods step down one tier per new
  prompt: table flip -> comforting tea -> back to normal.
- Night mode: the pet sleeps between 22h and 7h (rage still wakes it up).
- It poops when the session deletes too many lines. Sorry.
- Three-line display: sprite on the left, vitals and session info on the right.

No external dependencies — plain Python 3.
"""

import json
import os
import re
import sys
import time
from pathlib import Path

STATE_FILE = Path.home() / ".claude" / "pet_state.json"

# Catppuccin Mocha, as truecolor ANSI escapes (for text)
MAUVE = "\033[38;2;203;166;247m"
LAVENDER = "\033[38;2;180;190;254m"
PINK = "\033[38;2;245;194;231m"
GREEN = "\033[38;2;166;227;161m"
TEAL = "\033[38;2;148;226;213m"
YELLOW = "\033[38;2;249;226;175m"
PEACH = "\033[38;2;250;179;135m"
RED = "\033[38;2;243;139;168m"
SKY = "\033[38;2;137;220;235m"
OVERLAY = "\033[38;2;108;112;134m"
RESET = "\033[0m"

# pixel palette: sprite char -> "r;g;b" ('.' = transparent)
PIXELS = {
    "t": "148;226;213",  # teal body
    "m": "203;166;247",  # mauve wing
    "y": "249;226;175",  # yellow chick / flames
    "p": "250;179;135",  # peach beak / phoenix body
    "r": "243;139;168",  # red wing / rage eyes
    "w": "245;224;220",  # rosewater eggshell
    "l": "180;190;254",  # lavender egg spots
    "k": "17;17;27",     # crust — open eyes
    "s": "137;220;235",  # sky — nervous sweat drop
    "h": "245;194;231",  # pink — comforted blush cheeks
    "R": "210;15;57",    # deep red — rage eyes (mocha red reads as blush)
    "B": "148;108;80",   # brown — you know what this is
    "g": "88;91;112",    # gray — tiny keyboard
}

SPRITE_W = 13

# species evolve DURING each session, from lines of code written (hatching arc)
# base sprites: 6 pixel rows -> 3 terminal rows. 'E' = eye slot.
SPECIES = [
    (0, "egg", "w", [
        "......w......",
        ".....www.....",
        "....wwwww....",
        "....wlwww....",
        "....wwwlw....",
        ".....www.....",
    ]),
    (50, "chick", "y", [
        ".....yyy.....",
        "....yyyyy....",
        "....yEyEy....",
        "....yypyy....",
        "....yyyyy....",
        ".....y.y.....",
    ]),
    (400, "bird", "t", [
        "....ttttt....",
        "...ttttttt...",
        "..ttEtttEtt..",
        "..tttpppttt..",
        "..ttttttttt..",
        "...tt...tt...",
    ]),
    (2500, "phoenix", "p", [
        ".y..ppppp..y.",
        "...ppppppp...",
        "..ppEpppEpp..",
        "..pppyyyppp..",
        "..ppppppppp..",
        "...pp...pp...",
    ]),
]

# mood stages by context usage: (low, high, mood text, color, animation)
STAGES = [
    (0, 20, "napping", GREEN, "rest"),
    (20, 40, "stretching", GREEN, "stretch"),
    (40, 60, "coding with you", TEAL, "type"),
    (60, 80, "getting excited", YELLOW, "flap"),
    (80, 92, "a bit nervous", PEACH, "shiver"),
    (92, 101, "BEGGING for /compact", RED, "shake"),
]

COMFORT = ("\u2665 deep breaths, we got this \U0001f375", PINK, "calm")
RAGE = ("(╯°□°)╯︵┻━┻ rage detected... breathe", RED, "shake")
DEBUG_PAIN = ("debugging is pain, hold on", YELLOW, "shiver")
SLEEP = ("sleeping... go to bed too?", LAVENDER, "rest")

SWEARS = (
    # pt
    "pqp", "caralho", "porra", "merda", "krl", "vsf", "fdp", "puta",
    # en
    "fuck", "shit", "wtf", "ffs", "dammit", "goddamn",
    # es
    "joder", "mierda", "carajo", "coño", "cabrón", "cabron", "la concha",
)
# emotional interjections — unlike work talk ("não funciona"), these only show up when exasperated
EXASPERATION = (
    # pt
    "pelo amor", "misericordia", "misericórdia", "socorro", "affs",
    "que odio", "que ódio", "to surtando", "tô surtando", "desisto",
    # en
    "for the love of god", "i give up", "i hate this", "oh come on",
    # es
    "por dios", "dios mio", "dios mío", "no puede ser", "me rindo",
    "qué rabia", "que rabia", "estoy harta", "estoy harto",
)

# whole words only — substring matching would hit "comPUTAdor" or "SHITlist"
SWEAR_RE = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in SWEARS) + r")\b")
EXASPERATION_RE = re.compile(r"\b(?:" + "|".join(re.escape(p) for p in EXASPERATION) + r")\b")

# a run of 4+ repeated letters reads as a scream — except k/K, which is Brazilian laughter
SCREAM_RE = re.compile(r"([a-jl-zA-JL-Z])\1{3,}")

SESSION_TTL = 86400  # drop per-session mood state after a day
TRANSCRIPT_TAIL_BYTES = 65536
TRANSCRIPT_TAIL_MAX_BYTES = 1048576  # fallback window when huge tool results push the prompt back

EVOLUTION_SECONDS = 5  # how long the hatch/evolution celebration plays

# hatching: the chick pops out of the broken shell, then wears the cap
HATCH_FRAMES = [
    [
        ".....yyy.....",
        "....yyyyy....",
        "....yEyEy....",
        "...wyypyyw...",
        "...wwwwwww...",
        "....wwwww....",
    ],
    [
        ".....www.....",
        "....yyyyy....",
        "....yEyEy....",
        "....yypyy....",
        "....yyyyy....",
        ".....y.y.....",
    ],
]

NIGHT_START = 22
NIGHT_END = 7
POOP_THRESHOLD = 300  # lines removed in one session


def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"max_pct_seen": 0}


def save_state(state):
    # atomic write: concurrent sessions update this file every second, and a
    # plain write_text can be read half-finished, wiping everyone's mood
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_FILE.with_name(f"pet_state.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(state))
        tmp.replace(STATE_FILE)
    except Exception:
        pass  # never let the statusline break because of this


def pick_stage(pct):
    for lo, hi, mood, color, anim in STAGES:
        if lo <= pct < hi:
            return mood, color, anim
    last = STAGES[-1]
    return last[2], last[3], last[4]


def bar(pct, color, width=10):
    filled = int(round(width * pct / 100))
    return color + "█" * filled + OVERLAY + "░" * (width - filled) + RESET


def git_info(cwd):
    # branch name and HEAD sha read straight from .git files — the statusline
    # runs every second, so no subprocess spawning per tick
    try:
        d = Path(cwd).resolve()
        gitdir = None
        while True:
            g = d / ".git"
            if g.is_dir():
                gitdir = g
                break
            if g.is_file():  # worktree/submodule: ".git" points elsewhere
                gitdir = Path(g.read_text().split(":", 1)[1].strip())
                if not gitdir.is_absolute():
                    gitdir = (d / gitdir).resolve()
                break
            if d == d.parent:
                return "", None
            d = d.parent

        head = (gitdir / "HEAD").read_text().strip()
        if not head.startswith("ref: "):
            return "", head  # detached HEAD

        ref = head[5:]
        branch = ref[11:] if ref.startswith("refs/heads/") else ref

        # refs live in the common dir when inside a linked worktree
        common = gitdir
        commondir = gitdir / "commondir"
        if commondir.exists():
            common = (gitdir / commondir.read_text().strip()).resolve()

        sha = None
        ref_file = common / ref
        if ref_file.exists():
            sha = ref_file.read_text().strip()
        else:
            packed = common / "packed-refs"
            if packed.exists():
                for line in packed.read_text().splitlines():
                    if line.endswith(" " + ref):
                        sha = line.split()[0]
                        break
        return branch, sha
    except Exception:
        return "", None


def read_recent_entries(path, tail_bytes=TRANSCRIPT_TAIL_BYTES):
    # only the tail of the transcript, so long sessions stay cheap to read
    try:
        p = Path(path)
        size = p.stat().st_size
        with p.open("rb") as f:
            if size > tail_bytes:
                f.seek(size - tail_bytes)
                f.readline()  # drop the partial first line
            raw = f.read().decode("utf-8", errors="replace")
        entries = []
        for line in raw.splitlines():
            try:
                entries.append(json.loads(line))
            except Exception:
                pass
        return entries
    except Exception:
        return []


def looks_typed(text):
    # skip pastes (long), system tags and interruptions — keep what the human typed
    stripped = text.strip()
    if not stripped or len(stripped) > 1500:
        return False
    if stripped.startswith("<") or stripped.startswith("[Request interrupted"):
        return False
    return True


def last_user_prompt(entries):
    # a real prompt is a user entry with typed text and no tool_result blocks
    for entry in reversed(entries):
        if entry.get("type") != "user" or entry.get("isMeta"):
            continue
        content = (entry.get("message") or {}).get("content")
        if isinstance(content, str):
            if looks_typed(content):
                return entry.get("uuid"), content
            continue
        if isinstance(content, list):
            if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
                continue
            texts = [
                b.get("text", "") for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            joined = " ".join(texts)
            if texts and looks_typed(joined):
                return entry.get("uuid"), joined
    return None, ""


def error_streak(entries):
    # consecutive erroring tool results at the tail of the session
    streak = 0
    for entry in reversed(entries):
        if entry.get("type") != "user":
            continue
        content = (entry.get("message") or {}).get("content")
        if not isinstance(content, list):
            break
        results = [
            b for b in content if isinstance(b, dict) and b.get("type") == "tool_result"
        ]
        if not results:
            break
        if any(b.get("is_error") for b in results):
            streak += 1
            continue
        break
    return streak


def rate_frustration(text):
    lowered = text.lower()
    points = 0
    if SWEAR_RE.search(lowered):
        points += 3
    letters = [c for c in text if c.isalpha()]
    if len(letters) >= 8:
        caps_ratio = sum(c.isupper() for c in letters) / len(letters)
        if caps_ratio > 0.6:
            points += 2
    if "???" in text or "!!!" in text:
        points += 1
    if SCREAM_RE.search(text):
        points += 2
    if EXASPERATION_RE.search(lowered):
        points += 2
    return min(5, points)


def update_frustration(state, session_id, entries, transcript_path):
    # mood state is per session — parallel sessions must not feed each other.
    # moods step down one tier per new prompt: rage (2) -> comfort (1) -> normal (0);
    # an angry prompt jumps straight back to its tier.
    now = time.time()
    sessions = state.get("sessions") or {}
    sessions = {
        sid: fr for sid, fr in sessions.items()
        if now - fr.get("ts", 0) < SESSION_TTL
    }
    fr = sessions.get(session_id) or {}
    stage = fr.get("stage", 0)

    uuid, text = last_user_prompt(entries)
    if uuid is None and entries:
        # giant tool results can push the last prompt out of the small tail
        wider = read_recent_entries(transcript_path, TRANSCRIPT_TAIL_MAX_BYTES)
        uuid, text = last_user_prompt(wider)
    if uuid and uuid != fr.get("uuid"):
        rated = rate_frustration(text)
        if rated >= 4:
            fresh = 2
        elif rated >= 2:
            fresh = 1
        else:
            fresh = 0
        stage = max(fresh, stage - 1)
    # merge, don't rebuild: other features (species/evolution) keep keys here
    sessions[session_id] = {**fr, "stage": stage, "ts": now, "uuid": uuid or fr.get("uuid")}
    state["sessions"] = sessions
    state.pop("frustration", None)  # migrate away from the old shared field
    return stage


def pick_species(session_lines):
    # the pet hatches and grows within each session as you write code
    current = SPECIES[0]
    for species in SPECIES:
        if session_lines >= species[0]:
            current = species
    return current


def is_night(hour):
    return hour >= NIGHT_START or hour < NIGHT_END


def render_sprite(rows):
    # half blocks: each terminal cell shows two vertical pixels (fg=top, bg=bottom)
    out = []
    for top, bottom in zip(rows[::2], rows[1::2]):
        cells = []
        for tc, bc in zip(top, bottom):
            t = PIXELS.get(tc)
            b = PIXELS.get(bc)
            if t is None and b is None:
                cells.append(" ")
            elif t is not None and b is None:
                cells.append(f"\033[38;2;{t}m▀\033[0m")
            elif t is None and b is not None:
                cells.append(f"\033[38;2;{b}m▄\033[0m")
            else:
                cells.append(f"\033[38;2;{t}m\033[48;2;{b}m▀\033[0m")
        out.append("".join(cells))
    return out


def put_pixel(rows, x, y, char):
    if 0 <= y < len(rows) and 0 <= x < len(rows[y]):
        rows[y] = rows[y][:x] + char + rows[y][x + 1:]


def body_span(row):
    solid = [x for x, c in enumerate(row) if c != "."]
    if not solid:
        return None
    return solid[0], solid[-1]


def wings_out(rows, body_char, y=3):
    span = body_span(rows[y])
    if span is None:
        return
    first, last = span
    for x in (first - 2, first - 1, last + 1, last + 2):
        put_pixel(rows, x, y, body_char)


# hand-drawn wing rows, symmetric per species: everything else in the sprite
# stays pixel-identical between frames, so ONLY the wings appear to move
# wings open sideways at belly height: pixel rows 3+4 stack into one solid
# square block per column (bottom half of the middle cell + top half of the
# bottom cell), so they never touch the face row and never render droopy
STRETCH_ROWS = {
    "t": ("tttttpppttttt", "ttttttttttttt"),
    "y": ("..yyyypyyyy..", "..yyyyyyyyy.."),
    "p": ("pppppyyyppppp", "ppppppppppppp"),
}


def spread_wings(rows, body_char):
    wing_rows = STRETCH_ROWS.get(body_char)
    if wing_rows:
        rows[3], rows[4] = wing_rows


# facial expressions: colored pixels inside the face silhouette — the only
# kind of detail that reads at this scale (like the beak). coordinates are
# per species; eggs have no face and skip all of this.
EYE_XS = {"t": (4, 8), "y": (5, 7), "p": (4, 8)}
CHEEK_XS = {"t": (3, 9), "y": (4, 8), "p": (3, 9)}
BEAK_XS = {"t": (5, 6, 7), "y": (6,), "p": (5, 6, 7)}
BEAK_CHAR = {"t": "p", "y": "p", "p": "y"}
# note: nerd glasses were tried and reverted — at this resolution (1px eyes)
# they read as a ski mask, not glasses. the keyboard is the coding prop.
# closed eyes: wide dark dashes, twice the width of an open eye
SLEEP_EYES_XS = {"t": (3, 4, 8, 9), "y": (4, 5, 7, 8), "p": (3, 4, 8, 9)}


def apply_face(rows, body_char, face):
    if face == "blush":
        # comforted: pink cheeks beside the beak
        for x in CHEEK_XS.get(body_char, ()):
            put_pixel(rows, x, 3, "h")
    elif face == "rage":
        # furious: heated red cheeks (eyes go deep red separately)
        for x in CHEEK_XS.get(body_char, ()):
            put_pixel(rows, x, 3, "r")
    elif face == "tears":
        # debugging is pain: a tear under each eye, TwT
        for x in EYE_XS.get(body_char, ()):
            put_pixel(rows, x, 3, "s")
    elif face == "chirp":
        # excited: beak open, chirping mid-flight
        beak = BEAK_CHAR.get(body_char)
        for x in BEAK_XS.get(body_char, ()):
            put_pixel(rows, x, 4, beak)


def shift_down(rows):
    return ["." * SPRITE_W] + rows[:-1]


def crack_shell(rows, level):
    # the egg cracks as hatching approaches
    if level >= 1:
        put_pixel(rows, 6, 1, "k")
        put_pixel(rows, 7, 2, "k")
    if level >= 2:
        put_pixel(rows, 5, 2, "k")
        put_pixel(rows, 6, 3, "k")
        put_pixel(rows, 8, 3, "k")


def sweat_drop(rows):
    span = body_span(rows[1])
    if span is None:
        return
    put_pixel(rows, span[1] + 1, 1, "s")


def shift_right(rows, by=1):
    return ["." * by + row[:-by] for row in rows]


def build_sprite(base, body_char, tick, eyes, anim, poop, cracks=0, face=None):
    rows = [row.ljust(SPRITE_W, ".")[:SPRITE_W] for row in base]
    is_egg = body_char == "w"

    if is_egg and cracks:
        crack_shell(rows, cracks)

    # pose phase: wing spreads happen before the face so the chirping beak
    # can land on top of the open-wing rows
    if not is_egg:
        if anim == "stretch" and tick % 2:
            spread_wings(rows, body_char)
        if anim == "flap" and not tick % 2:
            # excited: standing tall, wings open <-> closed (no squashing hop)
            spread_wings(rows, body_char)

    apply_face(rows, body_char, face)
    if anim == "shiver":
        sweat_drop(rows)

    # "closed" = asleep (dashed anime eyes); "blink" = eyes gone for a second
    eye_char = {
        "open": "k", "closed": body_char, "blink": body_char,
        "rage": "R", "wide": "w",
    }[eyes]
    rows = [row.replace("E", eye_char) for row in rows]
    if eyes == "closed":
        for x in SLEEP_EYES_XS.get(body_char, ()):
            put_pixel(rows, x, 2, "k")

    # motion phase: whole-body shifts, applied last so the face moves along.
    # eggs can only wobble (or shake in a panic)
    if anim == "shake":
        if tick % 2:
            rows = shift_right(rows, 2)
    elif is_egg:
        if tick % 2:
            rows = shift_right(rows)
    elif anim == "rest":
        # slow breathing: sink for two seconds, rise for two
        if tick % 4 >= 2:
            rows = shift_down(rows)
    elif anim in ("bob", "type"):
        if tick % 2:
            rows = shift_down(rows)
    elif anim == "shiver":
        if tick % 2:
            rows = shift_right(rows)

    # ground objects get their own columns appended to the right, each with
    # an empty gap column — never glued to (or trampled by) the pet
    if anim == "type":
        put_pixel(rows, SPRITE_W - 3, 5, "g")
        put_pixel(rows, SPRITE_W - 2, 5, "g")

    ext = ["" for _ in range(6)]
    if poop:
        for y in range(6):
            ext[y] += {4: "..B.", 5: ".BBB"}.get(y, "....")
    return [row + e for row, e in zip(rows, ext)]


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}

    ctx = data.get("context_window") or {}
    pct = ctx.get("used_percentage")
    if pct is None:
        used = ctx.get("total_input_tokens")
        size = ctx.get("context_window_size")
        if used is not None and size:
            pct = 100 * used / size
        else:
            pct = 0
    pct = max(0, min(100, round(pct)))

    model = (data.get("model") or {}).get("display_name", "Claude")
    cwd = (data.get("workspace") or {}).get("current_dir") or data.get("cwd", ".")
    cost = data.get("cost") or {}
    limits = data.get("rate_limits") or {}

    state = load_state()
    state["max_pct_seen"] = max(state.get("max_pct_seen", 0), pct)

    transcript_path = data.get("transcript_path")
    session_id = data.get("session_id") or transcript_path or "default"
    entries = read_recent_entries(transcript_path) if transcript_path else []
    frustration = update_frustration(state, session_id, entries, transcript_path)
    streak = error_streak(entries)
    save_state(state)

    now = time.localtime()
    tick = int(time.time())
    night = is_night(now.tm_hour)

    mood, ctx_color, anim = pick_stage(pct)
    color = ctx_color
    sleeping = False
    if frustration == 2:
        mood, color, anim = RAGE
    elif streak >= 4:
        mood, color, anim = DEBUG_PAIN
    elif frustration == 1:
        mood, color, anim = COMFORT
    elif night and pct < 92:
        mood, color, anim = SLEEP
        sleeping = True

    if sleeping or anim == "rest":
        eyes = "closed"
    elif tick % 7 == 0:
        eyes = "blink"
    elif frustration == 2:
        eyes = "rage"
    elif pct >= 92:
        eyes = "wide"
    else:
        eyes = "open"

    face = None
    if frustration == 2:
        face = "rage"
    elif streak >= 4:
        face = "tears"
    elif frustration == 1:
        face = "blush"
    elif anim == "flap":
        face = "chirp"

    added = cost.get("total_lines_added")
    removed = cost.get("total_lines_removed")
    species = pick_species(added or 0)
    _, species_name, body_char, base = species

    # evolution celebration: detect the species changing within this session
    sess = (state.get("sessions") or {}).get(session_id)
    evo_from = None
    if sess is not None:
        sp_idx = SPECIES.index(species)
        prev = sess.get("sp")
        if prev is not None and sp_idx > prev:
            sess["evo_ts"] = time.time()
            sess["evo_from"] = prev
        sess["sp"] = sp_idx
        evo_ts = sess.get("evo_ts")
        if evo_ts and time.time() - evo_ts < EVOLUTION_SECONDS:
            evo_from = sess.get("evo_from")
        save_state(state)

    # poop mechanics: shows up after 300+ lines deleted since the last cleanup;
    # committing (HEAD moves) tidies the workspace and cleans it up
    poop_visible = False
    clean_ts = None
    if sess is not None:
        poop_visible = removed is not None and removed - sess.get("cr", 0) >= POOP_THRESHOLD
        if poop_visible:
            branch_now, head = git_info(cwd)
            if not sess.get("ph") or sess.get("pb") != branch_now:
                # anchor (or re-anchor after a branch switch — checkouts made
                # in other sessions must not count as cleaning)
                sess["ph"], sess["pb"] = head, branch_now
            elif head and head != sess["ph"]:
                # HEAD moved on the SAME branch: a real commit tidied things up
                sess["cr"] = removed
                sess["clean_ts"] = time.time()
                sess["ph"] = sess["pb"] = None
                poop_visible = False
        clean_ts = sess.get("clean_ts")
        save_state(state)

    hatching = evo_from == 0
    if hatching:
        # hatching! the egg becomes a chick
        body_char = "y"
        mood, color, anim = "hatching!! \U0001f423", YELLOW, "calm"
        face = None
        eyes = "open"
    elif evo_from is not None:
        mood, color = f"evolved into {species_name}!!", MAUVE
        anim = "flap"
        face = "chirp"
    elif clean_ts and time.time() - clean_ts < EVOLUTION_SECONDS:
        mood, color = "\u2728 all clean, nice commit!", PINK
        anim = "calm"
        face = "blush"
    cracks = 0
    if (added or 0) >= 35:
        cracks = 2
    elif (added or 0) >= 20:
        cracks = 1
    def build_frame(t):
        frame_base = HATCH_FRAMES[t % 2] if hatching else base
        return build_sprite(
            frame_base, body_char, t,
            eyes=eyes,
            anim=anim,
            poop=poop_visible,
            cracks=cracks,
            face=face,
        )

    # trim the canvas to the content of BOTH animation phases: the pet sits
    # close to the text, and the text never wiggles as frames alternate
    rows_now, rows_alt = build_frame(tick), build_frame(tick + 1)

    def rightmost(frame_rows):
        return max(
            max((i for i, c in enumerate(r) if c != "."), default=-1)
            for r in frame_rows
        )

    width = max(rightmost(rows_now), rightmost(rows_alt)) + 1
    rows_now = [r[:width].ljust(width, ".") for r in rows_now]
    sprite = render_sprite(rows_now)

    # line 1: mood
    if anim == "rest":
        zzz = ("Zzz", "zZz", "zzZ")[tick % 3]
        mood = f"{zzz}...{mood}"
    mood_text = f"{color}{mood}{RESET}"
    if data.get("fast_mode"):
        mood_text += f" {PEACH}»»{RESET}"
    line1 = mood_text

    # line 2: vitals — energy, model, context
    vitals = []
    five_hour = (limits.get("five_hour") or {})
    used = five_hour.get("used_percentage")
    if used is not None:
        energy = max(0, round(100 - used))
        label = f"{SKY}⚡{energy}%{RESET}"
        resets_at = five_hour.get("resets_at")
        if resets_at:
            reset = time.strftime("%H:%M", time.localtime(resets_at))
            label += f" {OVERLAY}↻{reset}{RESET}"
        vitals.append(label)
    vitals.append(f"{MAUVE}{model}{RESET} {bar(pct, ctx_color)} {pct}%")

    # line 3: session info — project, branch, work, pr, level
    workspace = data.get("workspace") or {}
    project_dir = workspace.get("project_dir") or workspace.get("current_dir") or data.get("cwd")
    info = []
    if project_dir:
        info.append(f"{PEACH}⌂ {Path(project_dir).name}{RESET}")

    branch, _ = git_info(cwd)
    if branch:
        info.append(f"{LAVENDER}⎇ {branch}{RESET}")

    added = cost.get("total_lines_added")
    if added is not None or removed is not None:
        info.append(f"{GREEN}+{added or 0}{RESET}{OVERLAY}/{RESET}{RED}-{removed or 0}{RESET}")

    pr = data.get("pr") or {}
    if pr.get("number"):
        info.append(f"{SKY}⚑#{pr['number']}{RESET}")

    level = SPECIES.index(pick_species(added or 0)) + 1
    info.append(f"{OVERLAY}lv{level}{RESET}")

    sep = f" {OVERLAY}|{RESET} "
    print(f"{sprite[0]} {line1}")
    print(f"{sprite[1]} {sep.join(vitals)}")
    print(f"{sprite[2]} {sep.join(info)}")


if __name__ == "__main__":
    main()
```

2. MERGE this key into my `~/.claude/settings.json` (preserve every key that already exists — do NOT overwrite the file). If I already have a `statusLine` configured, ask me before replacing it:

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 ~/.claude/claude_pet_tama.py",
    "refreshInterval": 1
  }
}
```

On Windows, use `python` instead of `python3`.

3. Verify it works:

```bash
echo '{"model":{"display_name":"Test"},"context_window":{"used_percentage":95}}' | python3 ~/.claude/claude_pet_tama.py
```

Expected: two lines, with a panicking `(@_@)!!` pet on the first one. Then remind me to restart Claude Code.

4. OPTIONAL — matching theme: the pet uses the Catppuccin Mocha palette, and Claude Code supports custom themes. Ask me if I want a custom theme and which palette I prefer (Catppuccin Mocha/Latte/Frappe/Macchiato, or anything else). If I do, create `~/.claude/themes/<slug>.json` like this and add `"theme": "custom:<slug>"` to the settings merge:

```json
{
  "name": "Theme Name",
  "base": "dark",
  "overrides": { "tokenName": "#rrggbb" }
}
```

Tokens you can override (use colors from the palette I pick): `claude`, `text`, `inverseText`, `inactive`, `subtle`, `suggestion`, `permission`, `remember`, `success`, `error`, `warning`, `merged`, `promptBorder`, `planMode`, `autoAccept`, `bashBorder`, `ide`, `fastMode`, `diffAdded`, `diffRemoved`, `diffAddedDimmed`, `diffRemovedDimmed`, `diffAddedWord`, `diffRemovedWord`, `userMessageBackground`, `userMessageBackgroundHover`, `bashMessageBackgroundColor`, `memoryBackgroundColor`, `selectionBg`, `rate_limit_fill`, `rate_limit_empty`, `briefLabelYou`, `briefLabelClaude`, plus the `*Shimmer` variants (`claudeShimmer`, `warningShimmer`, `permissionShimmer`, `promptBorderShimmer`, `inactiveShimmer`, `fastModeShimmer`). If I pick a palette other than Mocha, also update the color constants at the top of `claude_pet_tama.py` to match.

Context on what the pet shows (in case I ask): a pixel-art sprite (half-block rendering, Catppuccin Mocha) that hatches and evolves within each session from lines of code written (egg -> chick 50 -> bird 400 -> phoenix 2500, shown as lv1-4), with a distinct animation per mood (breathing, wing stretches, bobbing, flapping, shivering with a sweat drop, shaking); mood follows context usage (`context_window.used_percentage`) and it shakes begging for `/compact` above 92%; frustration detection reads my last typed message (swears/CAPS/screams in pt/en/es, word-boundary matched) and steps down one tier per prompt: rage -> tea -> normal; 4+ consecutive tool errors get a "debugging is pain" mood; it sleeps 22h-7h; it poops when a session removes 300+ lines; `⚡` is the remaining 5h subscription quota with reset time; `⌂` project, `⎇` git branch, `+X/-Y` session lines, `⚑#N` open PR. Sprites live in `SPECIES`, vocabulary in `SWEARS`/`EXASPERATION` — customize freely if I ask.
