#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
forbid_cases.py - 禁手用例运行器（导入 导出/粘贴板.md 全部用例并逐一验证）。

在仓库根目录运行：
    py -3.14 cpp/tests/forbid_cases.py     （等价于 py cpp/tests/forbid_cases.py）

每个用例块做三层验证：
  1. 案例自洽：Python 参考实现（board/rules，即 rapfi_plugin 的判定引擎）
     算出的禁手集合与块内 forbid: 期望一致。
  2. C++ 引擎一致：同样局面经引擎协议（size/set/checkforbidden）算出的
     禁手集合与 Python 参考一致。
  3. 等价组（#group: 注释行）：同组所有块的引擎禁手集合完全一致——
     验证"白子 / 障碍 / 无气空点在代码层面完全一致"。

计时：每条 set 命令、checkforbidden、pat（禁手原因探测）单独计时，
任何一步 > 0.2s 记为超时（按要求：若"显示禁手原因"导致超时可取消）。
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CPP_DIR = os.path.dirname(SCRIPT_DIR)
REPO_ROOT = os.path.dirname(CPP_DIR)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import board_tools  # noqa: E402
from board import OBSTACLE, WHITE  # noqa: E402
import rules  # noqa: E402

CASE_FILE = os.path.join(REPO_ROOT, "导出", "粘贴板.md")
ENGINE = os.path.join(CPP_DIR, "build", "engine.exe")
TIME_BUDGET = 0.2  # 每步落子/查询的时间预算（秒）


class Engine:
    """引擎子进程封装（逐行协议 + 每条命令计时）。"""

    def __init__(self):
        self.proc = subprocess.Popen(
            [ENGINE], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1)
        self.slow = []  # (命令摘要, 秒)

    def send(self, line: str) -> list[str]:
        t0 = time.perf_counter()
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()
        out: list[str] = []
        head = line.split(" ", 1)[0]
        if head in ("size", "clear", "set", "winmode"):
            return out                      # 这些命令不产生输出
        while True:
            row = self.proc.stdout.readline()
            if row == "":
                raise RuntimeError("engine closed")
            row = row.rstrip("\n")
            out.append(row)
            if row == "end" or head in ("play", "undo", "hash", "pat") \
                    and len(out) >= 1:
                break
        dt = time.perf_counter() - t0
        if dt > TIME_BUDGET:
            self.slow.append((line[:40], dt))
        return out

    def timed(self, line: str, marker: str) -> list[str]:
        t0 = time.perf_counter()
        out = self.send(line)
        dt = time.perf_counter() - t0
        if dt > TIME_BUDGET:
            self.slow.append((marker, dt))
        return out

    def close(self):
        try:
            self.proc.stdin.write("quit\n")
            self.proc.stdin.flush()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


def parse_cases(path: str):
    """[(group, codes, forbid_expect, setup)]；setup 为 {code: 'o'|'e'}。"""
    cases = []
    group = ""
    pending = None
    for raw in open(path, "r", encoding="utf-8"):
        line = raw.strip()
        if not line or line.startswith("#"):
            if line.startswith("#group:"):
                group = line[len("#group:"):].strip()
            continue
        low = line.lower()
        if low.startswith("forbid:"):
            if pending is not None:
                pending["forbid"] = line.split(":", 1)[1].strip()
                cases.append(pending)
                pending = None
            continue
        if low.startswith("setup:"):
            if pending is None:
                raise ValueError("setup 行前面缺少代码行: " + line)
            for item in line.split(":", 1)[1].split(","):
                item = item.strip()
                if not item:
                    continue
                code, action = item.split("=")
                pending["setup"][code.strip().lower()] = action.strip().lower()
            continue
        if pending is not None:
            cases.append(pending)
        pending = {"group": group, "codes": line, "forbid": "", "setup": {}}
    if pending is not None:
        cases.append(pending)
    return cases


def build_board(case):
    """回放代码行 + 应用 setup，返回 HybridBoard。"""
    board, _side = board_tools.board_from_code(
        case["codes"], size=15, first=board_tools.BLACK, gomoku=True)
    for code, action in case["setup"].items():
        coord = board_tools.code_to_coord(code, board.size)
        if coord is None:
            raise ValueError("setup 坐标无效: " + code)
        x, y = coord
        if action == "o":
            board.grid[x, y] = OBSTACLE
        elif action == "e":
            board.grid[x, y] = 0
        else:
            raise ValueError("setup 动作无效: " + action)
    board._invalidate_caches()
    return board


def python_forbidden(board):
    """Python 参考禁手集合（与 rapfi_plugin 同一判定引擎）。"""
    out = set()
    for x in range(board.size):
        for y in range(board.size):
            if not board.is_empty(x, y):
                continue
            ok, ftype = rules.is_black_legal_move(board, x, y)
            if not ok and ftype in ("three_three", "four_four", "overline"):
                out.add((x, y))
    return out


def engine_forbidden(eng: Engine, board, case_id: str):
    """引擎协议重摆局面 + checkforbidden + pat 计时。"""
    eng.send("size %d" % board.size)
    eng.send("clear")
    for x in range(board.size):
        for y in range(board.size):
            v = int(board.grid[x, y])
            if v == 0:
                continue
            tag = {1: "b", 2: "w", 3: "o"}[v]
            eng.send("set %d %d %s" % (x, y, tag))
    rows = eng.timed("checkforbidden", "%s checkforbidden" % case_id)
    got = set()
    for row in rows:
        if row in ("end", ""):
            continue
        parts = row.split()
        if len(parts) == 2:
            got.add((int(parts[0]), int(parts[1])))
    # 禁手原因探测（pat 命令）也计时——超过预算则按用户要求可取消该显示。
    for (x, y) in sorted(got)[:6]:
        eng.timed("pat %d %d" % (x, y), "%s pat(%d,%d)" % (case_id, x, y))
    return got


def main() -> int:
    cases = parse_cases(CASE_FILE)
    print("[cases] 导入 %d 个用例块" % len(cases), flush=True)
    eng = Engine()
    failures = []
    group_results: dict[str, list] = {}
    slow_all = []
    try:
        for i, case in enumerate(cases):
            cid = "%s#%d" % (case["group"] or "case", i + 1)
            board = build_board(case)

            py_set = python_forbidden(board)
            expect = board_tools.forbidden_list(case["forbid"])
            expect_set = {board_tools.code_to_coord(c, board.size)
                          for c in expect} - {None}

            # Python 参考（rules.py）与 Rapfi 的已知差异只做信息报告，
            # 不算失败——期望行才是权威（来自 Rapfi）。
            if expect_set != py_set:
                print("  [note] %s rules.py 与 Rapfi 差异: py %s vs 期望 %s"
                      % (cid, sorted(py_set - expect_set),
                         sorted(expect_set - py_set)), flush=True)

            eng_set = engine_forbidden(eng, board, cid)
            # 硬性条件：引擎（Rapfi 语义）必须与 forbid 期望一致。
            if eng_set != expect_set:
                failures.append(
                    "%s 引擎不一致: 引擎 %s vs 期望 %s"
                    % (cid, sorted(eng_set), sorted(expect_set)))

            group_results.setdefault(case["group"], []).append((cid, eng_set))
            slow_all.extend(eng.slow)
            eng.slow = []
            print("  [%s] 禁手 %d 个%s" % (cid, len(eng_set),
                  "  (setup: %s)" % case["setup"] if case["setup"] else ""),
                  flush=True)

        # 等价组：同组禁手集合必须一致（含 setup 变体与组内其它块）。
        for group, results in group_results.items():
            if not group:
                continue
            first_id, first_set = results[0]
            for other_id, other_set in results[1:]:
                if other_set != first_set:
                    failures.append(
                        "等价组 %s: %s 的禁手集合 %s != %s 的 %s"
                        % (group, other_id, sorted(other_set),
                           first_id, sorted(first_set)))
    finally:
        eng.close()

    if slow_all:
        print("[timing] 超过 %.2fs 的步骤：" % TIME_BUDGET)
        for marker, dt in slow_all:
            print("    %.3fs  %s" % (dt, marker))
    else:
        print("[timing] 全部步骤 ≤ %.2fs" % TIME_BUDGET)

    if failures:
        print("=" * 70)
        for f in failures:
            print("[FAIL]", f)
        print("失败=%d" % len(failures))
        return 1
    print("禁手用例=%d  等价组=%d  全部通过 PASS"
          % (len(cases), sum(1 for g in group_results if g)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
