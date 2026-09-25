#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Independent verification of every mismatch (original 20240917 scope).

For each mismatch it brute-forces the Renju question:
  * py three_three vs cpp legal: can the claimed Python three become a
    genuine OPEN four (two distinct legal exact-five completions) with one
    black move?  If no -> the shape is a sleep three (鐪犱笁); Rapfi is right.
  * cpp_stricter (four-four): for each Rapfi four direction, are all its
    five-completions illegal (overline / self-capture / forbidden)?
"""
from __future__ import annotations

import os
import random
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CPP_DIR = os.path.dirname(SCRIPT_DIR)
REPO_ROOT = os.path.dirname(CPP_DIR)
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, REPO_ROOT)

from board import HybridBoard, EMPTY, BLACK, WHITE, OBSTACLE, DIRECTIONS  # noqa: E402
import rules  # noqa: E402
import diff_forbidden as d  # noqa: E402


# --- original generator (identical to the delivered acceptance script) ---
def random_selfplay(rng, snapshots):
    size = rng.choice([9, 9, 11, 13, 13, 15, 15, 15, 15, 17, 19])
    b = HybridBoard(size)
    steps = rng.randint(8, 70)
    for _ in range(steps):
        empties = [(x, y) for x in range(size) for y in range(size)
                   if b.grid[x, y] == EMPTY]
        if not empties:
            break
        if rng.random() < 0.30:
            snapshots.append(b.copy())
        if b.turn == BLACK:
            legal = [c for c in empties if rules.is_black_legal_move(b, *c)[0]]
            if not legal:
                b.pass_turn()
                continue
            mv = rng.choice(legal)
            b.play_black(*mv)
            if b.check_black_five(*mv):
                snapshots.append(b.copy())
                return
        else:
            b.play_white(*rng.choice(empties))


def random_scatter(rng, snapshots):
    size = rng.choice([9, 11, 13, 15, 15, 19])
    b = HybridBoard(size)
    density = rng.uniform(0.10, 0.32)
    for x in range(size):
        for y in range(size):
            r = rng.random()
            if r < density * 0.55:
                b.grid[x, y] = BLACK
            elif r < density:
                b.grid[x, y] = WHITE
    snapshots.append(b)


def build_positions(rng):
    snaps = []
    guard = 0
    while len(snaps) < 45 and guard < 4000:
        guard += 1
        random_selfplay(rng, snaps)
    for _ in range(18):
        random_scatter(rng, snaps)
    snaps.extend(d.constructed_positions())
    return snaps


def valid_five_completions(board, x, y, dx, dy, radius=5):
    """Empty points within radius that, when black plays there, make an exact
    legal five along (dx,dy).  Returns their count."""
    n = 0
    for i in range(-radius, radius + 1):
        ex, ey = x + i * dx, y + i * dy
        if not board.in_bounds(ex, ey) or int(board.grid[ex, ey]) != EMPTY:
            continue
        board.grid[ex, ey] = BLACK
        try:
            if board.black_run_length(ex, ey) == 5:
                _s, lib = board.get_group(ex, ey)
                if lib:
                    n += 1
        finally:
            board.grid[ex, ey] = EMPTY
    return n


def line_code11(board, x, y, dx, dy):
    """11-cell Rapfi window around the placed black stone at (x,y)."""
    ch = []
    for i in range(-5, 6):
        if i == 0:
            ch.append("1")
            continue
        cx, cy = x + i * dx, y + i * dy
        if not board.in_bounds(cx, cy):
            ch.append("2")
            continue
        v = int(board.grid[cx, cy])
        ch.append("1" if v == BLACK else ("2" if v in (WHITE, OBSTACLE) else "0"))
    return "".join(ch)


def verify(b, x, y, py_bad, ftype, cpp_bad, notes):
    b.grid[x, y] = BLACK
    try:
        pats = [d.dir_pattern_py(b, x, y, dx, dy) for dx, dy in DIRECTIONS]
        codes = [line_code11(b, x, y, dx, dy) for dx, dy in DIRECTIONS]
        if ftype == "three_three":
            for dd, (dx, dy) in enumerate(DIRECTIONS):
                sets = rules._three_sets(b, x, y, dx, dy, set())
                if not sets:
                    continue
                # brute force: any single black move making a genuine open four?
                live_ext = []
                for i in range(-4, 5):
                    ex, ey = x + i * dx, y + i * dy
                    if not b.in_bounds(ex, ey) or int(b.grid[ex, ey]) != EMPTY:
                        continue
                    b.grid[ex, ey] = BLACK
                    try:
                        t = rules.classify_direction_after_move(b, ex, ey, dx, dy)
                    finally:
                        b.grid[ex, ey] = EMPTY
                    if t == "open_four":
                        live_ext.append((ex, ey))
                notes.append(
                    ("three", dd, PAT_NAME[pats[dd]], codes[dd],
                     sorted(sets, key=sorted)[0], live_ext))
        elif ftype in (None, "four_four") and cpp_bad:
            for dd, (dx, dy) in enumerate(DIRECTIONS):
                if pats[dd] not in (d.B4, d.B4S, d.F4):
                    continue
                if rules._four_sets(b, x, y, dx, dy):
                    continue
                n5 = valid_five_completions(b, x, y, dx, dy)
                notes.append(("four", dd, PAT_NAME[pats[dd]], codes[dd], n5))
    finally:
        b.grid[x, y] = EMPTY


PAT_NAME = d.PAT_NAME


def main():
    rng = random.Random(20240917)
    positions = build_positions(rng)
    eng = d.Engine()
    mismatches = []
    try:
        for b in positions:
            cpp = eng.forbidden(b)
            for x in range(b.size):
                for y in range(b.size):
                    if int(b.grid[x, y]) != EMPTY:
                        continue
                    ok, ftype = rules.is_black_legal_move(b, x, y)
                    if (not ok) != ((x, y) in cpp):
                        mismatches.append((b.copy(), x, y, not ok, ftype,
                                           (x, y) in cpp))
    finally:
        eng.close()

    print("mismatches=%d" % len(mismatches))
    bad = 0
    for (b, x, y, py_bad, ftype, cpp_bad) in mismatches:
        notes = []
        verify(b, x, y, py_bad, ftype, cpp_bad, notes)
        tag = "OK " if notes else "?? "
        if not notes:
            bad += 1
        print("%s(%2d,%2d) size=%d py=%s cpp_bad=%s" %
              (tag, x, y, b.size, ftype, cpp_bad))
        for n in notes:
            if n[0] == "three":
                _, dd, pat, code, first_set, live = n
                print("     dir%d pat=%s code=%s three=%s open4_ext=%s"
                      % (dd, pat, code, sorted(first_set), live))
            else:
                _, dd, pat, code, n5 = n
                print("     dir%d pat=%s code=%s legal5completions=%d"
                      % (dd, pat, code, n5))
    print("unexplained=%d" % bad)


if __name__ == "__main__":
    main()

