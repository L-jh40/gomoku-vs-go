#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""pat 探针：查看指定用例、指定点的四方向线型。"""
import subprocess
import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
sys.path.insert(0, REPO_ROOT)

import board_tools  # noqa: E402

CASES = {
    "b": "h8 p0 g7 p0 j10 p0 l12",
    "4": "h8 p0 h7 p0 h6 p0 i8 p0 j7 h5 p0",
    "5": "h8 p0 h7 p0 h6",
    "a": "h8 p0 h7 p0 h6 p0 i8 p0 j7",
    "c": "g9 h9 f10 i8 g10 p0 g11 p0 e11 c13 p0",
}

PROBES = {
    "b": ["i9", "k11", "f6", "m13"],
    "4": ["h9", "h10", "g10", "k6", "h4", "g9", "f10"],
    "5": ["h9", "h5", "h10", "h4"],
    "a": ["h9", "h5", "g10", "k6", "h10", "h4"],
    "c": ["g8", "g12", "h8", "d12", "g7", "g13", "i9"],
}

PAT_NAMES = {0: "DEAD", 1: "OL", 2: "B1", 3: "F1", 4: "B2", 5: "F2", 6: "F2A",
             7: "F2B", 8: "B3", 9: "F3", 10: "F3S", 11: "B4", 12: "F4", 13: "F5"}
DIRS = ["(1,0)", "(0,1)", "(1,1)", "(1,-1)"]


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "b"
    codes = CASES[which]
    p = subprocess.Popen([os.path.join(SCRIPT_DIR, "..", "build", "engine.exe")],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, text=True, bufsize=1)

    def send_raw(line):
        p.stdin.write(line + "\n")
        p.stdin.flush()
        return p.stdout.readline().rstrip("\n")

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

    board, _ = board_tools.board_from_code(codes, size=15,
                                           first=board_tools.BLACK, gomoku=True)
    send("size 15")
    for x in range(15):
        for y in range(15):
            v = int(board.grid[x, y])
            if v:
                send("set %d %d %s" % (x, y, {1: "b", 2: "w", 3: "o"}[v]))
    print("case %s stones:" % which)
    for x in range(15):
        for y in range(15):
            v = int(board.grid[x, y])
            if v:
                print("   %s = %s" % (board_tools.coord_to_code(x, y, 15),
                                      "B" if v == 1 else ("W" if v == 2 else "O")))
    for code in PROBES[which]:
        x, y = board_tools.code_to_coord(code, 15)
        row = send_raw("pat %d %d" % (x, y))
        vals = row.split()
        dirs = [PAT_NAMES.get(int(v), "?") for v in vals[:4]]
        print("pat %s (x=%d y=%d): %s | p4=%s fours=%s threes=%s forbid=%s"
              % (code, x, y, " ".join("%s:%s" % (DIRS[i], dirs[i]) for i in range(4)),
                 vals[4], vals[5], vals[6], vals[7]))
    p.stdin.write("quit\n")
    p.stdin.flush()
    p.wait(timeout=5)


if __name__ == "__main__":
    main()
