# claude-pet-tamagotchi 🐾

A pixel-art tamagotchi that lives in your [Claude Code](https://claude.com/claude-code)
statusline. It's rendered with half-block characters (2 pixels per terminal
cell, Catppuccin Mocha palette), animated at 1 fps, and it *reacts to you*:
its mood follows your context window, it detects frustration in your prompts
(pt/en/es), it evolves as you write code, sleeps at night, and — when a
session deletes too many lines — it poops.

```
   ▄▄▄▄       coding with you
  ▀▀•▀▀•▀▀    ⚡76% ↻17:13 | Fable █████░░░░░ 47%
  ▀▀▀▀▀▀▀▀    ⌂ my-project | ⎇ feat/my-branch | +312/-88 | lv3
```

(imagine this but as an actual colored sprite bouncing in your terminal)

## Features

- **Species evolution** — the pet hatches and grows *within each session*,
  from lines of code written: `lv1` egg → `lv2` chick (50) → `lv3` bird (400)
  → `lv4` phoenix (2500). Every chat starts with an egg; the shell cracks as
  hatching approaches, then a 5-second hatching animation plays (chick pops
  out of the broken shell, then wears the cap). Later evolutions get a
  celebratory "evolved into bird!!" flap.
- **A distinct animation per mood** — breathing while napping, morning wing
  stretches, pecking at a tiny keyboard while coding, excited flapping,
  shivering with a sweat drop when nervous, full-body shaking in a panic.
  Eggs just wobble.
- **Context moods** — napping → stretching → coding with you → getting
  excited → a bit nervous → BEGGING for `/compact`, following
  `context_window.used_percentage`. Above 92% the sprite shakes.
- **Frustration detection** — reads the tail of the session transcript
  (never the whole file). Swearing, ALL CAPS, screams (`AAAAA`, but not
  Brazilian laughter `kkkk`) and exasperation phrases in Portuguese, English
  and Spanish. Moods step down one tier per new prompt:
  rage (red eyes, shaking) → comforting tea (blushing cheeks) → back to normal.
  Only your *latest* message counts, matched on word boundaries
  (`computador` is safe), per-session state so parallel sessions don't
  contaminate each other.
- **Facial expressions** — blushing cheeks when comforted, crying (TwT)
  while debugging fails, heated red cheeks + deep red eyes when you rage,
  wide scared eyes near context overflow, open-beak chirping when excited.
- **Debugging pain** — 4+ consecutive erroring tool calls get their own mood.
- **Night mode** — between 22h and 7h the pet sleeps (eyes closed, `zZ`),
  unless you rage at it or the context is about to overflow.
- **Poop** — appears after 300+ lines deleted since the last cleanup. To
  clean it, do what you'd do anyway: **commit** (any HEAD move counts). The
  pet thanks you with a blushing "✨ all clean, nice commit!". Delete another
  300 lines and it's back — the full tamagotchi cycle.
- **Blinks** every 7 seconds, bounces every other second, sleeps with dashed
  anime eyes, and shows your
  subscription energy (`⚡` remaining 5h quota + reset time), model, context
  bar, project, git branch, session line counts, open PR number, and level.

## Install

**The lazy way:** open Claude Code and paste the contents of
[`PROMPT.md`](PROMPT.md) — your Claude installs everything for you, asks
before touching any existing config, and offers to build the matching
Catppuccin theme in the flavor of your choice.

**By hand:**

1. Copy `claude_pet_tama.py` to `~/.claude/claude_pet_tama.py`.
2. Copy `catppuccin-mocha.json` to `~/.claude/themes/catppuccin-mocha.json` (optional).
3. Merge into `~/.claude/settings.json` (keep your existing keys):

   ```json
   {
     "theme": "custom:catppuccin-mocha",
     "statusLine": {
       "type": "command",
       "command": "python3 ~/.claude/claude_pet_tama.py",
       "refreshInterval": 1
     }
   }
   ```

   On Windows, use `python` instead of `python3`. Skip the `theme` key if you
   like your current theme — the pet works standalone.
4. Restart Claude Code.

Verify without restarting:

```bash
echo '{"model":{"display_name":"Test"},"context_window":{"used_percentage":95}}' | python3 ~/.claude/claude_pet_tama.py
```

You should get three lines with a shaking sprite BEGGING for `/compact`.

## Requirements

- Python 3, stdlib only — nothing to pip-install
- A truecolor terminal (iTerm2, Ghostty, Kitty, WezTerm, VS Code, Windows
  Terminal — macOS Terminal.app renders the colors poorly)
- A font with the glyphs `▀ ▄ █ ░ ⎇ ⌂ ↻` (any coding font)
- a git repo for the branch display and commit detection (optional — read
  directly from `.git` files, no git subprocess is ever spawned)

## Customize

- **Preview before you ship**: `python3 tools/preview.py out.png` renders
  every mood and species to a PNG with terminal-faithful cell proportions
  (1:2 cells, line seams) — naive square-pixel previews hide exactly the
  artifacts that show up in a real terminal.
- **Sprites** live in `SPECIES` — 6 pixel rows of palette characters
  (`PIXELS` maps chars to RGB), rendered as 3 terminal rows via `▀`
  half-blocks. `E` marks the eye slots. Draw your own cat/slime/dragon;
  keep rows `SPRITE_W` wide.
- **Evolution thresholds** are the first element of each `SPECIES` entry.
- **Frustration vocabulary** is in `SWEARS` / `EXASPERATION` — add your
  language, matched on word boundaries.
- **Night hours** are `NIGHT_START` / `NIGHT_END`; poop trigger is
  `POOP_THRESHOLD`.
- **The theme** (`catppuccin-mocha.json`) overrides Claude Code UI color
  tokens; any token can point at any `#rrggbb` value. Theme edits hot-reload
  after the first restart.

## License

[MIT](LICENSE)
