#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
engine_protocol.py - engine.exe 命令行协议回归测试。

在仓库根目录运行：
    py cpp/tests/engine_protocol.py

流程（对应任务 A 的 10 步）：
  1. 启动引擎；size 15 → clear → hash 记 h0。
  2. 依次 play 十手，逐条断言引擎回 "ok"。
  3. hash 记 h1，断言 h1 != h0。
  4. play b 7 7（重复点）→ "illegal"；play w 0 0 → "ok"；undo → "ok"。
  5. 连发 11 次 undo：断言不崩溃，最终 hash == h0。
     注：第 10 次 undo 后历史已空；引擎对空历史 undo 返回 "err"
     （见 IMPLEMENTATION.md 与 diff_forbidden.py 的既有断言），故第 11 次
     接受 ok / nohistory / err 三种“无更多历史”的表示。
  6. 恢复小局面（play b 7 7 / play w 8 8）→ hash h2；genmove b 2 0 5 收集到
     move/pass/resign 为止，断言末行类型合法、坐标在盘内且不与既有子重叠；
     hash h3 == h2（genmove 不改棋盘）。
  7. candidates b 11 10 收集到 end；断言无 "error hash"；hash 仍 == h2。
  8. size 9 → clear → checkforbidden 以 end 结束；size 8 后引擎不崩溃。
  9. quit 后进程 5 秒内退出且退出码 0。
 10. 末尾打印汇总；有失败则打印明细并以退出码 1 结束。

Engine 子进程封装复制自 diff_eval.py：启动 cpp/build/engine.exe、逐行写 stdin、
后台线程逐行抽干 stdout（避免管道/缓冲死锁）、读取带超时保护。
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
ENGINE = os.path.join(CPP_DIR, "build", "engine.exe")

READ_TIMEOUT = 60.0


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


class Checks:
    """极简断言计数器：每次 check 计一条断言，失败打印明细。"""

    def __init__(self):
        self.total = 0
        self.failures = 0

    def check(self, cond, msg) -> bool:
        self.total += 1
        if not cond:
            self.failures += 1
            print("  [FAIL] " + msg)
        return bool(cond)


def is_final_move_line(line: str) -> bool:
    return line.startswith(("move ", "pass", "resign"))


def main() -> int:
    c = Checks()
    eng = Engine()
    try:
        # ---- 1. 启动 + 初始 hash ----
        eng.send("size 15")
        eng.send("clear")
        eng.send("hash")
        h0 = eng.readline()

        # ---- 2. 十手落子，全部 ok ----
        opening = [
            (7, 7, "b"), (8, 8, "w"), (7, 8, "b"), (8, 7, "w"), (6, 6, "b"),
            (9, 9, "w"), (5, 5, "b"), (10, 10, "w"), (7, 6, "b"), (6, 7, "w"),
        ]
        for (x, y, col) in opening:
            eng.send("play %s %d %d" % (col, x, y))
            line = eng.readline()
            c.check(line == "ok",
                    "play %s %d %d -> %r（期望 ok）" % (col, x, y, line))

        # ---- 3. hash 随落子变化 ----
        eng.send("hash")
        h1 = eng.readline()
        c.check(h1 != h0, "hash 未随落子变化：h0=%s h1=%s" % (h0, h1))

        # ---- 4. illegal / 合法落子 / undo ----
        eng.send("play b 7 7")
        line = eng.readline()
        c.check(line == "illegal",
                "重复落子 (7,7) -> %r（期望 illegal）" % line)

        eng.send("play w 0 0")
        line = eng.readline()
        c.check(line == "ok", "play w 0 0 -> %r（期望 ok）" % line)

        eng.send("undo")
        line = eng.readline()
        c.check(line == "ok", "undo -> %r（期望 ok）" % line)

        # ---- 5. 连发 11 次 undo，回到初始局面 ----
        for i in range(11):
            eng.send("undo")
            line = eng.readline()
            if i < 10:
                c.check(line == "ok",
                        "第 %d 次 undo -> %r（期望 ok）" % (i + 1, line))
            else:
                c.check(line in ("ok", "nohistory", "err"),
                        "第 11 次 undo -> %r（期望 ok/nohistory/err）" % line)
        c.check(eng.p.poll() is None, "连续 undo 后引擎进程已退出（不应发生）")
        eng.send("hash")
        h_undo = eng.readline()
        c.check(h_undo == h0,
                "全部 undo 后 hash=%s != h0=%s" % (h_undo, h0))

        # ---- 6. 恢复小局面 + genmove 无副作用 ----
        for (x, y, col) in ((7, 7, "b"), (8, 8, "w")):
            eng.send("play %s %d %d" % (col, x, y))
            line = eng.readline()
            c.check(line == "ok",
                    "恢复 play %s %d %d -> %r（期望 ok）" % (col, x, y, line))

        eng.send("hash")
        h2 = eng.readline()

        eng.send("genmove b 2 0 5")
        final = None
        for _ in range(10000):
            ln = eng.readline()
            if is_final_move_line(ln):
                final = ln
                break
        c.check(final is not None,
                "genmove 未以 move/pass/resign 结束（读取到 EOF/超时）")
        if final is not None:
            c.check(is_final_move_line(final),
                    "genmove 末行类型非法：%r" % final)
            if final.startswith("move "):
                parts = final.split()
                mx, my = int(parts[1]), int(parts[2])
                c.check(0 <= mx < 15 and 0 <= my < 15,
                        "genmove 坐标越界：%r" % final)
                c.check((mx, my) not in ((7, 7), (8, 8)),
                        "genmove 落在已有子上：%r" % final)

        eng.send("hash")
        h3 = eng.readline()
        c.check(h3 == h2, "genmove 改动了棋盘：h2=%s h3=%s" % (h2, h3))

        # ---- 7. candidates 无副作用 ----
        eng.send("candidates b 11 10")
        cands = []
        got_end = False
        for _ in range(100000):
            ln = eng.readline()
            if ln == "end":
                got_end = True
                break
            cands.append(ln)
        c.check(got_end, "candidates 未以 end 结束")
        c.check(all(ln != "error hash" for ln in cands),
                "candidates 输出了 error hash")
        eng.send("hash")
        h4 = eng.readline()
        c.check(h4 == h2, "candidates 改动了棋盘：h2=%s h4=%s" % (h2, h4))

        # ---- 8. size 9 + checkforbidden，size 8 不崩溃 ----
        eng.send("size 9")
        eng.send("clear")
        eng.send("checkforbidden")
        forb = []
        got_end = False
        for _ in range(10000):
            ln = eng.readline()
            if ln == "end":
                got_end = True
                break
            forb.append(ln)
        c.check(got_end, "size 9 后 checkforbidden 未以 end 结束")
        bad = [ln for ln in forb
               if len(ln.split()) != 2 or not all(p.isdigit() for p in ln.split())]
        c.check(not bad, "checkforbidden 行格式异常：%r" % bad[:3])
        c.check(all(0 <= int(ln.split()[0]) < 9 and 0 <= int(ln.split()[1]) < 9
                    for ln in forb if len(ln.split()) == 2),
                "checkforbidden 坐标越界：%r" % forb[:3])

        eng.send("size 8")
        time.sleep(0.2)
        c.check(eng.p.poll() is None, "size 8 后引擎进程已退出（不应发生）")

        # ---- 9. quit 后 5 秒内退出 ----
        eng.send("quit")
        try:
            rc = eng.p.wait(timeout=5)
            exited = True
        except subprocess.TimeoutExpired:
            exited = False
            rc = None
        c.check(exited, "quit 后 5 秒内未退出")
        c.check(rc == 0, "quit 退出码=%r（期望 0）" % rc)
    finally:
        if eng.p.poll() is None:
            try:
                eng.p.kill()
            except Exception:
                pass

    # ---- 10. 汇总 ----
    print("=" * 64)
    if c.failures:
        print("协议测试失败 断言=%d 失败=%d FAIL" % (c.total, c.failures))
        return 1
    print("协议测试通过 断言=%d 失败=0 PASS" % c.total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
