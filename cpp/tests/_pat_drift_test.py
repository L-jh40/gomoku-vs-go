#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""深度 make/undo 后 pat 一致性测试。

随机对局（含白提子）→ undo 到中间局面 → 与同局面的全新摆放逐点对比 pat 输出。
任何差异 = 增量棋型缓存漂移（make/undo 触碰集不对称）。
"""
import random
import subprocess
import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(SCRIPT_DIR, "..", "build", "engine.exe")


class Eng:
    def __init__(self):
        self.p = subprocess.Popen([ENGINE], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True, bufsize=1)

    def cmd(self, line):
        self.p.stdin.write(line + "\n")
        self.p.stdin.flush()
        head = line.split(" ", 1)[0]
        if head in ("size", "clear", "set", "winmode", "forbid"):
            return None
        if head in ("play", "undo", "hash", "pat", "counters", "eval"):
            return self.p.stdout.readline().rstrip("\n")
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
    rng = random.Random(20261007)
    e = Eng()
    total_diff = 0
    total_checked = 0
    for trial in range(8):
        e.cmd("size 15")
        e.cmd("clear")
        moves = []
        for step in range(40):
            color = "b" if step % 2 == 0 else "w"
            empties = [(x, y) for x in range(15) for y in range(15)]
            rng.shuffle(empties)
            # 白棋优先贴黑下（引发提子）
            if color == "w" and moves:
                lx, ly = moves[-1][0], moves[-1][1]
                near = [(lx + dx, ly + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                        if 0 <= lx + dx < 15 and 0 <= ly + dy < 15]
                rng.shuffle(near)
                empties = near + empties
            placed = False
            for (x, y) in empties:
                if e.cmd("play %s %d %d" % (color, x, y)) == "ok":
                    moves.append((x, y, color))
                    placed = True
                    break
            if not placed:
                break
        if len(moves) < 10:
            continue
        # undo 到中间（保留约一半）
        keep = len(moves) // 2
        for _ in range(len(moves) - keep):
            e.cmd("undo")
        # 走子序列下的 pat
        played_pats = {}
        for x in range(15):
            for y in range(15):
                played_pats[(x, y)] = e.cmd("pat %d %d" % (x, y))
        h1 = e.cmd("hash")
        # 同局面全新摆放
        e.cmd("size 15")
        e.cmd("clear")
        for (x, y, color) in moves[:keep]:
            e.cmd("set %d %d %s" % (x, y, color))
        fresh_pats = {}
        for x in range(15):
            for y in range(15):
                fresh_pats[(x, y)] = e.cmd("pat %d %d" % (x, y))
        h2 = e.cmd("hash")
        diffs = [(xy, played_pats[xy], fresh_pats[xy])
                 for xy in played_pats if played_pats[xy] != fresh_pats[xy]]
        hash_ok = (h1 == h2)
        total_diff += len(diffs)
        total_checked += len(played_pats)
        print("[trial %d] keep=%d hash=%s pats-diff=%d / %d" %
              (trial, keep, "OK" if hash_ok else "DIFF", len(diffs), len(played_pats)))
        for xy, a, b in diffs[:4]:
            print("    (%d,%d): played=%s fresh=%s" % (xy[0], xy[1], a, b))
    e.quit()
    print("done: pat-diffs=%d / %d checks" % (total_diff, total_checked))


if __name__ == "__main__":
    main()
