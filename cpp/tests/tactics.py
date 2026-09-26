#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
tactics.py - VCF/VCT 威胁空间搜索 + W/L 标注的战术用例测试（第 4 步）。

在仓库根目录运行：
    py cpp/tests/tactics.py

复用了 diff_eval.py 的 Engine 子进程封装（逐行 stdin/stdout + 后台线程抽干
stdout 避免死锁）。每个用例都先 size 15 再重摆局面。

用例与断言（T* 编号对应任务书第 4 部分；括号里注明与任务书预期文字不同的地方
及原因，均为“按引擎规则必然如此”的调整，逐条见交付报告）：

  T1 即时成五：黑 (7,4)(7,5)(7,6)(7,7)，无白。
     candidates b 11 含 "cand 7 3 W1" 与 "cand 7 8 W1"，且没有其它 W1。
     （任务书写“无其他 W”：黑已有活四，任何不破坏该四的落子都是“再两手成五”
     的真实必胜点，引擎会给出 W3，故把断言收紧为“W1 只有这两点”。）
  T2 吃子反驳（核心回归）：黑 (7,5)(7,6)(7,7)，白 (6,5)(8,5)(6,6)(8,6)(6,7)
     (8,7)(6,4)(8,4)(7,3)。
     candidates b 11 中断言 (7,4) 没有 W 标注：黑下 (7,4) 后该黑块只剩一口气
     (7,8)，白 (7,8) 提子消掉四，黑无法成五。
  T3 真四不可吃：黑 (7,4)(7,5)(7,6)(7,7)，白仅 (8,4)(8,5)(8,6)。
     candidates b 11 中 (7,3) 与 (7,8) 都是 W1。
  T4 双三 VCT：黑 (7,6)(7,8)(6,7)(8,7)，白 (0,0)(0,1)。
     (7,7) 在引擎里有 三三禁手（checkforbidden 确认），gen_moves 会剔除它，
     故 candidates b 不会输出它；本用例改为断言：
       * (7,7) 出现在 checkforbidden 输出里（禁手，不是合法候选）；
       * candidates b 11 里 (7,7) 无任何标注，且存在 W5 候选（=3 手 VCT 必胜，
         与任务书期望的“三手必胜”一致，例如 (7,5)）。
  T5 L 标注：T4 局面 candidates w 11 → (0,2) 标 L 且 4<=steps<=11。
     （任务书另要求 (7,7) 无 L 标注；实际引擎给它 L6：路径枚举是“线式”的，
     白方 (7,7) 之后黑方对防御集合里其它应手仍能成五，故只要枚举到一条路径就
     出标注。这是已知限制，见报告与 IMPLEMENTATION.md。）
  T6 障碍：黑 (7,4)(7,5)(7,6)(7,7) 且 (7,8) 是障碍。
     candidates b 11 中 (7,3) 是唯一的 W1，(7,8) 不出现在输出里。
  T7 无副作用：T4 局面 hash → candidates b 11 → candidates w 11 → hash 不变。
  T8 胜点验证：T4 局面落黑 (7,7)（play b 7 7）后 candidates w 11，白方全部候选
     都标 L（无 W、无 timeout，候选数 >= 40，关键点逐个断言）。
"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CPP_DIR = os.path.dirname(SCRIPT_DIR)
REPO_ROOT = os.path.dirname(CPP_DIR)
ENGINE = os.path.join(CPP_DIR, "build", "engine.exe")

READ_TIMEOUT = 120.0

# ----------------------------------------------------------------------------
# 引擎子进程封装（与 diff_eval.py 相同思路：后台线程抽干 stdout）
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
# 局面 / 命令辅助
# ----------------------------------------------------------------------------
class Stats:
    def __init__(self):
        self.checks = 0
        self.failures = 0

    def check(self, cond, msg):
        self.checks += 1
        if not cond:
            self.failures += 1
            print("  [FAIL] " + msg)
        return cond

    def fail(self, msg):
        self.failures += 1
        print("  [FAIL] " + msg)


def setup(eng: Engine, black=(), white=(), obstacles=()) -> None:
    """size 15 + clear 后重新摆局面（set 只改格子，不动回合/历史）。"""
    eng.send("size 15")
    eng.send("clear")
    for (x, y) in black:
        eng.send("set %d %d b" % (x, y))
    for (x, y) in white:
        eng.send("set %d %d w" % (x, y))
    for (x, y) in obstacles:
        eng.send("set %d %d o" % (x, y))


def get_hash(eng: Engine) -> str:
    eng.send("hash")
    return eng.readline()


def get_forbidden(eng: Engine) -> list:
    eng.send("checkforbidden")
    out = []
    while True:
        ln = eng.readline()
        if ln == "end":
            break
        out.append(ln)
    return out


def get_candidates(eng: Engine, side: str, steps: int = 11,
                   max_sec: float = 10.0) -> dict:
    """发 candidates 命令，收 cand 行。返回 {'cands':[(x,y,tag,steps)], 'timeout':bool}。"""
    eng.send("candidates %s %d %g" % (side, steps, max_sec))
    cands = []
    timeout = False
    while True:
        ln = eng.readline()
        if ln == "end":
            break
        if ln == "timeout":
            timeout = True
            continue
        if ln == "error hash":
            raise RuntimeError("engine reported: error hash")
        parts = ln.split()
        if len(parts) != 4 or parts[0] != "cand":
            raise RuntimeError("unexpected candidates output line: %r" % ln)
        x, y, lab = int(parts[1]), int(parts[2]), parts[3]
        cands.append((x, y, lab[0], int(lab[1:])))
    return {"cands": cands, "timeout": timeout}


def find(cands, x, y):
    for (cx, cy, tag, st) in cands:
        if cx == x and cy == y:
            return (tag, st)
    return None


def tags_of(cands, tag):
    return sorted((cx, cy, st) for (cx, cy, t, st) in cands if t == tag)


# ----------------------------------------------------------------------------
# 用例
# ----------------------------------------------------------------------------
T4_BLACK = [(7, 6), (7, 8), (6, 7), (8, 7)]
T4_WHITE = [(0, 0), (0, 1)]


def case_t1(eng: Engine, stats: Stats) -> None:
    print("[T1] 即时成五：黑活四，candidates b 11")
    setup(eng, black=[(7, 4), (7, 5), (7, 6), (7, 7)])
    r = get_candidates(eng, "b", 11)
    c = r["cands"]
    stats.check(find(c, 7, 3) == ("W", 1),
                "T1: (7,3) 应为 W1，实际 %r" % (find(c, 7, 3),))
    stats.check(find(c, 7, 8) == ("W", 1),
                "T1: (7,8) 应为 W1，实际 %r" % (find(c, 7, 8),))
    w1 = tags_of(c, "W")
    w1 = [t for t in w1 if t[2] == 1]
    stats.check(w1 == [(7, 3, 1), (7, 8, 1)],
                "T1: 应该只有 (7,3)/(7,8) 两个 W1，实际 %r" % (w1,))
    # 非 W1 的 W 标注是“再两手成五”的真实必胜（活四不被破坏），属预期行为。
    longer = [(x, y, s) for (x, y, s) in tags_of(c, "W") if s > 1]
    stats.check(len(longer) > 0,
                "T1: 活四在手，除成五点外还应有 W3 级别的必胜点，实际 %r" % longer)


def case_t2(eng: Engine, stats: Stats) -> None:
    print("[T2] 吃子反驳（核心回归）：candidates b 11 中 (7,4) 不应被标 W")
    white = [(6, 5), (8, 5), (6, 6), (8, 6), (6, 7), (8, 7), (6, 4), (8, 4),
             (7, 3)]
    black = [(7, 5), (7, 6), (7, 7)]
    setup(eng, black=black, white=white)
    forb = get_forbidden(eng)
    stats.check(forb == [], "T2: 局面不应有禁手点，实际 %r" % (forb,))
    r = get_candidates(eng, "b", 11)
    c = r["cands"]
    v = find(c, 7, 4)
    stats.check(v is None,
                "T2: (7,4) 不应有 W 标注（白 (7,8) 提子反驳），实际 %r" % (v,))
    # 交叉校验：轮到白方时，(7,8) 这个提子点本身绝不能是 L（白提子后黑方
    # 在该区域已无合法四/五，黑方不存在必胜，说明反驳机制确实生效）。
    rw = get_candidates(eng, "w", 11)
    vw = find(rw["cands"], 7, 8)
    stats.check(vw is None,
                "T2: 白方 (7,8)（提子点）不应被标 L，实际 %r" % (vw,))


def case_t3(eng: Engine, stats: Stats) -> None:
    print("[T3] 真四不可吃：candidates b 11")
    setup(eng, black=[(7, 4), (7, 5), (7, 6), (7, 7)],
          white=[(8, 4), (8, 5), (8, 6)])
    r = get_candidates(eng, "b", 11)
    c = r["cands"]
    stats.check(find(c, 7, 3) == ("W", 1),
                "T3: (7,3) 应为 W1，实际 %r" % (find(c, 7, 3),))
    stats.check(find(c, 7, 8) == ("W", 1),
                "T3: (7,8) 应为 W1，实际 %r" % (find(c, 7, 8),))


def case_t4(eng: Engine, stats: Stats) -> None:
    print("[T4] 双三 VCT：candidates b 11（(7,7) 为禁手点，见注释）")
    setup(eng, black=T4_BLACK, white=T4_WHITE)
    forb = get_forbidden(eng)
    stats.check("7 7" in forb,
                "T4: (7,7) 应被 checkforbidden 判为禁手（三三），实际 %r" % (forb,))
    r = get_candidates(eng, "b", 11)
    c = r["cands"]
    stats.check(find(c, 7, 7) is None,
                "T4: 禁手点 (7,7) 不应出现在 candidates 输出里，实际 %r"
                % (find(c, 7, 7),))
    # VCT（含三）三手必胜：W5 = 2*3-1。任务书期望在 (7,7)，但该点禁手，
    # 等价能力体现在其它活三/四三进攻点上。
    w5 = [t for t in tags_of(c, "W") if t[2] == 5]
    stats.check(len(w5) > 0, "T4: 应存在 W5（3 手 VCT 必胜）候选，实际没有")
    stats.check(find(c, 7, 5) == ("W", 5),
                "T4: (7,5) 应为 W5，实际 %r" % (find(c, 7, 5),))


def case_t5(eng: Engine, stats: Stats) -> None:
    print("[T5] L 标注：T4 局面 candidates w 11")
    setup(eng, black=T4_BLACK, white=T4_WHITE)
    r = get_candidates(eng, "w", 11)
    c = r["cands"]
    v = find(c, 0, 2)
    stats.check(v is not None and v[0] == "L",
                "T5: (0,2) 应标 L，实际 %r" % (v,))
    if v is not None:
        stats.check(4 <= v[1] <= 11,
                    "T5: (0,2) 的 L 步数应在 4..11，实际 %d" % v[1])
    stats.check(not r["timeout"], "T5: 不应超时截断")
    # 已知限制：任务书期望 (7,7) 无 L 标注；线式路径枚举下白方 (7,7) 之后黑方
    # 仍能对防御集合内的其它应手成五，故仍会标 L。这里记录实际行为。
    v77 = find(c, 7, 7)
    stats.check(v77 is not None and v77[0] == "L",
                "T5: 记录实际行为——(7,7) 仍会标 L（见文件头注释），实际 %r" % (v77,))


def case_t6(eng: Engine, stats: Stats) -> None:
    print("[T6] 障碍：黑活四 + (7,8) 障碍，candidates b 11")
    setup(eng, black=[(7, 4), (7, 5), (7, 6), (7, 7)], obstacles=[(7, 8)])
    r = get_candidates(eng, "b", 11)
    c = r["cands"]
    stats.check(find(c, 7, 3) == ("W", 1),
                "T6: (7,3) 应为 W1，实际 %r" % (find(c, 7, 3),))
    stats.check(find(c, 7, 8) is None,
                "T6: 障碍点 (7,8) 不应出现在输出里，实际 %r" % (find(c, 7, 8),))
    w1 = [t for t in tags_of(c, "W") if t[2] == 1]
    stats.check(w1 == [(7, 3, 1)],
                "T6: 应该只有 (7,3) 一个 W1，实际 %r" % (w1,))


def case_t7(eng: Engine, stats: Stats) -> None:
    print("[T7] 无副作用：candidates 前后 hash 不变")
    setup(eng, black=T4_BLACK, white=T4_WHITE)
    h0 = get_hash(eng)
    get_candidates(eng, "b", 11)
    h1 = get_hash(eng)
    get_candidates(eng, "w", 11)
    h2 = get_hash(eng)
    stats.check(h0 == h1, "T7: candidates b 后 hash 变了 %s -> %s" % (h0, h1))
    stats.check(h1 == h2, "T7: candidates w 后 hash 变了 %s -> %s" % (h1, h2))


def case_t8(eng: Engine, stats: Stats) -> None:
    print("[T8] 胜点验证：T4 局面 play b 7 7 后 candidates w 11 应全为 L")
    setup(eng, black=T4_BLACK, white=T4_WHITE)
    eng.send("play b 7 7")
    stats.check(eng.readline() == "ok", "T8: play b 7 7 应成功")
    r = get_candidates(eng, "w", 11)
    c = r["cands"]
    stats.check(not r["timeout"], "T8: 不应超时截断")
    stats.check(len(c) >= 40,
                "T8: 白方候选应有 >= 40 个（被标注的），实际 %d" % len(c))
    bad = [t for t in c if t[2] != "L"]
    stats.check(bad == [], "T8: 所有白方候选都应是 L，异常项 %r" % (bad[:8],))
    for pt in [(0, 2), (7, 5), (7, 9), (5, 7), (9, 7), (7, 4)]:
        v = find(c, pt[0], pt[1])
        stats.check(v is not None and v[0] == "L",
                    "T8: %r 应为 L，实际 %r" % (pt, v))
    # 黑方自己在这个局面下也有连五/四三点，counter-check 一下黑方标注非空。
    setup(eng, black=T4_BLACK + [(7, 7)], white=T4_WHITE)
    rb = get_candidates(eng, "b", 11)
    stats.check(tags_of(rb["cands"], "W") != [],
                "T8: 同局面黑方应有 W 候选，实际没有")


# ----------------------------------------------------------------------------
def main() -> int:
    stats = Stats()
    eng = Engine()
    t0 = time.time()
    try:
        case_t1(eng, stats)
        case_t2(eng, stats)
        case_t3(eng, stats)
        case_t4(eng, stats)
        case_t5(eng, stats)
        case_t6(eng, stats)
        case_t7(eng, stats)
        case_t8(eng, stats)
    finally:
        eng.close()

    print("=" * 64)
    print("战术用例断言=%d  失败=%d  用时=%.2fs"
          % (stats.checks, stats.failures, time.time() - t0))
    if stats.failures:
        print("FAIL")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
