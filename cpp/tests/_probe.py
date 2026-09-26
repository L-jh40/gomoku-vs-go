#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""临时探针：自对弈若干步，统计用时与终局。"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CPP_DIR = os.path.dirname(SCRIPT_DIR)
REPO_ROOT = os.path.dirname(CPP_DIR)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from board import HybridBoard, BLACK, WHITE, OBSTACLE  # noqa: E402
import rules  # noqa: E402

ENGINE = os.path.join(CPP_DIR, "build", "engine.exe")


class Engine:
    def __init__(self):
        self.p = subprocess.Popen([ENGINE], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  text=True, bufsize=1)
        self.q = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        for line in self.p.stdout:
            self.q.put(line.rstrip("\r\n"))
        self.q.put(None)

    def send(self, s):
        self.p.stdin.write(s + "\n")
        self.p.stdin.flush()

    def readline(self, timeout=120):
        return self.q.get(timeout=timeout)

    def close(self):
        try:
            self.send("quit")
            self.p.wait(timeout=10)
        except Exception:
            self.p.kill()


def run(size, obstacles, steps, depth, max_sec, label):
    eng = Engine()
    b = HybridBoard(size)
    for (x, y) in obstacles:
        b.grid[x, y] = OBSTACLE
    eng.send("size %d" % size)
    eng.send("clear")
    for (x, y) in obstacles:
        eng.send("set %d %d o" % (x, y))
    t0 = time.time()
    for step in range(steps):
        if step > 0 and (b.white_wins_by_capture() or b.white_wins_by_occupy()
                         or b.white_wins_by_line_block()):
            print("[%s] white wins at step %d" % (label, step))
            break
        color = b.turn
        cs = "b" if color == BLACK else "w"
        eng.send("genmove %s %d 0 %g" % (cs, depth, max_sec))
        lines = []
        while True:
            ln = eng.readline()
            lines.append(ln)
            if ln.startswith("move") or ln in ("pass", "resign"):
                break
        if ln == "pass":
            print("[%s] white pass at step %d" % (label, step))
            break
        if ln == "resign":
            print("[%s] black resign at step %d" % (label, step))
            break
        _, mx, my = ln.split()
        mx, my = int(mx), int(my)
        if b.grid[mx, my] != 0 or not rules.is_black_legal_move(b, mx, my)[0] and color == BLACK:
            print("[%s] ILLEGAL %s at %s,%s" % (label, cs, mx, my))
            break
        eng.send("play %s %d %d" % (cs, mx, my))
        r = eng.readline()
        assert r == "ok", (r, mx, my, cs)
        if color == BLACK:
            b.play_black(mx, my)
        else:
            b.play_white(mx, my)
        if step % 10 == 0:
            print("[%s] step %d %s %d %d  elapsed %.1fs" % (label, step, cs, mx, my, time.time() - t0))
        if color == BLACK and b.check_black_five(mx, my):
            print("[%s] black five at step %d" % (label, step))
            break
    else:
        print("[%s] reached step cap %d" % (label, steps))
    print("[%s] total %.1fs" % (label, time.time() - t0))
    eng.close()


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "15"
    if which == "15":
        run(15, [], 120, 4, 10, "15x15")
    elif which == "9":
        run(9, [(0, 0), (0, 8), (8, 0), (8, 8)], 120, 4, 10, "9x9+obs")
    elif which == "fast":
        run(15, [], 60, 4, 3, "15x15-fast")
