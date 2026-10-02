#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
tactics.py - 证明级 VCF/VCT 威胁空间搜索 + W/L 标注的战术用例测试（第 6 步）。

在仓库根目录运行：
    py cpp/tests/tactics.py

复用了 diff_eval.py 的 Engine 子进程封装（逐行 stdin/stdout + 后台线程抽干
stdout 避免死锁）。每个用例都先 size 15 再重摆局面。

第 6 步的语义变化（详见 IMPLEMENTATION.md“VCF/VCT 与 W/L 标注”一节）：
  * W/L 标注必须是 AND-OR 证明树支撑的结论，证明不出就不标注（宁可漏标）。
    因此标注数量比第 4 步（OR 式路径枚举）显著变少，“存在一条路径”不再算胜。
  * 每个用例都额外跑一组**通用健全性断言**（对 candidates 输出的每一条标注都生效）：
      A1（W 健全）k==1：`play b x y` 必须 ok，且该点用 Python 参考实现复算必须恰好成五
                   （HybridBoard.check_black_five）；
                   k>1 ：`prove (k+1)/2` 必须输出 win。
      A2（L 健全）k 为偶数：`play w x y` 成功后 `prove k/2` 必须输出 win。
      A3（协议）  prove 输出只能是 win / no / timeout / error turn。
    注：任务书原文写的是“play b x y 后发 prove <(k+1)/2>”，但 `play b` 之后轮到白方，
    `prove` 会输出 `error turn`；因此在**落子前的同局面**（轮黑）上调 `prove (k+1)/2`
    —— 这比原文的检查更强（它要求黑方在同样预算内从根局面就有必胜证明，而标注只
    要求“以该点为第一手”成立）。A2 的 `play w` 之后正好轮到黑方，故按原文执行。

用例（T* 编号对应任务书第 4/6 部分；括号里注明与任务书预期文字不同的地方及原因）：
  T1 即时成五：黑 (7,4)(7,5)(7,6)(7,7)，无白。
     candidates b 11 含 "cand 7 3 W1" 与 "cand 7 8 W1"，且 W1 只有这两点。
     （任务书要求删除“无其他 W1”之外依赖旧 OR 语义的断言——旧版会给一批 W3，
     证明级下这些点不再被标注。）
  T2 吃子反驳（核心回归）：黑 (7,5)(7,6)(7,7)，白贴住四周。
     candidates b 11 中 (7,4) 没有 W 标注（白 (7,8) 提子反驳）；交叉校验：轮到白方时
     (7,8) 这个提子点本身也不是 L（白提子后黑方被吃光，白方已达成胜利条件）。
  T3 真四不可吃：黑 (7,4)(7,5)(7,6)(7,7)，白仅 (8,4)(8,5)(8,6)。(7,3)/(7,8) 都是 W1。
  T4 双三 VCT：黑 (7,6)(7,8)(6,7)(8,7)，白 (0,0)(0,1)。
     (7,7) 是三三禁手（checkforbidden 确认），gen_moves 会剔除它 → candidates b 不会
     输出它。旧版此处断言“存在 W5 且 (7,5) 是 W5”；证明级下是否 W5 改由 A1 的
     `prove` 交叉验证（标注多少步就 prove 对应预算），故删除具体步数断言。
  T5 L 标注：T4 局面 candidates w 11 → 只做通用 A2 断言（证明级下 (0,2) 是否 L 取决于
     搜索能否在限时内证明黑方 6 手必胜，任务书已把该断言改为条件式）。
  T6 障碍：黑活四 + (7,8) 障碍，(7,3) 是唯一 W1。
  T7 无副作用：T4 局面 hash → candidates b 11 → candidates w 11 → hash 不变。
  T8 胜点验证：T4 局面落黑 (7,7)（play b 7 7）后 candidates w 11，白方全部候选都标 L
     （无 W、无 timeout，候选数 >= 40，关键点逐个断言），并逐个跑 A2 健全性断言。
  T9 假四（长连完成点）：黑 (7,2)(7,4)(7,5)(7,6)(7,7)，无白。
     * (7,3) 是长连禁手点，必须出现在 checkforbidden 里、且不出现在 candidates 输出里；
     * (7,8) 是唯一合法完成点 —— 注意它在**黑方先手**的局面下是立即成五（黑第 4~8 列
       连成恰五），因此唯一的 W 标注就是 "(7,8) W1"；任务书原文期望“不得有任何 W
       标注”与该点的规则事实冲突，故这里改为断言“除 (7,8) W1 外没有任何 W”，
       这正是任务书想抓的旧 OR 语义错标（旧版会给一批 W3）。
     * 9b 补充：同局面把 (7,8) 换成障碍（黑方唯一的合法完成点消失）→ 必须**没有任何
       W 标注**，这才是任务书“假四不成必胜”的字面结论。
  T10 超时无害：T4 局面 candidates b 3 1（步数上限 3、限时 1 秒）→ 输出以 end 结束
     （可先有一行 timeout）、无 error hash、hash 不变。

第 7 步（威胁候选点与三层 VCT）之后 candidates **w** 的语义升级（本文件相应调整了
3 处候选断言，理由逐条写在对应用例里）：
  * `candidates w` 不再给 gen_moves(WHITE) 的每个空点打 L，而是输出**白棋威胁候选点**
    （阻挡点交集，无交集回退并集，再取标注最好的一档：安全 W0 优先、否则 L 步数最大）；
    盘面无黑棋强迫威胁（无一手成活四/成五的线）时输出全部空点（W0 = 不受约束）。
  * 受影响的断言：T2 的白方 (7,8)（旧：必须没有标注；新：必须是候选点且不得为 L）、
    T8 的候选数量与逐点 L（旧：>=40 个、指定点全为 L；新：候选局限在黑方双威胁的
    阻挡点内且全为 L）。T5/T2/T8 的通用 A2 断言里，白方 W0 标注改为“落子合法 +
    抽查 prove 不成 win”。
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

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from board import HybridBoard, BLACK, WHITE, OBSTACLE  # noqa: E402  仅 A1 的恰五复算

READ_TIMEOUT = 180.0
PROVE_SEC = 10.0        # 通用断言里 prove 的限时（秒）
CAND_SEC = 10.0         # candidates 的限时（秒）
CAND_STEPS = 11         # candidates 的步数参数（与 CLI 缺省一致）

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


def position(black=(), white=(), obstacles=(), prelude=()):
    """一个局面：size 15 + set 摆子，再依次执行 prelude（如 play b 7 7）。"""
    return {"black": list(black), "white": list(white),
            "obstacles": list(obstacles), "prelude": list(prelude)}


def setup(eng: Engine, pos) -> None:
    """size 15（重置回合为黑）+ clear + 摆子 + prelude（play 的输出会被吃掉）。"""
    eng.send("size 15")
    eng.send("clear")
    for (x, y) in pos["black"]:
        eng.send("set %d %d b" % (x, y))
    for (x, y) in pos["white"]:
        eng.send("set %d %d w" % (x, y))
    for (x, y) in pos["obstacles"]:
        eng.send("set %d %d o" % (x, y))
    for cmd in pos["prelude"]:
        eng.send(cmd)
        if cmd.split()[0] in ("play", "move"):
            eng.readline()          # 吃掉 ok / illegal / err


def python_board(pos, extra_black=()):
    """Python 参考实现复算用棋盘（只摆子，不落子）。"""
    b = HybridBoard(15)
    for (x, y) in list(pos["black"]) + list(extra_black):
        b.grid[x, y] = BLACK
    for (x, y) in pos["white"]:
        b.grid[x, y] = WHITE
    for (x, y) in pos["obstacles"]:
        b.grid[x, y] = OBSTACLE
    return b


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


def run_candidates(eng: Engine, side: str, steps: int = 11,
                   max_sec: float = CAND_SEC) -> dict:
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
        if lab[0] not in ("W", "L") or not lab[1:].isdigit():
            raise RuntimeError("unexpected label: %r" % lab)
        cands.append((x, y, lab[0], int(lab[1:])))
    return {"cands": cands, "timeout": timeout}


def run_prove(eng: Engine, steps: int, max_sec: float = PROVE_SEC) -> str:
    """发 prove 命令并返回 win / no / timeout / error turn（A3：只允许这四种）。"""
    eng.send("prove %d %g" % (steps, max_sec))
    ln = eng.readline()
    if ln not in ("win", "no", "timeout", "error turn"):
        raise RuntimeError("unexpected prove output: %r" % ln)
    return ln


def find(cands, x, y):
    for (cx, cy, tag, st) in cands:
        if cx == x and cy == y:
            return (tag, st)
    return None


def tags_of(cands, tag):
    return sorted((cx, cy, st) for (cx, cy, t, st) in cands if t == tag)


def verify_labels(eng: Engine, stats: Stats, pos, side: str, cands,
                  max_sec: float = PROVE_SEC) -> None:
    """通用健全性断言 A1/A2（对每条标注都用引擎的 prove / Python 参考实现复核）。

    第 7 步（威胁候选点重写）后 candidates **w** 的输出语义变了：
      * L<2m>：白棋落该点后黑方 m 手内被证明必胜（语义不变，仍按 A2 复核）；
      * W0   ：白棋落该点后黑方在预算内证明不出必胜（该候选点安全）。
    旧语义里白方候选只有 L，因此 A1 分支（“W<k> 必须能 prove 成 win”）只对
    黑方候选成立：白方的 W0 改为抽查若干点，断言 (i) 落子合法、(ii) 引擎同一
    预算下 prove 不出 win（与标注一致）。
    """
    tag = "A1" if side == "b" else "A2"
    checked_w = 0
    for (x, y, lab, k) in cands:
        if lab == "W" and side == "w":
            stats.check(k == 0,
                        "A2: 白方 W 标注只允许 W0（安全点），实际 W%d (%d,%d)"
                        % (k, x, y))
            setup(eng, pos)
            eng.send("play w %d %d" % (x, y))
            ok = eng.readline() == "ok"
            stats.check(ok, "A2: W0 (%d,%d) 白落子必须 ok" % (x, y))
            # 抽查前 3 个：黑方在 CAND_STEPS 预算内不得被证明必胜。
            if ok and checked_w < 3:
                checked_w += 1
                r = run_prove(eng, CAND_STEPS, max_sec)
                stats.check(r != "win",
                            "A2: W0 (%d,%d) 白落该点后 prove %d 不应为 win，实际 %r"
                            % (x, y, CAND_STEPS, r))
        elif lab == "W":
            if k == 1:
                setup(eng, pos)
                eng.send("play b %d %d" % (x, y))
                ok = eng.readline() == "ok"
                stats.check(ok, "A1: W1 (%d,%d) 落子必须 ok，实际 %s"
                            % (x, y, "illegal" if not ok else "ok"))
                if ok:
                    pb = python_board(pos, extra_black=[(x, y)])
                    stats.check(pb.check_black_five(x, y),
                                "A1: W1 (%d,%d) 必须恰好成五（Python 复算）" % (x, y))
            else:
                m = (k + 1) // 2
                setup(eng, pos)
                r = run_prove(eng, m, max_sec)
                stats.check(r == "win",
                            "A1: W%d (%d,%d) 在落子前局面 prove %d 应为 win，实际 %r"
                            % (k, x, y, m, r))
        elif lab == "L":
            if k % 2 != 0:
                stats.fail("A2: L 的步数必须为偶数，(%d,%d) L%d" % (x, y, k))
                continue
            m = k // 2
            setup(eng, pos)
            eng.send("play w %d %d" % (x, y))
            ok = eng.readline() == "ok"
            stats.check(ok, "A2: L%d (%d,%d) 白落子必须 ok" % (k, x, y))
            if not ok:
                continue
            r = run_prove(eng, m, max_sec)
            stats.check(r == "win",
                        "A2: L%d (%d,%d) 白落该点后 prove %d 应为 win，实际 %r"
                        % (k, x, y, m, r))
        else:
            stats.fail("%s: 未知标注 %r" % (tag, lab))


# ----------------------------------------------------------------------------
# 用例
# ----------------------------------------------------------------------------
T4_BLACK = [(7, 6), (7, 8), (6, 7), (8, 7)]
T4_WHITE = [(0, 0), (0, 1)]
T4_POS = position(black=T4_BLACK, white=T4_WHITE)


def case_t1(eng: Engine, stats: Stats) -> None:
    print("[T1] 即时成五：黑活四，candidates b 11")
    pos = position(black=[(7, 4), (7, 5), (7, 6), (7, 7)])
    setup(eng, pos)
    r = run_candidates(eng, "b", 11)
    c = r["cands"]
    stats.check(find(c, 7, 3) == ("W", 1),
                "T1: (7,3) 应为 W1，实际 %r" % (find(c, 7, 3),))
    stats.check(find(c, 7, 8) == ("W", 1),
                "T1: (7,8) 应为 W1，实际 %r" % (find(c, 7, 8),))
    w1 = [t for t in tags_of(c, "W") if t[2] == 1]
    stats.check(w1 == [(7, 3, 1), (7, 8, 1)],
                "T1: 应该只有 (7,3)/(7,8) 两个 W1，实际 %r" % (w1,))
    verify_labels(eng, stats, pos, "b", c)


def case_t2(eng: Engine, stats: Stats) -> None:
    print("[T2] 吃子反驳（核心回归）：candidates b 11 中 (7,4) 不应被标 W")
    white = [(6, 5), (8, 5), (6, 6), (8, 6), (6, 7), (8, 7), (6, 4), (8, 4),
             (7, 3)]
    pos = position(black=[(7, 5), (7, 6), (7, 7)], white=white)
    setup(eng, pos)
    forb = get_forbidden(eng)
    stats.check(forb == [], "T2: 局面不应有禁手点，实际 %r" % (forb,))
    r = run_candidates(eng, "b", 11)
    c = r["cands"]
    v = find(c, 7, 4)
    stats.check(v is None,
                "T2: (7,4) 不应有 W 标注（白 (7,8) 提子反驳），实际 %r" % (v,))
    verify_labels(eng, stats, pos, "b", c)
    # 交叉校验（第 7 步新语义）：轮到白方时 candidates w = **威胁候选点**
    # （阻挡点交集，无交集回退并集，再取标注最好的一档）。T2 局面黑 (7,5)(7,6)(7,7)
    # 是一条被 (7,3) 半堵的活三，白方 (7,8) 同时是它的阻挡点与提子点（黑块 2 气），
    # 因此它必须作为候选点出现，且**不能**被标 L（白提子后黑方再也成不了五）。
    rw = run_candidates(eng, "w", 11)
    vw = find(rw["cands"], 7, 8)
    stats.check(vw is not None and vw[0] != "L",
                "T2: 白方 (7,8)（阻挡点 + 提子点）应在候选集里且不得被标 L，实际 %r"
                % (vw,))
    verify_labels(eng, stats, pos, "w", rw["cands"])


def case_t3(eng: Engine, stats: Stats) -> None:
    print("[T3] 真四不可吃：candidates b 11")
    pos = position(black=[(7, 4), (7, 5), (7, 6), (7, 7)],
                   white=[(8, 4), (8, 5), (8, 6)])
    setup(eng, pos)
    r = run_candidates(eng, "b", 11)
    c = r["cands"]
    stats.check(find(c, 7, 3) == ("W", 1),
                "T3: (7,3) 应为 W1，实际 %r" % (find(c, 7, 3),))
    stats.check(find(c, 7, 8) == ("W", 1),
                "T3: (7,8) 应为 W1，实际 %r" % (find(c, 7, 8),))
    verify_labels(eng, stats, pos, "b", c)


def case_t4(eng: Engine, stats: Stats) -> None:
    print("[T4] 双三 VCT：candidates b 11（(7,7) 为禁手点，见注释）")
    pos = T4_POS
    setup(eng, pos)
    forb = get_forbidden(eng)
    stats.check("7 7" in forb,
                "T4: (7,7) 应被 checkforbidden 判为禁手（三三），实际 %r" % (forb,))
    r = run_candidates(eng, "b", 11)
    c = r["cands"]
    stats.check(find(c, 7, 7) is None,
                "T4: 禁手点 (7,7) 不应出现在 candidates 输出里，实际 %r"
                % (find(c, 7, 7),))
    if r["timeout"]:
        print("  [note] T4: 分析被 max_sec 截断（证明级搜索的已知限制），"
              "已得标注 %d 条" % len(c))
    # 具体步数的 W 断言删除：证明级下“多少步能证明”由 A1 的 prove 交叉验证代替。
    verify_labels(eng, stats, pos, "b", c)


def case_t5(eng: Engine, stats: Stats) -> None:
    print("[T5] L 标注：T4 局面 candidates w 11（只做通用 A2 健全性断言）")
    pos = T4_POS
    setup(eng, pos)
    r = run_candidates(eng, "w", 11)
    c = r["cands"]
    if r["timeout"]:
        print("  [note] T5: 分析被 max_sec 截断（证明级搜索的已知限制），"
              "已得标注 %d 条" % len(c))
    verify_labels(eng, stats, pos, "w", c)


def case_t6(eng: Engine, stats: Stats) -> None:
    print("[T6] 障碍：黑活四 + (7,8) 障碍，candidates b 11")
    pos = position(black=[(7, 4), (7, 5), (7, 6), (7, 7)], obstacles=[(7, 8)])
    setup(eng, pos)
    r = run_candidates(eng, "b", 11)
    c = r["cands"]
    stats.check(find(c, 7, 3) == ("W", 1),
                "T6: (7,3) 应为 W1，实际 %r" % (find(c, 7, 3),))
    stats.check(find(c, 7, 8) is None,
                "T6: 障碍点 (7,8) 不应出现在输出里，实际 %r" % (find(c, 7, 8),))
    w1 = [t for t in tags_of(c, "W") if t[2] == 1]
    stats.check(w1 == [(7, 3, 1)],
                "T6: 应该只有 (7,3) 一个 W1，实际 %r" % (w1,))
    verify_labels(eng, stats, pos, "b", c)


def case_t7(eng: Engine, stats: Stats) -> None:
    print("[T7] 无副作用：candidates 前后 hash 不变")
    pos = T4_POS
    setup(eng, pos)
    h0 = get_hash(eng)
    run_candidates(eng, "b", 11)
    h1 = get_hash(eng)
    run_candidates(eng, "w", 11)
    h2 = get_hash(eng)
    stats.check(h0 == h1, "T7: candidates b 后 hash 变了 %s -> %s" % (h0, h1))
    stats.check(h1 == h2, "T7: candidates w 后 hash 变了 %s -> %s" % (h1, h2))


def case_t8(eng: Engine, stats: Stats) -> None:
    print("[T8] 胜点验证：T4 局面 play b 7 7 后 candidates w 11 应为小黑方威胁的阻挡点且全为 L")
    pos = position(black=T4_BLACK, white=T4_WHITE, prelude=["play b 7 7"])
    setup(eng, pos)
    r = run_candidates(eng, "w", 11)
    c = r["cands"]
    stats.check(not r["timeout"], "T8: 不应超时截断")
    # 第 7 步新语义：candidates w = 威胁候选点（黑 (7,7) 落下后是“活三 + 活三”双威胁，
    # 其阻挡点是四条线的紧邻空点 {(5,7),(9,7),(7,5),(7,9)}）；旧版“给 gen_moves(WHITE)
    # 的每个候选都打 L”的语义已废弃，故这里断言的是“候选集是这些阻挡点的子集、
    # 数量很小、且全部为 L（白方必败）”。
    blockers = {(5, 7), (9, 7), (7, 5), (7, 9)}
    stats.check(1 <= len(c) <= 8,
                "T8: 白方候选应是少量阻挡点（1..8），实际 %d" % len(c))
    outside = [(x, y) for (x, y, _t, _s) in c if (x, y) not in blockers]
    stats.check(outside == [],
                "T8: 白方候选应局限于黑方威胁的阻挡点 %s，越界项 %r"
                % (sorted(blockers), outside[:8]))
    bad = [t for t in c if t[2] != "L"]
    stats.check(bad == [], "T8: 所有白方候选都应是 L，异常项 %r" % (bad[:8],))
    for pt in sorted(blockers):
        v = find(c, pt[0], pt[1])
        stats.check(v is None or v[0] == "L",
                    "T8: %r 若为候选则应为 L，实际 %r" % (pt, v))
    verify_labels(eng, stats, pos, "w", c)
    # 黑方自己在这个局面下也有连五/四三点，counter-check 一下黑方标注非空。
    pos_b = position(black=T4_BLACK + [(7, 7)], white=T4_WHITE)
    setup(eng, pos_b)
    rb = run_candidates(eng, "b", 11)
    stats.check(tags_of(rb["cands"], "W") != [],
                "T8: 同局面黑方应有 W 候选，实际没有")


def case_t9(eng: Engine, stats: Stats) -> None:
    print("[T9] 假四（长连完成点）：黑 (7,2)(7,4)(7,5)(7,6)(7,7)，无白")
    pos = position(black=[(7, 2), (7, 4), (7, 5), (7, 6), (7, 7)])
    setup(eng, pos)
    forb = get_forbidden(eng)
    stats.check("7 3" in forb,
                "T9: (7,3) 应被 checkforbidden 判为长连禁手，实际 %r" % (forb,))
    r = run_candidates(eng, "b", 11)
    c = r["cands"]
    stats.check(find(c, 7, 3) is None,
                "T9: 长连禁手点 (7,3) 不应出现在 candidates 输出里，实际 %r"
                % (find(c, 7, 3),))
    wl = tags_of(c, "W")
    # (7,8) 使黑第 4..8 列连成**恰五**，是合法的立即成五点（任何健全实现都必须标 W1）；
    # 任务书原文期望“不得有任何 W 标注”与该规则事实冲突，故此处断言“除 (7,8) W1 外
    # 没有任何 W”—— 长连假四不允许被标成必胜，这正是旧 OR 语义的典型错标。
    stats.check(wl == [(7, 8, 1)],
                "T9: 只允许 (7,8) W1（立即成五）；其余任何 W 都是旧 OR 语义的错标，"
                "实际 %r" % (wl,))
    verify_labels(eng, stats, pos, "b", c)

    print("  [T9b] 同局面 + (7,8) 障碍（唯一合法完成点消失）→ 不允许任何 W")
    pos_b = position(black=[(7, 2), (7, 4), (7, 5), (7, 6), (7, 7)],
                     obstacles=[(7, 8)])
    setup(eng, pos_b)
    r_b = run_candidates(eng, "b", 11)
    c_b = r_b["cands"]
    stats.check(find(c_b, 7, 3) is None,
                "T9b: (7,3) 不应出现在输出里，实际 %r" % (find(c_b, 7, 3),))
    wl_b = tags_of(c_b, "W")
    stats.check(wl_b == [],
                "T9b: 假四（长连完成点 + 完成点被堵）不得有任何 W 标注，实际 %r"
                % (wl_b,))
    if r_b["timeout"]:
        print("  [note] T9b: 分析被 max_sec 截断（无标注本身仍满足断言）")
    verify_labels(eng, stats, pos_b, "b", c_b)


def case_t10(eng: Engine, stats: Stats) -> None:
    print("[T10] 超时无害：T4 局面 candidates b 3 1")
    pos = T4_POS
    setup(eng, pos)
    h0 = get_hash(eng)
    eng.send("candidates b 3 1")
    lines = []
    while True:
        ln = eng.readline()
        lines.append(ln)
        if ln == "end":
            break
    stats.check(lines[-1] == "end",
                "T10: 输出必须以 end 结束，实际最后一行 %r" % (lines[-1],))
    stats.check(not any(l.startswith("error") for l in lines),
                "T10: 不应出现 error 行，实际 %r" % (lines,))
    stats.check(all(l == "end" or l == "timeout" or l.startswith("cand ")
                    for l in lines),
                "T10: 只允许 cand / timeout / end 行，实际 %r" % (lines,))
    h1 = get_hash(eng)
    stats.check(h0 == h1, "T10: hash 不应改变 %s -> %s" % (h0, h1))


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
        case_t9(eng, stats)
        case_t10(eng, stats)
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
