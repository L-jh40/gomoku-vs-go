#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
search_sanity.py - alpha-beta 搜索的健全性测试（固定种子 20240917）。

在仓库根目录运行：
    py cpp/tests/search_sanity.py

覆盖（对应任务指令 16）：
  a) 自对弈：15x15 与 9x9(含 4 障碍) 各一局，双方 genmove depth4 max_sec 10，
     ≤120 步内正常终局或到步数上限；断言每一步引擎返回的着法合法
     （空点、不在引擎 checkforbidden 列表里；白方任意空点合法），且引擎
     接受该步（play 返回 ok）。用 Python HybridBoard 同步镜像局面。
  b) 无副作用：每局抽 10 个随机时刻，记录 genmove 前后的 Zobrist hash 并比对，
     同时 dump 棋盘与 Python 镜像比对（搜索不得留下测试棋子）。
  c) 确定性：固定 12 手序列的局面连续两次 genmove depth4，输出完全相同，
     且 hash 不变。
  d) 必胜立即执行：黑四连两头空，genmove 黑 depth2 必须在 1 秒内返回成五点。
  e) 救叫吃：黑块仅 1 气，genmove 黑 depth2 必须补气（或直接成五）。
  f) nps 报告：固定中局 genmove depth6 max_sec 30，记录完成深度、用时、节点数。
  g) 末尾 PASS/FAIL，FAIL 退出码 1。
"""
from __future__ import annotations

import os
import queue
import random
import subprocess
import sys
import threading
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CPP_DIR = os.path.dirname(SCRIPT_DIR)
REPO_ROOT = os.path.dirname(CPP_DIR)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from board import HybridBoard, EMPTY, BLACK, WHITE, OBSTACLE  # noqa: E402

ENGINE = os.path.join(CPP_DIR, "build", "engine.exe")
SEED = 20240917
READ_TIMEOUT = 180.0


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

    def hash(self) -> str:
        self.send("hash")
        return self.readline()

    def dump(self, size: int):
        self.send("dump")
        return [self.readline() for _ in range(size)]

    def forbidden(self) -> set:
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


class Checker:
    def __init__(self):
        self.failures = 0

    def check(self, cond, msg):
        if not cond:
            self.failures += 1
            print("  [FAIL] " + msg)
        return cond


def genmove(eng: Engine, color: str, depth: int, min_sec: float, max_sec: float):
    """返回 (info 行列表, 结果, 原始末行)；结果 = ('move',x,y) | ('pass',) | ('resign',)。"""
    eng.send("genmove %s %d %g %g" % (color, depth, min_sec, max_sec))
    infos = []
    while True:
        line = eng.readline()
        if line.startswith("info "):
            infos.append(line)
            continue
        if line.startswith("move "):
            parts = line.split()
            return infos, ("move", int(parts[1]), int(parts[2])), line
        if line in ("pass", "resign"):
            return infos, (line,), line
        raise RuntimeError("unexpected genmove output: %r" % line)


def load(eng: Engine, b: HybridBoard) -> None:
    eng.send("size %d" % b.size)
    eng.send("clear")
    for x in range(b.size):
        for y in range(b.size):
            v = int(b.grid[x, y])
            if v == BLACK:
                eng.send("set %d %d b" % (x, y))
            elif v == WHITE:
                eng.send("set %d %d w" % (x, y))
            elif v == OBSTACLE:
                eng.send("set %d %d o" % (x, y))


def check_dump(eng: Engine, b: HybridBoard, ck: Checker, tag: str) -> None:
    rows = eng.dump(b.size)
    for x in range(b.size):
        for y in range(b.size):
            if int(rows[x][y]) != int(b.grid[x, y]):
                ck.check(False, "%s: dump mismatch (%d,%d) engine=%s python=%d"
                         % (tag, x, y, rows[x][y], int(b.grid[x, y])))
                return


# ----------------------------------------------------------------------------
# a) + b) 自对弈
# ----------------------------------------------------------------------------
def white_has_won(b: HybridBoard) -> bool:
    """白方胜利条件（Python 规则口径，用于结束自对弈）。"""
    if not any(int(b.grid[x, y]) == BLACK
               for x in range(b.size) for y in range(b.size)):
        return True
    return b.white_wins_by_occupy() or b.white_wins_by_line_block()


def selfplay(eng: Engine, ck: Checker, rng, size: int, obstacles, depth: int,
             max_sec: float, max_steps: int, label: str) -> dict:
    b = HybridBoard(size)
    for (x, y) in obstacles:
        b.grid[x, y] = OBSTACLE
    load(eng, b)
    check_dump(eng, b, ck, "%s load" % label)

    checkpoints = set(rng.randrange(max_steps) for _ in range(10))
    stats = {"steps": 0, "hash_checks": 0, "dump_checks": 0,
             "pass": 0, "resign": 0, "ended": ""}
    for step in range(max_steps):
        if step > 0 and white_has_won(b):
            stats["ended"] = "white_win"
            break
        color = b.turn
        cs = "b" if color == BLACK else "w"

        forbidden = eng.forbidden() if color == BLACK else set()
        h0 = eng.hash()
        _infos, res, _raw = genmove(eng, cs, depth, 0.0, max_sec)
        h1 = eng.hash()

        # 搜索不得改变任何棋盘状态：每一步都比对 Zobrist，并在抽样的
        # 10 个随机时刻 + 每 10 步 dump 整盘与 Python 镜像比对。
        ck.check(h0 == h1, "%s step %d: genmove changed Zobrist (%s -> %s)"
                 % (label, step, h0, h1))
        stats["hash_checks"] += 1
        if step in checkpoints or step % 10 == 0:
            check_dump(eng, b, ck, "%s step %d post-genmove" % (label, step))
            stats["dump_checks"] += 1

        if res[0] == "resign":
            stats["resign"] += 1
            stats["ended"] = "resign"
            break
        if res[0] == "pass":
            stats["pass"] += 1
            stats["ended"] = "pass"
            break

        _, x, y = res
        if not ck.check(b.in_bounds(x, y) and int(b.grid[x, y]) == EMPTY,
                        "%s step %d: illegal move (%d,%d) on occupied/out cell"
                        % (label, step, x, y)):
            break
        if color == BLACK and not ck.check(
                (x, y) not in forbidden,
                "%s step %d: black move (%d,%d) is in engine forbidden list"
                % (label, step, x, y)):
            break

        eng.send("play %s %d %d" % (cs, x, y))
        reply = eng.readline()
        if not ck.check(reply == "ok",
                        "%s step %d: engine rejected %s (%d,%d) -> %s"
                        % (label, step, cs, x, y, reply)):
            break

        # Python 镜像：跳过 Rapfi/Python 有已知差异的禁手复核，保证与引擎同步。
        if color == BLACK:
            ok, _cap = b.play_black(x, y, check_rules=False)
        else:
            ok, _cap = b.play_white(x, y)
        if not ck.check(ok, "%s step %d: python mirror rejected (%d,%d)"
                        % (label, step, x, y)):
            break
        stats["steps"] += 1

        if color == BLACK and b.check_black_five(x, y):
            stats["ended"] = "black_five"
            break
    else:
        stats["ended"] = "step_cap"

    check_dump(eng, b, ck, "%s final" % label)
    print("[%s] size=%d obstacles=%d steps=%d ended=%s pass=%d resign=%d "
          "hash_checks=%d dump_checks=%d"
          % (label, size, len(obstacles), stats["steps"], stats["ended"],
             stats["pass"], stats["resign"], stats["hash_checks"],
             stats["dump_checks"]))
    return stats


# ----------------------------------------------------------------------------
# c) 确定性
# ----------------------------------------------------------------------------
SEQ12 = [
    ("b", 7, 7), ("w", 7, 8), ("b", 8, 8), ("w", 6, 6),
    ("b", 7, 6), ("w", 6, 8), ("b", 9, 7), ("w", 5, 7),
    ("b", 8, 6), ("w", 6, 7), ("b", 9, 9), ("w", 5, 5),
]


def determinism(eng: Engine, ck: Checker) -> None:
    eng.send("size 15")
    eng.send("clear")
    for (c, x, y) in SEQ12:
        eng.send("play %s %d %d" % (c, x, y))
        reply = eng.readline()
        if not ck.check(reply == "ok", "determinism: play %s (%d,%d) -> %s"
                        % (c, x, y, reply)):
            return
    h_before = eng.hash()
    infos1, res1, raw1 = genmove(eng, "b", 4, 0.0, 10.0)
    h_mid = eng.hash()
    infos2, res2, raw2 = genmove(eng, "b", 4, 0.0, 10.0)
    h_after = eng.hash()

    out1 = infos1 + [raw1]
    out2 = infos2 + [raw2]
    ck.check(out1 == out2, "determinism: outputs differ\n    run1=%s\n    run2=%s"
             % (out1, out2))
    ck.check(h_before == h_mid == h_after,
             "determinism: hash changed (%s -> %s -> %s)"
             % (h_before, h_mid, h_after))
    print("[determinism] depth4 两次输出一致=%s 末行=%s hash=%s"
          % (out1 == out2, raw1, h_before))


# ----------------------------------------------------------------------------
# d) 必胜立即执行
# ----------------------------------------------------------------------------
def immediate_win(eng: Engine, ck: Checker) -> None:
    b = HybridBoard(15)
    for (x, y) in [(7, 3), (7, 4), (7, 5), (7, 6)]:
        b.grid[x, y] = BLACK
    for (x, y) in [(0, 0), (0, 1), (0, 2), (0, 3), (0, 4), (0, 5)]:
        b.grid[x, y] = WHITE
    load(eng, b)

    t0 = time.time()
    _infos, res, raw = genmove(eng, "b", 2, 0.0, 1.0)
    dt = time.time() - t0
    ck.check(dt < 1.0, "immediate_win: took %.3fs (>= 1s)" % dt)
    if not ck.check(res[0] == "move", "immediate_win: no move (%s)" % (res,)):
        return
    _, x, y = res
    b.grid[x, y] = BLACK
    ck.check(b.black_run_length(x, y) == 5,
             "immediate_win: engine returned (%d,%d) which is not a five" % (x, y))
    print("[immediate_win] move=(%d,%d) run=%d elapsed=%.3fs raw=%s"
          % (x, y, b.black_run_length(x, y), dt, raw))


# ----------------------------------------------------------------------------
# e) 救叫吃
# ----------------------------------------------------------------------------
def save_atari(eng: Engine, ck: Checker) -> None:
    b = HybridBoard(15)
    for (x, y) in [(7, 7), (7, 8), (8, 7), (8, 8)]:
        b.grid[x, y] = BLACK
    for (x, y) in [(6, 7), (6, 8), (9, 7), (9, 8), (8, 6), (7, 9), (8, 9)]:
        b.grid[x, y] = WHITE
    liberty = (7, 6)
    load(eng, b)

    _stones, libs = b.get_group(*next(
        (x, y) for x in range(15) for y in range(15)
        if int(b.grid[x, y]) == BLACK))
    ck.check(sorted(libs) == [liberty],
             "save_atari: constructed liberty set %s != %s" % (libs, [liberty]))

    _infos, res, raw = genmove(eng, "b", 2, 0.0, 2.0)
    if not ck.check(res[0] == "move", "save_atari: no move (%s)" % (res,)):
        return
    _, x, y = res
    b.grid[x, y] = BLACK
    five = b.black_run_length(x, y) == 5
    ck.check((x, y) == liberty or five,
             "save_atari: engine played (%d,%d), not the liberty %s nor a five"
             % (x, y, liberty))
    print("[save_atari] liberty=%s move=(%d,%d) five=%s raw=%s"
          % (liberty, x, y, five, raw))


# ----------------------------------------------------------------------------
# f) nps 报告
# ----------------------------------------------------------------------------
SEQ_MID = [
    ("b", 7, 7), ("w", 7, 8), ("b", 8, 7), ("w", 6, 7),
    ("b", 7, 6), ("w", 8, 8), ("b", 9, 7), ("w", 6, 8),
    ("b", 8, 6), ("w", 6, 9),
]


def nps_report(eng: Engine, ck: Checker) -> dict:
    eng.send("size 15")
    eng.send("clear")
    for (c, x, y) in SEQ_MID:
        eng.send("play %s %d %d" % (c, x, y))
        reply = eng.readline()
        if not ck.check(reply == "ok", "nps: play %s (%d,%d) -> %s"
                        % (c, x, y, reply)):
            return {}
    t0 = time.time()
    infos, res, raw = genmove(eng, "b", 6, 0.0, 30.0)
    dt = time.time() - t0
    eng.send("searchstat")
    stat = eng.readline()
    nodes = int(stat.split()[2])
    completed = 0
    for ln in infos:
        p = ln.split()
        if p[0] == "info" and p[1] == "depth":
            completed = max(completed, int(p[2]))
    nps = nodes / dt if dt > 0 else 0.0
    ck.check(completed == 6, "nps: completed_depth=%d (expected 6) in %.1fs"
             % (completed, dt))
    print("[nps] fixed midgame depth6: completed_depth=%d elapsed=%.2fs "
          "nodes=%d nps=%.0f raw=%s" % (completed, dt, nodes, nps, raw))
    return {"completed_depth": completed, "elapsed": dt, "nodes": nodes,
            "nps": nps}


# ----------------------------------------------------------------------------
def main() -> int:
    rng = random.Random(SEED)
    ck = Checker()
    eng = Engine()
    t_start = time.time()
    try:
        print("=" * 72)
        print("search_sanity (seed=%d) engine=%s" % (SEED, ENGINE))
        print("-" * 72)
        selfplay(eng, ck, rng, 15, [], 4, 10.0, 120, "15x15")
        obs = []
        while len(obs) < 4:
            p = (rng.randrange(9), rng.randrange(9))
            if p not in obs:
                obs.append(p)
        selfplay(eng, ck, rng, 9, obs, 4, 10.0, 120, "9x9+obs")
        print("-" * 72)
        determinism(eng, ck)
        immediate_win(eng, ck)
        save_atari(eng, ck)
        nps_report(eng, ck)
        print("-" * 72)
    finally:
        eng.close()

    total = time.time() - t_start
    print("总用时 %.1fs  失败=%d" % (total, ck.failures))
    if ck.failures:
        print("FAIL")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
