#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""捕获提子后棋型缓存新鲜度探针。"""
import subprocess
import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
sys.path.insert(0, REPO_ROOT)

import board_tools  # noqa: E402

ENGINE = os.path.join(SCRIPT_DIR, "..", "build", "engine.exe")


class Eng:
    def __init__(self):
        self.p = subprocess.Popen([ENGINE], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True, bufsize=1)

    def cmd(self, line):
        """发送命令，按命令类型读取输出。"""
        self.p.stdin.write(line + "\n")
        self.p.stdin.flush()
        head = line.split(" ", 1)[0]
        if head in ("size", "clear", "set", "winmode", "forbid"):
            return None
        if head in ("play", "undo", "hash", "pat", "counters", "eval", "move"):
            return self.p.stdout.readline().rstrip("\n")
        if head == "dump":
            return [self.p.stdout.readline().rstrip("\n")
                    for _ in range(15)]
        out = []
        while True:
            r = self.p.stdout.readline()
            if r == "":
                raise RuntimeError("closed")
            r = r.rstrip("\n")
            out.append(r)
            if r == "end":
                break
        return out

    def quit(self):
        self.p.stdin.write("quit\n")
        self.p.stdin.flush()
        self.p.wait(timeout=5)


def main():
    codes = "g9 h9 f10 i8 g10 p0 g11 p0 e11 c13 p0"
    board, _ = board_tools.board_from_code(codes, size=15,
                                           first=board_tools.BLACK, gomoku=True)
    e = Eng()
    e.cmd("size 15")
    for x in range(15):
        for y in range(15):
            v = int(board.grid[x, y])
            if v:
                e.cmd("set %d %d %s" % (x, y, {1: "b", 2: "w", 3: "o"}[v]))
    print("play b h8:", e.cmd("play b 7 7"))
    print("pat d12 (h8 黑子在, F5 合理):", e.cmd("pat 3 3"))
    print("play w h7 (提 h8):", e.cmd("play w 8 7"))
    print("counters:", e.cmd("counters"))
    rows = e.cmd("dump")
    print("board (rows 4..9, cols 5..9):")
    for x in range(4, 10):
        print("  x=%2d: %s" % (x, rows[x][5:10]))
    print("pat d12 after capture (期望非 F5):", e.cmd("pat 3 3"))
    print("pat i9  after capture (期望非 F5):", e.cmd("pat 8 8"))
    e.quit()


if __name__ == "__main__":
    main()
