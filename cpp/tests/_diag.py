#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Diagnostic: reproduce the original 20240917 mismatches and dump details.

Uses the ORIGINAL position generator (18 scatters, density 0.10..0.32) so the
same 27 mismatches as the failed acceptance run are produced.
"""
from __future__ import annotations

import os
import random
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CPP_DIR = os.path.dirname(SCRIPT_DIR)
REPO_ROOT = os.path.dirname(CPP_DIR)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from board import HybridBoard, EMPTY, BLACK, WHITE, OBSTACLE, DIRECTIONS  # noqa: E402
import rules  # noqa: E402
import diff_forbidden as d  # noqa: E402

PAT_NAME = d.PAT_NAME
P4_NAME = d.P4_NAME


# ---- ORIGINAL generator (copy of the delivered version) ----
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


def main():
    rng = random.Random(20240917)
    positions = build_positions(rng)
    print("positions=%d" % len(positions))
    eng = d.Engine()
    points = 0
    mismatches = []
    try:
        for b in positions:
            cpp = eng.forbidden(b)
            for x in range(b.size):
                for y in range(b.size):
                    if int(b.grid[x, y]) != EMPTY:
                        continue
                    points += 1
                    ok, ftype = rules.is_black_legal_move(b, x, y)
                    py_bad = not ok
                    cpp_bad = (x, y) in cpp
                    if py_bad == cpp_bad:
                        continue
                    mismatches.append((b.copy(), x, y, py_bad, ftype, cpp_bad))
    finally:
        eng.close()

    print("points=%d mismatches=%d" % (points, len(mismatches)))
    for (b, x, y, py_bad, ftype, cpp_bad) in mismatches:
        print("=" * 70)
        print("point (%d,%d) py_bad=%s py_type=%s cpp_bad=%s size=%d"
              % (x, y, py_bad, ftype, cpp_bad, b.size))
        d.print_board(b)
        # C++ probe
        eng2 = d.Engine()
        try:
            eng2.load(b)
            eng2.send("pat %d %d" % (x, y))
            print("  cpp pat:", eng2.readline())
        finally:
            eng2.close()
        # Python per-direction
        b.grid[x, y] = BLACK
        try:
            for dd, (dx, dy) in enumerate(DIRECTIONS):
                threes = rules._three_sets(b, x, y, dx, dy, set())
                fours = rules._four_sets(b, x, y, dx, dy)
                pydir = d.dir_pattern_py(b, x, y, dx, dy)
                print("  dir%d (%d,%d) py_threes=%d py_fours=%d rapfi_pat=%s"
                      % (dd, dx, dy, len(threes), len(fours),
                         PAT_NAME.get(pydir)))
        finally:
            b.grid[x, y] = EMPTY


if __name__ == "__main__":
    main()
