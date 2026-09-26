#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
diff_eval.py - 增量评估计数器的差分测试（种子固定 20240917）。

在仓库根目录运行：
    py cpp/tests/diff_eval.py

覆盖内容：
  a) 复用 diff_forbidden.py 的 Engine 子进程封装（后台线程抽干 stdout）。
  b) 在测试内独立重算 Python 参考值：
     * 六类线型计数：行/列/两对角线的每条线，两端补 '2'，逐位置逐类匹配
       pattern 或其反转（同一位置同类只加一次）；
     * risk = Σ over board.get_black_groups() [气数==1]*4 + [气数==2]*1；
     * territory = len(board.get_dead_positions())；
     * packed 按 pack_score 规则重算。
  c) 随机自对弈 4 局（15x15 / 13x13 / 9x9 / 9x9+4 障碍）：每步引擎落子后发
     counters 与 eval，与 Python 从头重算逐项断言相等。
  d) 每局结束逐步 undo 到底，每一步 counters 与对应 Python 局面重算一致，
     且全部 undo 后 hash 回到初始值。
  e) 查询命令无副作用：同一局面连发两次 counters/eval/checkforbidden，
     两次输出完全相同，且 hash 不变。
  f) 末尾打印汇总与 PASS/FAIL，FAIL 时退出码 1。
"""
from __future__ import annotations

import os
import queue
import random
import subprocess
import sys
import threading

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CPP_DIR = os.path.dirname(SCRIPT_DIR)
REPO_ROOT = os.path.dirname(CPP_DIR)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from board import HybridBoard, EMPTY, BLACK, WHITE, OBSTACLE  # noqa: E402
import rules  # noqa: E402

ENGINE = os.path.join(CPP_DIR, "build", "engine.exe")

VERBOSE = "--verbose" in sys.argv or "-v" in sys.argv
READ_TIMEOUT = 60.0

# ----------------------------------------------------------------------------
# Python 参考实现
# ----------------------------------------------------------------------------
# 类别顺序：open_four / rush_four / open_three / sleep_three / open_two / sleep_two
PATTERNS = {
    0: ["011110"],
    1: ["211110", "11101", "11011"],
    2: ["011100", "011010"],
    3: ["211100", "211010", "210110", "2011102", "10101", "11001"],
    4: ["001100", "011000", "010100", "010010"],
    5: ["211000", "210100", "210010", "2011002", "2010102", "10001"],
}


def count_line(line: str) -> list:
    """按指令 2-4 的规则对一条线计数（两端补 4 个 '2'，位置×类别去重）。"""
    p = "2222" + line + "2222"
    out = [0] * 6
    for cls, pats in PATTERNS.items():
        for i in range(len(p)):
            hit = False
            for pat in pats:
                if p.startswith(pat, i) or p.startswith(pat[::-1], i):
                    hit = True
                    break
            if hit:
                out[cls] += 1
    return out


def iter_lines(board: HybridBoard):
    """枚举行 / 列 / 两对角方向的每条极大线（与 C++ 的 4 方向一致）。"""
    n = board.size
    for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
        for x in range(n):
            for y in range(n):
                if board.in_bounds(x - dx, y - dy):
                    continue
                cells = []
                cx, cy = x, y
                while board.in_bounds(cx, cy):
                    cells.append((cx, cy))
                    cx += dx
                    cy += dy
                yield cells


def ref_counts(board: HybridBoard):
    black = [0] * 6
    white = [0] * 6
    for cells in iter_lines(board):
        sb, sw = [], []
        for (x, y) in cells:
            v = int(board.grid[x, y])
            if v == BLACK:
                sb.append("1")
                sw.append("2")
            elif v == WHITE:
                sb.append("2")
                sw.append("1")
            elif v == OBSTACLE:
                sb.append("2")
                sw.append("2")
            else:
                sb.append("0")
                sw.append("0")
        cb = count_line("".join(sb))
        cw = count_line("".join(sw))
        for i in range(6):
            black[i] += cb[i]
            white[i] += cw[i]
    return black, white


def ref_risk(board: HybridBoard) -> int:
    total = 0
    for _stones, liberties in board.get_black_groups():
        if len(liberties) == 1:
            total += 4
        elif len(liberties) == 2:
            total += 1
    return total


def ref_territory(board: HybridBoard) -> int:
    return len(board.get_dead_positions())


def ref_pack(black, risk, territory) -> int:
    F1 = min(black[0], 255)
    F2 = min(black[1], 255)
    F3 = min(black[2], 255)
    F4 = min(black[3] + black[4], 255)
    F5 = min(black[5], 255)
    F6 = 255 - min(risk, 255)
    F7 = 255 - min(territory, 255)
    F8 = 0
    return (F1 << 56) | (F2 << 48) | (F3 << 40) | (F4 << 32) | \
           (F5 << 24) | (F6 << 16) | (F7 << 8) | F8


def ref_all(board: HybridBoard):
    black, white = ref_counts(board)
    risk = ref_risk(board)
    terr = ref_territory(board)
    return black, white, risk, terr, ref_pack(black, risk, terr)


# ----------------------------------------------------------------------------
# 引擎交互（后台线程读 stdout，避免管道/缓冲死锁）
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
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        self.q: queue.Queue = queue.Queue()
        self.reader = threading.Thread(target=self._pump, daemon=True)
        self.reader.start()

    def _pump(self):
        try:
            for line in self.p.stdout:
                self.q.put(line.rstrip("\r\n"))
        except Exception:
            pass
        self.q.put(None)

    def send(self, cmd: str) -> None:
        self.p.stdin.write(cmd + "\n")
        self.p.stdin.flush()

    def readline(self) -> str:
        try:
            line = self.q.get(timeout=READ_TIMEOUT)
        except queue.Empty:
            raise RuntimeError("engine did not respond within %.0fs" % READ_TIMEOUT)
        if line is None:
            raise RuntimeError("engine closed its stdout unexpectedly")
        return line

    def close(self) -> None:
        try:
            self.send("quit")
            self.p.wait(timeout=10)
        except Exception:
            try:
                self.p.kill()
            except Exception:
                pass


# ----------------------------------------------------------------------------
# 局面 / 命令解析
# ----------------------------------------------------------------------------
class Stats:
    def __init__(self):
        self.steps = 0
        self.checks = 0
        self.failures = 0

    def fail(self, msg):
        self.failures += 1
        print("  [FAIL] " + msg)


def parse_counters(line: str):
    # cnt b=a,b,c,d,e,f w=... risk=R terr=T
    parts = line.split()
    if not parts or parts[0] != "cnt":
        return None
    b = [int(v) for v in parts[1][2:].split(",")]
    w = [int(v) for v in parts[2][2:].split(",")]
    risk = int(parts[3].split("=")[1])
    terr = int(parts[4].split("=")[1])
    return b, w, risk, terr


def parse_eval(line: str):
    # eval <packed> F1=.. F2=.. F3=.. F4=.. F5=.. risk=.. terr=..
    parts = line.split()
    if not parts or parts[0] != "eval":
        return None
    packed = int(parts[1])
    return packed


def load_position(eng: Engine, board: HybridBoard) -> None:
    eng.send("size %d" % board.size)
    eng.send("clear")
    for x in range(board.size):
        for y in range(board.size):
            v = int(board.grid[x, y])
            if v == BLACK:
                eng.send("set %d %d b" % (x, y))
            elif v == WHITE:
                eng.send("set %d %d w" % (x, y))
            elif v == OBSTACLE:
                eng.send("set %d %d o" % (x, y))


def check_state(eng: Engine, board: HybridBoard, stats: Stats, tag: str) -> None:
    black, white, risk, terr, packed = ref_all(board)

    eng.send("counters")
    cline = eng.readline()
    got = parse_counters(cline)
    if got is None:
        stats.fail("%s: bad counters line %r" % (tag, cline))
        return
    gb, gw, grisk, gterr = got
    if gb != black:
        stats.fail("%s: black counts engine=%s python=%s" % (tag, gb, black))
    if gw != white:
        stats.fail("%s: white counts engine=%s python=%s" % (tag, gw, white))
    if grisk != risk:
        stats.fail("%s: risk engine=%d python=%d" % (tag, grisk, risk))
    if gterr != terr:
        stats.fail("%s: territory engine=%d python=%d" % (tag, gterr, terr))

    eng.send("eval")
    eline = eng.readline()
    gpacked = parse_eval(eline)
    if gpacked != packed:
        stats.fail("%s: packed engine=%d python=%d" % (tag, gpacked, packed))
    stats.checks += 1


def check_dump(eng: Engine, board: HybridBoard, stats: Stats, tag: str) -> None:
    eng.send("dump")
    rows = [eng.readline() for _ in range(board.size)]
    for x in range(board.size):
        for y in range(board.size):
            if int(rows[x][y]) != int(board.grid[x, y]):
                stats.fail("%s: dump mismatch (%d,%d) engine=%s python=%d"
                           % (tag, x, y, rows[x][y], int(board.grid[x, y])))
                return


# ----------------------------------------------------------------------------
# 单局自对弈 + 逐步 undo
# ----------------------------------------------------------------------------
def play_game(eng: Engine, rng: random.Random, size: int, obstacles: list,
              max_steps: int, stats: Stats, label: str) -> None:
    board = HybridBoard(size)
    for (x, y) in obstacles:
        board.grid[x, y] = OBSTACLE

    load_position(eng, board)
    eng.send("hash")
    initial_hash = eng.readline()
    check_dump(eng, board, stats, "%s load" % label)
    check_state(eng, board, stats, "%s initial" % label)

    states = [board.copy()]
    moves = []  # (color, x, y)

    for step in range(max_steps):
        empties = [(x, y) for x in range(size) for y in range(size)
                   if board.grid[x, y] == EMPTY]
        if not empties:
            break
        color = board.turn
        chosen = None
        if color == BLACK:
            order = empties[:]
            rng.shuffle(order)
            for (x, y) in order:
                if not rules.is_black_legal_move(board, x, y)[0]:
                    continue
                eng.send("move %d %d b" % (x, y))
                if eng.readline() == "ok":
                    chosen = (x, y)
                    break
            if chosen is None:
                break
            board.play_black(*chosen)
        else:
            order = empties[:]
            rng.shuffle(order)
            for (x, y) in order:
                eng.send("move %d %d w" % (x, y))
                if eng.readline() == "ok":
                    chosen = (x, y)
                    break
            if chosen is None:
                break
            board.play_white(*chosen)

        moves.append((color, chosen[0], chosen[1]))
        states.append(board.copy())

        # 查询命令无副作用（每局抽查一次固定步）。
        if step == max_steps // 2:
            side_effect_check(eng, board, stats, "%s side-effect" % label)

        check_state(eng, board, stats, "%s step %d" % (label, step))
        stats.steps += 1

        if color == BLACK and board.check_black_five(chosen[0], chosen[1]):
            break

    check_dump(eng, board, stats, "%s final" % label)

    # ---- 逐步 undo 到底 ----
    for depth in range(len(moves), 0, -1):
        eng.send("undo")
        if eng.readline() != "ok":
            stats.fail("%s: undo failed at depth %d" % (label, depth))
            break
        check_state(eng, states[depth - 1], stats, "%s undo %d" % (label, depth))

    eng.send("hash")
    final_hash = eng.readline()
    if final_hash != initial_hash:
        stats.fail("%s: hash after full undo %s != initial %s"
                   % (label, final_hash, initial_hash))
    check_dump(eng, states[0], stats, "%s after-undo" % label)

    print("[%s] size=%d obstacles=%d moves=%d checks=%d"
          % (label, size, len(obstacles), len(moves), stats.checks))


def side_effect_check(eng: Engine, board: HybridBoard, stats: Stats,
                      tag: str) -> None:
    eng.send("hash")
    h0 = eng.readline()

    eng.send("counters")
    c1 = eng.readline()
    eng.send("counters")
    c2 = eng.readline()
    if c1 != c2:
        stats.fail("%s: counters changed between identical queries" % tag)

    eng.send("eval")
    e1 = eng.readline()
    eng.send("eval")
    e2 = eng.readline()
    if e1 != e2:
        stats.fail("%s: eval changed between identical queries" % tag)

    outs = []
    for _ in range(2):
        eng.send("checkforbidden")
        lines = []
        while True:
            ln = eng.readline()
            if ln == "end":
                break
            lines.append(ln)
        outs.append(lines)
    if outs[0] != outs[1]:
        stats.fail("%s: checkforbidden changed between identical queries" % tag)

    eng.send("hash")
    h1 = eng.readline()
    if h0 != h1:
        stats.fail("%s: hash changed by query commands (%s -> %s)" % (tag, h0, h1))

    # 顺便验证查询后 counters 仍与 Python 一致。
    check_state(eng, board, stats, tag + " post-query")


# ----------------------------------------------------------------------------
def main() -> int:
    rng = random.Random(20240917)
    stats = Stats()

    games = [
        ("15x15", 15, []),
        ("13x13", 13, []),
        ("9x9", 9, []),
    ]
    # 9x9 带 4 个障碍（用固定种子随机挑选空格）。
    obs = []
    guard = 0
    while len(obs) < 4 and guard < 10000:
        guard += 1
        x, y = rng.randrange(9), rng.randrange(9)
        if (x, y) not in obs:
            obs.append((x, y))
    games.append(("9x9+obs", 9, obs))

    eng = Engine()
    try:
        for (label, size, obstacles) in games:
            play_game(eng, rng, size, obstacles, 48, stats, label)
    finally:
        eng.close()

    print("=" * 64)
    print("自对弈步数=%d  计数器断言=%d  失败=%d"
          % (stats.steps, stats.checks, stats.failures))
    if stats.failures:
        print("FAIL")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
