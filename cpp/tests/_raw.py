#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Raw subprocess test: two engines, engine 2 dies at dump after 7 moves."""
from __future__ import annotations

import os
import subprocess
import sys
import time

ENGINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "build", "engine.exe")
ENGINE = os.path.abspath(ENGINE)


def spawn(tag, stderr_mode):
    p = subprocess.Popen([ENGINE], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=stderr_mode, text=True, bufsize=1)
    print("[%s] pid=%d" % (tag, p.pid), flush=True)
    return p


def main():
    use_first = "--nofirst" not in sys.argv
    stderr_mode = subprocess.DEVNULL
    if use_first:
        p1 = spawn("e1", stderr_mode)
        p1.stdin.write("size 9\nhash\n"); p1.stdin.flush()
        print("[e1]", p1.stdout.readline().strip(), flush=True)
        p1.stdin.write("quit\n"); p1.stdin.flush()
        p1.wait(timeout=10)
        print("[e1] exited rc=%s" % p1.returncode, flush=True)
        # Explicitly close pipes and drop the object.
        del p1

    p2 = spawn("e2", stderr_mode)
    p2.stdin.write("size 15\nclear\nhash\n"); p2.stdin.flush()
    print("[e2] initial", p2.stdout.readline().strip(), flush=True)

    moves = [(5, 7, "b"), (2, 8, "w"), (6, 13, "b"), (11, 4, "w"),
             (0, 12, "b"), (1, 4, "w"), (14, 6, "b")]
    for i, (x, y, c) in enumerate(moves):
        p2.stdin.write("move %d %d %s\n" % (x, y, c)); p2.stdin.flush()
        line = p2.stdout.readline()
        print("[e2] move %d -> %r" % (i, line.strip()), flush=True)
        if line == "":
            print("[e2] EOF during move", i); break
    p2.stdin.write("dump\n"); p2.stdin.flush()
    for r in range(15):
        line = p2.stdout.readline()
        if line == "":
            print("!!! EOF during dump at row %d" % r, flush=True)
            print("    poll=%r" % (p2.poll(),), flush=True)
            try:
                rc = p2.wait(timeout=3)
                print("    wait rc=%r hex=%s" % (rc, hex(rc & 0xFFFFFFFF)), flush=True)
            except Exception as e:
                print("    wait failed: %r" % (e,), flush=True)
            print("    stdin=%r stdout=%r" % (p2.stdin, p2.stdout), flush=True)
            return
        print("  row%d %s" % (r, line.strip()), flush=True)
    p2.stdin.write("quit\n"); p2.stdin.flush()
    p2.wait(timeout=5)
    print("done rc", p2.returncode)


if __name__ == "__main__":
    main()
