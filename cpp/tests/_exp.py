#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Isolate the two-engine EOF: pump thread vs raw reads."""
from __future__ import annotations

import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import diff_forbidden as d  # noqa: E402

MOVES = [(5, 7, "b"), (2, 8, "w"), (6, 13, "b"), (11, 4, "w"),
         (0, 12, "b"), (1, 4, "w"), (14, 6, "b")]


def raw_engine():
    return subprocess.Popen([d.ENGINE], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, bufsize=1)


def do_moves(reader, sender, label):
    sender("size 15\nclear\nhash\n")
    print("[%s] initial" % label, reader(), flush=True)
    for (x, y, c) in MOVES:
        sender("move %d %d %s\n" % (x, y, c))
        print("[%s] move %r" % (label, reader()), flush=True)
    sender("dump\n")
    rows = [reader() for _ in range(15)]
    print("[%s] dumped %d rows, empty=%s" % (label, len(rows), all(rows)), flush=True)


def scenario(label, first_maker):
    print("=" * 50, label, flush=True)
    p1 = first_maker()
    if isinstance(p1, d.Engine):
        p1.send("size 9"); p1.send("hash"); p1.readline()
        p1.close()
    else:
        p1.stdin.write("size 9\nhash\n"); p1.stdin.flush()
        p1.stdout.readline()
        p1.stdin.write("quit\n"); p1.stdin.flush()
        p1.wait(timeout=10)
    print("[e1] rc=%s" % (p1.p.returncode if isinstance(p1, d.Engine) else p1.returncode),
          flush=True)

    if isinstance(p1, d.Engine):
        p2 = d.Engine()
        do_moves(p2.readline, p2.send, "queue")
        p2.close()
    else:
        p2 = d.Engine()
        do_moves(p2.readline, p2.send, "queue")
        p2.close()


def main():
    # A: raw first, Engine second
    scenario("A raw-first", raw_engine)
    # B: Engine first (pump), raw second reads
    print("=" * 50, "B engine-first", flush=True)
    q1 = d.Engine()
    q1.send("size 9"); q1.send("hash"); q1.readline()
    q1.close()
    p2 = raw_engine()

    def send(s):
        p2.stdin.write(s); p2.stdin.flush()

    def read():
        line = p2.stdout.readline()
        return line.rstrip("\r\n") if line else "<EOF>"

    do_moves(read, send, "raw")
    p2.stdin.write("quit\n"); p2.stdin.flush()
    p2.wait(timeout=5)


if __name__ == "__main__":
    main()
