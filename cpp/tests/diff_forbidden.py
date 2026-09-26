#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
diff_forbidden.py - 黑棋禁手判定的差分测试。

在仓库根目录运行：
    py cpp/tests/diff_forbidden.py

流程：
  1. 子进程启动 cpp/build/engine.exe（stdout 用后台线程持续抽干，绝不在别处
     重复读同一管道，避免管道 EOF/死锁），逐行写命令、逐行读结果。
  2. 用 Python 的 board.HybridBoard + rules.is_black_legal_move 生成随机局面
     （45 个随机自对弈快照 + 18 个随机泼洒 + 5 个构造局面 + 6 个含无气点局面），
     共 70+ 个局面，比较空点数与验收失败的版本一致或更多。
  3. 把每个局面的所有子写入引擎，调 checkforbidden，与 Python 逐点比较。
  4. 断言：occupied/自杀/成五/长连类不一致 == 0。三三/四四类不一致逐个复核并
     归因，只允许两类 Rapfi 语义差异：
       (i)  Rapfi 的线型 DP 判定该方向不是活三（眠三 B3/B3S 或四 B4S），或
            该方向无法延伸成活四/成五；
       (ii) 三的延伸点（或四的补五点）本身是禁手/长连/自杀点。
     归因逻辑在 Python 里独立重实现了 Rapfi 的线型 DP，不依赖引擎的自述。
     无法归因则退出码 1。
  5. make/undo 压力测试（见 make_undo_test）：200 步对局逐步记录 Zobrist，
     逐步 undo 检查哈希可逆；空历史 undo 必须 err；整局 make/undo 重复 3 轮；
     再做 300 步随机 make/undo 游走（乱序 undo 到任意深度）；最后全部 undo 后
     空盘且哈希回到初始值。关键步 dump 与 Python 网格比对。
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
    """随机泼洒棋子，快速制造无气点、密集棋形、接近五连。

    密度/数量与上一轮交付、验收失败的版本完全一致（density 0.10..0.32，
    18 个局面），保证比较范围没有被收窄。
    """
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
    """与失败验收完全相同的 45+18+5 个局面，另追加 6 个含无气点的局面。

    追加的 6 个局面在 rng 序列的最后生成，因此 45+18+5 个原始局面的
    随机序列与验收失败的版本逐位一致（比较范围只增不减）。
    """
    snaps: list = []
    guard = 0
    while len(snaps) < 45 and guard < 4000:
        guard += 1
        random_selfplay(rng, snaps)
    for _ in range(18):
        random_scatter(rng, snaps)
    snaps.extend(constructed_positions())
    for _ in range(6):
        random_dead_position(rng, snaps)
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
    """复算 Rapfi 第三条（真三）在该方向上的判定。

    返回 'noext'（没有任何延伸点能成为活四/成五）| ('forbidden', e)
    （能延伸，但该延伸点本身是禁手/长连/自杀）| ('true', e)（真正的活三）。

    Rapfi 只承认 p4c == B_FLEX4 或 pc == F5 的延伸点；这里额外记录
    “延伸点自己是禁手” 的细节，便于归因汇总打印。
    """
    exts = ext_points(board, x, y, dx, dy)
    if not exts:
        return "noext"
    forbidden_ext = None
    for (ex, ey) in exts:
        if board.would_self_capture(ex, ey):
            if forbidden_ext is None:
                forbidden_ext = (ex, ey)
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
        # 即使该点不能把本方向延伸成活四，它本身仍可能是四四/长连等禁手点。
        if p4 == FORBID or not rules.is_black_legal_move(board, ex, ey)[0]:
            if forbidden_ext is None:
                forbidden_ext = (ex, ey)
    if forbidden_ext is not None:
        return ("forbidden", forbidden_ext)
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
WALK_STEPS = 300
REPLAY_ROUNDS = 3


def _plan_game(rng: random.Random, size: int = 15, max_moves: int = 200) -> list:
    """用 Python 规则生成一局随机对局的落子序列（(color, x, y) 列表）。

    黑只走合法点（含禁手/自杀过滤），白走任意空点；黑连五即结束。
    序列显式携带颜色，重放时与引擎的回合推进一致。
    """
    b = HybridBoard(size)
    plan: list = []
    while len(plan) < max_moves:
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
        plan.append((color, mv[0], mv[1]))
    return plan


def make_undo_test(eng: Engine, rng: random.Random) -> bool:
    """make/undo 压力测试。

    覆盖上一轮验收暴露的崩溃路径：
      1. 200 步随机对局，每步记录引擎 Zobrist，关键步 dump 与 Python 网格比对；
      2. 逐步 undo 到空历史，每一步哈希必须回到上一步的值（逐步可逆）；
      3. 空历史 undo 必须回 err（历史栈不下溢）；
      4. 整局 make/undo 重复 REPLAY_ROUNDS 轮；
      5. 随机 make/undo 游走（乱序 undo 到任意深度再继续），哈希全程可逆；
      6. 全部 undo 后空盘、哈希回到初始值。
    """
    size = 15
    plan = _plan_game(rng, size)
    ok_all = True
    state = {"dumps": 0, "reply_bad": 0}

    b = HybridBoard(size)
    eng.send("size %d" % size)
    eng.send("clear")
    eng.send("hash")
    initial = eng.readline()

    def engine_hash() -> str:
        eng.send("hash")
        return eng.readline()

    def check_dump(label) -> None:
        nonlocal ok_all
        eng.send("dump")
        rows = [eng.readline() for _ in range(size)]
        state["dumps"] += 1
        for x in range(size):
            for y in range(size):
                if int(rows[x][y]) != int(b.grid[x, y]):
                    print("[make/undo] dump mismatch at %s cell (%d,%d): "
                          "engine=%d python=%d"
                          % (label, x, y, int(rows[x][y]), int(b.grid[x, y])))
                    ok_all = False

    def apply(pos: int) -> bool:
        """把 plan[pos] 同时落到 Python 盘与引擎；失败返回 False。"""
        nonlocal ok_all
        color, x, y = plan[pos]
        res = b.play_black(x, y) if color == BLACK else b.play_white(x, y)
        if not res[0]:
            print("[make/undo] python rejected planned move (%d,%d,%s)"
                  % (x, y, color))
            ok_all = False
            return False
        eng.send("move %d %d %s" % (x, y, "b" if color == BLACK else "w"))
        reply = eng.readline()
        if reply != "ok":
            print("[make/undo] engine rejected move (%d,%d,%s) -> %s"
                  % (x, y, color, reply))
            state["reply_bad"] += 1
            ok_all = False
            return False
        return True

    def undo_once() -> bool:
        nonlocal ok_all
        eng.send("undo")
        reply = eng.readline()
        if reply != "ok":
            print("[make/undo] undo failed -> %s" % reply)
            state["reply_bad"] += 1
            ok_all = False
            return False
        b.undo()
        return True

    # ---- 第 1 段：完整推进，逐步记录哈希，关键步 dump 比对 ----
    hashes = [initial]
    applied = 0
    for i in range(len(plan)):
        if not apply(i):
            break
        applied += 1
        hashes.append(engine_hash())
        if applied % 20 == 0 or applied in DUMP_STEPS:
            check_dump("applied=%d" % applied)

    # ---- 第 2 段：逐步 undo，哈希必须逐步可逆 ----
    for depth in range(applied, 0, -1):
        if not undo_once():
            break
        h = engine_hash()
        if h != hashes[depth - 1]:
            print("[make/undo] hash not reversible at depth %d: %s != %s"
                  % (depth, h, hashes[depth - 1]))
            ok_all = False

    if engine_hash() != initial:
        print("[make/undo] hash after full undo != initial")
        ok_all = False
    check_dump("empty-after-undo")

    # ---- 第 3 段：空历史 undo 必须 err（历史栈不下溢） ----
    for _ in range(3):
        eng.send("undo")
        if eng.readline() != "err":
            print("[make/undo] undo on empty history did not return err")
            ok_all = False
    if engine_hash() != initial:
        print("[make/undo] empty-history undo corrupted the hash")
        ok_all = False

    # ---- 第 4 段：整局 make/undo 重复多轮 ----
    for _round in range(REPLAY_ROUNDS):
        for i in range(len(plan)):
            if not apply(i):
                break
        for _ in range(len(plan)):
            if not undo_once():
                break
        if engine_hash() != initial:
            print("[make/undo] replay round %d: hash != initial after undo"
                  % _round)
            ok_all = False
        check_dump("replay-%d" % _round)

    # ---- 第 5 段：随机 make/undo 游走（乱序 undo 到任意深度再继续） ----
    known = {0: initial}
    pos = 0
    for _ in range(WALK_STEPS):
        grow = (pos == 0) or (pos < len(plan) and rng.random() < 0.55)
        if grow:
            if not apply(pos):
                break
            pos += 1
            known[pos] = engine_hash()
        else:
            if not undo_once():
                break
            pos -= 1
            h = engine_hash()
            if h != known[pos]:
                print("[make/undo] walk hash mismatch at depth %d: %s != %s"
                      % (pos, h, known[pos]))
                ok_all = False
                break
    # 走到历史尽头，确认空盘与初始哈希。
    while pos > 0:
        if not undo_once():
            break
        pos -= 1
    if engine_hash() != initial:
        print("[make/undo] walk: hash != initial after undoing everything")
        ok_all = False
    check_dump("walk-empty")

    # ---- 第 6 段：增量 Zobrist 必须等于“clear + set 重建”的哈希 ----
    # 走到轮到黑棋（turn 键两次异或抵消），此时增量维护的 hash 应与从头
    # 摆放同一局面的 hash 完全相同；这一条覆盖提子/还原路径的哈希更新。
    cnt = min(len(plan), 40)
    for i in range(cnt):
        if not apply(i):
            break
    if b.turn == WHITE and cnt < len(plan):
        apply(cnt)
    if b.turn == BLACK:
        incremental = engine_hash()
        eng.send("dump")
        rows = [eng.readline() for _ in range(size)]
        eng.send("clear")
        for x in range(size):
            for y in range(size):
                v = int(rows[x][y])
                if v == BLACK:
                    eng.send("set %d %d b" % (x, y))
                elif v == WHITE:
                    eng.send("set %d %d w" % (x, y))
                elif v == OBSTACLE:
                    eng.send("set %d %d o" % (x, y))
        rebuilt = engine_hash()
        if rebuilt != incremental:
            print("[make/undo] incremental hash %s != rebuilt hash %s"
                  % (incremental, rebuilt))
            ok_all = False

    print("[make/undo] plan=%d applied=%d dumps=%d bad_replies=%d "
          "initial=%s final=%s ok=%s"
          % (len(plan), applied, state["dumps"], state["reply_bad"],
             initial, initial, ok_all))
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
