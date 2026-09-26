#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""C++ engine vs. an independent Rapfi reimplementation, point by point.

This is stronger than the acceptance test: the acceptance test compares the
engine against Python's *naive* rules and then attributes the differences.
Here we re-derive Rapfi's `checkForbiddenPoint` from scratch (same DP as the
attribution, no engine input) and assert the engine agrees on every empty
point of every position.
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


def rapfi_forbidden(board, x, y, depth=0):
    """Faithful re-derivation of forbidden.cpp:check_forbidden_impl."""
    if not board.in_bounds(x, y) or int(board.grid[x, y]) != EMPTY:
        return False
    pats = [d.dir_pattern_py(board, x, y, dx, dy) for dx, dy in DIRECTIONS]
    if not any(p in (d.OL, d.B4, d.B4S, d.F4, d.F3, d.F3S) for p in pats):
        return False
    if any(p == d.OL for p in pats):
        return True
    if any(p == d.F5 for p in pats):
        return False
    if sum(1 for p in pats if p in (d.B4, d.B4S, d.F4)) >= 2:
        return True

    board.grid[x, y] = BLACK
    try:
        threes = 0
        for dd, (dx, dy) in enumerate(DIRECTIONS):
            if pats[dd] not in (d.F3, d.F3S):
                continue
            found = False
            for sgn in (-1, 1):
                cx, cy = x, y
                for _ in range(4):
                    cx += sgn * dx
                    cy += sgn * dy
                    if not board.in_bounds(cx, cy):
                        break
                    v = int(board.grid[cx, cy])
                    if v == EMPTY:
                        p4c = d.pattern4_py(board, cx, cy)
                        pc = d.dir_pattern_py(board, cx, cy, dx, dy)
                        ok = (p4c == d.B_FLEX4) or (pc == d.F5)
                        if ok and board.would_self_capture(cx, cy):
                            ok = False
                        if ok and depth < 1:
                            ok = not rapfi_forbidden(board, cx, cy, depth + 1)
                        if ok:
                            found = True
                        break
                    if v != BLACK:
                        break
            if found:
                threes += 1
        return threes >= 2
    finally:
        board.grid[x, y] = EMPTY


def main():
    rng = random.Random(20240917)
    positions = d.build_positions(rng)
    eng = d.Engine()
    total = 0
    disagree = 0
    try:
        for b in positions:
            cpp = eng.forbidden(b)
            for x in range(b.size):
                for y in range(b.size):
                    if int(b.grid[x, y]) != EMPTY:
                        continue
                    total += 1
                    # 引擎的 checkforbidden 输出的是“黑棋不能落”的全部点：
                    # 无气自杀 或 Renju 禁手。
                    want = b.would_self_capture(x, y) or \
                        rapfi_forbidden(b, x, y)
                    got = (x, y) in cpp
                    if want != got:
                        disagree += 1
                        if disagree <= 20:
                            print("DISAGREE (%d,%d) size=%d engine=%s rapfi_py=%s"
                                  % (x, y, b.size, got, want))
                            d.print_board(b)
    finally:
        eng.close()
    print("points=%d engine_vs_rapfi_disagreements=%d" % (total, disagree))
    return 0 if disagree == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
