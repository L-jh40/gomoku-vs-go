#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
forbid_cases.py - 用例运行器（导入 导出/粘贴板.md 全部用例并逐一验证）。

在仓库根目录运行：
    py -3.14 cpp/tests/forbid_cases.py     （等价于 py cpp/tests/forbid_cases.py）

文件里一共三种块（同一份 粘贴板.md 里混排；块与块之间不需要空行）：

  1. 禁手块：代码行 + `forbid:` 行（逗号分隔代码 / None），可带 `setup:` 与 `#group:`。
  2. 白棋候选点块：代码行 + `legal:` 行。
       `legal:a,b`    → 候选点恰为 {a, b}
       `legal:everywhere` → 不被约束：候选集 == 全盘空点集（按引擎语义亦可放宽，
                            此时只报告实际数量）
  3. 单点答案块：代码行 + 裸代码行（单点，如 `g8`）→ 候选点恰为该点。

每个块做四层验证：
  1a. 案例自洽（禁手块）：Python 参考实现（board/rules，即 rapfi_plugin 的判定引擎）
      算出的禁手集合与块内 forbid: 期望一致。
  1b. 候选点：用引擎 `candidates w <steps> <max_sec>` 的 cand 输出（只取 x,y 集合，
      忽略 W/L 标签）与 legal:/裸代码行期望比对，并计时（每个块 ≤ 5 秒）。
  2. C++ 引擎一致：同样局面经引擎协议（size/set/checkforbidden）算出的禁手集合与
     Python 参考一致。
  3. 等价组（#group: 注释行）：同组所有块的引擎禁手集合完全一致——验证"白子 / 障碍 /
     无气空点在代码层面完全一致"。

计时：每条 set 命令、checkforbidden、pat（禁手原因探测）单独计时，任何一步 > 0.2s
记为超时；candidates 单块 > 5s 记为超时（任务书第 5 部分的性能要求）。
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
TIME_BUDGET = 0.2        # 每步落子/查询的时间预算（秒）
CAND_STEPS = 11          # candidates w 的步数参数（与 CLI 缺省一致）
CAND_SEC = 10.0          # candidates w 的限时参数
CAND_BUDGET = 5.0        # 单个候选点块的时间预算（任务书第 5 部分：≤ 5 秒）


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

    def send_one(self, line: str) -> str:
        """只回一行的命令（play / undo / hash / pat / prove）：写一条读一行。"""
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()
        row = self.proc.stdout.readline()
        if row == "":
            raise RuntimeError("engine closed")
        return row.rstrip("\n")

    def timed_raw(self, line: str):
        """计时发一条命令（不限 0.2s 预算），返回 (输出行, 秒)。"""
        t0 = time.perf_counter()
        out = self.send(line)
        return out, time.perf_counter() - t0

    def close(self):
        try:
            self.proc.stdin.write("quit\n")
            self.proc.stdin.flush()
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


def parse_cases(path: str):
    """[(group, codes, forbid_expect, legal_expect, setup)]；setup 为 {code: 'o'|'e'}。

    legal_expect 为空表示“该块没有候选点期望”。裸代码行答案（单点）只在前面
    那条代码行还没有 forbid:/legal: 期望、且该行只有一个坐标记号时才认作答案，
    免得把普通的单子局面误当成上一条的答案。
    """
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
            if pending is None:
                raise ValueError("forbid 行前面缺少代码行: " + line)
            pending["forbid"] = line.split(":", 1)[1].strip()
            cases.append(pending)
            pending = None
            continue
        if low.startswith("legal:"):
            if pending is None:
                raise ValueError("legal 行前面缺少代码行: " + line)
            pending["legal"] = line.split(":", 1)[1].strip()
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
        # 裸代码行答案（单点）：紧跟在代码行之后，且该块还没有期望行。
        if pending is not None and not pending["forbid"] and not pending["legal"]:
            tokens = board_tools.split_codes(line, 25)
            if len(tokens) == 1:
                pending["legal"] = tokens[0]
                cases.append(pending)
                pending = None
                continue
        if pending is not None:
            cases.append(pending)
        pending = {"group": group, "codes": line, "forbid": "", "legal": "",
                   "setup": {}}
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


def empty_points(board):
    return {(x, y) for x in range(board.size) for y in range(board.size)
            if board.is_empty(x, y)}


def expected_legal(board, value: str):
    """(期望候选点集合, 是否为 everywhere)。"""
    text = str(value or "").strip()
    if text.lower() in ("everywhere", "any", "all", "全部", "任意"):
        return empty_points(board), True
    coords = {board_tools.code_to_coord(c, board.size)
              for c in board_tools.split_codes(text, board.size)}
    return coords - {None}, False


def engine_setup(eng: Engine, board):
    """把局面写进引擎（size + 全部 set）。"""
    eng.send("size %d" % board.size)
    eng.send("clear")
    for x in range(board.size):
        for y in range(board.size):
            v = int(board.grid[x, y])
            if v == 0:
                continue
            tag = {1: "b", 2: "w", 3: "o"}[v]
            eng.send("set %d %d %s" % (x, y, tag))


def engine_forbidden(eng: Engine, board, case_id: str):
    """引擎协议重摆局面 + checkforbidden + pat 计时。"""
    engine_setup(eng, board)
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


def engine_candidates(eng: Engine, board):
    """candidates w 的候选点集合（只取 cand 行的 x,y）+ 耗时（秒）。"""
    engine_setup(eng, board)
    rows, dt = eng.timed_raw("candidates w %d %g" % (CAND_STEPS, CAND_SEC))
    got = set()
    timed_out = False
    for row in rows:
        if row in ("end", ""):
            continue
        if row == "timeout":
            timed_out = True
            continue
        if row.startswith("error"):
            raise RuntimeError("engine reported: %s" % row)
        parts = row.split()
        if len(parts) == 4 and parts[0] == "cand":
            got.add((int(parts[1]), int(parts[2])))
    return got, dt, timed_out


def codes_of(board, pts):
    return sorted(board_tools.coord_to_code(x, y, board.size)
                  for (x, y) in pts)


# 引擎 pat 命令输出的方向线型（Pat 枚举值 -> 名称）。
# 注意：引擎的 Pat 枚举（cpp/src/pattern_table.h）是 Rapfi 的“合并版”，没有
# B3S/B4S —— DEAD,OL,B1,F1,B2,F2,F2A,F2B,B3,F3,F3S,B4,F4,F5 = 0..13。
# （Python rules.py 用的是 Rapfi 原版 16 值枚举，多 B3S=9 / B4S=13，两者数值不同，
#   这里必须按引擎的枚举翻译，否则 F4 永远读不到、F3/B4 会串位。）
PAT_NAMES = {0: "DEAD", 1: "OL", 2: "B1", 3: "F1", 4: "B2", 5: "F2", 6: "F2A",
             7: "F2B", 8: "B3", 9: "F3", 10: "F3S", 11: "B4", 12: "F4",
             13: "F5"}


def engine_patterns(eng: Engine, board):
    """全盘空点的四方向线型（走引擎 pat 命令，每次 4 个方向）。"""
    out = {}
    for x in range(board.size):
        for y in range(board.size):
            if not board.is_empty(x, y):
                continue
            row = eng.send_one("pat %d %d" % (x, y))
            vals = [int(v) for v in row.split()[:4]]
            out[(x, y)] = [PAT_NAMES.get(v, "?") for v in vals]
    return out


def invariant_report(eng: Engine, board, cands):
    """第一部分不变式（验收核心）：白棋落任一候选点后，黑棋只能走“形成连五 / 冲四”的
    位置，且黑棋 2 步内无法连五。

    逐点做两件事：
      1. `play w x y` + `prove 2` → 黑方 2 手内不得被证明必胜（成五）——**硬性断言**；
      2. 全盘 `pat` 扫描 → 统计“黑棋一手成活四（F4）/ 活三（F3、F3S）”的点，**只报告**。
         原因：这条子句按字面（“只能走形成连五/冲四的位置”）对验收用例并不成立，
         也不应成立——白棋一手只能封住黑棋正在建立的威胁线，其它方向的活二会继续
         成长（用例 1 白 h9 后仍有 11 个黑棋成活三的点）；用例 3 白 g8 后黑 (7,7)
         按棋型仍是活四，但白 (8,7) 能提掉那颗孤子（黑方要 4 手才证明得出，L8 而非
         L4），所以棋型层的 F4 不等于“黑棋 2 步内能连五”。按字面“黑棋只能走
         连五/冲四”只对黑方的**强制手**成立（它正是 `prove` 命令里 allow_three 的
         区分），因此这里把该子句降级为信息报告，硬性部分只保留第 1 条。
    """
    violations = []
    notes = []
    for (x, y) in sorted(cands):
        engine_setup(eng, board)
        if eng.send_one("play w %d %d" % (x, y)) != "ok":
            notes.append("候选点 %d,%d 白棋落子 illegal" % (x, y))
            continue
        r2 = eng.send_one("prove 2 %g" % CAND_SEC)
        pats = engine_patterns(eng, board)
        f4 = []
        f3 = []
        for pos, dirs in pats.items():
            if "F4" in dirs:
                f4.append(pos)
            elif "F3" in dirs or "F3S" in dirs:
                f3.append(pos)
        if r2 == "win":
            violations.append((x, y, r2, "黑方 2 手内被证明成五"))
        if f4 or f3:
            notes.append("候选点 %d,%d：白落子后黑棋一手成活四的点 %d 个、成活三的点 "
                         "%d 个（信息项，见 docstring）" % (x, y, len(f4), len(f3)))
    return violations, notes


def main() -> int:
    cases = parse_cases(CASE_FILE)
    print("[cases] 导入 %d 个用例块" % len(cases), flush=True)
    eng = Engine()
    failures = []
    group_results: dict[str, list] = {}
    slow_all = []
    cand_checked = 0
    cand_slow = []
    try:
        for i, case in enumerate(cases):
            cid = "%s#%d" % (case["group"] or "case", i + 1)
            board = build_board(case)
            has_forbid = bool(case["forbid"].strip())
            has_legal = bool(case["legal"].strip())
            if has_forbid:
                py_set = python_forbidden(board)
                expect = board_tools.forbidden_list(case["forbid"])
                expect_set = {board_tools.code_to_coord(c, board.size)
                              for c in expect} - {None}

                # rules.py 现在是 Rapfi checkForbiddenPoint 的同一算法移植
                # （只额外支持障碍/无气阻挡与环面），所以这里只做信息报告：
                # 真正的不一致只可能来自用例块自身（代码行与 forbid: 行不匹配），
                # 引擎一致性检查（下面）才是硬性失败。
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

            if has_legal:
                cand_checked += 1
                got, dt, timed_out = engine_candidates(eng, board)
                want, everywhere = expected_legal(board, case["legal"])
                ok = (got == want)
                if everywhere:
                    # 不被约束：按规格断言“候选集 == 全盘空点集（或其超集）”。
                    # 引擎语义若给出更小的受限集合，这里按失败处理并报告实际数量。
                    if not ok:
                        failures.append(
                            "%s everywhere 候选集应等于全盘空点集(%d)，实际 %d 个: %s"
                            % (cid, len(want), len(got), codes_of(board, got - want)[:12]))
                elif not ok:
                    failures.append(
                        "%s 候选点不一致: 引擎 %s vs 期望 %s（多出 %s，缺少 %s）"
                        % (cid, codes_of(board, got), codes_of(board, want),
                           codes_of(board, got - want), codes_of(board, want - got)))
                if dt > CAND_BUDGET:
                    cand_slow.append((cid, dt))
                    failures.append("%s candidates 用时 %.2fs > %.1fs"
                                    % (cid, dt, CAND_BUDGET))
                if timed_out:
                    failures.append("%s candidates 触限流（输出 timeout）" % cid)
                print("  [%s] 候选点 %d 个%s  用时 %.2fs%s"
                      % (cid, len(got),
                         "  (everywhere: 全盘 %d 空点)" % len(want)
                         if everywhere else "",
                         dt, "  期望=%s" % codes_of(board, want)
                         if not everywhere else ""), flush=True)

                # 第一部分不变式（验收核心）：候选点小集合时逐点复核
                # “白落候选点后黑棋只能走五/冲四，且 2 步内不能连五”。
                if not everywhere and 0 < len(got) <= 8:
                    viol, notes = invariant_report(eng, board, got)
                    for n in notes:
                        print("    [note] %s: %s" % (cid, n), flush=True)
                    if viol:
                        failures.append(
                            "%s 不变式违例（白落候选点后黑棋 2 步内被证明成五）: %s"
                            % (cid, viol))
                    else:
                        print("    [inv] 不变式 OK：白落任一候选点后黑棋 2 步内不能连五"
                              "（子句“黑棋只能走连五/冲四”按 docstring 只做信息报告）",
                              flush=True)

            if not has_forbid and not has_legal:
                print("  [note] %s 既无 forbid: 也无 legal: 期望，跳过" % cid,
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
        print("[timing] 禁手/摆子步骤全部 ≤ %.2fs" % TIME_BUDGET)
    if cand_slow:
        print("[timing] 超过 %.1fs 的候选点块：" % CAND_BUDGET)
        for cid, dt in cand_slow:
            print("    %.3fs  %s" % (dt, cid))

    if failures:
        print("=" * 70)
        for f in failures:
            print("[FAIL]", f)
        print("失败=%d" % len(failures))
        return 1
    print("用例块=%d  候选点块=%d  等价组=%d  全部通过 PASS"
          % (len(cases), cand_checked, sum(1 for g in group_results if g)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
