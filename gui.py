"""
gui.py - tkinter windowed AI-vs-AI application.

Black plays Gomoku with forbidden-move restrictions; White plays Go and
captures zero-liberty black groups.  White wins by blocking every black
five line (or by capturing all black stones).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
import threading
import time

from board import EMPTY, BLACK, WHITE, HybridBoard, THREAT_MARKER
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
        self.last_move = None
        self.game_over = False
        self.ai_thinking = False
        self.pass_count = 0
        self.search_epoch = 0
        self.search_interrupt = threading.Event()

        # Replay / table mode.
        self.replay_mode = False
        self.replay_new_stones = set()
        self.replay_map = {}
        self.replay_black_moves = []
        self.black_table_mode = False
        self.replay_start_history_len = 0
        self.replay_pre_ai = (True, True)
        self.current_max_depth = 2
        self.active_dialog = None
        self.last_even_depth = 0
        self.last_even_time = 0.0
        self.last_layer_depth = 0
        self.last_layer_time = 0.0
        self.search_start_time = 0.0
        self._last_progress_ui_time = 0.0
        self.depth0_unfinished = False
        self.last_focused = False
        self.last_focused_depth = -1
        self.prev_layer_depth = -1
        self.prev_layer_time = 0.0
        self.pass_log: list[int] = []
        self.previous_game_snapshot = None
        self.moves_since_new_game = 0
        self.max_time_after_id = None

        self.dark_mode_var = tk.IntVar(value=0)
        self.board_bg = "#f0d68c"
        self.line_color = "black"
        self.star_color = "black"
        self.panel_bg = "#f0f0f0"
        self.fg_color = "black"

        canvas_size = MARGIN * 2 + (board_size - 1) * CELL + 20
        self.canvas = tk.Canvas(root, width=canvas_size, height=canvas_size,
                                bg=self.board_bg)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH)

        # Keep the window only as tall as the board / controls need.
        info_height = canvas_size + 80
        self.info = tk.Frame(root, width=300, height=info_height)
        self.info.pack(side=tk.RIGHT, fill=tk.Y, padx=6, pady=4)
        self.info.pack_propagate(False)

        self.status_var = tk.StringVar(value="黑棋先行")
        tk.Label(self.info, textvariable=self.status_var,
                 font=("Arial", 20, "bold")).pack(pady=(4, 1))

        self.stats_var = tk.StringVar(value="黑: 0  白: 0\n黑被吃: 0")
        tk.Label(self.info, textvariable=self.stats_var,
                 font=("Arial", 10)).pack(pady=1)

        self.thinking_label = tk.Label(self.info, text="", fg="blue",
                                       font=("Arial", 9))
        self.thinking_label.pack(pady=1)
        self.depth_label = tk.Label(self.info, text="", fg="green",
                                    font=("Arial", 9))
        self.depth_label.pack(pady=1)

        tk.Button(self.info, text="新对局", command=self.new_game).pack(
            fill=tk.X, pady=1)
        tk.Button(self.info, text="悔棋", command=self.undo_move).pack(
            fill=tk.X, pady=1)
        tk.Button(self.info, text="Pass", command=self.human_pass).pack(
            fill=tk.X, pady=1)
        tk.Button(self.info, text="AI 立即落子",
                  command=self.force_ai_current).pack(fill=tk.X, pady=1)

        self.black_ai_var = tk.IntVar(value=1 if black_is_ai else 0)
        self.white_ai_var = tk.IntVar(value=1 if white_is_ai else 0)
        tk.Checkbutton(self.info, text="黑棋 AI",
                       variable=self.black_ai_var,
                       command=self.update_mode_label).pack(anchor=tk.W)
        tk.Checkbutton(self.info, text="白棋 AI",
                       variable=self.white_ai_var,
                       command=self.update_mode_label).pack(anchor=tk.W)

        self.depth_var = tk.StringVar(value="2")
        frame = tk.Frame(self.info)
        frame.pack(fill=tk.X, pady=1)
        tk.Label(frame, text="Minimax 层数:", font=("Arial", 9)).pack(side=tk.LEFT)
        for value in (0, 2, 4, 6, 8):
            tk.Radiobutton(frame, text=str(value), variable=self.depth_var,
                           value=str(value),
                           command=self._on_depth_change).pack(side=tk.LEFT)

        self.min_search_time_var = tk.StringVar(value="0")
        time_frame = tk.Frame(self.info)
        time_frame.pack(fill=tk.X, pady=1)
        tk.Label(time_frame, text="最短搜索时间(s):",
                 font=("Arial", 9)).pack(side=tk.LEFT)
        tk.Entry(time_frame, textvariable=self.min_search_time_var,
                 width=6).pack(side=tk.LEFT)

        self.max_search_time_var = tk.StringVar(value="0")
        max_time_frame = tk.Frame(self.info)
        max_time_frame.pack(fill=tk.X, pady=1)
        tk.Label(max_time_frame, text="最长搜索时间(s):",
                 font=("Arial", 9)).pack(side=tk.LEFT)
        tk.Entry(max_time_frame, textvariable=self.max_search_time_var,
                 width=6).pack(side=tk.LEFT)

        self.hint_var = tk.IntVar(value=0)
        tk.Checkbutton(self.info, text="玩家落子提示",
                       variable=self.hint_var,
                       command=self.draw_board).pack(anchor=tk.W)
        self.show_moves_var = tk.IntVar(value=0)
        tk.Checkbutton(self.info, text="显示手数",
                       variable=self.show_moves_var,
                       command=self.draw_board).pack(anchor=tk.W)
        tk.Checkbutton(self.info, text="暗夜模式",
                       variable=self.dark_mode_var,
                       command=self.apply_theme).pack(anchor=tk.W)
        self.cancel_resign_var = tk.IntVar(value=0)
        tk.Checkbutton(self.info, text="取消投子认负",
                       variable=self.cancel_resign_var).pack(anchor=tk.W)

        win_frame = tk.Frame(self.info)
        win_frame.pack(fill=tk.X, pady=1)
        tk.Label(win_frame, text="白棋获胜:", font=("Arial", 9)).pack(side=tk.LEFT)
        self.white_win_var = tk.StringVar(value="line_block")
        tk.Radiobutton(win_frame, text="全线封堵", variable=self.white_win_var,
                       value="line_block").pack(side=tk.LEFT)
        tk.Radiobutton(win_frame, text="占领全盘", variable=self.white_win_var,
                       value="occupy").pack(side=tk.LEFT)

        self.auto_white_win_var = tk.IntVar(value=1)
        tk.Checkbutton(self.info, text="自动判定白棋获胜",
                       variable=self.auto_white_win_var).pack(anchor=tk.W)
        tk.Button(self.info, text="手动判定白棋获胜",
                  command=self.manual_white_win_check).pack(fill=tk.X, pady=1)

        self.mode_label = tk.Label(self.info, text="", font=("Arial", 9),
                                   fg="gray")
        self.mode_label.pack(pady=1)
        self._on_depth_change()

        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<Button-3>", self.on_right_click)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.apply_theme()
        self.update_mode_label()

        if self.black_ai_var.get() and self.current == BLACK:
            self.root.after(300, self.maybe_play_ai)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def black_is_human(self):
        return (not self.black_ai_var.get() and not self.black_table_mode
                and not self.replay_mode)

    def white_is_human(self):
        return not self.white_ai_var.get()

    def _on_close(self):
        self.search_interrupt.set()
        self._close_active_dialog()
        try:
            self.root.destroy()
        except Exception:
            pass

    def _restore_main_window(self):
        """Bring the main window back before showing dialogs / game-over UI.

        Tk on Windows can otherwise leave an iconified root behind a modal
        Toplevel grab, making the window impossible to reopen."""
        try:
            if self.root.state() == "iconic":
                self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        except Exception:
            pass

    def _on_depth_change(self):
        try:
            self.current_max_depth = int(self.depth_var.get())
        except ValueError:
            self.current_max_depth = 2
        self.update_mode_label()

    def apply_theme(self):
        if self.dark_mode_var.get():
            self.board_bg = "#4a3f1f"
            self.line_color = "#c9b56a"
            self.star_color = "#c9b56a"
            self.panel_bg = "#1e1e1e"
            self.fg_color = "#d8c88a"
        else:
            self.board_bg = "#f0d68c"
            self.line_color = "black"
            self.star_color = "black"
            self.panel_bg = "#f0f0f0"
            self.fg_color = "black"

        self.root.configure(bg=self.panel_bg)
        self.info.configure(bg=self.panel_bg)
        self.canvas.configure(bg=self.board_bg)
        self._apply_theme_to_widgets(self.info, self.panel_bg, self.fg_color)
        self.draw_board()

    def _apply_theme_to_widgets(self, parent, bg, fg):
        for child in parent.winfo_children():
            try:
                if isinstance(child, tk.Frame):
                    child.configure(bg=bg)
                    self._apply_theme_to_widgets(child, bg, fg)
                elif isinstance(child, tk.Label):
                    child.configure(bg=bg, fg=fg)
                elif isinstance(child, (tk.Button, tk.Checkbutton, tk.Radiobutton)):
                    child.configure(
                        bg=bg, fg=fg,
                        activebackground=bg, activeforeground=fg,
                        highlightthickness=0
                    )
                elif isinstance(child, tk.Entry):
                    child.configure(bg="#2b2b2b" if self.dark_mode_var.get() else "white",
                                    fg=fg, insertbackground=fg)
            except Exception:
                pass

    def update_mode_label(self):
        bh = "人类" if self.black_is_human() else "AI"
        wh = "人类" if self.white_is_human() else "AI"
        extra = " | 黑棋查表必胜" if self.black_table_mode else ""
        self.mode_label.config(
            text=f"模式: 黑({bh}) vs 白({wh}) | 深度 {self.depth_var.get()}{extra}"
        )
        self.draw_board()

    def update_info(self):
        nb = self.board.black_stone_count()
        nw = self.board.white_stone_count()
        cap = self.board.captured_count[WHITE]
        self.stats_var.set(f"黑: {nb}  白: {nw}\n黑被白吃: {cap}")
        if not self.game_over:
            turn = "● 黑棋" if self.current == BLACK else "○ 白棋"
            self.status_var.set(f"{turn} 行棋")

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def draw_board(self, with_hints=True):
        self.canvas.delete("all")
        self.canvas.configure(bg=self.board_bg)
        size = self.size
        for i in range(size):
            x0 = MARGIN + i * CELL
            self.canvas.create_line(
                x0, MARGIN, x0, MARGIN + (size - 1) * CELL, fill=self.line_color
            )
            self.canvas.create_line(
                MARGIN, x0, MARGIN + (size - 1) * CELL, x0, fill=self.line_color
            )

        star_points = []
        if size == 15:
            star_points = [(3, 3), (3, 11), (11, 3), (11, 11), (7, 7)]
        elif size == 19:
            star_points = [(3, 3), (3, 9), (3, 15), (9, 3), (9, 9),
                           (9, 15), (15, 3), (15, 9), (15, 15)]
        for sx, sy in star_points:
            cx = MARGIN + sy * CELL
            cy = MARGIN + sx * CELL
            self.canvas.create_oval(
                cx - 3, cy - 3, cx + 3, cy + 3, fill=self.star_color
            )

        move_numbers = {}
        if self.show_moves_var.get():
            move_numbers = self.get_move_numbers()

        dead = self.board.get_dead_positions() if with_hints else set()
        for x in range(size):
            for y in range(size):
                v = self.board.grid[x, y]
                if v != EMPTY:
                    self.draw_stone(x, y, v, move_numbers.get((x, y)),
                                    dead_black=(v == BLACK and (x, y) in dead))

        if self.last_move is not None and self.board.grid[self.last_move] != EMPTY:
            lx, ly = self.last_move
            cx = MARGIN + ly * CELL
            cy = MARGIN + lx * CELL
            r = 10 if self.replay_mode and (lx, ly) in self.replay_new_stones \
                else CELL // 2 - 2
            self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                    outline="red", width=2)

        if with_hints and self.hint_var.get():
            self.draw_hints(dead)

    def draw_stone(self, x, y, color, move_num=None, dead_black=False):
        cx = MARGIN + y * CELL
        cy = MARGIN + x * CELL
        r = 10 if self.replay_mode and (x, y) in self.replay_new_stones \
            else CELL // 2 - 2
        fill = "black" if color == BLACK else "white"
        self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                fill=fill, outline="black")
        if dead_black:
            s = 6
            self.canvas.create_rectangle(cx - s, cy - s, cx + s, cy + s,
                                         fill="gray", outline="darkgray")
        if move_num is not None:
            text_color = "white" if color == BLACK else "black"
            self.canvas.create_text(cx, cy, text=str(move_num),
                                    fill=text_color, font=("Arial", 8, "bold"))

    def draw_hints(self, dead):
        size = self.size
        # White territory: grey square on the upper layer.
        for x, y in dead:
            if self.board.grid[x, y] != EMPTY:
                continue
            cx = MARGIN + y * CELL
            cy = MARGIN + x * CELL
            s = 6
            self.canvas.create_rectangle(cx - s, cy - s, cx + s, cy + s,
                                         fill="white", outline="gray",
                                         stipple="gray50")

        # Blue crosses: forbidden / no-liberty points (cached).
        blue_crosses = self.board.get_blue_cross_positions()
        for x, y in blue_crosses:
            if not self.board.is_empty(x, y):
                continue
            cx = MARGIN + y * CELL
            cy = MARGIN + x * CELL
            r = 6
            self.canvas.create_line(cx - r, cy - r, cx + r, cy + r,
                                    fill="blue", width=2)
            self.canvas.create_line(cx - r, cy + r, cx + r, cy - r,
                                    fill="blue", width=2)

        # Red markers.
        threats = self.board.compute_threats()
        for (x, y), threat in threats.items():
            if not self.board.is_empty(x, y):
                continue
            cx = MARGIN + y * CELL
            cy = MARGIN + x * CELL
            if threat == "five_point":
                r = 8
                self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                        fill="red", outline="darkred")
            elif threat in ("four_three", "open_four"):
                r = 8
                if self.board.is_hollow_triangle((x, y), threat):
                    self.canvas.create_polygon(
                        cx, cy - r, cx - r, cy + r, cx + r, cy + r,
                        outline="red", width=2, fill=""
                    )
                else:
                    self.canvas.create_polygon(
                        cx, cy - r, cx - r, cy + r, cx + r, cy + r,
                        fill="red", outline="darkred"
                    )
            elif threat in ("rush_four", "open_three"):
                r = 8
                self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                        outline="red", width=2)
            elif threat in ("sleep_three", "open_two"):
                r = 5
                self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                        outline="red", width=2)
            elif threat == "sleep_two":
                self.canvas.create_oval(cx - 2, cy - 2, cx + 2, cy + 2,
                                        fill="red", outline="red")

    def get_move_numbers(self):
        out = {}
        for i, (color, x, y, captured) in enumerate(self.board.history):
            out[(x, y)] = i + 1
            for cx, cy in captured:
                out.pop((cx, cy), None)
        return out

    # ------------------------------------------------------------------
    # Interaction
    # ------------------------------------------------------------------
    def on_click(self, event):
        if self.game_over or self.ai_thinking:
            return
        x = round((event.y - MARGIN) / CELL)
        y = round((event.x - MARGIN) / CELL)
        if not self.board.in_bounds(x, y):
            return
        if self.replay_mode and self.current == BLACK:
            return
        if self.current == BLACK and self.black_is_human():
            self.try_play_black(x, y)
        elif self.current == WHITE and (self.white_is_human() or self.replay_mode):
            self.try_play_white(x, y)

    def on_right_click(self, _event=None):
        if self.game_over or self.ai_thinking or self.replay_mode:
            return
        if not self.hint_var.get():
            return
        if self.current == BLACK:
            if self.black_is_human():
                self.run_ai_move(BLACK)
        elif self.current == WHITE and self.white_is_human():
            self.run_ai_move(WHITE)

    def try_play_black(self, x, y):
        if not self.board.is_empty(x, y):
            return
        ok, _ftype = rules.is_black_legal_move(self.board, x, y)
        if not ok:
            messagebox.showinfo("禁手", "黑棋不能落在此处")
            return
        ok, _ = self.board.play_black(x, y)
        if not ok:
            messagebox.showinfo("落子失败", "黑棋不能落在此处")
            return
        self.last_move = (x, y)
        self.pass_count = 0
        self.pass_log = []
        self._register_move()
        if self.board.check_black_five(x, y):
            self.draw_board(with_hints=False)
            self.end_game("黑棋连五，黑胜!")
            return
        self.current = WHITE
        self.draw_board()
        self.update_info()
        self.root.after(300, self.maybe_play_ai)

    def try_play_white(self, x, y):
        if not self.board.is_empty(x, y):
            return
        ok, _ = self.board.play_white(x, y)
        if not ok:
            messagebox.showinfo("落子失败", "白棋不能落在此处")
            return
        if self.replay_mode:
            self.replay_new_stones.add((x, y))
        self.last_move = (x, y)
        self.pass_count = 0
        self.pass_log = []
        self._register_move()
        if self.check_white_win():
            return
        self.current = BLACK
        self.draw_board()
        self.update_info()
        self.root.after(300, self.maybe_play_ai)

    def human_pass(self):
        if self.game_over:
            return
        if self.ai_thinking:
            self._stop_search()
        self._pass_turn()

    def _pass_turn(self):
        self.pass_log.append(self.current)
        self.pass_count += 1
        # Only a black pass followed by a white pass ends the game.
        if self.pass_log[-2:] == [BLACK, WHITE]:
            self.end_game("黑棋 Pass + 白棋 Pass，对局结束")
            return
        self.current = WHITE if self.current == BLACK else BLACK
        self.last_move = None
        self.draw_board()
        self.update_info()
        self.root.after(300, self.maybe_play_ai)

    # ------------------------------------------------------------------
    # AI execution
    # ------------------------------------------------------------------
    def maybe_play_ai(self):
        if self.game_over or self.ai_thinking:
            return
        if self.replay_mode:
            if self.current == BLACK:
                self.play_replay_black()
            return
        if self.black_table_mode and self.current == BLACK:
            self.play_table_black()
            return
        if self.current == BLACK and self.black_ai_var.get():
            self.run_ai_move(BLACK)
        elif self.current == WHITE and self.white_ai_var.get():
            self.run_ai_move(WHITE)
        else:
            self.update_mode_label()

    def force_ai_current(self):
        if self.game_over:
            return
        if self.ai_thinking:
            # "AI 立即落子" during a search interrupts the current depth and
            # commits the last completed even-depth move.
            self.search_interrupt.set()
            return
        if self.replay_mode:
            return
        if self.current == BLACK:
            if not self.black_ai_var.get():
                return
        else:
            if not self.white_ai_var.get():
                return
        self.run_ai_move(self.current)

    def _cancel_max_search_timer(self):
        if self.max_time_after_id is not None:
            try:
                self.root.after_cancel(self.max_time_after_id)
            except Exception:
                pass
            self.max_time_after_id = None

    def _on_max_search_time(self):
        self.max_time_after_id = None
        if self.ai_thinking:
            # Same effect as clicking "AI 立即落子": interrupt the current
            # depth and commit the best completed/partial result.
            self.search_interrupt.set()

    def _stop_search(self):
        self.search_epoch += 1
        self.search_interrupt.set()
        self.ai_thinking = False
        self._cancel_max_search_timer()

    def run_ai_move(self, color):
        if self.game_over:
            return
        self.ai_thinking = True
        self.search_epoch += 1
        epoch = self.search_epoch
        self.search_interrupt.clear()
        self.last_even_depth = 0
        self.last_even_time = 0.0
        self.last_layer_depth = 0
        self.last_layer_time = 0.0
        self._last_progress_ui_time = 0.0
        self.depth0_unfinished = False
        self.last_focused = False
        self.last_focused_depth = -1
        self.prev_layer_depth = -1
        self.prev_layer_time = 0.0
        self.search_start_time = time.time()
        self.thinking_label.config(text="AI 搜索中...")
        self.root.update_idletasks()
        self._schedule_search_ticker()

        board_copy = self.board.copy()
        max_depth = self.current_max_depth
        try:
            min_search_time = float(self.min_search_time_var.get())
        except ValueError:
            min_search_time = 0.0
        if min_search_time < 0:
            min_search_time = 0.0
        try:
            max_search_time = float(self.max_search_time_var.get())
        except ValueError:
            max_search_time = 0.0
        if max_search_time < 0:
            max_search_time = 0.0

        if max_search_time > 0:
            self._cancel_max_search_timer()
            self.max_time_after_id = self.root.after(
                int(max_search_time * 1000), self._on_max_search_time
            )

        def progress_callback(completed_depth, elapsed_layer, finished=True,
                              focused=False):
            if focused:
                if completed_depth < self.last_focused_depth:
                    return
                self.last_focused_depth = completed_depth
            if completed_depth > self.last_layer_depth:
                self.prev_layer_depth = self.last_layer_depth
                self.prev_layer_time = self.last_layer_time
            self.last_even_depth = completed_depth
            self.last_even_time = elapsed_layer
            self.last_layer_depth = completed_depth
            self.last_layer_time = elapsed_layer
            self.depth0_unfinished = (completed_depth == 0 and not finished)
            self.last_focused = focused
            # Throttle actual Tk label updates: b is updated in the shared
            # variables immediately, but the main loop is poked at most
            # twice per second so depth-0 b updates do not slow the search.
            now = time.monotonic()
            if now - self._last_progress_ui_time >= 0.5:
                self._last_progress_ui_time = now
                self.root.after(
                    0, self._update_search_progress,
                    completed_depth, elapsed_layer
                )

        def work():
            t0 = time.time()
            try:
                if color == BLACK:
                    move, depth = ai_black.best_black_move_with_info(
                        board_copy, time_limit=None, max_depth=max_depth,
                        min_search_time=min_search_time,
                        interrupt_event=self.search_interrupt,
                        progress_callback=progress_callback
                    )
                else:
                    move, depth = ai_white.best_white_move_with_info(
                        board_copy, time_limit=None, max_depth=max_depth,
                        min_search_time=min_search_time,
                        interrupt_event=self.search_interrupt,
                        progress_callback=progress_callback
                    )
            except ai_search.SearchTimeout:
                move, depth = None, 0
            except Exception as exc:  # never leave GUI stuck
                move, depth = None, 0
                self.root.after(0, self._show_search_error, str(exc))
            elapsed = time.time() - t0

            def apply():
                if epoch != self.search_epoch:
                    return
                self._cancel_max_search_timer()
                self.ai_thinking = False
                self.search_interrupt.clear()
                total = time.time() - self.search_start_time
                b_time = self.prev_layer_time if self.prev_layer_depth >= 0 else (
                    self.last_layer_time if self.last_layer_time else total
                )
                if self.depth0_unfinished:
                    self.thinking_label.config(
                        text=f"AI搜索中，用时: {total:.2f}，未完成搜索"
                    )
                elif self.last_focused:
                    self.thinking_label.config(
                        text=(
                            f"AI专注搜索中，用时: {total:.2f}s / "
                            f"{b_time:.2f}s，深度: {self.last_layer_depth}"
                        )
                    )
                else:
                    self.thinking_label.config(
                        text=(
                            f"AI搜索中，用时: {total:.2f}s / "
                            f"{b_time:.2f}s，深度: {self.last_layer_depth}"
                        )
                    )
                self.depth_label.config(
                    text=f"上一步AI用时: {elapsed:.2f}s | 搜索深度: {depth}"
                )
                if move is None:
                    self.handle_no_move(color, board_copy)
                    return
                x, y = move
                if color == BLACK:
                    ok, _ = self.board.play_black(x, y)
                    if not ok:
                        self.end_game("黑棋 AI 落子失败")
                        return
                    self.last_move = (x, y)
                    self.pass_count = 0
                    self.pass_log = []
                    self._register_move()
                    # If the AI reported a forced table win, switch Black to
                    # table mode from now on.
                    if board_copy._black_replay_map or board_copy._last_black_win_path:
                        self.black_table_mode = True
                        self.replay_map = dict(board_copy._black_replay_map)
                        self.replay_black_moves = list(board_copy._last_black_win_path)
                    if self.board.check_black_five(x, y):
                        self.draw_board(with_hints=False)
                        self.end_game("黑棋连五，黑胜!")
                        return
                    self.current = WHITE
                else:
                    ok, _ = self.board.play_white(x, y)
                    if not ok:
                        self.end_game("白棋 AI 落子失败")
                        return
                    self.last_move = (x, y)
                    self.pass_count = 0
                    self.pass_log = []
                    self._register_move()
                    if self.check_white_win():
                        return
                    self.current = BLACK
                self.draw_board()
                self.update_info()
                self.root.after(300, self.maybe_play_ai)

            self.root.after(0, apply)

        threading.Thread(target=work, daemon=True).start()

    def _show_search_error(self, msg):
        self.ai_thinking = False
        self.thinking_label.config(text="")
        self._restore_main_window()
        messagebox.showerror("AI 错误", msg)

    def _update_search_progress(self, depth, elapsed):
        self.last_layer_depth = depth
        self.last_layer_time = elapsed
        self._refresh_thinking_label()

    def _schedule_search_ticker(self):
        self.root.after(2000, self._search_ticker)

    def _search_ticker(self):
        if not self.ai_thinking:
            return
        self._refresh_thinking_label()
        self._schedule_search_ticker()

    def _refresh_thinking_label(self):
        if self.search_start_time <= 0:
            return
        total = time.time() - self.search_start_time
        if self.ai_thinking and self.depth0_unfinished:
            self.thinking_label.config(
                text=f"AI搜索中，用时: {total:.2f}，未完成搜索"
            )
            return
        b_time = self.prev_layer_time if self.prev_layer_depth >= 0 else (
            self.last_layer_time if self.last_layer_time else total
        )
        if self.ai_thinking and self.last_focused:
            self.thinking_label.config(
                text=(
                    f"AI专注搜索中，用时: {total:.2f}s / {b_time:.2f}s，"
                    f"深度: {self.last_layer_depth}"
                )
            )
            return
        self.thinking_label.config(
            text=(
                f"AI搜索中，用时: {total:.2f}s / {b_time:.2f}s，"
                f"深度: {self.last_layer_depth}"
            )
        )

    def handle_no_move(self, color, board_copy=None):
        if color == BLACK:
            self._prompt_black_resign()
        else:
            if board_copy is not None and ai_search.white_should_pass(board_copy):
                self._pass_turn(manual=False)
            elif self.cancel_resign_var.get():
                self.play_fallback_white_move()
            else:
                self._prompt_white_resign(board_copy)

    def play_fallback_white_move(self):
        threats = self.board.compute_threats()
        for threat in ("five_point", "four_three", "open_four"):
            for pos, t in threats.items():
                if t == threat and self.board.is_empty(*pos):
                    self.try_play_white(*pos)
                    return
        for x in range(self.size):
            for y in range(self.size):
                if self.board.is_empty(x, y):
                    self.try_play_white(x, y)
                    return
        self.end_game("白棋投子认负，黑胜")

    # ------------------------------------------------------------------
    # Resign dialogs and replay
    # ------------------------------------------------------------------
    def _dialog(self, title, text, buttons):
        if self.active_dialog is not None:
            return self.active_dialog
        self._restore_main_window()
        win = tk.Toplevel(self.root)
        self.active_dialog = win
        win.title(title)
        win.geometry("360x130")
        win.transient(self.root)
        try:
            win.grab_set()
        except Exception:
            pass
        win.protocol("WM_DELETE_WINDOW", self._close_active_dialog)
        tk.Label(win, text=text, font=("Arial", 12)).pack(
            padx=12, pady=14, fill=tk.X)
        frame = tk.Frame(win)
        frame.pack(pady=6)

        def run_then_close(command):
            self._close_active_dialog()
            command()

        for label, command in buttons:
            tk.Button(frame, text=label, command=lambda c=command: run_then_close(c)).pack(
                side=tk.LEFT, padx=8)
        return win

    def _close_active_dialog(self):
        if self.active_dialog is not None:
            try:
                self.active_dialog.grab_release()
            except Exception:
                pass
            try:
                self.active_dialog.destroy()
            except Exception:
                pass
            self.active_dialog = None

    def _prompt_black_resign(self):
        def confirm():
            self.end_game("黑棋投子认负，白胜")

        self._dialog("投子认负", "黑棋投子认负，白胜。",
                     [("确定", confirm)])

    def _prompt_white_resign(self, board_copy=None):
        board_copy = board_copy or self.board

        def confirm():
            self.end_game("白棋投子认负，黑胜")

        def replay():
            path = list(getattr(board_copy, "_last_black_win_path", None) or [])
            replay_map = dict(getattr(board_copy, "_black_replay_map", None) or {})
            if not path and not replay_map:
                self._restore_main_window()
                messagebox.showinfo("复盘", "没有可展示的获胜过程。")
                self.end_game("白棋投子认负，黑胜")
                return
            self.start_black_win_replay(path, replay_map)

        self._dialog("投子认负", "白棋投子认负，黑胜。",
                     [("确定", confirm), ("显示黑棋获胜过程", replay)])

    def start_black_win_replay(self, black_path, replay_map):
        self.replay_mode = True
        self.replay_black_moves = list(black_path)
        self.replay_map = dict(replay_map or {})
        self.replay_new_stones = set()
        self.replay_start_history_len = len(self.board.history)
        self.replay_pre_ai = (bool(self.black_ai_var.get()),
                              bool(self.white_ai_var.get()))
        self.game_over = False
        self.ai_thinking = False
        self.search_interrupt.set()
        self.search_epoch += 1
        self.black_ai_var.set(0)
        self.white_ai_var.set(0)
        self.black_table_mode = False
        self.current = WHITE
        self.last_move = None
        self.pass_count = 0
        self.pass_log = []
        self.thinking_label.config(text="黑棋获胜复盘", fg="blue")
        self.depth_label.config(text="你执白棋；黑棋自动应手")
        self.draw_board()
        self.update_info()

    def _replay_failed(self, message=None):
        self.replay_mode = False
        self.black_table_mode = False
        self.game_over = True
        self.ai_thinking = False
        self.search_interrupt.set()
        self._restore_main_window()
        self.status_var.set("复盘失败")
        messagebox.showerror("复盘失败", "复盘失败")

    def _choose_table_move(self, key):
        entry = self.replay_map.get(key)
        if entry is None:
            return None
        if isinstance(entry, list):
            for move in entry:
                if self.board.is_empty(*move):
                    return move
            return None
        return entry if self.board.is_empty(*entry) else None

    def _apply_replay_black_move(self, move):
        ok, _ = self.board.play_black(*move)
        if not ok:
            self._replay_failed("复盘无法继续：黑棋未能获胜。")
            return
        self.replay_new_stones.add(move)
        self.last_move = move
        if self.board.check_black_five(*move):
            self.replay_mode = False
            self.draw_board(with_hints=False)
            self.end_game("黑棋连五，黑胜（复盘完成）")
            return
        self.current = WHITE
        self.draw_board()
        self.update_info()

    def play_replay_black(self):
        if not self.replay_mode:
            return
        move = self._choose_table_move(ai_search._board_signature(self.board))
        if move is not None:
            self._apply_replay_black_move(move)
            return

        # The player chose a move outside the searched replies.  If Black
        # already has a direct winning point or triangle, play the first one
        # immediately instead of starting an expensive search.
        threats = self.board.compute_threats()
        five = ai_search._five_points(threats)
        if five:
            self._apply_replay_black_move(five[0])
            return
        tri = ai_search._triangles(threats)
        if tri:
            self._apply_replay_black_move(tri[0])
            return

        # No direct forced point: calculate a black reply for this concrete
        # position instead.
        self.ai_thinking = True
        self.search_interrupt.clear()
        self.thinking_label.config(text="复盘：计算黑棋下法...")
        board_copy = self.board.copy()
        depth = max(2, self.current_max_depth)
        token = self.search_epoch

        def work():
            try:
                move2 = ai_black.best_black_move(
                    board_copy, max_depth=depth,
                    interrupt_event=self.search_interrupt
                )
            except Exception:
                move2 = None

            def apply():
                if not self.replay_mode or token != self.search_epoch:
                    return
                self.ai_thinking = False
                self.search_interrupt.clear()
                self.thinking_label.config(text="")
                if move2 is None or not self.board.is_empty(*move2):
                    self._replay_failed(
                        "复盘无法继续：黑棋未能获胜。"
                    )
                    return
                self._apply_replay_black_move(move2)

            self.root.after(0, apply)

        threading.Thread(target=work, daemon=True).start()

    def play_table_black(self):
        move = self._choose_table_move(ai_search._board_signature(self.board))
        if move is None:
            self.black_table_mode = False
            self.run_ai_move(BLACK)
            return
        ok, _ = self.board.play_black(*move)
        if not ok:
            self.black_table_mode = False
            self.run_ai_move(BLACK)
            return
        self.last_move = move
        if self.board.check_black_five(*move):
            self.draw_board(with_hints=False)
            self.end_game("黑棋连五，黑胜!")
            return
        self.current = WHITE
        self.draw_board()
        self.update_info()
        self.root.after(300, self.maybe_play_ai)

    # ------------------------------------------------------------------
    # Game control
    # ------------------------------------------------------------------
    def check_white_win(self):
        if self.white_win_var.get() == "occupy":
            if self.board.white_wins_by_occupy():
                self.end_game("白棋获胜！")
                return True
        else:
            if (self.auto_white_win_var.get() and
                    self.board.white_wins_by_line_block()):
                self.end_game("白棋获胜！")
                return True
        return False

    def manual_white_win_check(self):
        if self.game_over:
            return
        if self.board.white_wins_by_line_block():
            self.end_game("白棋获胜！")
        elif self.board.white_wins_by_occupy():
            self.end_game("白棋获胜！")
        else:
            self._show_unblocked_lines()
            self._restore_main_window()
            messagebox.showinfo("判定", "白棋尚未获胜。")
            self.draw_board()

    def _show_unblocked_lines(self):
        for line in self.board.get_unblocked_lines():
            x1, y1 = line[0]
            x2, y2 = line[-1]
            cx1 = MARGIN + y1 * CELL
            cy1 = MARGIN + x1 * CELL
            cx2 = MARGIN + y2 * CELL
            cy2 = MARGIN + x2 * CELL
            self.canvas.create_line(cx1, cy1, cx2, cy2,
                                    fill="red", width=1)

    def end_game(self, text):
        self.game_over = True
        self.ai_thinking = False
        self.search_interrupt.set()
        self._restore_main_window()
        self.status_var.set(text)
        # Draw only the board/stones after the game is over.  Computing
        # hints/territory here was the cause of the frozen-looking window.
        self.draw_board(with_hints=False)
        self.update_info()

    def new_game(self):
        self._close_active_dialog()
        self._stop_search()
        # Keep the previous position for one undo after starting a new game.
        if self.board.history or self.board.black_stone_count() or \
                self.board.white_stone_count():
            self.previous_game_snapshot = {
                "board": self.board.copy(),
                "current": self.current,
                "last_move": self.last_move,
                "game_over": self.game_over,
                "pass_count": self.pass_count,
                "pass_log": list(self.pass_log),
                "replay_mode": self.replay_mode,
                "replay_new_stones": set(self.replay_new_stones),
                "replay_map": dict(self.replay_map),
                "replay_black_moves": list(self.replay_black_moves),
                "black_table_mode": self.black_table_mode,
                "replay_start_history_len": self.replay_start_history_len,
                "replay_pre_ai": self.replay_pre_ai,
                "black_ai_var": bool(self.black_ai_var.get()),
                "white_ai_var": bool(self.white_ai_var.get()),
                "current_max_depth": self.current_max_depth,
            }
        else:
            self.previous_game_snapshot = None
        self.moves_since_new_game = 0
        self.board = HybridBoard(self.size)
        self.current = BLACK
        self.last_move = None
        self.game_over = False
        self.pass_count = 0
        self.pass_log = []
        self.replay_mode = False
        self.replay_new_stones = set()
        self.replay_map = {}
        self.replay_black_moves = []
        self.black_table_mode = False
        self.replay_start_history_len = 0
        self.replay_pre_ai = (True, True)
        self.search_interrupt.clear()
        self.thinking_label.config(text="")
        self.depth_label.config(text="")
        self.draw_board()
        self.update_info()
        self.update_mode_label()
        if self.black_ai_var.get():
            self.root.after(300, self.maybe_play_ai)

    def _register_move(self):
        self.moves_since_new_game += 1
        if self.moves_since_new_game >= 2:
            self.previous_game_snapshot = None

    def _restore_previous_game(self):
        snap = self.previous_game_snapshot
        self.previous_game_snapshot = None
        self.board = snap["board"]
        self.current = snap["current"]
        self.last_move = snap["last_move"]
        self.game_over = snap["game_over"]
        self.pass_count = snap["pass_count"]
        self.pass_log = list(snap["pass_log"])
        self.replay_mode = snap["replay_mode"]
        self.replay_new_stones = set(snap["replay_new_stones"])
        self.replay_map = dict(snap["replay_map"])
        self.replay_black_moves = list(snap["replay_black_moves"])
        self.black_table_mode = snap["black_table_mode"]
        self.replay_start_history_len = snap["replay_start_history_len"]
        self.replay_pre_ai = snap["replay_pre_ai"]
        self.black_ai_var.set(1 if snap["black_ai_var"] else 0)
        self.white_ai_var.set(1 if snap["white_ai_var"] else 0)
        self.current_max_depth = snap["current_max_depth"]
        self.depth_var.set(str(self.current_max_depth))
        self.moves_since_new_game = 0
        self.search_interrupt.clear()
        self.thinking_label.config(text="")
        self.depth_label.config(text="")
        self.draw_board()
        self.update_info()
        self.update_mode_label()
        if not self.game_over:
            self.root.after(300, self.maybe_play_ai)

    def undo_move(self):
        if self.ai_thinking:
            self._stop_search()
        if not self.board.history:
            if self.previous_game_snapshot is not None:
                self._restore_previous_game()
                return
            messagebox.showinfo("悔棋", "没有可悔的棋")
            return

        # Inside a black-win replay, undo stays in replay mode until the
        # board returns to the state just before White resigned.
        if self.replay_mode:
            if len(self.board.history) > self.replay_start_history_len:
                # Step back to the previous white decision point: remove the
                # automatic black reply (if present) and the white move that
                # caused it.
                if self.board.history[-1][0] == BLACK:
                    self.board.undo()
                    if self.moves_since_new_game > 0:
                        self.moves_since_new_game -= 1
                if (self.board.history and
                        len(self.board.history) > self.replay_start_history_len and
                        self.board.history[-1][0] == WHITE):
                    self.board.undo()
                    if self.moves_since_new_game > 0:
                        self.moves_since_new_game -= 1
                self.current = WHITE
                self.pass_count = 0
                self.pass_log = []
                self.last_move = (
                    (self.board.history[-1][1], self.board.history[-1][2])
                    if self.board.history else None
                )
                self.draw_board()
                self.update_info()
                self.root.after(300, self.maybe_play_ai)
                return
            # Reached the resignation point: undo the move that caused the
            # resignation and leave replay mode, restoring the previous
            # human/AI settings.
            self.board.undo()
            self.replay_mode = False
            self.replay_new_stones = set()
            self.replay_map = {}
            self.replay_black_moves = []
            self.black_table_mode = False
            self.black_ai_var.set(1 if self.replay_pre_ai[0] else 0)
            self.white_ai_var.set(1 if self.replay_pre_ai[1] else 0)
            self.game_over = False
            self.pass_count = 0
            self.pass_log = []
            self.current = self.board.turn
            self.last_move = (
                (self.board.history[-1][1], self.board.history[-1][2])
                if self.board.history else None
            )
            self.draw_board()
            self.update_info()
            self.update_mode_label()
            self.root.after(300, self.maybe_play_ai)
            return

        self.board.undo()
        self.game_over = False
        self.pass_count = 0
        self.pass_log = []
        if self.moves_since_new_game > 0:
            self.moves_since_new_game -= 1
        self.replay_mode = False
        self.replay_new_stones = set()
        self.replay_map = {}
        self.replay_black_moves = []
        self.black_table_mode = False
        self.last_move = (self.board.history[-1][1], self.board.history[-1][2]) \
            if self.board.history else None
        self.current = self.board.turn
        self.draw_board()
        self.update_info()
        self.update_mode_label()
        self.root.after(300, self.maybe_play_ai)


def main(board_size: int = BOARD_SIZE):
    root = tk.Tk()
    root.title(f"Gomoku vs Go  ({board_size}x{board_size})")
    GameGUI(root, board_size=board_size)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        try:
            root.destroy()
        except Exception:
            pass


if __name__ == "__main__":
    main()
