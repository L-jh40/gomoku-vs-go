"""
gui.py - tkinter 可视化对弈界面 (威胁分析调用 board 模块)

符号映射（board.compute_threats() 返回的威胁类型 → 显示）：
  连五(实心圆) ← five_point
  四三获胜点/活三旁空格(三角形) ← four_three, open_four
  活二旁空格/眠三旁空格(大圆圈) ← rush_four, open_three
  活一旁空格/眠二旁空格(小圆圈) ← open_two, sleep_three
  眠一旁空格(红点) ← sleep_two
  活一/眠一 → 不显示
"""
from __future__ import annotations
import tkinter as tk
from tkinter import messagebox
import threading
import time

from board import EMPTY, BLACK, WHITE, HybridBoard
import rules
import ai_black
import ai_white
import ai_search

CELL = 30
MARGIN = 24
BOARD_SIZE = 15


class GameGUI:
    def __init__(self, root: tk.Tk, board_size: int = BOARD_SIZE,
                 black_is_ai: bool = True, white_is_ai: bool = True):
        self.root = root
        self.size = board_size
        self.board = HybridBoard(board_size)
        self.current = BLACK
        self.last_move: tuple[int, int] | None = None
        self.game_over = False
        self.ai_thinking = False
        self.pass_count = 0
        self.search_interrupt = threading.Event()
        self.last_even_depth = 0
        self.last_even_time = 0.0
        self.pending_ai_params = False
        self.search_epoch = 0
        self.replay_mode = False
        self.replay_black_moves: list[tuple[int, int]] = []
        self.replay_new_stones: set[tuple[int, int]] = set()
        self.replay_map: dict = {}
        self.replay_mode = False

        canvas_size = MARGIN * 2 + (board_size - 1) * CELL + 40
        self.canvas = tk.Canvas(root, width=canvas_size, height=canvas_size, bg="#f0d68c")
        self.canvas.pack(side=tk.LEFT)

        info_height = max(canvas_size, 720)
        self.info = tk.Frame(root, width=300, height=info_height)
        self.info.pack(side=tk.RIGHT, fill=tk.Y, padx=8, pady=8)
        self.info.pack_propagate(False)

        self.status_var = tk.StringVar(value="黑棋先行")
        tk.Label(self.info, textvariable=self.status_var, font=("Arial", 30, "bold")).pack(pady=4)
        self.stats_var = tk.StringVar(value="黑: 0  白: 0\n黑被吃: 0")
        tk.Label(self.info, textvariable=self.stats_var, font=("Arial", 11)).pack(pady=4)
        self.thinking_label = tk.Label(self.info, text="", fg="blue", font=("Arial", 10))
        self.thinking_label.pack(pady=2)
        self.depth_label = tk.Label(self.info, text="", fg="green", font=("Arial", 10))
        self.depth_label.pack(pady=2)

        tk.Button(self.info, text="新对局", command=self.new_game).pack(fill=tk.X, pady=3)
        tk.Button(self.info, text="悔棋", command=self.undo_move).pack(fill=tk.X, pady=3)
        tk.Button(self.info, text="Pass", command=self.human_pass).pack(fill=tk.X, pady=3)
        tk.Button(self.info, text="AI 立即落子", command=self.force_ai_current).pack(fill=tk.X, pady=3)

        self.black_ai_var = tk.IntVar(value=1 if black_is_ai else 0)
        self.white_ai_var = tk.IntVar(value=1 if white_is_ai else 0)
        tk.Checkbutton(self.info, text="黑棋 AI", variable=self.black_ai_var,
                       command=self.update_mode_label).pack(anchor=tk.W)
        tk.Checkbutton(self.info, text="白棋 AI", variable=self.white_ai_var,
                       command=self.update_mode_label).pack(anchor=tk.W)

        self.minimax_depth_var = tk.StringVar(value="2")
        depth_frame = tk.Frame(self.info)
        depth_frame.pack(fill=tk.X, pady=2)
        tk.Label(depth_frame, text="Minimax 层数:", font=("Arial", 9)).pack(side=tk.LEFT)
        for depth_value in (0, 2, 4, 6, 8):
            tk.Radiobutton(
                depth_frame,
                text=str(depth_value),
                variable=self.minimax_depth_var,
                value=str(depth_value),
            ).pack(side=tk.LEFT)

        self.min_search_time_var = tk.StringVar(value="0")
        time_frame = tk.Frame(self.info)
        time_frame.pack(fill=tk.X, pady=2)
        tk.Label(time_frame, text="最短搜索时间(s):", font=("Arial", 9)).pack(side=tk.LEFT)
        tk.Entry(time_frame, textvariable=self.min_search_time_var, width=6).pack(side=tk.LEFT)

        self.show_moves_var = tk.IntVar(value=0)
        tk.Checkbutton(self.info, text="显示手数", variable=self.show_moves_var,
                       command=self.draw_board).pack(anchor=tk.W)
        self.hint_var = tk.IntVar(value=0)
        tk.Checkbutton(self.info, text="玩家落子提示", variable=self.hint_var,
                       command=self.draw_board).pack(anchor=tk.W)
        self.forbidden_blue_var = tk.IntVar(value=0)
        tk.Checkbutton(
            self.info,
            text="AI算法加入禁手判断",
            variable=self.forbidden_blue_var,
        ).pack(anchor=tk.W)
        self.cancel_resign_var = tk.IntVar(value=0)
        tk.Checkbutton(self.info, text="取消投子认负", variable=self.cancel_resign_var).pack(anchor=tk.W)

        win_frame = tk.Frame(self.info)
        win_frame.pack(fill=tk.X, pady=2)
        tk.Label(win_frame, text="白棋获胜:", font=("Arial", 9)).pack(side=tk.LEFT)
        self.white_win_var = tk.StringVar(value="line_block")
        tk.Radiobutton(win_frame, text="全线封堵", variable=self.white_win_var,
                       value="line_block").pack(side=tk.LEFT)
        tk.Radiobutton(win_frame, text="占领全盘", variable=self.white_win_var,
                       value="occupy").pack(side=tk.LEFT)

        self.auto_white_win_var = tk.IntVar(value=1)
        tk.Checkbutton(self.info, text="自动判定白棋获胜", variable=self.auto_white_win_var).pack(anchor=tk.W)
        tk.Button(self.info, text="手动判定白棋获胜", command=self.manual_white_win_check).pack(fill=tk.X, pady=2)

        self.mode_label = tk.Label(self.info, text="", font=("Arial", 9), fg="gray")
        self.mode_label.pack(pady=2)

        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<Button-3>", self.on_right_click)
        self.root.bind("<Map>", self._on_window_map)
        self.draw_board()
        self.update_mode_label()

        if self.black_ai_var.get() and self.current == BLACK:
            self.root.after(300, self.maybe_play_ai)

    def _on_window_map(self, _event=None):
        self.root.after_idle(self._refresh_after_map)

    def _refresh_after_map(self):
        self.root.update_idletasks()
        self.draw_board()
        self.canvas.update_idletasks()

    # ---------- 模式 ----------
    def black_is_human(self): return not self.black_ai_var.get()
    def white_is_human(self): return not self.white_ai_var.get()

    def update_mode_label(self):
        if self.ai_thinking:
            self.pending_ai_params = True
            return
        bh = "人类" if self.black_is_human() else "AI"
        wh = "人类" if self.white_is_human() else "AI"
        self.mode_label.config(
            text=(
                f"模式: 黑({bh}) vs 白({wh})\n"
                f"Minimax {self.minimax_depth_var.get()} 层 | 点击棋盘落子 | 右键自动应对"
            )
        )
        self.draw_board()

    # ---------- 绘制 ----------
    def draw_board(self):
        self.canvas.delete("all")
        size = self.size
        # 棋盘线
        for i in range(size):
            x0 = MARGIN + i * CELL
            self.canvas.create_line(x0, MARGIN, x0, MARGIN + (size - 1) * CELL)
            self.canvas.create_line(MARGIN, x0, MARGIN + (size - 1) * CELL, x0)

        # 星位
        star_points = []
        if size == 15:
            star_points = [(3, 3), (3, 11), (11, 3), (11, 11), (7, 7)]
        elif size == 19:
            star_points = [(3, 3), (3, 9), (3, 15), (9, 3), (9, 9), (9, 15), (15, 3), (15, 9), (15, 15)]
        for (sx, sy) in star_points:
            cx = MARGIN + sy * CELL
            cy = MARGIN + sx * CELL
            self.canvas.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill="black")

        # 手数映射
        move_numbers = {}
        if self.show_moves_var.get():
            move_numbers = self.board.get_move_numbers()

        # ----- 白棋领地标识 (仅提示开启时绘制) -----
        dead_black = set()
        if self.hint_var.get():
            dead_black = self.board.get_dead_black_stones() if hasattr(self.board, 'get_dead_black_stones') else set()

        # 绘制棋子（含白棋领地标记）
        for x in range(size):
            for y in range(size):
                v = self.board.grid[x, y]
                if v != EMPTY:
                    is_dead = (v == BLACK and (x, y) in dead_black)
                    self.draw_stone(x, y, v, move_numbers.get((x, y)), dead_black=is_dead)

        # 上一手红色轮廓
        if self.last_move and self.board.grid[self.last_move] != EMPTY:
            lx, ly = self.last_move
            cx = MARGIN + ly * CELL
            cy = MARGIN + lx * CELL
            r = (
                10
                if self.replay_mode and (lx, ly) in self.replay_new_stones
                else CELL // 2 - 2
            )
            self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline="red", width=2)

        # 落子提示最后绘制：蓝叉 -> 领地 -> 红色位置（含胜势黄色标记）
        if self.hint_var.get():
            self._draw_hints()

    def draw_stone(self, x, y, color, move_num=None, dead_black=False):
        cx = MARGIN + y * CELL
        cy = MARGIN + x * CELL
        r = (
            10
            if self.replay_mode and (x, y) in self.replay_new_stones
            else CELL // 2 - 2
        )
        fill = "black" if color == BLACK else "white"
        self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=fill, outline="black")
        # ----- 白棋领地标识：黑子上层绘制灰色小方格 -----
        if dead_black:
            s = 6
            self.canvas.create_rectangle(cx - s, cy - s, cx + s, cy + s,
                                         fill="gray", outline="darkgray")
        if move_num is not None:
            text_color = "white" if color == BLACK else "black"
            self.canvas.create_text(cx, cy, text=str(move_num), fill=text_color, font=("Arial", 8, "bold"))

    def _draw_hints(self):
        size = self.size
        # ----- 白棋领地标识：空格死位灰方格 -----
        dead = self.board.get_dead_positions()
        for (x, y) in dead:
            cx = MARGIN + y * CELL
            cy = MARGIN + x * CELL
            s = 6
            self.canvas.create_rectangle(cx - s, cy - s, cx + s, cy + s,
                                         fill="white", outline="gray", stipple="gray50")

        # 禁手与无气（蓝色叉）
        for x in range(size):
            for y in range(size):
                if self.board.grid[x, y] != EMPTY:
                    continue
                ok, ftype = rules.is_black_legal_move(self.board, x, y)
                if not ok and ftype in ("overline", "three_three", "four_four", "self_capture"):
                    cx = MARGIN + y * CELL
                    cy = MARGIN + x * CELL
                    r = 6
                    self.canvas.create_line(cx - r, cy - r, cx + r, cy + r, fill="blue", width=2)
                    self.canvas.create_line(cx - r, cy + r, cx + r, cy - r, fill="blue", width=2)

        # 威胁标记（数据直接来自 board.compute_threats()）
        threats = self.board.compute_threats()
        for (x, y), t in threats.items():
            if self.board.grid[x, y] != EMPTY:
                continue
            cx = MARGIN + y * CELL
            cy = MARGIN + x * CELL
            if t == "five_point":
                r = 8
                self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill="red", outline="darkred")
            elif t in ("four_three", "open_four"):
                r = 8
                if not ai_search.triangle_is_hollow(self.board, (x, y)):
                    self.canvas.create_polygon(
                        cx, cy - r, cx - r, cy + r, cx + r, cy + r,
                        fill="red", outline="darkred",
                    )
                else:
                    self.canvas.create_polygon(
                        cx, cy - r, cx - r, cy + r, cx + r, cy + r,
                        outline="red", width=2,
                    )
            elif t in ("rush_four", "open_three"):
                r = 8
                self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline="red", width=2)
            elif t in ("open_two", "sleep_three"):
                r = 5
                self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline="red", width=2)
            elif t == "sleep_two":
                self.canvas.create_oval(cx - 2, cy - 2, cx + 2, cy + 2, fill="red", outline="red")

    # ---------- 交互 ----------
    def on_click(self, event):
        if self.game_over or self.ai_thinking:
            return
        x = round((event.y - MARGIN) / CELL)
        y = round((event.x - MARGIN) / CELL)
        if not (0 <= x < self.size and 0 <= y < self.size):
            return
        if self.replay_mode and self.current == BLACK:
            return
        if self.current == BLACK and self.black_is_human():
            self.try_play_black(x, y)
        elif self.current == WHITE and (self.white_is_human() or self.replay_mode):
            self.try_play_white(x, y)

    def on_right_click(self, event):
        if self.game_over or self.ai_thinking:
            return
        if not self.hint_var.get():
            messagebox.showinfo("提示", "请先开启“玩家落子提示”以使用右键自动应对。")
            return

        threats = self.board.compute_threats()
        five_points = [pos for pos, t in threats.items() if t == "five_point"]
        if len(five_points) > 1:
            self.end_game("黑棋有多个连五威胁, 白棋无法全部阻断. 黑棋必胜!")
            return
        if len(five_points) == 1:
            bx, by = five_points[0]
            ok, _ = self.board.play_white(bx, by)
            if ok:
                self.last_move = (bx, by)
                if self.check_white_win():
                    self.draw_board(); self.update_info()
                    return
                self.current = BLACK
                self.draw_board(); self.update_info()
                self.root.after(300, self.maybe_play_ai)
            else:
                messagebox.showwarning("错误", "自动阻断失败")
            return

        blocking, black_wins = self.board.find_blocking_moves()
        if black_wins:
            self.end_game("黑棋有多个连五威胁, 白棋无法全部阻断. 黑棋必胜!")
            return
        if len(blocking) == 1:
            bx, by = blocking[0]
            ok, _ = self.board.play_white(bx, by)
            if ok:
                self.last_move = (bx, by)
                if self.check_white_win():
                    self.draw_board(); self.update_info()
                    return
                self.current = BLACK
                self.draw_board(); self.update_info()
                self.root.after(300, self.maybe_play_ai)
        elif len(blocking) == 0:
            messagebox.showinfo("提示", "黑棋当前无连五威胁, 无需阻断.")
        else:
            names = ", ".join(f"({x},{y})" for x, y in blocking)
            messagebox.showinfo("提示", f"有 {len(blocking)} 处可阻断: {names}\n请手动选择.")

    def try_play_black(self, x, y):
        if not self.board.is_empty(x, y): return
        ok, ftype = rules.is_black_legal_move(self.board, x, y)
        if not ok:
            msgs = {"overline": "长连禁手", "three_three": "三三禁手", "four_four": "四四禁手",
                    "self_capture": "自吃 (不可送死)", "occupied": "位置已占"}
            messagebox.showwarning("禁手", f"黑棋下 ({x},{y}): {msgs.get(ftype, ftype)}")
            return
        ok2, _ = self.board.play_black(x, y)
        if not ok2:
            messagebox.showwarning("错误", f"黑棋下 ({x},{y}) 失败")
            return
        self.last_move = (x, y)
        if self.board.check_black_five(x, y):
            self.draw_board(); self.update_info(); self.end_game("黑棋连五, 黑胜!")
            return
        self.current = WHITE
        self.draw_board(); self.update_info()
        self.root.after(300, self.maybe_play_ai)

    def try_play_white(self, x, y):
        if not self.board.is_empty(x, y): return
        ok, _ = self.board.play_white(x, y)
        if not ok: return
        if self.replay_mode:
            self.replay_new_stones.add((x, y))
        self.last_move = (x, y)
        if self.check_white_win():
            self.draw_board(); self.update_info()
            return
        self.current = BLACK
        self.draw_board(); self.update_info()
        self.root.after(300, self.maybe_play_ai)

    def force_ai_current(self):
        if self.game_over:
            return
        if self.ai_thinking:
            # 先更新绿色（总用时/深度区域），再更新蓝色搜索状态。
            self.depth_label.config(text="正在立即落子...")
            self.root.update()
            self.search_interrupt.set()
            self.thinking_label.config(text="AI搜索中（立即落子）...")
            return
        self.maybe_play_ai()

    def _stop_search(self):
        self.search_epoch += 1
        self.search_interrupt.set()
        self.ai_thinking = False

    def human_pass(self):
        if self.game_over:
            return
        if self.ai_thinking:
            self._stop_search()
        self._human_pass_now()

    def _human_pass_now(self):
        turn = "黑棋" if self.current == BLACK else "白棋"
        messagebox.showinfo("Pass", f"{turn}pass")
        self.pass_count += 1
        if self.pass_count >= 2:
            self.end_game("双方 Pass, 对局结束"); return
        self.current = WHITE if self.current == BLACK else BLACK
        self.last_move = None
        self.draw_board(); self.update_info()
        self.root.after(300, self.maybe_play_ai)

    def maybe_play_ai(self):
        if self.game_over or self.ai_thinking: return
        if self.replay_mode:
            if self.current == BLACK:
                self._play_replay_black()
            return
        if self.current == BLACK and self.black_ai_var.get():
            self.run_ai_move(BLACK)
        elif self.current == WHITE and self.white_ai_var.get():
            self.run_ai_move(WHITE)
        else:
            self.update_mode_label()

    def run_ai_move(self, color):
        self.ai_thinking = True
        self.pending_ai_params = False
        self.search_epoch += 1
        search_epoch = self.search_epoch
        self.search_interrupt.clear()
        self.last_even_depth = 0
        self.last_even_time = 0.0
        self.thinking_label.config(text="AI 搜索中...")
        self.root.update()

        def work():
            t0 = time.time()
            board_copy = self.board.copy()
            board_copy._update_forbidden_blue = bool(
                self.forbidden_blue_var.get()
            )
            max_depth = int(self.minimax_depth_var.get())
            try:
                min_search_time = float(self.min_search_time_var.get())
            except ValueError:
                min_search_time = 0.0
            if min_search_time < 0:
                min_search_time = 0.0

            def progress_callback(depth, elapsed_even):
                self.root.after(
                    0, self._update_search_progress, depth, elapsed_even
                )

            if color == BLACK:
                move, depth = ai_black.best_black_move_with_info(
                    board_copy,
                    time_limit=1.0,
                    max_depth=max_depth,
                    min_search_time=min_search_time,
                    interrupt_event=self.search_interrupt,
                    progress_callback=progress_callback,
                )
            else:
                move, depth = ai_white.best_white_move_with_info(
                    board_copy,
                    time_limit=1.0,
                    max_depth=max_depth,
                    min_search_time=min_search_time,
                    interrupt_event=self.search_interrupt,
                    progress_callback=progress_callback,
                )
            elapsed = time.time() - t0

            def apply():
                if search_epoch != self.search_epoch:
                    return
                self.ai_thinking = False
                self.search_interrupt.clear()
                if self.pending_ai_params:
                    self.pending_ai_params = False
                    self.update_mode_label()
                if self.last_even_depth:
                    self.thinking_label.config(
                        text=(
                            f"AI搜索中，用时: {self.last_even_time:.2f}s，"
                            f"深度: {self.last_even_depth}"
                        )
                    )
                else:
                    self.thinking_label.config(
                        text=f"AI搜索中，用时: {elapsed:.2f}s，深度: 0"
                    )
                self.depth_label.config(
                    text=f"上一步AI用时: {elapsed:.2f}s | 搜索深度: {depth}"
                )
                if move is None:
                    if color == BLACK:
                        if self.cancel_resign_var.get():
                            messagebox.showinfo("Pass", "黑棋pass")
                            self.status_var.set("黑棋pass")
                            self.pass_count += 1
                            if self.pass_count >= 2:
                                self.end_game("双方 Pass, 对局结束"); return
                            self.current = WHITE
                            self.last_move = None
                            self.draw_board(); self.update_info()
                            self.root.after(300, self.maybe_play_ai); return
                        else:
                            self.end_game("黑棋投子认负, 白胜"); return
                    else:
                        if not self.cancel_resign_var.get():
                            if ai_search.white_should_pass(board_copy):
                                # 没有候选点：白棋只 Pass，不认负。
                                self._human_pass_now()
                                return
                            # 投子认负：白棋在搜索深度内找不到能清除实心圆的安全点。
                            self._prompt_white_resign(board_copy); return
                        fallback = self._first_empty_white_move()
                        if fallback is None:
                            self.end_game("白棋投子认负, 黑胜"); return
                        fx, fy = fallback
                        ok, _ = self.board.play_white(fx, fy)
                        if not ok:
                            self.end_game("白棋投子认负, 黑胜"); return
                        if self.check_white_win():
                            self.last_move = (fx, fy)
                            self.draw_board(); self.update_info(); return
                        self.current = BLACK
                        self.last_move = (fx, fy)
                        self.pass_count = 0
                        self.draw_board(); self.update_info()
                        self.root.after(300, self.maybe_play_ai); return
                x, y = move
                if color == BLACK:
                    ok, _ = self.board.play_black(x, y)
                    if not ok: return
                    if self.board.check_black_five(x, y):
                        self.last_move = (x, y); self.draw_board(); self.update_info()
                        self.end_game("黑棋连五, 黑胜!"); return
                    self.current = WHITE
                else:
                    ok, _ = self.board.play_white(x, y)
                    if not ok: return
                    if self.check_white_win():
                        self.last_move = (x, y); self.draw_board(); self.update_info(); return
                    self.current = BLACK
                self.last_move = (x, y)
                self.pass_count = 0
                self.draw_board(); self.update_info()
                self.root.after(300, self.maybe_play_ai)
            self.root.after(0, apply)
        threading.Thread(target=work, daemon=True).start()

    def _update_search_progress(self, depth, elapsed):
        self.last_even_depth = depth
        self.last_even_time = elapsed
        self.thinking_label.config(
            text=f"AI搜索中，用时: {elapsed:.2f}s，深度: {depth}"
        )

    def _prompt_white_resign(self, board_copy=None):
        win = tk.Toplevel(self.root)
        win.title("投子认负")
        tk.Label(win, text="白棋投子认负，黑胜", font=("Arial", 12)).pack(
            padx=12, pady=10
        )
        btn_frame = tk.Frame(win)
        btn_frame.pack(pady=6)

        def confirm():
            win.destroy()
            self.game_over = True
            self.status_var.set("黑胜")

        def replay():
            win.destroy()
            path = []
            replay_map = {}
            if board_copy is not None:
                path = list(
                    getattr(board_copy, "_last_black_win_path", None) or []
                )
                replay_map = dict(
                    getattr(board_copy, "_black_replay_map", None) or {}
                )
            if not path and not replay_map:
                self.game_over = True
                self.status_var.set("黑胜")
                messagebox.showinfo("复盘", "未找到黑棋胜利路径，无法复盘")
                return
            self._start_black_win_replay(path, replay_map)

        tk.Button(btn_frame, text="确定", command=confirm).pack(
            side=tk.LEFT, padx=6
        )
        tk.Button(
            btn_frame, text="展示黑棋胜利路径", command=replay
        ).pack(side=tk.LEFT, padx=6)

    def _start_black_win_replay(self, black_path, replay_map=None):
        self.replay_mode = True
        self.replay_black_moves = list(black_path)
        self.replay_map = dict(replay_map or {})
        self.replay_new_stones = set()
        self.game_over = False
        self.ai_thinking = False
        self.search_interrupt.set()
        self.search_epoch += 1
        self.black_ai_var.set(0)
        self.white_ai_var.set(0)
        self.current = WHITE
        self.last_move = None
        self.pass_count = 0
        self.thinking_label.config(text="黑棋胜利复盘", fg="blue")
        self.depth_label.config(text="你执白棋，黑棋由AI自动走")
        self.draw_board()
        self.update_info()

    def _play_replay_black(self):
        move = self.replay_map.get(ai_search._board_signature(self.board))
        if move is None or not self.board.is_empty(*move):
            self.replay_mode = False
            return
        self.board.play_black(*move)
        self.replay_new_stones.add(move)
        self.last_move = move
        if self.board.check_black_five(*move):
            self.draw_board(); self.update_info()
            self.end_game("黑胜")
            return
        self.current = WHITE
        self.draw_board(); self.update_info()

    def _first_empty_white_move(self) -> tuple[int, int] | None:
        """白棋被要求不投子认负时，优先在实心圆/三角形落子，否则靠近中心。"""
        threats = self.board.compute_threats()
        for threat_type in ("five_point", "four_three", "open_four"):
            for pos, threat in threats.items():
                if threat == threat_type:
                    return pos

        best = None
        best_dist = 10**9
        for x in range(self.size):
            for y in range(self.size):
                if self.board.grid[x, y] != EMPTY:
                    continue
                dist = abs(x - self.size // 2) + abs(y - self.size // 2)
                if dist < best_dist:
                    best_dist = dist
                    best = (x, y)
        return best

    # ---------- 白棋获胜 ----------
    def check_white_win(self):
        if self.white_win_var.get() == "occupy":
            if self.board.white_wins_by_occupy():
                self.end_game("白棋占领全盘, 白胜!"); return True
        else:
            if self.auto_white_win_var.get() and self.board.white_wins_by_line_block():
                self.end_game("白棋封堵所有 5 连线路, 白胜!"); return True
        return False

    def manual_white_win_check(self):
        if self.game_over: return
        if self.board.white_wins_by_line_block():
            self.end_game("白棋封堵所有 5 连线路, 白胜!")
        elif self.board.white_wins_by_occupy():
            self.end_game("白棋占领全盘, 白胜!")
        else:
            self._show_unblocked_lines()
            messagebox.showinfo("判定", "白棋尚未获胜. 红线表示尚未封堵的 5 连线路.")
            self.draw_board()

    def _show_unblocked_lines(self):
        lines = self.board.get_unblocked_lines()
        for line in lines:
            x1, y1 = line[0]; x2, y2 = line[-1]
            cx1 = MARGIN + y1 * CELL; cy1 = MARGIN + x1 * CELL
            cx2 = MARGIN + y2 * CELL; cy2 = MARGIN + x2 * CELL
            self.canvas.create_line(cx1, cy1, cx2, cy2, fill="red", width=1)

    # ---------- 悔棋 ----------
    def undo_move(self):
        if self.ai_thinking:
            self._stop_search()
        self._undo_now()

    def _undo_now(self):
        self.replay_mode = False
        self.replay_black_moves = []
        self.replay_map = {}
        if not self.board.history:
            messagebox.showinfo("悔棋", "没有可悔的棋."); return
        self.board.undo()
        last = self.board.history[-1] if self.board.history else None
        self.current = BLACK if last is None else (WHITE if last[0] == BLACK else BLACK)
        self.last_move = (last[1], last[2]) if last else None
        self.game_over = False
        self.replay_mode = False
        self.thinking_label.config(text="")
        self.depth_label.config(text="")
        self.search_interrupt.clear()
        self.last_even_depth = 0
        self.last_even_time = 0.0
        self.draw_board(); self.update_info()
        if not self.game_over:
            self.root.after(300, self.maybe_play_ai)

    def update_info(self):
        n_b = self.board.black_stone_count()
        n_w = self.board.white_stone_count()
        cap_w = self.board.captured_count[WHITE]
        cap_b = self.board.captured_count[BLACK]
        turn = "●" if self.current == BLACK else "○"
        self.status_var.set(f"{turn} 行棋")
        cap_str = f"黑: {n_b}  白: {n_w}\n黑被白吃: {cap_w}"
        if cap_b > 0: cap_str += f"  黑自吃: {cap_b}"
        self.stats_var.set(cap_str)
        self.update_mode_label()

    def end_game(self, msg):
        self.game_over = True
        if "白胜" in msg or "白棋胜" in msg:
            short = "白胜"
        elif "黑胜" in msg or "黑棋胜" in msg:
            short = "黑胜"
        else:
            short = msg
        self.status_var.set(short)
        messagebox.showinfo("对局结束", msg)

    def new_game(self):
        if self.ai_thinking:
            self._stop_search()
        self._new_game_now()

    def _new_game_now(self):
        self.replay_mode = False
        self.replay_black_moves = []
        self.replay_map = {}
        self.board = HybridBoard(self.size)
        self.current = BLACK
        self.last_move = None
        self.game_over = False
        self.replay_mode = False
        self.ai_thinking = False
        self.pass_count = 0
        self.cancel_resign_var.set(0)
        self.thinking_label.config(text="")
        self.depth_label.config(text="")
        self.search_interrupt.clear()
        self.last_even_depth = 0
        self.last_even_time = 0.0
        self.draw_board(); self.update_info()
        if self.black_ai_var.get():
            self.root.after(300, self.maybe_play_ai)


def main():
    root = tk.Tk()
    root.title("混合规则对弈 - 黑五子+禁手 / 白围棋吃子")
    GameGUI(root, board_size=BOARD_SIZE, black_is_ai=True, white_is_ai=True)
    root.mainloop()

if __name__ == "__main__":
    main()
