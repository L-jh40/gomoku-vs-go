"""daoqi_gui.py - 道棋（环面围棋）对弈观察窗口，仅一个文件。

用 daoqi_katago/ 里的 KataGo（道棋神经网络）下环面围棋。规则全部由引擎
执行（GTP：play/genmove/undo/pass/final_score，chinese 规则 = 提子、禁
自杀、全局禁同形），本文件不含任何规则代码，只负责：

- 把引擎的棋盘（showboard）画成与主项目相同的环面 UI：四周镜面复制区、
  50% 淡色假棋子、镜框、悬停虚影、手数、最后一手红圈
- kata-analyze 实时胜率 / 目差（黑方视角，配置 reportAnalysisWinratesAs
  = BLACK）与候选点胜率标注
- 黑 / 白 AI（kata-genmove_analyze）自动对弈串，或勾掉一侧人手点击落子

运行：python daoqi_gui.py
引擎文件与下载来源见 daoqi_katago/README.md（git 忽略，换机重下即可）。
"""

from __future__ import annotations

import os
import queue
import re
import subprocess
import threading
import time
import tkinter as tk
from tkinter import messagebox

_BASE = os.path.dirname(os.path.abspath(__file__))
DAOQI_DIR = os.path.join(_BASE, "daoqi_katago")
MODEL_PATH = os.path.join(DAOQI_DIR, "model.bin.gz")
CONFIG_PATH = os.path.join(DAOQI_DIR, "gtp_daoqi.cfg")
BACKENDS = (("OpenCL", "katago_opencl.exe"), ("Eigen", "katago_eigen.exe"))

EMPTY, BLACK, WHITE = 0, 1, 2
BOARD_SIZES = (9, 11, 13, 15, 16, 17, 19)
STAR_POINTS = {
    9: ((2, 2), (6, 2), (2, 6), (6, 6), (4, 4)),
    11: ((2, 2), (8, 2), (2, 8), (8, 8), (5, 5)),
    13: ((3, 3), (9, 3), (3, 9), (9, 9), (6, 6)),
    15: ((3, 3), (11, 3), (3, 11), (11, 11), (7, 7)),
    16: ((3, 3), (12, 3), (3, 12), (12, 12)),
    17: ((3, 3), (13, 3), (3, 13), (13, 13), (8, 8)),
    19: ((3, 3), (9, 3), (15, 3), (3, 9), (9, 9), (15, 9),
         (3, 15), (9, 15), (15, 15)),
}

CELL = 28
MARGIN = 26
PANEL_W = 250

BOARD_BG = "#f0d68c"
FAKE_FRAME = "#f2f2f2"
EVAL_FG = "#8a2be2"


class EngineDead(Exception):
    pass


def xy_to_vertex(x, y, size):
    """Grid (col, row-from-top) -> GTP vertex, e.g. (3, 0) on 9 = "D9"."""
    letter = chr(ord("A") + x + (1 if x >= 8 else 0))   # skip I
    return f"{letter}{size - y}"


def vertex_to_xy(v, size):
    """GTP vertex -> (col, row-from-top); None for pass/resign."""
    if not v or v in ("pass", "resign"):
        return None
    m = re.fullmatch(r"([A-T])(\d{1,2})", v.strip().upper())
    if not m or m.group(1) == "I":
        return None
    x = ord(m.group(1)) - ord("A")
    if m.group(1) > "I":
        x -= 1
    row = int(m.group(2))
    if not (0 <= x < size and 1 <= row <= size):
        return None
    return x, size - row


def parse_info_line(line):
    """One kata-analyze report line -> list of move-info dicts.

    A line holds several entries separated by the token "info"; each entry
    is "key value" pairs, with "pv" taking a variable-length vertex list.
    winrate / scoreLead are Black-perspective (gtp_daoqi.cfg)."""
    entries = []
    for chunk in line.split(" info "):
        tokens = chunk.split()
        if tokens and tokens[0] == "info":
            tokens = tokens[1:]
        if not tokens:
            continue
        info, i = {}, 0
        while i < len(tokens):
            tok = tokens[i]
            if tok == "pv":
                pv = []
                while (i + 1 < len(tokens)
                       and re.fullmatch(r"[A-T]\d{1,2}|pass", tokens[i + 1])):
                    pv.append(tokens[i + 1])
                    i += 1
                info["pv"] = pv
            elif tok == "isSymmetryOf" and i + 1 < len(tokens):
                info[tok] = tokens[i + 1]
                i += 1
            elif i + 1 < len(tokens):
                info[tok] = tokens[i + 1]
                i += 1
            i += 1
        if "move" in info:
            try:
                info["_order"] = int(info.get("order", "99"))
                info["_visits"] = int(info.get("visits", "0"))
                info["_wr"] = float(info.get("winrate", "0"))
                info["_sl"] = float(info.get("scoreLead", "0"))
            except ValueError:
                continue
            entries.append(info)
    return entries


def parse_showboard(block, size):
    """showboard reply -> {(x, y): color}.

    Rows are "16 . . . X3 . ..." — the last-played stone carries its move
    number glued on ("X3") which can even fuse with the next point ("O2."),
    so scan characters and ignore digits/spacing.  X=black, O=white."""
    stones = {}
    row_re = re.compile(r"^\s*(\d+)\s(.*)$")
    for line in block:
        m = row_re.match(line)
        if not m:
            continue
        y = size - int(m.group(1))
        if not (0 <= y < size):
            continue
        x = 0
        for ch in m.group(2):
            if ch in ("X", "O", "."):
                if x < size and ch != ".":
                    stones[(x, y)] = BLACK if ch == "X" else WHITE
                x += 1
    return stones


class KataGoGTP:
    """One KataGo GTP subprocess.  A worker thread runs queued jobs in
    order; between jobs it keeps a kata-analyze stream open so the UI can
    show live winrate / scoreLead / candidates.  Every command carries a
    GTP id and the worker matches responses BY ID, so interrupting the
    analyze stream (its terminator block arrives at unpredictable times)
    can never desync the request/response framing (verified v1.18.1)."""

    def __init__(self, on_event):
        self.on_event = on_event            # ("info", report) / ("dead", tail)
        self.proc = None
        self.backend = None
        self.evq = queue.Queue()
        self.jobs = queue.Queue()
        self.alive = False
        self.analyze_desired = True
        self._analyzing = False
        self._cmd_id = 0
        self._analyze_id = None
        self._stderr_tail = []
        self._gen = 0

    # ------------------------------------------------------------------
    def start(self):
        """Spawn the engine (OpenCL first, Eigen fallback)."""
        if not os.path.exists(MODEL_PATH) or not os.path.exists(CONFIG_PATH):
            raise EngineDead("缺少 daoqi_katago/model.bin.gz 或 gtp_daoqi.cfg")
        last_err = None
        for backend, exe in BACKENDS:
            path = os.path.join(DAOQI_DIR, exe)
            if not os.path.exists(path):
                last_err = f"{backend}: 未找到 {exe}"
                continue
            try:
                self.proc = subprocess.Popen(
                    [path, "gtp", "-model", MODEL_PATH, "-config", CONFIG_PATH],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True, encoding="utf-8",
                    bufsize=1, cwd=DAOQI_DIR)
            except OSError as exc:
                last_err = f"{backend}: {exc}"
                continue
            self.backend = backend
            self.alive = True
            threading.Thread(target=self._pump_stderr, daemon=True).start()
            threading.Thread(target=self._reader, daemon=True).start()
            threading.Thread(target=self._worker, daemon=True).start()
            return
        raise EngineDead(last_err or "没有可用的 KataGo 引擎")

    def _pump_stderr(self):
        try:
            for line in self.proc.stderr:
                self._stderr_tail.append(line.rstrip())
                del self._stderr_tail[:-8]
        except Exception:
            pass

    def _send(self, text):
        try:
            self.proc.stdin.write(text + "\n")
            self.proc.stdin.flush()
        except (OSError, ValueError):
            self._die()

    def _die(self):
        if self.alive:
            self.alive = False
            tail = " | ".join(self._stderr_tail[-3:])
            self.on_event(("dead", tail))

    # ------------------------------------------------------------------
    def _reader(self):
        """stdout -> events: block lines start with = or ?; a blank line
        closes the block; kata-analyze reports stream inside the block and
        go straight to the UI."""
        block = None
        while True:
            try:
                line = self.proc.stdout.readline()
            except (OSError, ValueError):
                line = ""
            if line == "":
                self.evq.put(("eof", None))
                self._die()
                return
            line = line.rstrip("\n")
            if line == "":
                if block is not None:
                    self.evq.put(("block", block))
                    block = None
                continue
            if line.startswith("=") or line.startswith("?"):
                block = [line]
            elif block is not None:
                if line.startswith("info "):
                    self.on_event(("info", line))
                block.append(line)
            # lines outside any block should not happen; drop them

    _BLOCK_RE = re.compile(r"([=?])(\d+)?\s*(.*)")

    def _send_cmd(self, cmd):
        """Send a GTP command with an id prefix; the engine echoes the id
        in the first line of its response block."""
        self._cmd_id += 1
        self._send(f"{self._cmd_id} {cmd}")
        return self._cmd_id

    def _wait_for(self, cmd_id, timeout):
        """Consume events until the response block for `cmd_id` arrives.

        Blocks are matched BY ID, so a stale block - e.g. the terminator of
        the kata-analyze stream that the new command just interrupted (it
        may or may not carry a final report depending on timing) - is
        discarded automatically instead of desyncing the framing."""
        deadline = time.time() + timeout
        while True:
            remain = deadline - time.time()
            if remain <= 0:
                return None
            try:
                kind, payload = self.evq.get(timeout=remain)
            except queue.Empty:
                return None
            if kind == "eof":
                return None
            if kind != "block" or not payload:
                continue
            m = self._BLOCK_RE.match(payload[0])
            if not m or not m.group(2):
                continue
            block_id = int(m.group(2))
            if block_id == cmd_id:
                if cmd_id == self._analyze_id:
                    self._analyzing = False
                return payload
            if block_id == self._analyze_id:
                self._analyzing = False     # interrupted analyze terminator

    # ------------------------------------------------------------------
    def _worker(self):
        try:
            # Ready ping: the engine answers only after the net is loaded
            # (~20s first start with a warm OpenCL tuning cache).
            cid = self._send_cmd("name")
            if self._wait_for(cid, 240) is None:
                self._die()
                return
            self.on_event(("ready", self.backend))
            while True:
                job = self.jobs.get()
                kind = job[0]
                if kind == "quit":
                    self._send_cmd("quit")
                    break
                if not self.alive:
                    break
                try:
                    result = self._run_job(job)
                except EngineDead:
                    self._die()
                    break
                self.on_event(("done", job, result))
                # Between jobs keep a live kata-analyze stream open so the
                # UI shows continuous winrate / scoreLead / candidates.
                if kind != "score" and self.analyze_desired and self.alive:
                    self._analyze_id = self._send_cmd("kata-analyze 100")
                    self._analyzing = True
        except Exception:
            self._die()

    def _run_job(self, job):
        kind = job[0]
        if kind == "newgame":
            cid = self._send_cmd(f"boardsize {job[1]}")
            if self._wait_for(cid, 60) is None:
                raise EngineDead()
            cid = self._send_cmd(f"komi {job[2]}")
            self._wait_for(cid, 30)
            cid = self._send_cmd("kata-set-rules chinese")
            self._wait_for(cid, 30)
            cid = self._send_cmd("clear_board")
            return self._ok(self._wait_for(cid, 60))
        if kind == "play":
            color, vtx = job[1], job[2]
            cid = self._send_cmd(
                f"play {'b' if color == BLACK else 'w'} {vtx}")
            return self._ok(self._wait_for(cid, 60))
        if kind == "undo":
            cid = self._send_cmd("undo")
            return self._ok(self._wait_for(cid, 60))
        if kind == "genmove":
            color, visits = job[1], job[2]
            cid = self._send_cmd(
                f"kata-set-param maxVisits {max(8, int(visits))}")
            self._wait_for(cid, 30)
            cid = self._send_cmd(
                f"kata-genmove_analyze "
                f"{'b' if color == BLACK else 'w'} 100")
            blk = self._wait_for(cid, 3600)
            if blk is None:
                raise EngineDead()
            move = None
            for line in blk:
                if line.startswith("play "):
                    move = line[5:].strip()
            return {"ok": move is not None, "move": move}
        if kind == "score":
            cid = self._send_cmd("final_score")
            blk = self._wait_for(cid, 120)
            if blk is None:
                raise EngineDead()
            text = ""
            if blk:
                m = self._BLOCK_RE.match(blk[0])
                if m and m.group(1) == "=":
                    text = m.group(3)
            return {"text": text or "?"}
        if kind == "board":
            cid = self._send_cmd("showboard")
            blk = self._wait_for(cid, 60)
            if blk is None:
                raise EngineDead()
            return {"stones": parse_showboard(blk, job[1])}
        return {"ok": False}

    @classmethod
    def _ok(cls, block):
        if block is None:
            return {"ok": False, "error": "引擎无响应"}
        m = cls._BLOCK_RE.match(block[0]) if block else None
        if m is None:
            return {"ok": False, "error": "无法解析引擎响应"}
        if m.group(1) == "?":
            return {"ok": False, "error": m.group(3) or "被引擎拒绝"}
        return {"ok": True, "error": None}

    def submit(self, job):
        self.jobs.put(job)

    def quit(self):
        if self.proc is None:
            return
        self.jobs.put(("quit",))
        try:
            self.proc.wait(timeout=5)
        except Exception:
            pass
        try:
            self.proc.kill()
        except Exception:
            pass
        self.alive = False


class DaoqiApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("道棋（环面围棋）— KataGo 对弈观察")
        self.size = tk.IntVar(value=16)
        self.komi_var = tk.StringVar(value="5.5")
        self.visits_var = tk.StringVar(value="200")
        self.black_ai = tk.IntVar(value=1)
        self.white_ai = tk.IntVar(value=1)
        self.show_numbers = tk.IntVar(value=1)
        self.hint_on = tk.IntVar(value=1)
        self.hint_width = tk.IntVar(value=2)

        # 引擎镜像的棋盘状态（全部来自 showboard / 引擎判定，UI 不算规则）
        self.stones = {}            # {(x, y): BLACK|WHITE}
        self.numbers = {}           # {(x, y): 手数}
        self.captures = {BLACK: 0, WHITE: 0}
        self.moves = []             # [(color, vertex|"pass")] 镜像手序
        self._snapshots = []        # 每手同步后的 (stones, numbers, captures, last)
        self.last_move = None
        self.turn = BLACK
        self.move_count = 0
        self.game_over = False
        self.result_text = ""
        self.prev_stones = {}
        self.engine_ready = False
        self.job_pending = False
        self.chain = tk.IntVar(value=1)      # 自动续弈（AI vs AI）
        self.backend_name = ""
        self.candidates = []                 # [(x, y, wr_side_view)]
        self.eval_text = ""
        self.pv_text = ""
        self.hover = None
        self._chain_gen = 0

        self._build_panel()
        self.canvas = tk.Canvas(root, width=800, height=820, bg=BOARD_BG,
                                highlightthickness=0)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Motion>", self._on_move)
        self.canvas.bind("<Leave>", self._on_leave)

        self.tkq = queue.Queue()
        self.engine = None
        self.root.after(80, self._poll)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._start_engine()

    # ------------------------------------------------------------------
    # 引擎事件（worker 线程 -> tk 主线程）
    # ------------------------------------------------------------------
    def _start_engine(self):
        self.engine_ready = False
        self.backend_name = ""
        self._set_status("引擎启动中…（首次约 20-40 秒）")
        try:
            self.engine = KataGoGTP(
                lambda ev: self.tkq.put(("engine", ev)))
            self.engine.start()
            self.engine.submit(("newgame", self.size.get(),
                                self._komi()))
        except EngineDead as exc:
            self.engine = None
            self._set_status(f"引擎不可用：{exc}")

    def _on_engine_event(self, ev):
        kind = ev[0]
        if kind == "info":
            self._on_report(ev[1])
        elif kind == "ready":
            self.engine_ready = True
            self.backend_name = ev[1]
            self._set_status("引擎就绪")
        elif kind == "done":
            # 落子类任务的 busy 状态保持到 showboard 同步完成（_sync_board
            # 里清零）；其余任务（score / 被拒绝的任务）立即清除。
            job, result = ev[1], ev[2]
            follows_sync = (job[0] in ("newgame", "play", "genmove", "undo",
                                       "board") and result.get("ok", True))
            if not follows_sync:
                self.job_pending = False
            self._on_job_done(job, result)
        elif kind == "dead":
            self.engine_ready = False
            self.job_pending = False
            tail = ev[1] or "进程退出"
            self._set_status(f"引擎已退出：{tail}")

    def _on_report(self, line):
        entries = parse_info_line(line)
        if not entries:
            return
        best = min(entries, key=lambda e: e["_order"])
        wr = best["_wr"]
        sl = best["_sl"]
        self.eval_text = (f"黑胜率 {wr * 100:.1f}% | 目差 {sl:+.1f}"
                          f"（{best['_visits']}访）")
        pv = best.get("pv", [])[:6]
        self.pv_text = "最佳线：→".join(pv)
        color = self.turn
        self.candidates = []
        for e in sorted(entries, key=lambda e: e["_order"])[:8]:
            xy = vertex_to_xy(e["move"], self.size.get())
            if xy is None:
                continue
            wr_e = e["_wr"] if color == BLACK else 1.0 - e["_wr"]
            self.candidates.append((xy[0], xy[1], wr_e))
        self.eval_label.config(text=self.eval_text)
        self.pv_label.config(text=self.pv_text)
        self.draw_board()

    def _on_job_done(self, job, result):
        kind = job[0]
        if not result.get("ok", True):
            err = result.get("error") or "失败"
            if kind == "undo" and "cannot undo" in err:
                self._set_status("无可悔棋")
            else:
                self._set_status(f"引擎拒绝：{err}")
            return
        if kind == "newgame":
            self.stones, self.prev_stones = {}, {}
            self.numbers = {}
            self.captures = {BLACK: 0, WHITE: 0}
            self.moves = []
            self._snapshots = []
            self.last_move = None
            self.move_count = 0
            self.game_over = False
            self.result_text = ""
            self.candidates = []
            self.eval_text = ""
            self.pv_text = ""
            self.turn = BLACK
            self.engine.analyze_desired = True
            self.eval_label.config(text="")
            self.pv_label.config(text="")
            self._set_status("新对局")
            self.engine.submit(("board", self.size.get()))
        elif kind == "board":
            self._sync_board(result["stones"])
        elif kind == "play":
            color, vtx = job[1], job[2]
            self._register_move(color, vtx)
            self.engine.submit(("board", self.size.get()))
        elif kind == "genmove":
            move = result.get("move")
            if not move or move == "resign":
                self._set_status("引擎投子认负")
                self.game_over = True
                return
            color = job[1]
            self._register_move(color, move)
            self.engine.submit(("board", self.size.get()))
        elif kind == "undo":
            if self.moves:
                self.moves.pop()
            self.move_count = max(0, self.move_count - 1)
            self.game_over = False
            self.result_text = ""
            # 恢复被撤销那手的派生状态（手数标注 / 提子计数 / 最后一手）
            if self._snapshots:
                self._snapshots.pop()
                if self._snapshots:
                    st, num, cap, lm = self._snapshots[-1]
                    self.stones = dict(st)
                    self.numbers = dict(num)
                    self.captures = dict(cap)
                    self.last_move = lm
            self.engine.analyze_desired = True
            self.engine.submit(("board", self.size.get()))
        elif kind == "score":
            self.result_text = result.get("text", "?")
            self._set_status(f"对局结束：{self.result_text}")

    def _register_move(self, color, vtx):
        self.moves.append((color, vtx))
        self.move_count += 1
        if vtx == "pass":
            self.last_move = None
            self._set_status(f"{'黑' if color == BLACK else '白'}方停一手"
                             f"（第 {self.move_count} 手）")
        else:
            self.last_move = vertex_to_xy(vtx, self.size.get())
        self.turn = BLACK if len(self.moves) % 2 == 0 else WHITE
        self._chain_gen += 1

    def _sync_board(self, stones):
        """Diff the new showboard snapshot into numbers / captures."""
        removed = [p for p in self.stones if p not in stones]
        added = [p for p in stones if p not in self.stones]
        for p in removed:
            color = self.stones[p]
            self.captures[WHITE if color == BLACK else BLACK] += 1
            self.numbers.pop(p, None)
        for p in added:
            self.numbers[p] = self.move_count
        self.stones = stones
        if self.moves and self.moves[-1][1] != "pass":
            self.last_move = vertex_to_xy(self.moves[-1][1], self.size.get())
        else:
            self.last_move = None
        # 快照：悔棋时恢复手数标注 / 提子计数（引擎盘面之外的全部派生状态）
        self._snapshots.append((dict(self.stones), dict(self.numbers),
                                dict(self.captures), self.last_move))
        cap_text = f"提子 黑{self.captures[BLACK]} 白{self.captures[WHITE]}"
        if self.game_over:
            pass
        elif self.move_count and self.moves[-1][1] == "pass":
            passes = 0
            for _c, v in reversed(self.moves):
                if v == "pass":
                    passes += 1
                else:
                    break
            if passes >= 2:
                self.game_over = True
                self.engine.analyze_desired = False
                self.engine.submit(("score",))
                self._set_status("双方连续停一手，计算胜负…")
            else:
                self._set_status(f"{'黑' if self.turn == BLACK else '白'}方行棋"
                                 f"（第 {self.move_count + 1} 手）· {cap_text}")
        else:
            self._set_status(f"{'黑' if self.turn == BLACK else '白'}方行棋"
                             f"（第 {self.move_count + 1} 手）· {cap_text}")
        # 先清 busy 再绘制：即使绘制抛异常也不会卡死对弈状态机。
        self.job_pending = False
        self.draw_board()
        self._maybe_chain()

    def _maybe_chain(self):
        """AI vs AI auto-play: schedule the next genmove when it is an AI
        side's turn, the chain is on, and the game is live."""
        if self.game_over or self.job_pending or not self.engine_ready:
            return
        if not self.chain.get():
            return
        if self.turn == BLACK and self.black_ai.get():
            pass
        elif self.turn == WHITE and self.white_ai.get():
            pass
        else:
            return
        gen = self._chain_gen
        self.root.after(350, lambda: self._auto_genmove(gen))

    def _auto_genmove(self, gen):
        if gen != self._chain_gen or self.game_over or self.job_pending:
            return
        if self.turn == BLACK and not self.black_ai.get():
            return
        if self.turn == WHITE and not self.white_ai.get():
            return
        self.job_pending = True
        visits = self._visits()
        self.engine.submit(("genmove", self.turn, visits))

    # ------------------------------------------------------------------
    # 面板与交互
    # ------------------------------------------------------------------
    def _build_panel(self):
        panel = tk.Frame(self.root, width=PANEL_W, padx=8, pady=6)
        panel.pack(side=tk.RIGHT, fill=tk.Y)
        panel.pack_propagate(False)

        self.status_label = tk.Label(panel, text="引擎启动中…",
                                     font=("微软雅黑", 11, "bold"),
                                     wraplength=PANEL_W - 20, justify=tk.LEFT)
        self.status_label.pack(anchor=tk.W, pady=(0, 4))
        self.eval_label = tk.Label(panel, text="", fg=EVAL_FG,
                                   font=("Arial", 10, "bold"),
                                   wraplength=PANEL_W - 20, justify=tk.LEFT)
        self.eval_label.pack(anchor=tk.W)
        self.pv_label = tk.Label(panel, text="", fg="#555555",
                                 font=("Arial", 8),
                                 wraplength=PANEL_W - 20, justify=tk.LEFT)
        self.pv_label.pack(anchor=tk.W, pady=(0, 6))

        row = tk.Frame(panel)
        row.pack(fill=tk.X)
        tk.Checkbutton(row, text="黑棋AI", variable=self.black_ai).pack(
            side=tk.LEFT)
        tk.Checkbutton(row, text="白棋AI", variable=self.white_ai).pack(
            side=tk.LEFT, padx=(8, 0))
        tk.Checkbutton(panel, text="自动续弈（双方AI时自动落子）",
                       variable=self.chain).pack(anchor=tk.W)

        btns = tk.Frame(panel)
        btns.pack(fill=tk.X, pady=4)
        tk.Button(btns, text="新对局", command=self._new_game).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(btns, text="悔棋", command=self._undo).pack(
            side=tk.LEFT, padx=(4, 0))
        tk.Button(btns, text="停一手", command=self._pass).pack(
            side=tk.LEFT, padx=(4, 0))

        tk.Label(panel, text="棋盘尺寸（新对局生效）", font=("Arial", 8),
                 fg="#555555").pack(anchor=tk.W, pady=(6, 0))
        size_row = tk.Frame(panel)
        size_row.pack(fill=tk.X)
        for n in BOARD_SIZES:
            tk.Radiobutton(size_row, text=str(n), variable=self.size,
                           value=n).pack(side=tk.LEFT)

        kv = tk.Frame(panel)
        kv.pack(fill=tk.X, pady=(6, 0))
        tk.Label(kv, text="贴目:").pack(side=tk.LEFT)
        tk.Entry(kv, textvariable=self.komi_var, width=5).pack(side=tk.LEFT)
        tk.Label(kv, text="  每手访问数:").pack(side=tk.LEFT)
        tk.Entry(kv, textvariable=self.visits_var, width=6).pack(side=tk.LEFT)

        opt = tk.Frame(panel)
        opt.pack(fill=tk.X, pady=(6, 0))
        tk.Checkbutton(opt, text="显示手数", variable=self.show_numbers,
                       command=self.draw_board).pack(side=tk.LEFT)
        tk.Checkbutton(opt, text="环面提示", variable=self.hint_on,
                       command=self.draw_board).pack(side=tk.LEFT,
                                                     padx=(8, 0))
        hw = tk.Frame(panel)
        hw.pack(anchor=tk.W)
        tk.Label(hw, text="镜面宽度:", font=("Arial", 8)).pack(side=tk.LEFT)
        tk.Radiobutton(hw, text="2格", variable=self.hint_width, value=2,
                       command=self.draw_board).pack(side=tk.LEFT)
        tk.Radiobutton(hw, text="4格", variable=self.hint_width, value=4,
                       command=self.draw_board).pack(side=tk.LEFT)
        tk.Label(panel, text="说明：规则全部由 KataGo 执行（chinese 规则：\n"
                             "提子、禁自杀、全局禁同形）；胜率/目差为黑方\n"
                             "视角。道棋特性来自 DAOQI 网络（daoqi_katago/）。",
                 font=("Arial", 8), fg="#777777", justify=tk.LEFT).pack(
            anchor=tk.W, pady=(10, 0))

    def _komi(self):
        try:
            v = float(str(self.komi_var.get()).strip())
        except (TypeError, ValueError):
            return 5.5
        return v

    def _visits(self):
        try:
            v = int(str(self.visits_var.get()).strip())
        except (TypeError, ValueError):
            return 200
        return max(8, min(v, 2000))

    def _set_status(self, text):
        self.status_label.config(text=text)

    def _busy_guard(self):
        if not self.engine_ready:
            self._set_status("引擎尚未就绪")
            return True
        if self.job_pending:
            self._set_status("引擎思考中，请稍候…")
            return True
        if self.game_over:
            self._set_status(f"对局已结束：{self.result_text}（点“新对局”）")
            return True
        return False

    def _new_game(self):
        if self.job_pending:
            return
        if self.engine is None or not self.engine.alive:
            self._start_engine()      # 引擎未起/已退出：重新拉起
            return
        self.job_pending = True
        self.engine.analyze_desired = True
        self.engine.submit(("newgame", self.size.get(), self._komi()))

    def _undo(self):
        if self._busy_guard():
            return
        self.job_pending = True
        self.engine.submit(("undo",))

    def _pass(self):
        if self._busy_guard():
            return
        self.job_pending = True
        self.engine.submit(("play", self.turn, "pass"))

    def _on_click(self, event):
        xy = self._hit_actual(event)
        if xy is None or self._busy_guard():
            return
        if (self.turn == BLACK and self.black_ai.get()) or \
                (self.turn == WHITE and self.white_ai.get()):
            self._set_status("轮到 AI 行棋（可勾掉该侧 AI 或点“悔棋”）")
            return
        x, y = xy
        if (x, y) in self.stones:
            return
        self.job_pending = True
        self.engine.submit(("play", self.turn, xy_to_vertex(x, y, self.size.get())))

    def _on_move(self, event):
        self.hover = self._hit_actual(event)
        self.draw_board()

    def _on_leave(self, _event=None):
        self.hover = None
        self.draw_board()

    # ------------------------------------------------------------------
    # 绘制（环面镜面 UI，与主项目同一套视觉）
    # ------------------------------------------------------------------
    def _pad(self):
        if not self.hint_on.get():
            return 0
        return 4 if self.hint_width.get() >= 4 else 2

    def _geometry(self):
        pad = self._pad()
        n = self.size.get() + 2 * pad
        cell = CELL
        ox = MARGIN + pad * cell
        oy = MARGIN + pad * cell
        w = n * cell + 2 * MARGIN
        h = n * cell + 2 * MARGIN
        return pad, cell, ox, oy, w, h

    def _draw_grid(self):
        self.canvas.delete("all")
        pad, cell, ox, oy, w, h = self._geometry()
        self.canvas.configure(width=w, height=h)
        n = self.size.get()
        # 网格：实际区域实线，镜面区 50% 白
        for i in range(n + 2 * pad):
            gx = ox + (i - pad) * cell
            gy = oy + (i - pad) * cell
            outside = i < pad or i >= n + pad
            colour = "#ffffff" if outside else "black"
            self.canvas.create_line(gx, oy - pad * cell, gx,
                                    oy + (n - 1 + pad) * cell,
                                    fill=colour)
            self.canvas.create_line(ox - pad * cell, gy,
                                    ox + (n - 1 + pad) * cell, gy,
                                    fill=colour)
        # 实际区域粗镜框
        self.canvas.create_rectangle(ox - cell / 2 - 2, oy - cell / 2 - 2,
                                     ox + (n - 1) * cell + cell / 2 + 2,
                                     oy + (n - 1) * cell + cell / 2 + 2,
                                     outline=FAKE_FRAME, width=3)
        for sx, sy in STAR_POINTS.get(n, ()):   # 星位（含镜像）
            for dx in (-n, 0, n):
                for dy in (-n, 0, n):
                    px, py = sx + dx, sy + dy
                    if not (0 <= px < n + 2 * pad and 0 <= py < n + 2 * pad):
                        continue
                    cx = ox + (px - pad) * cell
                    cy = oy + (py - pad) * cell
                    fill = "black" if (0 <= sx < n and 0 <= sy < n) \
                        else self._mix("black", 0.5)
                    self.canvas.create_oval(cx - 2, cy - 2, cx + 2, cy + 2,
                                            fill=fill, outline=fill)

    @staticmethod
    def _mix(color, ratio_to_bg):
        """把颜色向棋盘底色混合 ratio_to_bg（镜面区 50% 淡色）。
        支持 Tk 颜色名（black/white/red）与 #rrggbb。"""
        named = {"black": "#000000", "white": "#ffffff", "red": "#ff0000"}
        color = named.get(color, color)
        bg = (0xF0, 0xD6, 0x8C)
        try:
            rgb = (int(color[1:3], 16), int(color[3:5], 16),
                   int(color[5:7], 16))
        except ValueError:
            return color
        mixed = tuple(int(c * (1 - ratio_to_bg) + b * ratio_to_bg)
                      for c, b in zip(rgb, bg))
        return "#%02x%02x%02x" % mixed

    def _center(self, disp_x, disp_y):
        """显示格索引（0..n+2pad-1）-> 画布像素。"""
        pad, cell, ox, oy, _w, _h = self._geometry()
        return ox + (disp_x - pad) * cell, oy + (disp_y - pad) * cell

    def _copies(self, x, y):
        """(x, y) 及其环面镜像的显示格坐标。"""
        n = self.size.get()
        pad = self._pad()
        out = []
        for dx in (-n, 0, n):
            for dy in (-n, 0, n):
                px, py = x + pad + dx, y + pad + dy
                if 0 <= px < n + 2 * pad and 0 <= py < n + 2 * pad:
                    out.append((px, py, dx == 0 and dy == 0))
        return out

    def draw_board(self):
        self._draw_grid()
        _pad, cell, _ox, _oy, _w, _h = self._geometry()
        r = cell // 2 - 2
        for (x, y), color in self.stones.items():
            for px, py, actual in self._copies(x, y):
                cx, cy = self._center(px, py)
                fill = "black" if color == BLACK else "white"
                if not actual:
                    fill = self._mix(fill, 0.5)
                self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                        fill=fill, outline="black", width=1)
                if self.show_numbers.get() and actual:
                    num = self.numbers.get((x, y))
                    if num:
                        self.canvas.create_text(
                            cx, cy, text=str(num),
                            fill="white" if color == BLACK else "black",
                            font=("Arial", max(8, cell // 3 - 2)))
        if self.last_move:
            for px, py, actual in self._copies(*self.last_move):
                cx, cy = self._center(px, py)
                colour = "red" if actual else self._mix("red", 0.5)
                self.canvas.create_oval(cx - r - 2, cy - r - 2,
                                        cx + r + 2, cy + r + 2,
                                        outline=colour, width=2)
        # 候选点：行棋方视角胜率
        for x, y, wr in self.candidates:
            if (x, y) in self.stones:
                continue
            for px, py, actual in self._copies(x, y):
                cx, cy = self._center(px, py)
                colour = "#1a7f1a" if actual else self._mix("#1a7f1a", 0.5)
                self.canvas.create_rectangle(cx - 8, cy - 8, cx + 8, cy + 8,
                                             outline=colour, width=2)
                if actual:
                    self.canvas.create_text(
                        cx, cy, text=f"{wr * 100:.0f}", fill=colour,
                        font=("Arial", 8, "bold"))
        if self.hover and not self.game_over and (self.hover not in self.stones):
            x, y = self.hover
            pad = self._pad()
            cx, cy = self._center(x + pad, y + pad)
            fill = "black" if self.turn == BLACK else "white"
            self.canvas.create_oval(cx - r + 2, cy - r + 2,
                                    cx + r - 2, cy + r - 2,
                                    fill=self._mix(fill, 0.55), outline="")

    def _hit_actual(self, event):
        pad, cell, ox, oy, _w, _h = self._geometry()
        n = self.size.get()
        gx = round((event.x - ox) / cell) + pad
        gy = round((event.y - oy) / cell) + pad
        if not (0 <= gx < n + 2 * pad and 0 <= gy < n + 2 * pad):
            return None
        x, y = gx % n, gy % n
        return x, y

    # ------------------------------------------------------------------
    def _poll(self):
        try:
            while True:
                kind, *payload = self.tkq.get_nowait()
                if kind == "engine":
                    self._on_engine_event(payload[0])
        except queue.Empty:
            pass
        except Exception:
            pass
        self.root.after(80, self._poll)

    def _on_close(self):
        if self.engine is not None:
            try:
                self.engine.quit()
            except Exception:
                pass
        try:
            self.root.destroy()
        except Exception:
            pass


def main():
    root = tk.Tk()
    DaoqiApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
