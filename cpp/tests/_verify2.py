#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Independent verification of every mismatch (original 20240917 scope).

For each mismatch it re-derives Rapfi's verdict from scratch:
  * py three_three vs cpp legal: count the directions that are a *genuine*
    Rapfi open three (pattern F3/F3S and a legal extension to B_FLEX4/F5).
    Rapfi is justified iff that count < 2; print why each other direction
    fails (not F3 in Rapfi's DP / no live extension / extension point itself
    forbidden).
  * cpp_stricter (four-four): for every Rapfi four direction that Python does
    not count, print its legal five-completions and line code.
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

from board import HybridBoard, EMPTY, BLACK, WHITE, DIRECTIONS  # noqa: E402
import rules  # noqa: E402
import diff_forbidden as d  # noqa: E402

PAT_NAME = d.PAT_NAME


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


def line_code11(board, x, y, dx, dy):
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
        ch.append("1" if v == BLACK else ("2" if v != EMPTY else "0"))
    return "".join(ch)


def valid_five_completions(board, x, y, dx, dy, radius=5):
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


def explain_three(b, x, y, dx, dy, pat):
    """Why Rapfi would NOT count this Python three as a genuine open three."""
    if pat not in (d.F3, d.F3S):
        return "rapfi_dir_not_open_three(%s)" % PAT_NAME[pat]
    exts = d.ext_points(b, x, y, dx, dy)
    if not exts:
        return "no_live_extension"
    details = []
    for (ex, ey) in exts:
        if b.would_self_capture(ex, ey):
            details.append("(%d,%d)=self_capture" % (ex, ey))
            continue
        b.grid[ex, ey] = BLACK
        try:
            p4 = d.pattern4_py(b, ex, ey)
            pc = d.dir_pattern_py(b, ex, ey, dx, dy)
        finally:
            b.grid[ex, ey] = EMPTY
        if p4 == d.B_FLEX4 or pc == d.F5:
            legal = rules.is_black_legal_move(b, ex, ey)
            if not legal[0]:
                return "ext_point_forbidden(%d,%d,type=%s)" % (ex, ey, legal[1])
            return None  # a genuine true three
        legal = rules.is_black_legal_move(b, ex, ey)
        details.append("(%d,%d p4=%s dir=%s legal=%s)"
                       % (ex, ey, d.P4_NAME[p4], PAT_NAME[pc], legal))
    return "no_live_extension " + " ".join(details)


def verify(b, x, y, ftype, cpp_bad):
    b.grid[x, y] = BLACK
    try:
        pats = [d.dir_pattern_py(b, x, y, dx, dy) for dx, dy in DIRECTIONS]
        codes = [line_code11(b, x, y, dx, dy) for dx, dy in DIRECTIONS]
        out = []
        if ftype == "three_three":
            true_threes = 0
            for dd, (dx, dy) in enumerate(DIRECTIONS):
                if not rules._three_sets(b, x, y, dx, dy, set()):
                    continue
                why = explain_three(b, x, y, dx, dy, pats[dd])
                if why is None:
                    true_threes += 1
                    out.append("dir%d %s code=%s -> GENUINE open three"
                               % (dd, PAT_NAME[pats[dd]], codes[dd]))
                else:
                    out.append("dir%d %s code=%s -> %s"
                               % (dd, PAT_NAME[pats[dd]], codes[dd], why))
            return true_threes < 2, out
        if cpp_bad:
            for dd, (dx, dy) in enumerate(DIRECTIONS):
                if pats[dd] not in (d.B4, d.B4S, d.F4):
                    continue
                if rules._four_sets(b, x, y, dx, dy):
                    continue
                n5 = valid_five_completions(b, x, y, dx, dy)
                out.append("dir%d %s code=%s legal5completions=%d"
                           % (dd, PAT_NAME[pats[dd]], codes[dd], n5))
            return bool(out), out
        return False, out
    finally:
        b.grid[x, y] = EMPTY


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
                        mismatches.append((b.copy(), x, y, ftype, (x, y) in cpp))
    finally:
        eng.close()

    print("mismatches=%d" % len(mismatches))
    bad = 0
    for (b, x, y, ftype, cpp_bad) in mismatches:
        ok, out = verify(b, x, y, ftype, cpp_bad)
        if not ok:
            bad += 1
        print("%s (%2d,%2d) size=%d py=%s cpp_bad=%s"
              % ("OK " if ok else "?? ", x, y, b.size, ftype, cpp_bad))
        for line in out:
            print("      " + line)
    print("unexplained=%d" % bad)


if __name__ == "__main__":
    main()
