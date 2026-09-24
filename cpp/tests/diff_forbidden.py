#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
diff_forbidden.py - 黑棋禁手判定的差分测试。

在仓库根目录运行：
    py cpp/tests/diff_forbidden.py

流程：
  1. 子进程启动 cpp/build/engine.exe（stdout 用后台线程持续抽干，避免管道死锁），
     逐行写命令、逐行读结果。
  2. 用 Python 的 board.HybridBoard + rules.is_black_legal_move 生成随机局面
     （随机自对弈 + 少量随机泼洒以覆盖无气点/密集棋形），另加 5 个构造局面，
     累计 >= 60 个局面。
  3. 把每个局面的所有子写入引擎，调 checkforbidden，与 Python 逐点比较。
  4. 断言：occupied/自杀/成五/长连类不一致 == 0。三三/四四类不一致逐个复核并
     归因，只允许两类 Rapfi 语义差异：
       (i)  Rapfi 判定某方向不是活三 / 无法延伸成活四或成五（Python 却把它算成
            了一个三），即“三不能延伸”；
       (ii) 三的延伸点（或四的补五点）本身是禁手/自杀点。
     归因逻辑在 Python 里独立重实现了 Rapfi 的线型 DP（见 RapfiPattern），
     不依赖引擎的自述。无法归因则退出码 1。
  5. make/undo 一致性：200 步对局每 20 步记录引擎 Zobrist，全部 undo 后与初始
     一致；中途 10 个时刻与 Python 网格比对。
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

from board import HybridBoard, EMPTY, BLACK, WHITE, OBSTACLE, DIRECTIONS  # noqa: E402
import rules  # noqa: E402

ENGINE = os.path.join(CPP_DIR, "build", "engine.exe")

VERBOSE = "--verbose" in sys.argv or "-v" in sys.argv
READ_TIMEOUT = 30.0


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
            try:
                self.p.kill()
            except Exception:
                pass


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
            (x, y) for x in range(size) for y in range(size)
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
    """随机泼洒棋子/障碍，快速制造无气点、密集棋形、接近五连。"""
    size = rng.choice([9, 11, 13, 15, 15, 19])
    b = HybridBoard(size)
    density = rng.uniform(0.08, 0.24)
    for x in range(size):
        for y in range(size):
            r = rng.random()
            if r < density * 0.55:
                b.grid[x, y] = BLACK
            elif r < density:
                b.grid[x, y] = WHITE
            elif r < density + 0.02:
                b.grid[x, y] = OBSTACLE
    snapshots.append(b)


def random_dead_position(rng: random.Random, snapshots: list) -> None:
    """构造一个必定含无气点的局面：中心空点四邻皆黑，黑十字的其余气被白子封死。"""
    for _ in range(50):
        size = rng.choice([11, 13, 15, 19])
        b = HybridBoard(size)
        x = rng.randrange(2, size - 2)
        y = rng.randrange(2, size - 2)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            b.grid[x + dx, y + dy] = BLACK
        for dx, dy in ((2, 0), (-2, 0), (0, 2), (0, -2),
                       (1, 1), (1, -1), (-1, 1), (-1, -1)):
            b.grid[x + dx, y + dy] = WHITE
        # 再随机泼一点棋子（不含障碍，避免破坏死点判定）。
        for _ in range(rng.randint(0, 8)):
            cx, cy = rng.randrange(size), rng.randrange(size)
            if b.grid[cx, cy] == EMPTY:
                b.grid[cx, cy] = rng.choice([BLACK, WHITE])
        if b.is_empty(x, y) and b.would_self_capture(x, y):
            snapshots.append(b)
            return


def build_positions(rng: random.Random) -> list:
    snaps: list = []
    guard = 0
    while len(snaps) < 45 and guard < 4000:
        guard += 1
        random_selfplay(rng, snaps)
    for _ in range(12):
        random_scatter(rng, snaps)
    for _ in range(6):
        random_dead_position(rng, snaps)
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
    #    竖向延伸点被白棋占住，都不构成真活三（不应按三三禁手处理）。
    out.append(board_from_cells([
        (7, 4, "#"), (7, 5, "X"), (7, 6, "X"),
        (5, 7, "X"), (6, 7, "X"), (8, 7, "O"),
    ]))
    return out


# ----------------------------------------------------------------------------
# Rapfi 线型 DP 的 Python 独立重实现（仅用于归因，不依赖引擎）
# ----------------------------------------------------------------------------
DEAD, OL, B1, F1, B2, F2, F2A, F2B, B3, B3S, F3, F3S, B4, B4S, F4, F5 = range(16)
P4_NONE, FORBID, L_FLEX2, K_BLOCK3, J_FLEX2_2X, I_BLOCK3_PLUS, H_FLEX3, \
    G_FLEX3_PLUS, F_FLEX3_2X, E_BLOCK4, D_BLOCK4_PLUS, C_BLOCK4_FLEX3, \
    B_FLEX4, A_FIVE = range(14)

PAT_NAME = {
    DEAD: "DEAD", OL: "OL", B1: "B1", F1: "F1", B2: "B2", F2: "F2",
    F2A: "F2A", F2B: "F2B", B3: "B3", B3S: "B3S", F3: "F3", F3S: "F3S",
    B4: "B4", B4S: "B4S", F4: "F4", F5: "F5",
}
P4_NAME = {
    P4_NONE: "NONE", FORBID: "FORBID", L_FLEX2: "L_FLEX2", K_BLOCK3: "K_BLOCK3",
    J_FLEX2_2X: "J_FLEX2_2X", I_BLOCK3_PLUS: "I_BLOCK3_PLUS", H_FLEX3: "H_FLEX3",
    G_FLEX3_PLUS: "G_FLEX3_PLUS", F_FLEX3_2X: "F_FLEX3_2X", E_BLOCK4: "E_BLOCK4",
    D_BLOCK4_PLUS: "D_BLOCK4_PLUS", C_BLOCK4_FLEX3: "C_BLOCK4_FLEX3",
    B_FLEX4: "B_FLEX4", A_FIVE: "A_FIVE",
}

_SELF, _OPPO, _EMPT = 0, 1, 2
_H, _LEN, _MID = 5, 11, 5
_MEMO: dict = {}


def _count_line(line):
    real_len, full_len, inc = 1, 1, 1
    start = end = _MID
    for i in range(_MID - 1, -1, -1):
        if line[i] == _SELF:
            real_len += inc
        elif line[i] == _OPPO:
            break
        else:
            inc = 0
        full_len += 1
        start = i
    inc = 1
    for i in range(_MID + 1, _LEN):
        if line[i] == _SELF:
            real_len += inc
        elif line[i] == _OPPO:
            break
        else:
            inc = 0
        full_len += 1
        end = i
    return real_len, full_len, start, end


def _shift(line, i):
    return [line[j + i - _MID] if 0 <= j + i - _MID < _LEN else _OPPO
            for j in range(_LEN)]


def pattern_of(line):
    key = tuple(line)
    got = _MEMO.get(key)
    if got is not None:
        return got
    real_len, full_len, start, end = _count_line(line)
    if real_len >= 6:
        p = OL
    elif real_len >= 5:
        p = F5
    elif full_len < 5:
        p = DEAD
    else:
        cnt = [0] * 16
        f5_idx = [0, 0]
        for i in range(start, end + 1):
            if line[i] != _EMPT:
                continue
            sl = _shift(line, i)
            sl[_MID] = _SELF
            sp = pattern_of(sl)
            if sp == F5 and cnt[F5] < 2:
                f5_idx[cnt[F5]] = i
            cnt[sp] += 1
        if cnt[F5] >= 2:
            p = F4
            if f5_idx[1] - f5_idx[0] < 5:
                p = OL
        elif cnt[F5] == 1:
            blocked = list(line)
            blocked[f5_idx[0]] = _OPPO
            p = B4S if pattern_of(blocked) >= B3 else B4
        elif cnt[F4] >= 2:
            p = F3S
        elif cnt[F4]:
            p = F3
        elif cnt[B4S]:
            p = B3S
        elif cnt[B4]:
            p = B3
        elif cnt[F3S] + cnt[F3] >= 4:
            p = F2B
        elif cnt[F3S] + cnt[F3] >= 3:
            p = F2A
        elif cnt[F3S] + cnt[F3]:
            p = F2
        elif cnt[B3] + cnt[B3S]:
            p = B2
        elif cnt[F2] + cnt[F2A] + cnt[F2B]:
            p = F1
        elif cnt[B2]:
            p = B1
        else:
            p = DEAD
    _MEMO[key] = p
    return p


def combine4_forbid(p1, p2, p3, p4):
    n = [0] * 16
    for p in (p1, p2, p3, p4):
        n[p] += 1
    n[B4] += n[B4S]
    n[B3] += n[B3S]
    if n[F5] >= 1:
        return A_FIVE
    if n[OL] >= 1:
        return FORBID
    if n[F4] + n[B4] >= 2:
        return FORBID
    if n[F3] + n[F3S] >= 2:
        return FORBID
    if n[B4] >= 2:
        return B_FLEX4
    if n[F4] >= 1:
        return B_FLEX4
    return P4_NONE


def cell_flag(board, x, y):
    """黑棋视角：白/障碍/棋盘外/无气点 -> 阻挡(OPPO)，空点 -> EMPT，黑子 -> SELF。"""
    if not board.in_bounds(x, y):
        return _OPPO
    v = int(board.grid[x, y])
    if v == BLACK:
        return _SELF
    if v in (WHITE, OBSTACLE):
        return _OPPO
    return _OPPO if board.would_self_capture(x, y) else _EMPT


def dir_pattern_py(board, x, y, dx, dy):
    line = [_EMPT] * _LEN
    for i in range(-_H, _H + 1):
        if i == 0:
            line[_MID] = _SELF
        else:
            line[i + _MID] = cell_flag(board, x + i * dx, y + i * dy)
    return pattern_of(line)


def pattern4_py(board, x, y):
    return combine4_forbid(*[dir_pattern_py(board, x, y, dx, dy)
                             for dx, dy in DIRECTIONS])


def ext_points(board, x, y, dx, dy, maxdist=4):
    """Rapfi 式：从落子点穿过连续黑子，两个方向遇到的第一个空点。"""
    out = []
    for sgn in (-1, 1):
        cx, cy = x, y
        for _ in range(maxdist):
            cx += sgn * dx
            cy += sgn * dy
            if not board.in_bounds(cx, cy):
                break
            v = int(board.grid[cx, cy])
            if v == EMPTY:
                out.append((cx, cy))
                break
            if v != BLACK:
                break
    return out


def rapfi_ext_verdict(board, x, y, dx, dy):
    """返回 'noext' | ('forbidden', e) | ('true', e)。"""
    exts = ext_points(board, x, y, dx, dy)
    if not exts:
        return "noext"
    for (ex, ey) in exts:
        if board.would_self_capture(ex, ey):
            continue
        board.grid[ex, ey] = BLACK
        try:
            p4 = pattern4_py(board, ex, ey)
            pc = dir_pattern_py(board, ex, ey, dx, dy)
        finally:
            board.grid[ex, ey] = EMPTY
        if p4 == B_FLEX4 or pc == F5:
            if not rules.is_black_legal_move(board, ex, ey)[0]:
                return ("forbidden", (ex, ey))
            return ("true", (ex, ey))
    return "noext"


def four_completion_status(board, x, y, dx, dy):
    """Rapfi 认为该方向是四时，检查其补五点：
    返回 ('ok',) 表示存在合法恰好成五的补点；('forbidden', e) 表示补点本身是禁手/
    长连/自杀；('none',) 表示找不到补点。"""
    saw_any = None
    for i in list(range(-4, 0)) + list(range(1, 5)):
        ex, ey = x + i * dx, y + i * dy
        if not board.in_bounds(ex, ey) or int(board.grid[ex, ey]) != EMPTY:
            continue
        board.grid[ex, ey] = BLACK
        try:
            run = board.black_run_length(ex, ey)
        finally:
            board.grid[ex, ey] = EMPTY
        if run == 5:
            return ("ok",)
        if run >= 5 and saw_any is None:
            saw_any = (ex, ey)
    if saw_any is not None:
        return ("forbidden", saw_any)
    return ("none",)


# ----------------------------------------------------------------------------
# 归因
# ----------------------------------------------------------------------------
def attribute(board, x, y, cat):
    """对 (x,y) 的不一致给出 Rapfi 语义理由列表；空列表表示无法归因。"""
    board.grid[x, y] = BLACK
    try:
        pats = [dir_pattern_py(board, x, y, dx, dy) for dx, dy in DIRECTIONS]
        reasons = []

        if cat in ("four_four", "cpp_stricter"):
            for d, (dx, dy) in enumerate(DIRECTIONS):
                if pats[d] not in (B4, B4S, F4):
                    continue
                if rules._four_sets(board, x, y, dx, dy):
                    continue  # Python 也认可这个四
                status = four_completion_status(board, x, y, dx, dy)
                if status[0] == "forbidden":
                    reasons.append(("four_completion_forbidden", d, status[1]))
                elif status[0] == "none":
                    reasons.append(("four_completion_missing", d))
                else:
                    reasons.append(("four_not_counted", d))

        for d, (dx, dy) in enumerate(DIRECTIONS):
            if not rules._three_sets(board, x, y, dx, dy, set()):
                continue
            if pats[d] not in (F3, F3S):
                reasons.append(("rapfi_dir_not_open_three", d, PAT_NAME[pats[d]]))
                continue
            v = rapfi_ext_verdict(board, x, y, dx, dy)
            if v == "noext":
                reasons.append(("no_live_extension", d))
            elif isinstance(v, tuple) and v[0] == "forbidden":
                reasons.append(("ext_point_forbidden", d, v[1]))
        return reasons
    finally:
        board.grid[x, y] = EMPTY


# ----------------------------------------------------------------------------
# 比较
# ----------------------------------------------------------------------------
HARD = {"three_three", "four_four", "cpp_stricter", "py_unknown"}
TRIVIAL = {"self_capture", "overline", "five"}


def categorize(board, x, y, py_ok, ftype):
    if not py_ok:
        return ftype or "py_unknown"
    if board.would_self_capture(x, y):
        return "self_capture"
    board.grid[x, y] = BLACK
    try:
        run = board.black_run_length(x, y)
    finally:
        board.grid[x, y] = EMPTY
    if run >= 6:
        return "overline"
    if run == 5:
        return "five"
    return "cpp_stricter"


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
            cat = categorize(b, x, y, ok, ftype)
            stats["mismatch_" + cat] = stats.get("mismatch_" + cat, 0) + 1
            details.append((b.copy(), x, y, py_bad, ftype, cat))


# ----------------------------------------------------------------------------
# make/undo 一致性
# ----------------------------------------------------------------------------
DUMP_STEPS = (7, 33, 61, 95, 120, 150, 170, 185, 195, 199)


def make_undo_test(eng: Engine, rng: random.Random) -> bool:
    ok_all = True
    size = 15
    b = HybridBoard(size)
    eng.send("size %d" % size)
    eng.send("clear")
    eng.send("hash")
    initial = eng.readline()

    applied = 0
    dumps_checked = 0
    for _ in range(200):
        empties = [
            (x, y) for x in range(size) for y in range(size)
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
            res = b.play_black(*mv)
        else:
            mv = rng.choice(empties)
            res = b.play_white(*mv)
        if not res[0]:
            continue
        eng.send("move %d %d %s" % (mv[0], mv[1], "b" if color == BLACK else "w"))
        if eng.readline() != "ok":
            print("[make/undo] engine rejected move %s" % (mv,))
            ok_all = False
            break
        applied += 1

        if applied % 20 == 0:
            eng.send("hash")
            eng.readline()

        if applied in DUMP_STEPS:
            eng.send("dump")
            grid = []
            for _ in range(size):
                row = eng.readline()
                grid.append([int(row[y]) for y in range(size)])
            dumps_checked += 1
            for x in range(size):
                for y in range(size):
                    if grid[x][y] != int(b.grid[x, y]):
                        print("[make/undo] dump mismatch step %d cell (%d,%d): "
                              "engine=%d python=%d"
                              % (applied, x, y, grid[x][y], int(b.grid[x, y])))
                        ok_all = False

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
        if eng.readline() != "0" * size:
            print("[make/undo] board row %d not empty after undo" % x)
            ok_all = False

    print("[make/undo] applied=%d dumps_checked=%d initial=%s final=%s"
          % (applied, dumps_checked, initial, final))
    return ok_all


# ----------------------------------------------------------------------------
def print_board(b):
    chars = {EMPTY: ".", BLACK: "X", WHITE: "O", OBSTACLE: "#"}
    for x in range(b.size):
        print("    " + "".join(chars[int(b.grid[x, y])] for y in range(b.size)))


def main() -> int:
    rng = random.Random(20240917)
    positions = build_positions(rng)
    stats = {"points": 0, "agree": 0, "agree_forbidden": 0}
    details: list = []

    eng = Engine()
    try:
        for b in positions:
            compare(eng, b, stats, details)
    finally:
        eng.close()

    # 统计有多少局面含无气点，验证覆盖度。
    dead_positions = 0
    for b in positions:
        if any(b.is_empty(x, y) and b.would_self_capture(x, y)
               for x in range(b.size) for y in range(b.size)):
            dead_positions += 1

    print("=" * 72)
    print("局面数: %d (含无气点局面: %d)  比较空点数: %d  一致: %d (禁手/非法 %d)"
          % (len(positions), dead_positions, stats["points"], stats["agree"],
             stats["agree_forbidden"]))

    trivial_cats = sorted(k for k in stats
                          if k.startswith("mismatch_") and k[9:] in TRIVIAL)
    hard_cats = sorted(k for k in stats
                       if k.startswith("mismatch_") and k[9:] in HARD)
    for k in trivial_cats:
        print("  [硬性不一致] %-16s %d" % (k[9:], stats[k]))
    for k in hard_cats:
        print("  [需归因]     %-16s %d" % (k[9:], stats[k]))

    # 逐条归因。
    reason_counts: dict = {}
    unattributed = []
    for (b, x, y, py_bad, ftype, cat) in details:
        if cat not in HARD:
            continue
        reasons = attribute(b, x, y, cat)
        if reasons:
            r = reasons[0][0]
            reason_counts[r] = reason_counts.get(r, 0) + 1
            if VERBOSE:
                print("  [归因] (%d,%d) %s -> %s" % (x, y, cat, reasons))
        else:
            unattributed.append((b, x, y, cat, ftype))
            print("  [无法归因] (%d,%d) cat=%s py_type=%s" % (x, y, cat, ftype))
            if VERBOSE:
                print_board(b)

    print("-" * 72)
    print("硬性不一致(自杀/长连/成五/占用) = %d"
          % sum(stats.get(k, 0) for k in trivial_cats))
    for r in sorted(reason_counts):
        print("  归因[%s] = %d" % (r, reason_counts[r]))
    print("已归因 = %d" % sum(reason_counts.values()))
    print("无法归因不一致 = %d" % len(unattributed))
    print("=" * 72)

    make_undo_ok = False
    eng2 = Engine()
    try:
        make_undo_ok = make_undo_test(eng2, random.Random(7))
    finally:
        eng2.close()

    if sum(stats.get(k, 0) for k in trivial_cats) != 0:
        print("FAIL: 存在自杀/长连/成五/占用类不一致")
        return 1
    if unattributed:
        print("FAIL: 存在无法归因的禁手判定差异")
        return 1
    if not make_undo_ok:
        print("FAIL: make/undo 一致性未通过")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
