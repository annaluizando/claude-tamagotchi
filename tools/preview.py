#!/usr/bin/env python3
"""
pet_preview.py — terminal-faithful previewer for claude_pet_tama.py sprites.

Renders sprite frames to a PNG the way a real terminal draws them:
- cell aspect ratio 1:2 (width:height), so half-block pixels are square-ish
- a 2px dark seam between terminal rows (line spacing), which is what makes
  misaligned half-blocks visible in real terminals and invisible in naive
  square-pixel previews

Usage: python3 pet_preview.py out.png
Renders every mood animation (both frames) and every species, plus overlays.
"""

import importlib.util
import struct
import sys
import zlib
from pathlib import Path

spec = importlib.util.spec_from_file_location('pet', Path(__file__).resolve().parent.parent / 'claude_pet_tama.py')
pet = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pet)
pet.render_sprite = lambda rows: rows  # capture raw pixel rows

BG = (30, 30, 46)
SEAM = (17, 17, 27)
CELL_W = 16
CELL_H = 32
ROW_GAP = 2
PANEL_GAP = 12


def rgb(ch):
    value = pet.PIXELS.get(ch)
    if value is None:
        return None
    return tuple(int(x) for x in value.split(';'))


def draw_panel(img, ox, oy, rows):
    for cell_row in range(3):
        top_px, bottom_px = rows[cell_row * 2], rows[cell_row * 2 + 1]
        base_y = oy + cell_row * (CELL_H + ROW_GAP)
        for x in range(pet.SPRITE_W):
            for half, ch in ((0, top_px[x]), (1, bottom_px[x])):
                color = rgb(ch) or BG
                for dy in range(CELL_H // 2):
                    for dx in range(CELL_W):
                        img[base_y + half * (CELL_H // 2) + dy][ox + x * CELL_W + dx] = color
        for dy in range(ROW_GAP):
            for dx in range(pet.SPRITE_W * CELL_W):
                img[base_y + CELL_H + dy][ox + dx] = SEAM


def main():
    egg, chick, bird, phoenix = pet.SPECIES
    panels = []
    for anim, eyes, face in [('rest', 'closed', None), ('calm', 'open', 'blush'),
                             ('stretch', 'open', None), ('type', 'open', None),
                             ('flap', 'open', 'chirp'), ('shiver', 'open', 'tears'),
                             ('shake', 'rage', 'rage'), ('shake', 'wide', None)]:
        for tick in (0, 1):
            t = tick * 2 if anim == 'rest' else tick
            panels.append((bird, anim, eyes, False, 0, t, face))
    for sp, cracks in ((egg, 0), (egg, 2), (chick, 0), (phoenix, 0)):
        for tick in (0, 1):
            panels.append((sp, 'bob', 'open', False, cracks, tick, None))
    panels.append((bird, 'type', 'open', True, 0, 0, None))
    panels.append((bird, 'type', 'open', True, 0, 1, None))

    cols = 8
    panel_w = pet.SPRITE_W * CELL_W + PANEL_GAP
    panel_h = 3 * (CELL_H + ROW_GAP) + PANEL_GAP
    n_rows = (len(panels) + cols - 1) // cols
    img = [[BG] * (cols * panel_w + PANEL_GAP) for _ in range(n_rows * panel_h + PANEL_GAP)]

    for i, (sp, anim, eyes, poop, cracks, tick, face) in enumerate(panels):
        rows = pet.build_sprite(sp[3], sp[2], tick, eyes=eyes, anim=anim,
                                poop=poop, cracks=cracks, face=face)
        draw_panel(img, PANEL_GAP + (i % cols) * panel_w, PANEL_GAP + (i // cols) * panel_h, rows)

    out = sys.argv[1] if len(sys.argv) > 1 else 'pet_preview.png'
    height, width = len(img), len(img[0])
    raw = b''.join(b'\x00' + b''.join(bytes(px) for px in row) for row in img)

    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data))

    Path(out).write_bytes(
        b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
        + chunk(b'IDAT', zlib.compress(raw, 6))
        + chunk(b'IEND', b'')
    )
    print(f'{out}: r1 = rest f0/f1, calm+blush f0/f1, stretch f0/f1, type f0/f1; '
          f'r2 = flap+chirp f0/f1, shiver+tears f0/f1, shake+rage f0/f1, panic-wide f0/f1; '
          f'r3 = egg f0/f1, egg-cracked f0/f1, chick f0/f1, phoenix f0/f1; r4 = poop f0/f1')


if __name__ == '__main__':
    main()
