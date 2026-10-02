#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
forbid_switches.py - 禁手开关（长连 / 四四 / 三三）一致性测试。

在仓库根目录运行：
    py cpp/tests/forbid_switches.py

背景：GUI“选择模式”里的三个禁手复选框原来只影响 Python 侧（rules.py），
C++ 引擎无论开关怎么设都按 renju 三禁判定。现在引擎加了 `forbid <长连> <四四> <三三>`
命令（`Board::set_forbid`，会重算 p4_black_ 预筛标记），本测试逐个组合比对：

    引擎 checkforbidden（去掉无气自吃点） == Python rules.is_black_legal_move 的禁手集合

局面 = 导出/粘贴板.md 里所有坐标行 + 12 个随机簇局面，8 种开关组合。
任何不一致都算失败。
"""
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

import board_tools as bt  # noqa: E402
import rules  # noqa: E402
from board import BLACK, WHITE, HybridBoard  # noqa: E402

ENGINE = os.path.join(CPP_DIR, "build", "engine.exe")
CASE_FILE = os.path.join(REPO_ROOT, "导出", "粘贴板.md")


def load_positions():
    out = []
    if os.path.exists(CASE_FILE):
        for raw in open(CASE_FILE, encoding="utf-8"):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            low = line.lower()
            if any(low.startswith(p) for p in ("forbid:", "legal:", "setup:")):
                continue
            try:
                b, _ = bt.board_from_code(line, size=15, first=bt.BLACK,
                                          gomoku=True)
            except Exception:
                continue
            if b.history:
                out.append(b)
    rng = random.Random(4242)
    for _ in range(12):
        b = HybridBoard(15)
        cells = set()
        n = rng.randint(6, 22)
        while len(cells) < n:
            cells.add((rng.randint(3, 11), rng.randint(3, 11)))
        for (x, y) in cells:
            b.grid[x, y] = BLACK if rng.random() < 0.5 else WHITE
        b._invalidate_caches()
        out.append(b)
    return out


def python_forbidden(board):
    out = set()
    for x in range(board.size):
        for y in range(board.size):
            if not board.is_empty(x, y):
                continue
            ok, ftype = rules.is_black_legal_move(board, x, y)
            if not ok and ftype in ("three_three", "four_four", "overline"):
                out.add((x, y))
    return out


def engine_forbidden(proc, board, flags):
    def send(line):
        proc.stdin.write(line + "\n")
        proc.stdin.flush()

    send("size %d" % board.size)
    send("clear")
    for x in range(board.size):
        for y in range(board.size):
            v = int(board.grid[x, y])
            if v == 1:
                send("set %d %d b" % (x, y))
            elif v == 2:
                send("set %d %d w" % (x, y))
            elif v == 3:
                send("set %d %d o" % (x, y))
    send("forbid %d %d %d" % flags)
    send("checkforbidden")
    out = set()
    while True:
        row = proc.stdout.readline()
        if row == "":
            raise RuntimeError("engine closed")
        row = row.strip()
        if row == "end":
            break
        a, b2 = row.split()
        out.add((int(a), int(b2)))
    return out


def main() -> int:
    if not os.path.exists(ENGINE):
        print("engine not found: %s（先跑 cmd /c cpp\\build.bat）" % ENGINE)
        return 2
    positions = load_positions()
    proc = subprocess.Popen([ENGINE], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, encoding="utf-8", bufsize=1)
    total = 0
    bad = 0
    try:
        for flags in ((1, 1, 1), (1, 1, 0), (1, 0, 1), (1, 0, 0),
                      (0, 1, 1), (0, 1, 0), (0, 0, 1), (0, 0, 0)):
            for i, b in enumerate(positions):
                c = b.copy()
                c._forbid_overline = bool(flags[0])
                c._forbid_44 = bool(flags[1])
                c._forbid_33 = bool(flags[2])
                py = python_forbidden(c)
                self_cap = set(c.get_no_liberty_positions())
                eng = engine_forbidden(proc, b, flags) - self_cap
                total += 1
                if py != eng:
                    bad += 1
                    if bad <= 6:
                        print("DIFF forbid=%d%d%d 局面#%d: 引擎多 %s / Python 多 %s"
                              % (flags[0], flags[1], flags[2], i,
                                 sorted(eng - py), sorted(py - eng)))
    finally:
        try:
            proc.stdin.write("quit\n")
            proc.stdin.flush()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
    print("开关组合×局面 = %d，不一致 = %d" % (total, bad))
    if bad:
        print("FAIL")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
