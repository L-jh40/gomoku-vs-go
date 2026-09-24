#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Debug harness v2: mirror make_undo_test exactly, single engine."""
from __future__ import annotations

import os
import random
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CPP_DIR = os.path.dirname(SCRIPT_DIR)
REPO_ROOT = os.path.dirname(CPP_DIR)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from board import HybridBoard, EMPTY, BLACK, WHITE  # noqa: E402
import rules  # noqa: E402

ENGINE = os.path.join(CPP_DIR, "build", "engine.exe")


def main():
    size = 15
    b = HybridBoard(size)
    p = subprocess.Popen([ENGINE], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, bufsize=1)
    p.stdin.write("size %d\n" % size); p.stdin.flush()
    p.stdin.write("clear\n"); p.stdin.flush()
    p.stdin.write("hash\n"); p.stdin.flush()
    print("initial", p.stdout.readline().strip(), flush=True)

    rng = random.Random(7)
    applied = 0
    for step in range(200):
        empties = [(x, y) for x in range(size) for y in range(size)
                   if b.grid[x, y] == EMPTY]
        if not empties:
            break
        color = b.turn
        if color == BLACK:
            legal = [c for c in empties if rules.is_black_legal_move(b, *c)[0]]
            if not legal:
                b.pass_turn()
                continue
            mv = rng.choice(legal)
        else:
            mv = rng.choice(empties)
        res = b.play_black(*mv) if color == BLACK else b.play_white(*mv)
        if not res[0]:
            continue
        color_ch = "b" if color == BLACK else "w"
        p.stdin.write("move %d %d %s\n" % (mv[0], mv[1], color_ch)); p.stdin.flush()
        reply = p.stdout.readline()
        applied += 1
        if reply.strip() != "ok":
            print("REJECTED at applied=%d %s" % (applied, mv)); break
        if applied % 20 == 0:
            p.stdin.write("hash\n"); p.stdin.flush()
            h = p.stdout.readline().strip()
            print("applied=%d hash=%s" % (applied, h), flush=True)
        if applied in (7, 33, 61, 95, 120, 150, 170, 185, 195, 199):
            print("applied=%d sending dump" % applied, flush=True)
            p.stdin.write("dump\n"); p.stdin.flush()
            rows = []
            for _ in range(size):
                r = p.stdout.readline()
                if r == "":
                    print("STDOUT CLOSED during dump at applied=%d" % applied)
                    print("stderr:", p.stderr.read())
                    print("rc", p.poll())
                    return
                rows.append(r.rstrip("\n"))
            bad = sum(1 for x in range(size) for y in range(size)
                      if rows[x][y] != str(int(b.grid[x, y])))
            print("  dump mismatches=%d" % bad, flush=True)
    p.stdin.write("quit\n"); p.stdin.flush()
    try:
        p.wait(timeout=5)
    except Exception:
        p.kill()
    print("engine rc", p.returncode)
    print("stderr:", p.stderr.read())


if __name__ == "__main__":
    main()
