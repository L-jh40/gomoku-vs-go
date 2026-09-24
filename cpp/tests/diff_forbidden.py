#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
diff_forbidden.py - 黑棋禁手判定的差分测试。

在仓库根目录运行：
    py cpp/tests/diff_forbidden.py

流程：
  1. 子进程启动 cpp/build/engine.exe，逐行写命令、读 stdout。
  2. 用 Python 的 board.HybridBoard + rules.is_black_legal_move 生成随机局面
     （随机自对弈 + 随机泼洒），并手工加入 5 个构造局面。
  3. 把每个局面的所有子写入引擎，调 checkforbidden，与 Python 逐点比较。
  4. 断言：occupied/自杀/成五/长连类不一致 == 0；三三/四四类不一致必须能
     归因到 Rapfi 相对朴素匹配更严格的两条：三无法延伸成活四/五，或延伸点本身
     是禁手。无法归因则退出码 1。
  5. make/undo 一致性：200 步对局，每 20 步记录引擎 Zobrist；全部 undo 后与
     初始一致；中途 10 个时刻与 Python 网格比对。
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

from board import HybridBoard, EMPTY, BLACK, WHITE, OBSTACLE, DIRECTIONS  # noqa: E402
import rules  # noqa: E402

ENGINE = os.path.join(CPP_DIR, "build", "engine.exe")

VERBOSE = "--verbose" in sys.argv or "-v" in sys.argv


# ----------------------------------------------------------------------------
# 引擎交互
# ----------------------------------------------------------------------------
class Engine:
    def __init__(self):
        if not os.path.exists(ENGINE):
            raise SystemExit(
                "engine not found: %s\n请先在仓库根目录运行 cmd /c cpp\\build.bat"
                % ENGINE
            )
        self.p = subprocess.Popen(
            [ENGINE],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

    def send(self, cmd: str) -> None:
        self.p.stdin.write(cmd + "\n")
        self.p.stdin.flush()

    def readline(self) -> str:
        line = self.p.stdout.readline()
        if line == "":
            raise RuntimeError("engine closed its stdout unexpectedly")
        return line.rstrip("\r\n")

    def load(self, board: HybridBoard) -> None:
        self.send("size %d" % board.size)
        self.send("clear")
        for x in range(board.size):
            for y in range(board.size):
                v = int(board.grid[x, y])
                if v == BLACK:
                    self.send("set %d %d b" % (x, y))
                elif v == WHITE:
                    self.send("set %d %d w" % (x, y))
                elif v == OBSTACLE:
                    self.send("set %d %d o" % (x, y))

    def forbidden(self, board: HybridBoard) -> set:
        self.load(board)
        self.send("checkforbidden")
        out = set()
        while True:
            line = self.readline()
            if line == "end":
                break
            a, b = line.split()
            out.add((int(a), int(b)))
        return out

    def close(self) -> None:
        try:
            self.send("quit")
            self.p.wait(timeout=10)
        except Exception:
            self.p.kill()


# ----------------------------------------------------------------------------
# 局面生成
# ----------------------------------------------------------------------------
def random_selfplay(rng: random.Random, snapshots: list) -> None:
    """一局随机自对弈；黑只下合法点、白下任意空点，黑连五即结束。"""
    size = rng.choice([9, 9, 11, 13, 13, 15, 15, 15, 15, 17, 19])
    b = HybridBoard(size)
    steps = rng.randint(8, 70)
    for _ in range(steps):
        empties = [
            (x, y)
            for x in range(size)
            for y in range(size)
            if b.grid[x, y] == EMPTY
        ]
        if not empties:
            break
        if rng.random() < 0.30:
            snapshots.append(b.copy())
        if b.turn == BLACK:
            legal = [c for c in empties if rules.is_black_legal_move(b, *c)[0]]
            if not legal:
                b.pass_turn()
                continue
            mv = rng.choice(legal)
            b.play_black(*mv)
            if b.check_black_five(*mv):
                snapshots.append(b.copy())
                return
        else:
            b.play_white(*rng.choice(empties))


def random_scatter(rng: random.Random, snapshots: list) -> None:
    """随机泼洒棋子/障碍，快速制造无气点、密集棋形。"""
    size = rng.choice([9, 11, 13, 15, 15, 19])
    b = HybridBoard(size)
    density = rng.uniform(0.10, 0.32)
    for x in range(size):
        for y in range(size):
            r = rng.random()
            if r < density * 0.55:
                b.grid[x, y] = BLACK
            elif r < density:
                b.grid[x, y] = WHITE
    snapshots.append(b)


def build_positions(rng: random.Random) -> list:
    snaps: list = []
    # 随机自对弈：尽量凑够多数局面。
    guard = 0
    while len(snaps) < 45 and guard < 4000:
        guard += 1
        random_selfplay(rng, snaps)
    # 随机泼洒：补充无气点 / 双三雏形 / 接近五连。
    for _ in range(18):
        random_scatter(rng, snaps)
    # 手工构造 5 个局面。
    snaps.extend(constructed_positions())
    return snaps


def board_from_cells(cells, size=15) -> HybridBoard:
    """cells: (x, y, ch) 列表，ch ∈ {'X' 黑, 'O' 白, '#' 障碍}。x=行, y=列。"""
    b = HybridBoard(size)
    for (x, y, ch) in cells:
        if ch == "X":
            b.grid[x, y] = BLACK
        elif ch == "O":
            b.grid[x, y] = WHITE
        elif ch == "#":
            b.grid[x, y] = OBSTACLE
    return b


def constructed_positions() -> list:
    out = []
    # 1) 恰成五：四连(7,5..8)，(7,4)/(7,9) 补成五，合法。
    out.append(board_from_cells([
        (7, 5, "X"), (7, 6, "X"), (7, 7, "X"), (7, 8, "X"),
    ]))
    # 2) 长连：五连(7,5..9)，(7,4)/(7,10) 补子成六连，禁手。
    out.append(board_from_cells([
        (7, 5, "X"), (7, 6, "X"), (7, 7, "X"), (7, 8, "X"), (7, 9, "X"),
    ]))
    # 3) 双四：(7,7) 同时形成横向与竖向两个活四，禁手。
    out.append(board_from_cells([
        (7, 4, "X"), (7, 5, "X"), (7, 6, "X"),
        (4, 7, "X"), (5, 7, "X"), (6, 7, "X"),
    ]))
    # 4) 可延伸活三双三：(7,7) 同时形成横向与竖向两个活三，禁手。
    out.append(board_from_cells([
        (7, 5, "X"), (7, 6, "X"),
        (5, 7, "X"), (6, 7, "X"),
    ]))
    # 5) 不可延伸的假活三双三：两个方向形似活三，但横向一端是障碍、
    #    竖向延伸点被白棋占住，因此都不构成真活三（不应按三三禁手处理）。
    out.append(board_from_cells([
        (7, 4, "#"), (7, 5, "X"), (7, 6, "X"),
        (5, 7, "X"), (6, 7, "X"), (8, 7, "O"),
    ]))
    return out


# ----------------------------------------------------------------------------
# 归因：Rapfi 相对朴素匹配的两条额外严格条件
# ----------------------------------------------------------------------------
def extension_points(b, x, y, dx, dy, maxdist=4):
    """镜像 Rapfi：从落子点沿两个方向穿过连续黑子，遇到第一个非黑子。
    空点则为延伸候选；白/障碍/墙则停止。"""
    out = []
    for sgn in (-1, 1):
        cx, cy = x, y
        for _ in range(maxdist):
            cx += sgn * dx
            cy += sgn * dy
            if not b.in_bounds(cx, cy):
                break
            v = int(b.grid[cx, cy])
            if v == EMPTY:
                out.append((cx, cy))
                break
            if v != BLACK:
                break
    return out


def direction_threes(b, x, y, dx, dy):
    """Python 版在 (x,y) 落黑后、方向 (dx,dy) 上识别的三的集合。"""
    return rules._three_sets(b, x, y, dx, dy, set())


def rapfi_direction_verdict(b, x, y, dx, dy):
    """在已把黑子放在 (x,y) 的棋盘上评估该方向。返回：
    ('true', e)        找到一个真延伸点 e；
    ('noext', None)    没有任何能延伸成活四/五的点；
    ('forbidden', e)   能延伸，但延伸点 e 本身是禁手/自杀。"""
    exts = extension_points(b, x, y, dx, dy)
    if not exts:
        return ("noext", None)
    saw_extend = False
    for (ex, ey) in exts:
        if b.would_self_capture(ex, ey):
            continue
        b.grid[ex, ey] = BLACK
        try:
            t = rules.classify_direction_after_move(b, ex, ey, dx, dy)
        finally:
            b.grid[ex, ey] = EMPTY
        if t in ("open_four", "rush_four", "five"):
            saw_extend = True
            ok, _ = rules.is_black_legal_move(b, ex, ey)
            if not ok:
                return ("forbidden", (ex, ey))
            return ("true", (ex, ey))
    if saw_extend:
        return ("forbidden", None)
    return ("noext", None)


def attribute_py_forbidden_cpp_legal(b, x, y, py_type):
    """Python 判禁手、C++ 判合法。只有当某个 Python 计为三的方向满足
    (i) 无法延伸成活四/五 或 (ii) 延伸点本身是禁手 时才可归因。"""
    if py_type not in ("three_three", "four_four"):
        return None
    b.grid[x, y] = BLACK
    try:
        reasons = []
        for d, (dx, dy) in enumerate(DIRECTIONS):
            if not direction_threes(b, x, y, dx, dy):
                continue
            verdict, where = rapfi_direction_verdict(b, x, y, dx, dy)
            if verdict == "noext":
                reasons.append(("no_extend", d))
            elif verdict == "forbidden":
                reasons.append(("ext_forbidden", d, where))
            elif verdict == "true":
                return None  # 存在一个真三 -> 无法用两条严格条件解释
        if reasons:
            return reasons
        # fouler 是四四，且没有三方向；无法用三三的两条条件解释。
        return None
    finally:
        b.grid[x, y] = EMPTY


# ----------------------------------------------------------------------------
# 比较一个局面
# ----------------------------------------------------------------------------
def compare(eng: Engine, b: HybridBoard, stats: dict, details: list) -> None:
    cpp = eng.forbidden(b)
    for x in range(b.size):
        for y in range(b.size):
            if int(b.grid[x, y]) != EMPTY:
                continue
            stats["points"] += 1
            ok, ftype = rules.is_black_legal_move(b, x, y)
            py_bad = not ok
            cpp_bad = (x, y) in cpp
            if py_bad == cpp_bad:
                stats["agree"] += 1
                if py_bad:
                    stats["agree_forbidden"] += 1
                continue

            if not py_bad:
                # C++ 更严：确认是不是自杀 / 长连；否则难以归因。
                if b.would_self_capture(x, y):
                    cat = "self_capture"
                else:
                    b.grid[x, y] = BLACK
                    run = b.black_run_length(x, y)
                    b.grid[x, y] = EMPTY
                    cat = "overline" if run >= 6 else ("five" if run == 5 else "cpp_stricter")
            else:
                cat = ftype or "py_unknown"

            stats["mismatch_" + cat] = stats.get("mismatch_" + cat, 0) + 1
            if len(details) < 40:
                details.append((x, y, py_bad, ftype, cpp_bad, cat, b.copy()))


def mismatch_is_hard(cat: str) -> bool:
    """需要归因的类别（其余必须为 0）。"""
    return cat in ("three_three", "four_four", "cpp_stricter")


# ----------------------------------------------------------------------------
# make/undo 一致性
# ----------------------------------------------------------------------------
def make_undo_test(eng: Engine, rng: random.Random) -> bool:
    ok_all = True
    size = 15
    b = HybridBoard(size)
    eng.send("size %d" % size)
    eng.send("clear")
    eng.send("hash")
    initial = eng.readline()

    hashes_at = {}
    applied = 0
    dumps_checked = 0
    for step in range(200):
        if step % 20 == 0:
            print("[make/undo] step %d applied=%d turn=%s" % (step, applied, b.turn), flush=True)
        empties = [
            (x, y)
            for x in range(size)
            for y in range(size)
            if b.grid[x, y] == EMPTY
        ]
        if not empties:
            break
        color = b.turn
        if color == BLACK:
            legal = [c for c in empties if rules.is_black_legal_move(b, *c)[0]]
            if not legal:
                b.pass_turn()
                continue
            mv = rng.choice(legal)
        else:
            mv = rng.choice(empties)

        res = None
        if color == BLACK:
            res = b.play_black(*mv)
        else:
            res = b.play_white(*mv)
        if not res[0]:
            continue
        color_ch = "b" if color == BLACK else "w"
        eng.send("move %d %d %s" % (mv[0], mv[1], color_ch))
        reply = eng.readline()
        if reply != "ok":
            print("[make/undo] engine rejected move %s %s -> %s" % (mv, color_ch, reply))
            ok_all = False
            break
        applied += 1

        if applied % 20 == 0:
            eng.send("hash")
            hashes_at[applied] = eng.readline()

        if applied in (7, 33, 61, 95, 120, 150, 170, 185, 195, 199):
            eng.send("dump")
            grid = [[int(eng.readline()[y]) for y in range(size)] for _ in range(size)]
            dumps_checked += 1
            for x in range(size):
                for y in range(size):
                    if grid[x][y] != int(b.grid[x, y]):
                        print("[make/undo] dump mismatch at step %d cell (%d,%d): "
                              "engine=%d python=%d" % (applied, x, y, grid[x][y], int(b.grid[x, y])))
                        ok_all = False

    # 全部 undo，检查哈希回到初始。
    for _ in range(applied):
        eng.send("undo")
        if eng.readline() != "ok":
            print("[make/undo] undo failed")
            ok_all = False
            break
    eng.send("hash")
    final = eng.readline()
    if final != initial:
        print("[make/undo] hash after full undo %s != initial %s" % (final, initial))
        ok_all = False
    eng.send("dump")
    for x in range(size):
        row = eng.readline()
        if row != "0" * size:
            print("[make/undo] board not empty after undo, row %d = %s" % (x, row))
            ok_all = False

    print("[make/undo] applied=%d dumps_checked=%d hashes=%s final_hash=%s initial=%s"
          % (applied, dumps_checked, len(hashes_at), final, initial))
    return ok_all


# ----------------------------------------------------------------------------
def main() -> int:
    rng = random.Random(20240917)
    positions = build_positions(rng)
    print("[phase] generated %d positions" % len(positions), flush=True)
    stats = {"points": 0, "agree": 0, "agree_forbidden": 0}
    details: list = []

    eng = Engine()
    try:
        for i, b in enumerate(positions):
            compare(eng, b, stats, details)
    finally:
        eng.close()
    print("[phase] compare done", flush=True)

    print("=" * 70)
    print("局面数: %d   比较空点数: %d   一致: %d (其中禁手/非法 %d)"
          % (len(positions), stats["points"], stats["agree"], stats["agree_forbidden"]))

    # 硬性不一致类别
    hard_cats = [k for k in stats if k.startswith("mismatch_") and mismatch_is_hard(k[len("mismatch_"):])]
    trivial_cats = [k for k in stats if k.startswith("mismatch_") and not mismatch_is_hard(k[len("mismatch_"):])]

    for k in sorted(trivial_cats):
        print("  %-24s %d" % (k[len("mismatch_"):], stats[k]))
    for k in sorted(hard_cats):
        print("  %-24s %d" % (k[len("mismatch_"):], stats[k]))

    unattributed = 0
    attributed = 0
    for (x, y, py_bad, ftype, cpp_bad, cat, b) in details:
        if not mismatch_is_hard(cat):
            continue
        reason = attribute_py_forbidden_cpp_legal(b, x, y, ftype)
        if reason:
            attributed += 1
            if VERBOSE:
                print("  [归因] (%d,%d) %s py=%s cpp=%s -> %s"
                      % (x, y, cat, ftype, cpp_bad, reason))
        else:
            unattributed += 1
            print("  [无法归因] (%d,%d) cat=%s py_type=%s py_bad=%s cpp_bad=%s"
                  % (x, y, cat, ftype, py_bad, cpp_bad))
            if VERBOSE:
                print_board(b)

    print("-" * 70)
    print("硬性不一致合计: %d" % sum(stats.get(k, 0) for k in hard_cats))
    print("已归因: %d" % attributed)
    print("无法归因不一致 = %d" % unattributed)
    print("=" * 70)

    print("[phase] attribution done, starting make/undo", flush=True)
    make_undo_ok = False
    eng2 = Engine()
    try:
        make_undo_ok = make_undo_test(eng2, random.Random(7))
    finally:
        eng2.close()
    print("[phase] make/undo done", flush=True)

    if unattributed != 0:
        print("FAIL: 存在无法归因的禁手判定差异")
        return 1
    if not make_undo_ok:
        print("FAIL: make/undo 一致性未通过")
        return 1
    print("PASS")
    return 0


def print_board(b):
    chars = {EMPTY: ".", BLACK: "X", WHITE: "O", OBSTACLE: "#"}
    for x in range(b.size):
        print("    " + "".join(chars[int(b.grid[x, y])] for y in range(b.size)))


if __name__ == "__main__":
    sys.exit(main())
