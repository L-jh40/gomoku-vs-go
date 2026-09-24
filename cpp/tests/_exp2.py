#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Scenario C/D: both engines via diff_forbidden.Engine, with/without heavy compute."""
from __future__ import annotations

import os
import random
import sys
import threading
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CPP_DIR = os.path.dirname(SCRIPT_DIR)
REPO_ROOT = os.path.dirname(CPP_DIR)
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, REPO_ROOT)
import diff_forbidden as d  # noqa: E402
from board import HybridBoard, EMPTY, BLACK  # noqa: E402
import rules  # noqa: E402

MOVES = [(5, 7, "b"), (2, 8, "w"), (6, 13, "b"), (11, 4, "w"),
         (0, 12, "b"), (1, 4, "w"), (14, 6, "b")]


def check(e, label):
    print("[%s] poll=%r stdout_closed=%s reader_alive=%s"
          % (label, e.p.poll(), e.p.stdout.closed, e.reader.is_alive()), flush=True)


def run(heavy):
    e1 = d.Engine()
    e1.send("size 9"); e1.send("hash"); e1.readline()
    e1.close()
    time.sleep(0.2)
    check(e1, "e1-after-close")
    e2 = d.Engine()
    e2.send("size 15"); e2.send("clear"); e2.send("hash")
    print("[e2] initial", e2.readline(), flush=True)
    b = HybridBoard(15)
    for i, (x, y, c) in enumerate(MOVES):
        if heavy:
            empties = [(a, b2) for a in range(15) for b2 in range(15)
                       if b.grid[a, b2] == EMPTY]
            legal = [cc for cc in empties if rules.is_black_legal_move(b, *cc)[0]]
            print("    heavy: %d legal" % len(legal), flush=True)
            b.grid[legal[0]] = BLACK
        e2.send("move %d %d %s" % (x, y, c))
        line = e2.readline()
        print("[e2] move %d -> %r" % (i, line), flush=True)
        if line != "ok":
            check(e2, "e2-at-fail")
            return
    e2.send("dump")
    rows = [e2.readline() for _ in range(15)]
    print("[e2] dump rows ok=%s" % all(rows), flush=True)
    e2.close()


def main():
    heavy = "--heavy" in sys.argv
    print("heavy=%s" % heavy, flush=True)
    for rep in range(3):
        print("---- rep %d ----" % rep, flush=True)
        run(heavy)


if __name__ == "__main__":
    main()
