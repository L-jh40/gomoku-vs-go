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

# Standard star points (hoshi) per supported board size, in (row, col).
STAR_POINTS = {
    9: [(2, 2), (2, 6), (6, 2), (6, 6), (4, 4)],
    11: [(2, 2), (2, 8), (8, 2), (8, 8), (5, 5)],
    13: [(3, 3), (3, 9), (9, 3), (9, 9), (6, 6)],
    15: [(3, 3), (3, 11), (11, 3), (11, 11), (7, 7)],
    17: [(3, 3), (3, 13), (13, 3), (13, 13), (8, 8)],
    19: [(3, 3), (3, 9), (3, 15), (9, 3), (9, 9), (9, 15),
         (15, 3), (15, 9), (15, 15)],
}

BOARD_SIZES = (9, 11, 13, 15, 17, 19)


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
        self.time_black_ai = 0.0
        self.time_black_human = 0.0
        self.time_white_ai = 0.0
        self.time_white_human = 0.0
        self.turn_start_time = None
        self.turn_start_color = None

        self.board_bg = "#f0d68c"
        self.line_color = "black"
        self.star_color = "black"

        # "point" = stones on intersections, "cell" = stones inside cells.
        self.board_style = "point"
        # Canvas large enough for either style; draw_board centers the grid
        # inside the yellow area (origin_x / origin_y).
        self.canvas_size = board_size * CELL + 2 * MARGIN
        self.origin_x = MARGIN
        self.origin_y = MARGIN
        self.canvas = tk.Canvas(root, width=self.canvas_size,
                                height=self.canvas_size, bg=self.board_bg)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.info = tk.Frame(root, width=300)
        self.info.pack(side=tk.RIGHT, fill=tk.Y, padx=6, pady=4)

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

        top_buttons = tk.Frame(self.info)
        top_buttons.pack(fill=tk.X, pady=1)
        tk.Button(top_buttons, text="新对局", command=self.new_game).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(top_buttons, text="选择模式", command=self.open_mode_window).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 0))
        tk.Button(self.info, text="悔棋", command=self.undo_move).pack(
            fill=tk.X, pady=1)
        tk.Button(self.info, text="Pass", command=self.human_pass).pack(
            fill=tk.X, pady=1)
        tk.Button(self.info, text="AI 立即落子",
                  command=self.force_ai_current).pack(fill=tk.X, pady=1)

        self.black_ai_var = tk.IntVar(value=1 if black_is_ai else 0)
        self.white_ai_var = tk.IntVar(value=1 if white_is_ai else 0)

        self.first_player_var = tk.StringVar(value="black")
        self.forbid_overline_var = tk.IntVar(value=1)
        self.forbid_44_var = tk.IntVar(value=1)
        self.forbid_33_var = tk.IntVar(value=1)
        self.torus_mode_var = tk.IntVar(value=0)
        self.obstacle_enabled_var = tk.IntVar(value=0)
        self.obstacle_count_var = tk.StringVar(value="0")
        self.mode_window = None
        self.board_size_vars = {
            n: tk.IntVar(value=1 if n == board_size else 0)
            for n in BOARD_SIZES
        }
        self.style_point_var = tk.IntVar(value=1)
        self.style_cell_var = tk.IntVar(value=0)
        self.info_natural_height = 0

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
        self.show_candidates_var = tk.IntVar(value=0)
        tk.Checkbutton(self.info, text="显示候选点",
                       variable=self.show_candidates_var,
                       command=self.draw_board).pack(anchor=tk.W)
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

        # Fix the side panel height now that its content is built: keep every
        # control visible even when a small board makes the canvas short.
        self.info.update_idletasks()
        try:
            self.info_natural_height = max(self.info.winfo_reqheight(), 1)
        except Exception:
            self.info_natural_height = 1
        self.info.configure(height=max(self.canvas_size + 80,
                                       self.info_natural_height))
        self.info.pack_propagate(False)

        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<Button-3>", self.on_right_click)
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.root.bind("<KeyPress-z>", self._on_key)
        self.root.bind("<KeyPress-x>", self._on_key)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.draw_board()
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
        self._close_mode_window()
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

    def update_mode_label(self):
        bh = "人类" if self.black_is_human() else "AI"
        wh = "人类" if self.white_is_human() else "AI"
        extra = " | 黑棋查表必胜" if self.black_table_mode else ""
        self.mode_label.config(
            text=f"模式: 黑({bh}) vs 白({wh}) | 深度 {self.depth_var.get()}{extra}"
        )
        self.draw_board()

    def _format_time(self, seconds):
        seconds = max(0, int(seconds))
        return f"{seconds // 60}:{seconds % 60:02d}"

    def _finish_turn_time(self, color, is_ai):
        if self.turn_start_time is None or self.turn_start_color != color:
            return
        elapsed = time.time() - self.turn_start_time
        if color == BLACK:
            if is_ai:
                self.time_black_ai += elapsed
            else:
                self.time_black_human += elapsed
        else:
            if is_ai:
                self.time_white_ai += elapsed
            else:
                self.time_white_human += elapsed
        self.turn_start_time = None
        self.turn_start_color = None

    def _start_turn_timer(self, color):
        self.turn_start_time = time.time()
        self.turn_start_color = color

    def _display_time(self, color, is_ai):
        if color == BLACK:
            base = self.time_black_ai if is_ai else self.time_black_human
        else:
            base = self.time_white_ai if is_ai else self.time_white_human
        if self.current == color and self.turn_start_time is not None:
            base += time.time() - self.turn_start_time
        return self._format_time(base)

    def update_info(self):
        black_text = (
            f"黑: AI {self._display_time(BLACK, True)} | "
            f"人类 {self._display_time(BLACK, False)}"
        )
        white_text = (
            f"白: AI {self._display_time(WHITE, True)} | "
            f"人类 {self._display_time(WHITE, False)}"
        )
        cap = self.board.captured_count[WHITE]
        cap_b = self.board.captured_count[BLACK]
        cap_text = f"吃子：白吃黑 {cap}"
        if cap_b:
            cap_text += f"，黑自吃 {cap_b}"
        self.stats_var.set(f"{black_text}\n{white_text}\n{cap_text}")
        if not self.game_over:
            turn = "● 黑棋" if self.current == BLACK else "○ 白棋"
            self.status_var.set(f"{turn} 行棋")

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def _grid_extent(self):
        """Pixel span of the playing area for the current board style."""
        if self.board_style == "cell":
            return self.size * CELL
        return (self.size - 1) * CELL

    def _update_origin(self):
        """Center the playing area inside the yellow canvas."""
        extent = self._grid_extent()
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        if width <= 1:
            width = self.canvas_size
        if height <= 1:
            height = self.canvas_size
        self.origin_x = int(max(0, (width - extent) / 2))
        self.origin_y = int(max(0, (height - extent) / 2))

    def _point_center(self, x, y):
        """Canvas coords of logical point (x, y): an intersection, or the
        center of the matching cell in cell style."""
        if self.board_style == "cell":
            return (self.origin_x + (y + 0.5) * CELL,
                    self.origin_y + (x + 0.5) * CELL)
        return (self.origin_x + y * CELL, self.origin_y + x * CELL)

    def _on_canvas_resize(self, _event=None):
        self.draw_board()

    def draw_board(self, with_hints=True):
        self.canvas.delete("all")
        self.canvas.configure(bg=self.board_bg)
        self._update_origin()
        size = self.size
        ox, oy = self.origin_x, self.origin_y
        if self.board_style == "cell":
            # Stones sit inside cells: draw (size + 1) lines per direction.
            end = size * CELL
            for i in range(size + 1):
                p = i * CELL
                self.canvas.create_line(ox + p, oy, ox + p, oy + end,
                                        fill=self.line_color)
                self.canvas.create_line(ox, oy + p, ox + end, oy + p,
                                        fill=self.line_color)
        else:
            end = (size - 1) * CELL
            for i in range(size):
                p = i * CELL
                self.canvas.create_line(ox + p, oy, ox + p, oy + end,
                                        fill=self.line_color)
                self.canvas.create_line(ox, oy + p, ox + end, oy + p,
                                        fill=self.line_color)

        for sx, sy in STAR_POINTS.get(size, []):
            cx, cy = self._point_center(sx, sy)
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
            cx, cy = self._point_center(lx, ly)
            r = 10 if self.replay_mode and (lx, ly) in self.replay_new_stones \
                else CELL // 2 - 2
            self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                    outline="red", width=2)

        if with_hints and self.hint_var.get():
            self.draw_hints(dead)
        elif self.show_candidates_var.get():
            self._draw_candidate_squares()

    def draw_stone(self, x, y, color, move_num=None, dead_black=False):
        cx, cy = self._point_center(x, y)
        r = 10 if self.replay_mode and (x, y) in self.replay_new_stones \
            else CELL // 2 - 2
        fill = "black" if color == BLACK else "white"
        self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                fill=fill, outline=self.line_color)
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
            cx, cy = self._point_center(x, y)
            s = 6
            self.canvas.create_rectangle(cx - s, cy - s, cx + s, cy + s,
                                         fill="white", outline="gray",
                                         stipple="gray50")

        # Blue crosses: forbidden / no-liberty points (cached).
        blue_crosses = self.board.get_blue_cross_positions()
        for x, y in blue_crosses:
            if not self.board.is_empty(x, y):
                continue
            cx, cy = self._point_center(x, y)
            r = 6
            self.canvas.create_line(cx - r, cy - r, cx + r, cy + r,
                                    fill="blue", width=2)
            self.canvas.create_line(cx - r, cy + r, cx + r, cy - r,
                                    fill="blue", width=2)

        # Candidate squares are below red markers.
        self._draw_candidate_squares()

        # Red markers.
        threats = self.board.compute_threats()
        for (x, y), threat in threats.items():
            if not self.board.is_empty(x, y):
                continue
            cx, cy = self._point_center(x, y)
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

    def _draw_candidate_squares(self):
        if not self.show_candidates_var.get():
            return
        r = 8  # same half-size as a large circle
        for x, y in self._get_candidate_display_positions():
            if not self.board.is_empty(x, y):
                continue
            cx, cy = self._point_center(x, y)
            self.canvas.create_rectangle(
                cx - r, cy - r, cx + r, cy + r,
                outline="green", width=2
            )

    def _get_candidate_display_positions(self):
        threats = self.board.compute_threats()
        if self.current == BLACK:
            if ai_search._forced(threats):
                return ai_search._black_algorithm_a_candidates(self.board, threats)
            return self.board.get_black_priority_candidates(threats)
        if ai_search._forced(threats):
            return self.board.get_white_defense_candidates(threats)
        return self.board.get_white_priority_candidates(threats)

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
        if self.board_style == "cell":
            x = int((event.y - self.origin_y) // CELL)
            y = int((event.x - self.origin_x) // CELL)
        else:
            x = round((event.y - self.origin_y) / CELL)
            y = round((event.x - self.origin_x) / CELL)
        if not self.board.in_bounds(x, y):
            return
        if self.replay_mode and self.current == BLACK:
            return
        if self.current == BLACK and self.black_is_human():
            self.try_play_black(x, y)
        elif self.current == WHITE and (self.white_is_human() or self.replay_mode):
            self.try_play_white(x, y)

    def _on_key(self, event):
        if isinstance(event.widget, tk.Entry):
            return
        if event.keysym.lower() == "z":
            self.undo_move()
        elif event.keysym.lower() == "x":
            self.human_pass()

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
        self._stop_search()
        self._finish_turn_time(BLACK, False)
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
        self.thinking_label.config(text="")
        if self.board.check_black_five(x, y):
            self.draw_board(with_hints=False)
            self.end_game("黑棋连五，黑胜!")
            return
        self.current = WHITE
        self._start_turn_timer(WHITE)
        self.draw_board()
        self.update_info()
        self.root.after(300, self.maybe_play_ai)

    def try_play_white(self, x, y):
        if not self.board.is_empty(x, y):
            return
        self._stop_search()
        self._finish_turn_time(WHITE, False)
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
        self.thinking_label.config(text="")
        if self.check_white_win():
            return
        self.current = BLACK
        self._start_turn_timer(BLACK)
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
        color = self.current
        is_ai = (
            not self.black_is_human() if color == BLACK
            else not self.white_is_human()
        )
        self._finish_turn_time(color, is_ai)
        self.pass_log.append(color)
        self.pass_count += 1
        # Only a black pass followed by a white pass ends the game.
        if self.pass_log[-2:] == [BLACK, WHITE]:
            self.end_game("黑棋 Pass + 白棋 Pass，对局结束")
            return
        self.current = WHITE if color == BLACK else BLACK
        self._start_turn_timer(self.current)
        self.last_move = None
        self.thinking_label.config(text="")
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
            if completed_depth == -1:
                # Candidate-filtering debug refresh.
                self.root.after(0, self.draw_board)
                return
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
                self._finish_turn_time(color, True)
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
                    text=f"上一步AI用时: {total:.2f}s | 搜索深度: {depth}"
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
                    self._start_turn_timer(WHITE)
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
                    self._start_turn_timer(BLACK)
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
        self.update_info()
        self._schedule_search_ticker()

    def _refresh_thinking_label(self):
        if self.search_start_time <= 0:
            return
        total = time.time() - self.search_start_time
        if self.ai_thinking and not self.last_focused and \
                self.last_layer_depth == 0:
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
        # No grab: the main window stays clickable while this dialog is open.
        # Closing the main window will close this dialog through _on_close.
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

        # The player chose a move outside the searched replies.  Report the
        # table miss first, then fall back to direct/AI play.
        self._restore_main_window()
        messagebox.showwarning("复盘查表失败", "未找到对应应手，改用 AI 搜索。")

        # If Black already has a direct winning point or triangle, play the
        # first one immediately instead of starting an expensive search.
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
            cx1, cy1 = self._point_center(*line[0])
            cx2, cy2 = self._point_center(*line[-1])
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

    def open_mode_window(self):
        self._restore_main_window()
        if self.mode_window is not None and self.mode_window.winfo_exists():
            self.mode_window.lift()
            return
        win = tk.Toplevel(self.root)
        self.mode_window = win
        win.title("选择模式")
        win.geometry("420x470")
        win.transient(self.root)
        win.protocol("WM_DELETE_WINDOW", self._close_mode_window)

        tk.Label(win, text="棋盘尺寸", font=("Arial", 11, "bold")).pack(
            anchor=tk.W, padx=10)
        size_frame = tk.Frame(win)
        size_frame.pack(fill=tk.X, padx=10)
        for n in BOARD_SIZES:
            tk.Checkbutton(size_frame, text=f"{n}×{n}",
                           variable=self.board_size_vars[n],
                           command=lambda n=n: self._on_size_check(n)
                           ).pack(side=tk.LEFT)

        tk.Label(win, text="棋盘样式", font=("Arial", 11, "bold")).pack(
            anchor=tk.W, padx=10, pady=(10, 0))
        style_frame = tk.Frame(win)
        style_frame.pack(fill=tk.X, padx=10)
        tk.Checkbutton(style_frame, text="落子交叉点",
                       variable=self.style_point_var,
                       command=self._on_style_point).pack(side=tk.LEFT)
        tk.Checkbutton(style_frame, text="落子格子",
                       variable=self.style_cell_var,
                       command=self._on_style_cell).pack(side=tk.LEFT,
                                                         padx=10)

        tk.Label(win, text="先手", font=("Arial", 11, "bold")).pack(anchor=tk.W, padx=10)
        first_frame = tk.Frame(win)
        first_frame.pack(fill=tk.X, padx=10)
        tk.Radiobutton(first_frame, text="黑棋先手（五子棋规则）",
                       variable=self.first_player_var, value="black").pack(side=tk.LEFT)
        tk.Radiobutton(first_frame, text="白棋先手（围棋规则）",
                       variable=self.first_player_var, value="white").pack(side=tk.LEFT, padx=10)

        tk.Label(win, text="禁手设置", font=("Arial", 11, "bold")).pack(
            anchor=tk.W, padx=10, pady=(10, 0))
        forbidden_frame = tk.Frame(win)
        forbidden_frame.pack(fill=tk.X, padx=20)
        tk.Checkbutton(forbidden_frame, text="三三禁手",
                       variable=self.forbid_33_var).pack(side=tk.LEFT)
        tk.Checkbutton(forbidden_frame, text="四四禁手",
                       variable=self.forbid_44_var).pack(side=tk.LEFT, padx=10)
        tk.Checkbutton(forbidden_frame, text="长连禁手",
                       variable=self.forbid_overline_var).pack(side=tk.LEFT)

        tk.Label(win, text="预留接口", font=("Arial", 11, "bold")).pack(
            anchor=tk.W, padx=10, pady=(10, 0))
        tk.Checkbutton(win, text="环面模式",
                       variable=self.torus_mode_var).pack(anchor=tk.W, padx=10)
        tk.Checkbutton(win, text="启用障碍",
                       variable=self.obstacle_enabled_var).pack(anchor=tk.W, padx=10)
        obstacle_frame = tk.Frame(win)
        obstacle_frame.pack(fill=tk.X, padx=20)
        tk.Label(obstacle_frame, text="选择障碍个数:").pack(side=tk.LEFT)
        tk.Entry(obstacle_frame, textvariable=self.obstacle_count_var,
                 width=6).pack(side=tk.LEFT)

        bottom = tk.Frame(win)
        bottom.pack(side=tk.BOTTOM, fill=tk.X, pady=10)
        tk.Button(bottom, text="新对局", command=self._apply_mode_new_game).pack(
            side=tk.TOP)

    def _on_size_check(self, selected):
        var = self.board_size_vars[selected]
        if var.get():
            for n, other in self.board_size_vars.items():
                if n != selected:
                    other.set(0)
        else:
            # Keep exactly one board size selected at all times.
            var.set(1)

    def _selected_board_size(self):
        for n, var in self.board_size_vars.items():
            if var.get():
                return n
        return None

    def _on_style_point(self):
        if self.style_point_var.get():
            self.style_cell_var.set(0)
            self.board_style = "point"
        else:
            # One style must stay selected; restore it.
            self.style_point_var.set(1)
        self.draw_board()

    def _on_style_cell(self):
        if self.style_cell_var.get():
            self.style_point_var.set(0)
            self.board_style = "cell"
        else:
            # One style must stay selected; restore it.
            self.style_cell_var.set(1)
        self.draw_board()

    def _select_board_size_var(self, size):
        for n, var in self.board_size_vars.items():
            var.set(1 if n == size else 0)

    def _apply_canvas_size(self):
        """Resize the canvas / side panel for the current board size."""
        new_size = self.size * CELL + 2 * MARGIN
        if new_size == self.canvas_size:
            return
        self.canvas_size = new_size
        self.canvas.configure(width=new_size, height=new_size)
        self.info.configure(height=max(new_size + 80,
                                       self.info_natural_height))
        self.root.title(f"Gomoku vs Go  ({self.size}x{self.size})")
        try:
            # Let the window shrink/grow to fit the new board.
            self.root.geometry("")
        except Exception:
            pass

    def _close_mode_window(self):
        if self.mode_window is not None:
            try:
                self.mode_window.destroy()
            except Exception:
                pass
            self.mode_window = None

    def _apply_mode_new_game(self):
        self._close_mode_window()
        self.new_game()

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
                "time_black_ai": self.time_black_ai,
                "time_black_human": self.time_black_human,
                "time_white_ai": self.time_white_ai,
                "time_white_human": self.time_white_human,
            }
        else:
            self.previous_game_snapshot = None
        self.moves_since_new_game = 0
        selected_size = self._selected_board_size()
        if selected_size is not None:
            self.size = selected_size
        self.board = HybridBoard(self.size)
        self.board._forbid_overline = bool(self.forbid_overline_var.get())
        self.board._forbid_44 = bool(self.forbid_44_var.get())
        self.board._forbid_33 = bool(self.forbid_33_var.get())
        if self.first_player_var.get() == "white":
            self.current = WHITE
            self.board.turn = WHITE
        else:
            self.current = BLACK
            self.board.turn = BLACK
        self.last_move = None
        self.game_over = False
        self.pass_count = 0
        self.pass_log = []
        self.time_black_ai = 0.0
        self.time_black_human = 0.0
        self.time_white_ai = 0.0
        self.time_white_human = 0.0
        self.replay_mode = False
        self.replay_new_stones = set()
        self.replay_map = {}
        self.replay_black_moves = []
        self.black_table_mode = False
        self.replay_start_history_len = 0
        self.replay_pre_ai = (True, True)
        self.search_interrupt.clear()
        self._start_turn_timer(self.current)
        self.thinking_label.config(text="")
        self.depth_label.config(text="")
        self._apply_canvas_size()
        self.draw_board()
        self.update_info()
        self.update_mode_label()
        if self.current == BLACK and self.black_ai_var.get():
            self.root.after(300, self.maybe_play_ai)
        elif self.current == WHITE and self.white_ai_var.get():
            self.root.after(300, self.maybe_play_ai)

    def _register_move(self):
        self.moves_since_new_game += 1
        if self.moves_since_new_game >= 2:
            self.previous_game_snapshot = None

    def _restore_previous_game(self):
        snap = self.previous_game_snapshot
        self.previous_game_snapshot = None
        self.board = snap["board"]
        if self.board.size != self.size:
            self.size = self.board.size
            self._apply_canvas_size()
            self._select_board_size_var(self.size)
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
        self.time_black_ai = snap.get("time_black_ai", 0.0)
        self.time_black_human = snap.get("time_black_human", 0.0)
        self.time_white_ai = snap.get("time_white_ai", 0.0)
        self.time_white_human = snap.get("time_white_human", 0.0)
        self.moves_since_new_game = 0
        self.search_interrupt.clear()
        self._start_turn_timer(self.current)
        self.thinking_label.config(text="")
        self.depth_label.config(text="")
        self.draw_board()
        self.update_info()
        self.update_mode_label()
        if not self.game_over:
            self.root.after(300, self.maybe_play_ai)

    def undo_move(self):
        if self.ai_thinking:
            # First click while AI is searching only stops the search.
            self._stop_search()
            return
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
    GameGUI(root, board_size=board_size,
            black_is_ai=False, white_is_ai=False)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        try:
            root.destroy()
        except Exception:
            pass


if __name__ == "__main__":
    main()
