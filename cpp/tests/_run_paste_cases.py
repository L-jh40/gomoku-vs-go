#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""快速查看 粘贴板.md 各用例的引擎候选点输出（wcand + candidates）。"""
import subprocess
import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
sys.path.insert(0, REPO_ROOT)

import board_tools  # noqa: E402

CASES = [
    ("a", "h8 p0 h7 p0 h6 p0 i8 p0 j7"),
    ("b", "h8 p0 g7 p0 j10 p0 l12"),
    ("c", "g9 h9 f10 i8 g10 p0 g11 p0 e11 c13 p0"),
    ("4", "h8 p0 h7 p0 h6 p0 i8 p0 j7 h5 p0"),
    ("5", "h8 p0 h7 p0 h6"),
]

MODE = sys.argv[1] if len(sys.argv) > 1 else "cand"   # cand / wcand


def main():
    p = subprocess.Popen([os.path.join(SCRIPT_DIR, "..", "build", "engine.exe")],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, text=True, bufsize=1)

    def send(line):
        p.stdin.write(line + "\n")
        p.stdin.flush()
        out = []
        head = line.split(" ", 1)[0]
        if head in ("size", "clear", "set", "winmode", "forbid"):
            return out
        while True:
            r = p.stdout.readline()
            if r == "":
                raise RuntimeError("engine closed")
            r = r.rstrip("\n")
            out.append(r)
            if r == "end":
                break
        return out

    for name, codes in CASES:
        board, _ = board_tools.board_from_code(codes, size=15,
                                               first=board_tools.BLACK, gomoku=True)
        send("size 15")
        for x in range(15):
            for y in range(15):
                v = int(board.grid[x, y])
                if v:
                    send("set %d %d %s" % (x, y, {1: "b", 2: "w", 3: "o"}[v]))
        if MODE == "wcand":
            out = send("wcand")
            print("case %s:" % name)
            for r in out:
                if r != "end":
                    print("   ", r)
        else:
            out = send("candidates w 11 10")
            cands = [tuple(map(int, r.split()[1:3])) for r in out
                     if r.startswith("cand")]
            print("case %s: %d cands -> %s" % (
                name, len(cands),
                sorted(board_tools.coord_to_code(x, y, 15) for x, y in cands)))
    p.stdin.write("quit\n")
    p.stdin.flush()
    p.wait(timeout=5)


if __name__ == "__main__":
    main()
