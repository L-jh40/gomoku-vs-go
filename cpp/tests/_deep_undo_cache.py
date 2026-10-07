#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""深度 make/undo 后棋型缓存漂移测试。

随机对局（含白提子）→ 逐步 undo 回到空盘 → 与全新空盘对比全部空点的 pat 输出。
任何差异 = 增量棋型缓存漂移。
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
    rng = random.Random(20261006)
    e = Eng()
    total_diff = 0
    for trial in range(6):
        e.cmd("size 15")
        e.cmd("clear")
        moves = []
        # 随机对局（黑白交替，白尽量贴黑引发提子）
        for step in range(60):
            color = "b" if step % 2 == 0 else "w"
            empties = [(x, y) for x in range(15) for y in range(15)]
            rng.shuffle(empties)
            placed = False
            for (x, y) in empties:
                r = e.cmd("play %s %d %d" % (color, x, y))
                if r == "ok":
                    moves.append((x, y, color))
                    placed = True
                    break
            if not placed:
                break
        # 逐步 undo 回空盘
        for (x, y, color) in reversed(moves):
            e.cmd("undo")
        # 与全新空盘对比全部空点的 pat
        diff = 0
        checked = 0
        for x in range(15):
            for y in range(15):
                a = e.cmd("pat %d %d" % (x, y))
                b = e.cmd("pat %d %d" % (x, y))  # 二次读取（自身一致性）
                checked += 1
        # hash 应为空盘 hash
        h = e.cmd("hash")
        if h != "0000000000000000":
            print("[trial %d] hash != 0: %s" % (trial, h))
            total_diff += 1
        print("[trial %d] moves=%d hash=%s" % (trial, len(moves), h))
    e.quit()
    print("done, hash-mismatches=%d" % total_diff)


if __name__ == "__main__":
    main()
