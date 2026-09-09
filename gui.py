"""
gui.py - tkinter windowed AI-vs-AI application.

Black plays Gomoku with forbidden-move restrictions; White plays Go and
captures zero-liberty black groups.  White wins by blocking every black
five line (or by capturing all black stones).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox
import multiprocessing
import queue as queue_mod
import time

from board import EMPTY, BLACK, WHITE, HybridBoard, THREAT_MARKER
import rules
import ai_search
import ai_worker

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

# ---------------------------------------------------------------------------
# Header (top band) font size in points, per board road.  19x19 -> 20pt and
# the smaller boards shrink evenly (currently the "折中" series).  Tune this
# table directly and observe the result.
# ---------------------------------------------------------------------------
HEADER_FONT_PT = {
    9: 9,
    11: 11,
    13: 13,
    15: 16,
    17: 18,
    19: 20,
}


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
        # The AI search runs in a persistent worker process so the Tk main
        # loop never fights the search for the GIL (the window used to
        # freeze during deep searches).  Interruption goes through a shared
        # epoch counter: the worker aborts a job as soon as the GUI's
        # search epoch has moved on (see ai_worker._EpochInterrupt).
        self.mp_ctx = multiprocessing.get_context("spawn")
        self.worker_epoch_ctl = self.mp_ctx.Value("i", 0)
        self.job_queue = None
        self.result_queue = None
        self.ai_worker_proc = None
        self.worker_poll_ms = 80

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
        # Wall time of the most recent human move/pass (shown in the green
        # label while a human is thinking); None before any human move.
        self.last_human_move_sec = None

        self.board_bg = "#f0d68c"
        self.line_color = "black"
        self.star_color = "black"
        # Obstacle cells: board background mixed 1:1 with pure black.
        self.obstacle_color = self._mix_colors(self.board_bg, "#000000", 0.5)

        # "point" = stones on intersections, "cell" = stones inside cells.
        self.board_style = "point"
        self.hover_point = None
        self.hover_display = None
        # Layout state: cell size is dynamic (fitted to the window) and the
        # torus hint ring can be 2 or 4 cells wide (or off).
        self.cell = CELL
        self.info_width = 300
        self.torus_hint_var = tk.IntVar(value=1)
        self.torus_hint_width_var = tk.IntVar(value=2)
        self.header_in_panel = False
        self._canvas_key = None
        self._fitting = False
        self._fit_cell()
        # Canvas large enough for either style; draw_board centers the grid
        # inside the yellow area below the header readout strip
        # (origin_x / origin_y).  Width is based on the cell extent plus the
        # side margins; the extra header height is reserved above the grid.
        self.canvas_size = self._display_size() * self.cell + 2 * MARGIN
        self.canvas_height = self.canvas_size + self._band_height()
        self.origin_x = MARGIN
        self.origin_y = MARGIN + self._band_height()
        self.canvas = tk.Canvas(root, width=self.canvas_size,
                                height=self.canvas_height, bg=self.board_bg)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.info = tk.Frame(root, width=self.info_width)
        self.info.pack(side=tk.RIGHT, fill=tk.Y, padx=6, pady=4)

        self.status_var = tk.StringVar(value="黑棋先行")
        # Fallback readout when the header cannot fit above the board: the
        # times/captures are shown beside the board in the side panel.
        self.stats_var = tk.StringVar(value="")
        self.stats_label = tk.Label(self.info, textvariable=self.stats_var,
                                    font=("Arial", 9), fg="#4a3300",
                                    justify=tk.LEFT)
        tk.Label(self.info, textvariable=self.status_var,
                 font=("Arial", 20, "bold")).pack(pady=(4, 1))

        self.thinking_label = tk.Label(self.info, text="", fg="blue",
                                       font=("Arial", 9))
        self.thinking_label.pack(pady=1)
        self.depth_label = tk.Label(self.info, text="", fg="green",
                                    font=("Arial", 9))
        self.depth_label.pack(pady=1)
        self.stats_label.pack(pady=1)

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

        # Board style lives on the main window (outside the mode window).
        style_row = tk.Frame(self.info)
        style_row.pack(fill=tk.X, pady=1)
        tk.Label(style_row, text="棋盘样式:", font=("Arial", 9)).pack(
            side=tk.LEFT)
        tk.Checkbutton(style_row, text="落子交叉点",
                       variable=self.style_point_var,
                       command=self._on_style_point).pack(side=tk.LEFT)
        tk.Checkbutton(style_row, text="落子格子",
                       variable=self.style_cell_var,
                       command=self._on_style_cell).pack(side=tk.LEFT,
                                                         padx=(6, 0))

        # Mirrored hint ring (torus display only): on/off and 2 or 4 cells.
        hint_row = tk.Frame(self.info)
        hint_row.pack(fill=tk.X, pady=1)
        tk.Checkbutton(hint_row, text="环面提示",
                       variable=self.torus_hint_var,
                       command=self._on_torus_hint_change).pack(side=tk.LEFT)
        tk.Radiobutton(hint_row, text="2格",
                       variable=self.torus_hint_width_var, value=2,
                       command=self._on_torus_hint_change).pack(side=tk.LEFT)
        tk.Radiobutton(hint_row, text="4格",
                       variable=self.torus_hint_width_var, value=4,
                       command=self._on_torus_hint_change).pack(side=tk.LEFT)

        self.depth_var = tk.StringVar(value="2")
        frame = tk.Frame(self.info)
        frame.pack(fill=tk.X, pady=1)
        tk.Label(frame, text="Minimax 层数:", font=("Arial", 9)).pack(side=tk.LEFT)
        for value in (0, 1, 2, 3, 4):
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
        tk.Checkbutton(self.info, text="显示AI候选点",
                       variable=self.show_candidates_var,
                       command=self.draw_board).pack(anchor=tk.W)
        self.cancel_resign_var = tk.IntVar(value=0)
        tk.Checkbutton(self.info, text="取消投子认负",
                       variable=self.cancel_resign_var).pack(anchor=tk.W)

        # "白棋获胜条件" selection moved into the mode window
        # (open_mode_window); auto/manual judgement stays on the main window.
        self.white_win_var = tk.StringVar(value="line_block")

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
        self.info.configure(height=max(self.canvas_height + 80,
                                       self.info_natural_height))
        self.info.pack_propagate(False)

        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<Button-3>", self.on_right_click)
        self.canvas.bind("<Motion>", self._on_mouse_move)
        self.canvas.bind("<Leave>", self._on_mouse_leave)
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.root.bind("<KeyPress-z>", self._on_key)
        self.root.bind("<KeyPress-x>", self._on_key)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.draw_board()
        self.update_mode_label()

        # Keep the blue/green human-turn labels fresh while a human thinks.
        self.root.after(500, self._clock_ticker)
        # Drain worker messages so progress/UI stay live during searches.
        self.root.after(self.worker_poll_ms, self._poll_worker)
        # Start the worker eagerly so the first AI move pays no spawn cost.
        self._ensure_worker()

        if self.black_ai_var.get() and self.current == BLACK:
            self.root.after(300, self.maybe_play_ai)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _mix_colors(c1, c2, ratio=0.5):
        """Mix two #rrggbb colors; `ratio` is the share of c1."""
        r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
        r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)

        def mix(a, b):
            return int(round(a * ratio + b * (1 - ratio)))

        return f"#{mix(r1, r2):02x}{mix(g1, g2):02x}{mix(b1, b2):02x}"

    def black_is_human(self):
        return (not self.black_ai_var.get() and not self.black_table_mode
                and not self.replay_mode)

    def white_is_human(self):
        return not self.white_ai_var.get()

    def _on_close(self):
        self._shutdown_worker()
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
        torus = " | 环面" if self.board.torus else ""
        self.mode_label.config(
            text=f"模式: 黑({bh}) vs 白({wh}) | 深度 {self.depth_var.get()}"
                 f"{extra}{torus}"
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

    def _color_is_ai(self, color):
        """Is the side that currently controls `color` an AI?"""
        if color == BLACK:
            return not self.black_is_human()
        return not self.white_is_human()

    def _display_clock(self, color, is_ai):
        """One side's AI or human clock (mm:ss).  The human row ticks live
        while a human is thinking; the AI row only shows the accumulated
        search (thinking) time and updates when a search finishes, so it
        matches the sum of the blue "用时" figures.  Human + AI for a
        colour equals that colour's total move time."""
        if color == BLACK:
            base = self.time_black_ai if is_ai else self.time_black_human
        else:
            base = self.time_white_ai if is_ai else self.time_white_human
        if (not is_ai and self.current == color
                and self.turn_start_time is not None
                and not self._color_is_ai(color)):
            base += time.time() - self.turn_start_time
        return self._format_time(base)

    def _add_ai_search_time(self, color, seconds):
        """Add an actual AI search duration (the same figure the blue label
        reports) to the colour's AI clock - auto AI turns only."""
        seconds = max(0.0, seconds)
        if color == BLACK:
            self.time_black_ai += seconds
        else:
            self.time_white_ai += seconds

    def _record_human_move_time(self, color):
        """Remember the wall time of a just-finished human move/pass."""
        if self.turn_start_time is not None and self.turn_start_color == color:
            self.last_human_move_sec = max(
                0.0, time.time() - self.turn_start_time)

    def _refresh_human_clock_labels(self):
        """While a human is thinking, the blue label shows this step's
        elapsed time and the green label the previous human step's time."""
        if self.game_over or self.ai_thinking or self.replay_mode:
            return
        color = self.current
        if (color == BLACK and not self.black_is_human()) or \
                (color == WHITE and not self.white_is_human()):
            return
        live = 0.0
        if self.turn_start_time is not None and self.turn_start_color == color:
            live = max(0.0, time.time() - self.turn_start_time)
        self.thinking_label.config(
            text=f"人类思考中，用时: {live:.2f}s", fg="blue")
        if self.last_human_move_sec is None:
            self.depth_label.config(text="上一手人类思考用时: --", fg="green")
        else:
            self.depth_label.config(
                text=f"上一手人类思考用时: {self.last_human_move_sec:.2f}s",
                fg="green")

    def _clock_ticker(self):
        """Lightweight 0.25s loop: keeps the top-band clocks and the
        blue/green human-turn labels live while no AI search is running.
        (AI searches keep their own 2s ticker.)"""
        try:
            if not self.root.winfo_exists():
                return
        except Exception:
            return
        try:
            if not self.game_over and not self.ai_thinking:
                self.update_info()
                self._refresh_human_clock_labels()
        except Exception:
            pass
        self.root.after(250, self._clock_ticker)

    # ------------------------------------------------------------------
    # Header readout strip (above the grid, inside the yellow canvas)
    # ------------------------------------------------------------------
    def _band_font_size(self):
        """Header font size for the current board road, read from the
        explicit HEADER_FONT_PT table (19x19 -> 20pt, smaller boards shrink
        evenly).  Tweak that table to change the sizes.""" 
        pts = HEADER_FONT_PT.get(self.size)
        if pts is None:  # safety fallback for any other size
            pts = 9 + (self.size - 9) * 11.0 / 10.0
        return int(max(8, min(20, round(pts))))

    def _band_fonts(self):
        """(regular, bold, linespace) tk font objects for the current size.
        Microsoft YaHei UI has a real bold CJK face, avoiding the uneven
        fake-bold strokes Arial produces for Chinese glyphs at ~13-16pt."""
        size_pts = self._band_font_size()
        cache = getattr(self, "_band_font_cache", None)
        if cache is None:
            cache = self._band_font_cache = {}
        if size_pts not in cache:
            reg = tkfont.Font(root=self.root, family="Microsoft YaHei UI",
                              size=size_pts)
            bold = tkfont.Font(root=self.root, family="Microsoft YaHei UI",
                               size=size_pts, weight="bold")
            linespace = max(reg.metrics("linespace"),
                            bold.metrics("linespace"))
            cache[size_pts] = (reg, bold, linespace)
        return cache[size_pts]

    def _band_height(self):
        """Pixel height reserved above the grid: 3 header rows plus one blank
        row, so the header text stands exactly one line above the board."""
        _reg, _bold, linespace = self._band_fonts()
        pad = max(3, int(linespace * 0.2))
        return pad + 4 * linespace

    def _draw_top_band(self):
        """Header above the grid: black clock (3 lines), capture count,
        white clock (3 lines).  The black block hugs the left board edge,
        the white block the right edge, and "白吃黑 N子" is vertically
        centred between them."""
        if getattr(self, "canvas", None) is None:
            return
        self.canvas.delete("topband")
        if self.header_in_panel:
            return
        extent = self._grid_extent()
        ox = self.origin_x
        reg, bold, linespace = self._band_fonts()
        pad = max(3, int(linespace * 0.2))
        edge_pad = max(4, int(self._band_font_size() * 0.2))
        x_left = ox + edge_pad
        x_right = ox + extent - edge_pad

        cap = self.board.captured_count[WHITE]
        cap_b = self.board.captured_count[BLACK]
        eat_text = f"白吃黑 {cap}子"
        if cap_b:
            eat_text += f"，黑自吃 {cap_b}子"

        def line_y(i):
            return pad + (i + 0.5) * linespace

        tag = "topband"
        # Black clock - left edge.
        self.canvas.create_text(x_left, line_y(0), anchor="w",
                                text="黑棋时间", font=bold, fill="black",
                                tags=tag)
        self.canvas.create_text(
            x_left, line_y(1), anchor="w",
            text=f"AI | {self._display_clock(BLACK, True)}",
            font=reg, fill="#202020", tags=tag)
        self.canvas.create_text(
            x_left, line_y(2), anchor="w",
            text=f"人类 | {self._display_clock(BLACK, False)}",
            font=reg, fill="#202020", tags=tag)
        # Capture count - centred between the two clocks.
        self.canvas.create_text(ox + extent / 2, pad + 1.5 * linespace,
                                anchor="center", text=eat_text, font=bold,
                                fill="#4a3300", tags=tag)
        # White clock - right edge.
        self.canvas.create_text(x_right, line_y(0), anchor="e",
                                text="白棋时间", font=bold, fill="black",
                                tags=tag)
        self.canvas.create_text(
            x_right, line_y(1), anchor="e",
            text=f"AI | {self._display_clock(WHITE, True)}",
            font=reg, fill="#202020", tags=tag)
        self.canvas.create_text(
            x_right, line_y(2), anchor="e",
            text=f"人类 | {self._display_clock(WHITE, False)}",
            font=reg, fill="#202020", tags=tag)

    def update_info(self):
        self._draw_top_band()
        if self.header_in_panel:
            cap = self.board.captured_count[WHITE]
            cap_b = self.board.captured_count[BLACK]
            eat = f"白吃黑 {cap}子"
            if cap_b:
                eat += f"，黑自吃 {cap_b}子"
            self.stats_var.set(
                f"黑棋时间\nAI | {self._display_clock(BLACK, True)}\n"
                f"人类 | {self._display_clock(BLACK, False)}\n"
                f"白棋时间\nAI | {self._display_clock(WHITE, True)}\n"
                f"人类 | {self._display_clock(WHITE, False)}\n{eat}"
            )
        else:
            self.stats_var.set("")
        if not self.game_over:
            turn = "● 黑棋" if self.current == BLACK else "○ 白棋"
            prefix = "复盘 " if self.replay_mode else ""
            self.status_var.set(f"{prefix}{turn} 行棋")

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def _display_size(self):
        """Grid size shown on screen: n on a normal board, n + 4 on a torus
        (2 wrapped rows/columns on every side)."""
        return self.size + 4 if self.board.torus else self.size

    def _display_offset(self):
        """Display index offset of actual cell (0, 0)."""
        return 2 if self.board.torus else 0

    def _display_center(self, dx, dy):
        """Canvas coords of display-grid index (dx, dy)."""
        if self.board_style == "cell":
            return (self.origin_x + (dy + 0.5) * self.cell,
                    self.origin_y + (dx + 0.5) * self.cell)
        return (self.origin_x + dy * self.cell, self.origin_y + dx * self.cell)

    def _display_copies(self, x, y):
        """Every display index that shows actual cell (x, y)."""
        if not self.board.torus:
            return [(x, y)]
        n = self.size
        off = self._display_offset()
        out = []
        for i in range(self._display_size()):
            if (i - off) % n != x % n:
                continue
            for j in range(self._display_size()):
                if (j - off) % n == y % n:
                    out.append((i, j))
        return out

    def _display_to_actual(self, i, j):
        """Actual board cell shown at display index (i, j)."""
        if not self.board.torus:
            return i, j
        n = self.size
        off = self._display_offset()
        return (i - off) % n, (j - off) % n

    @staticmethod
    def _to_hex(color):
        """Hex form of the few named colours used for mixing."""
        named = {
            "black": "#000000", "white": "#ffffff", "red": "#ff0000",
            "blue": "#0000ff", "green": "#00a000", "gray": "#808080",
            "darkred": "#8b0000", "darkgray": "#a9a9a9",
        }
        return named.get(color, color)

    def _in_actual_region(self, i, j):
        """Is display index (i, j) part of the real n x n board?"""
        if not self.board.torus:
            return True
        off = self._display_offset()
        n = self.size
        return off <= i < off + n and off <= j < off + n

    def _ring_distance(self, i, j):
        """0 inside the real board, 1, 2, ... for each wrapped ring."""
        if not self.board.torus:
            return 0
        off = self._display_offset()
        n = self.size

        def dist(v):
            if v < off:
                return off - v
            if v > off + n - 1:
                return v - (off + n - 1)
            return 0

        return max(dist(i), dist(j))

    def _segment_ring(self, fixed, along):
        """Ring of a grid-line segment: fixed is the line index, along the
        index of the segment running along it."""
        if not self.board.torus:
            return 0
        off = self._display_offset()
        n = self.size
        cell_style = self.board_style == "cell"
        line_hi = off + n if cell_style else off + n - 1
        seg_lo, seg_hi = off, off + n - 1

        def dist(v, lo, hi):
            if v < lo:
                return lo - v
            if v > hi:
                return v - hi
            return 0

        return max(dist(fixed, off, line_hi), dist(along, seg_lo, seg_hi))

    def _fake_mix(self, color, ratio=0.5):
        """Faded colour used for everything drawn in the mirrored ring."""
        return self._mix_colors(self._to_hex(color), self.board_bg, ratio)

    def _grid_extent(self):
        """Pixel span of the playing area for the current board style."""
        n = self._display_size()
        if self.board_style == "cell":
            return n * self.cell
        return (n - 1) * self.cell

    def _update_origin(self):
        """Place the grid directly under the header strip (the header's last
        row is a blank line, giving exactly one-line spacing).  Only the
        horizontal position is centred inside the yellow canvas."""
        extent = self._grid_extent()
        width = self.canvas.winfo_width()
        if width <= 1:
            width = self.canvas_size
        band = self._band_height()
        self.origin_x = int(max(0, (width - extent) / 2))
        self.origin_y = int(band)

    def _point_center(self, x, y):
        """Canvas coords of logical point (x, y): an intersection, or the
        center of the matching cell in cell style."""
        if self.board_style == "cell":
            return (self.origin_x + (y + 0.5) * self.cell,
                    self.origin_y + (x + 0.5) * self.cell)
        return (self.origin_x + y * self.cell, self.origin_y + x * self.cell)

    def _on_canvas_resize(self, _event=None):
        # Re-fit the board to the (possibly resized) window, then redraw.
        if not getattr(self, "_fitting", False):
            self._fit_cell()
            self._apply_canvas_size()
        self.draw_board()

    def _draw_extension_background(self, dn):
        """Fade the mirrored ring background towards white."""
        if not self.board.torus:
            return
        h = self.cell / 2
        for i in range(dn):
            for j in range(dn):
                if self._in_actual_region(i, j):
                    continue
                # No gradient: every wrapped ring uses the first-ring tint.
                color = self._mix_colors(self.board_bg, "#ffffff", 0.72)
                cx, cy = self._display_center(i, j)
                self.canvas.create_rectangle(cx - h, cy - h, cx + h, cy + h,
                                             fill=color, outline="")

    def _grid_line_colour(self, ring):
        if ring <= 0:
            return self.line_color
        # Uniform 50% white for every wrapped ring (no gradient).
        return self._mix_colors(self._to_hex(self.line_color), "#ffffff", 0.5)

    def _draw_grid(self, dn, ox, oy):
        if not self.board.torus:
            if self.board_style == "cell":
                end = dn * self.cell
                for i in range(dn + 1):
                    p = i * self.cell
                    self.canvas.create_line(ox + p, oy, ox + p, oy + end,
                                            fill=self.line_color)
                    self.canvas.create_line(ox, oy + p, ox + end, oy + p,
                                            fill=self.line_color)
            else:
                end = (dn - 1) * self.cell
                for i in range(dn):
                    p = i * self.cell
                    self.canvas.create_line(ox + p, oy, ox + p, oy + end,
                                            fill=self.line_color)
                    self.canvas.create_line(ox, oy + p, ox + end, oy + p,
                                            fill=self.line_color)
            return
        if self.board_style == "cell":
            for i in range(dn + 1):
                x = ox + i * self.cell
                for j in range(dn):
                    ring = self._segment_ring(i, j)
                    y1 = oy + j * self.cell
                    self.canvas.create_line(x, y1, x, y1 + self.cell,
                                            fill=self._grid_line_colour(ring))
            for j in range(dn + 1):
                y = oy + j * self.cell
                for i in range(dn):
                    ring = self._segment_ring(j, i)
                    x1 = ox + i * self.cell
                    self.canvas.create_line(x1, y, x1 + self.cell, y,
                                            fill=self._grid_line_colour(ring))
        else:
            for i in range(dn):
                x = ox + i * self.cell
                for j in range(dn - 1):
                    ring = self._segment_ring(i, j)
                    y1 = oy + j * self.cell
                    self.canvas.create_line(x, y1, x, y1 + self.cell,
                                            fill=self._grid_line_colour(ring))
            for j in range(dn):
                y = oy + j * self.cell
                for i in range(dn - 1):
                    ring = self._segment_ring(j, i)
                    x1 = ox + i * self.cell
                    self.canvas.create_line(x1, y, x1 + self.cell, y,
                                            fill=self._grid_line_colour(ring))

    def _draw_board_frame(self, dn, ox, oy):
        """Mirror-like white frame around the real board."""
        if not self.board.torus:
            return
        off = self._display_offset()
        n = self.size
        if self.board_style == "cell":
            left = ox + off * self.cell
            top = oy + off * self.cell
            right = ox + (off + n) * self.cell
            bottom = oy + (off + n) * self.cell
        else:
            left = ox + (off - 0.5) * self.cell
            top = oy + (off - 0.5) * self.cell
            right = ox + (off + n - 0.5) * self.cell
            bottom = oy + (off + n - 0.5) * self.cell
        self.canvas.create_rectangle(left, top, right, bottom,
                                     outline="#f2f2f2", width=3)
    def draw_board(self, with_hints=True):
        self.canvas.delete("all")
        self.canvas.configure(bg=self.board_bg)
        self._update_origin()
        dn = self._display_size()
        ox, oy = self.origin_x, self.origin_y
        self._draw_extension_background(dn)
        self._draw_grid(dn, ox, oy)
        self._draw_board_frame(dn, ox, oy)

        for sx, sy in STAR_POINTS.get(self.size, []):
            for dx, dy in self._display_copies(sx, sy):
                cx, cy = self._display_center(dx, dy)
                fill = self.star_color
                if not self._in_actual_region(dx, dy):
                    fill = self._fake_mix(fill)
                self.canvas.create_oval(
                    cx - 3, cy - 3, cx + 3, cy + 3, fill=fill
                )

        # Obstacles: dark-yellow filled cells (walls).  Drawn after the grid
        # so the surrounding lines stay visible.
        half = self.cell // 2 - 2
        for x, y in self.board.obstacle_positions():
            for dx, dy in self._display_copies(x, y):
                cx, cy = self._display_center(dx, dy)
                color = self.obstacle_color
                if not self._in_actual_region(dx, dy):
                    color = self._fake_mix(color)
                self.canvas.create_rectangle(cx - half, cy - half,
                                             cx + half, cy + half,
                                             fill=color, outline=color)

        move_numbers = {}
        if self.show_moves_var.get():
            move_numbers = self.get_move_numbers()

        dead = self.board.get_dead_positions() if with_hints else set()
        for x in range(self.size):
            for y in range(self.size):
                v = self.board.grid[x, y]
                if v in (BLACK, WHITE):
                    self.draw_stone(x, y, v, move_numbers.get((x, y)),
                                    dead_black=(v == BLACK and (x, y) in dead))

        if self.last_move is not None and self.board.grid[self.last_move] != EMPTY:
            lx, ly = self.last_move
            r = 10 if self.replay_mode and (lx, ly) in self.replay_new_stones \
                else self.cell // 2 - 2
            for dx, dy in self._display_copies(lx, ly):
                cx, cy = self._display_center(dx, dy)
                color = "red"
                if not self._in_actual_region(dx, dy):
                    color = self._fake_mix("red")
                self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                        outline=color, width=2)

        # Drop-position preview is drawn under the hint overlays so the
        # red/blue/green markers stay fully readable on top of it.
        self._draw_hover()
        if with_hints and self.hint_var.get():
            self.draw_hints(dead)
        elif self.show_candidates_var.get():
            self._draw_candidate_squares()
        self._draw_top_band()

    def draw_stone(self, x, y, color, move_num=None, dead_black=False):
        r = 10 if self.replay_mode and (x, y) in self.replay_new_stones \
            else self.cell // 2 - 2
        fill = "black" if color == BLACK else "white"
        for dx, dy in self._display_copies(x, y):
            cx, cy = self._display_center(dx, dy)
            fake = not self._in_actual_region(dx, dy)
            stone_fill = self._fake_mix(fill) if fake else fill
            outline = self._fake_mix(self.line_color) if fake \
                else self.line_color
            self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                    fill=stone_fill, outline=outline)
            if dead_black:
                s = 6
                dead_fill = self._fake_mix("gray") if fake else "gray"
                dead_outline = self._fake_mix("darkgray") if fake \
                    else "darkgray"
                self.canvas.create_rectangle(cx - s, cy - s, cx + s, cy + s,
                                             fill=dead_fill, outline=dead_outline)
            if move_num is not None:
                text_color = "white" if color == BLACK else "black"
                if fake:
                    text_color = self._fake_mix(text_color)
                self.canvas.create_text(cx, cy, text=str(move_num),
                                        fill=text_color,
                                        font=("Arial", 8, "bold"))

    def draw_hints(self, dead):
        def paint(color, fake):
            return self._fake_mix(color) if fake else color

        # White territory: grey square on the upper layer.
        for x, y in dead:
            if self.board.grid[x, y] != EMPTY:
                continue
            for dx, dy in self._display_copies(x, y):
                cx, cy = self._display_center(dx, dy)
                fake = not self._in_actual_region(dx, dy)
                s = 6
                self.canvas.create_rectangle(
                    cx - s, cy - s, cx + s, cy + s,
                    fill=paint("white", fake), outline=paint("gray", fake),
                    stipple="gray50")

        # Blue crosses: forbidden / no-liberty points (cached).
        blue_crosses = self.board.get_blue_cross_positions()
        for x, y in blue_crosses:
            if not self.board.is_empty(x, y):
                continue
            for dx, dy in self._display_copies(x, y):
                cx, cy = self._display_center(dx, dy)
                fake = not self._in_actual_region(dx, dy)
                color = paint("blue", fake)
                r = 6
                self.canvas.create_line(cx - r, cy - r, cx + r, cy + r,
                                        fill=color, width=2)
                self.canvas.create_line(cx - r, cy + r, cx + r, cy - r,
                                        fill=color, width=2)

        # Candidate squares are below red markers.
        self._draw_candidate_squares()

        # Red markers.
        threats = self.board.compute_threats()
        for (x, y), threat in threats.items():
            if not self.board.is_empty(x, y):
                continue
            hollow = (threat in ("four_three", "open_four")
                      and self.board.is_hollow_triangle((x, y), threat))
            for dx, dy in self._display_copies(x, y):
                cx, cy = self._display_center(dx, dy)
                fake = not self._in_actual_region(dx, dy)
                red = paint("red", fake)
                dark = paint("darkred", fake)
                if threat == "five_point":
                    r = 8
                    self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                            fill=red, outline=dark)
                elif threat in ("four_three", "open_four"):
                    r = 8
                    if hollow:
                        self.canvas.create_polygon(
                            cx, cy - r, cx - r, cy + r, cx + r, cy + r,
                            outline=red, width=2, fill=""
                        )
                    else:
                        self.canvas.create_polygon(
                            cx, cy - r, cx - r, cy + r, cx + r, cy + r,
                            fill=red, outline=dark
                        )
                elif threat in ("rush_four", "open_three"):
                    r = 8
                    self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                            outline=red, width=2)
                elif threat in ("sleep_three", "open_two"):
                    r = 5
                    self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                            outline=red, width=2)
                elif threat == "sleep_two":
                    self.canvas.create_oval(cx - 2, cy - 2, cx + 2, cy + 2,
                                            fill=red, outline=red)

    def _draw_candidate_squares(self):
        if not self.show_candidates_var.get():
            return
        r = 8  # same half-size as a large circle
        for x, y in self._get_candidate_display_positions():
            if not self.board.is_empty(x, y):
                continue
            for dx, dy in self._display_copies(x, y):
                cx, cy = self._display_center(dx, dy)
                color = "green"
                if not self._in_actual_region(dx, dy):
                    color = self._fake_mix(color)
                self.canvas.create_rectangle(
                    cx - r, cy - r, cx + r, cy + r,
                    outline=color, width=2
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
    def _screen_to_display(self, event):
        """Display-grid index under the mouse (may be outside the grid)."""
        if self.board_style == "cell":
            return (int((event.y - self.origin_y) // self.cell),
                    int((event.x - self.origin_x) // self.cell))
        return (round((event.y - self.origin_y) / self.cell),
                round((event.x - self.origin_x) / self.cell))

    def _screen_to_point(self, event):
        i, j = self._screen_to_display(event)
        dn = self._display_size()
        if self.board.torus:
            if not (0 <= i < dn and 0 <= j < dn):
                return None
            return self._display_to_actual(i, j)
        return (i, j)

    def _on_mouse_move(self, event):
        if self.game_over:
            if self.hover_point is not None:
                self.hover_point = None
                self.draw_board()
            return
        point = self._screen_to_point(event)
        if point is None or not self.board.in_bounds(*point):
            if self.hover_point is not None:
                self.hover_point = None
                self.hover_display = None
                self.draw_board()
            return
        x, y = point
        i, j = self._screen_to_display(event)
        if self.hover_point != (x, y) or self.hover_display != (i, j):
            self.hover_point = (x, y)
            self.hover_display = (i, j)
            self.draw_board()

    def _on_mouse_leave(self, _event=None):
        if self.hover_point is not None:
            self.hover_point = None
            self.hover_display = None
            self.draw_board()

    def _draw_hover(self):
        """Preview where a left click would drop a stone.

        Cell style: the whole hovered cell is highlighted (translucent gold
        overlay).  Point style: a ghost stone of the current colour whose
        "75% transparency" is drawn directly - the stone colour is blended
        with 75% of the board background colour into a solid fill."""
        if self.hover_point is None or self.board.grid[self.hover_point] != EMPTY:
            return
        if self.game_over or self.ai_thinking:
            return
        x, y = self.hover_point
        if self.board.torus:
            # The ghost is shown on the real board cell, even when the mouse
            # is over a mirrored copy in the ring.
            off = self._display_offset()
            di, dj = x + off, y + off
        else:
            di, dj = x, y
        cx, cy = self._display_center(di, dj)
        if self.board_style == "cell":
            half = self.cell // 2
            self.canvas.create_rectangle(cx - half, cy - half,
                                         cx + half, cy + half,
                                         fill="#d8a63f", outline="",
                                         stipple="gray50")
        else:
            stone = "#000000" if self.current == BLACK else "#ffffff"
            ghost = self._mix_colors(stone, self.board_bg, 0.25)
            r = self.cell // 2 - 2
            if self.current == WHITE:
                # light ghost fill needs a dark (black+75% bg) ring to be
                # recognisable against the yellow board.
                ring = self._mix_colors("#000000", self.board_bg, 0.25)
                self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                        fill=ghost, outline=ring, width=1)
            else:
                self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                        fill=ghost, outline="")

    def on_click(self, event):
        if self.game_over or self.ai_thinking:
            return
        point = self._screen_to_point(event)
        if point is None or not self.board.in_bounds(*point):
            return
        x, y = point
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
        # Right-click assists the human side only.
        if self.current == BLACK and not self.black_is_human():
            return
        if self.current == WHITE and not self.white_is_human():
            return
        # "显示AI候选点" on (alone or together with "玩家落子提示"):
        # full AI search, then drop the chosen stone.
        if self.show_candidates_var.get():
            self._run_ai_for_human()
            return
        # Only "玩家落子提示" on: quick forced response - when a five-point
        # exists, play/block it immediately instead of a full AI search.
        if self.hint_var.get():
            if not self._quick_forced_response():
                self._restore_main_window()
                messagebox.showinfo(
                    "自动落子",
                    "当前没有可一步成五/必应的点位。\n"
                    "开启“显示AI候选点”后，右键将执行完整AI搜索落子。"
                )
            return
        self._restore_main_window()
        messagebox.showinfo(
            "自动落子",
            "请开启“玩家落子提示”（快速应对）或\n"
            "“显示AI候选点”（完整AI搜索落子）后使用右键自动落子。"
        )

    def _run_ai_for_human(self):
        """Full AI search + drop for the current human player.  Runs as an
        assist so its time is charged to the human clock, not the AI row."""
        if self.current == BLACK and self.black_is_human():
            self.run_ai_move(BLACK, assist=True)
        elif self.current == WHITE and self.white_is_human():
            self.run_ai_move(WHITE, assist=True)

    def _quick_forced_response(self):
        """Immediate forced drop: if a black five-point exists, play it when
        it is Black's move or block it when it is White's move."""
        threats = self.board.compute_threats()
        five = [pos for pos, t in threats.items() if t == "five_point"]
        if not five:
            return False
        x, y = five[0]
        if self.current == BLACK:
            if not self.board.is_empty(x, y):
                return False
            self.try_play_black(x, y)
        elif self.current == WHITE:
            self.try_play_white(x, y)
        else:
            return False
        return True

    def try_play_black(self, x, y):
        if not self.board.is_empty(x, y):
            return
        self._stop_search()
        was_human = self.black_is_human()
        if was_human:
            self._record_human_move_time(BLACK)
        self._finish_turn_time(BLACK, not was_human)
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
        was_human = self.white_is_human()
        if was_human:
            self._record_human_move_time(WHITE)
        self._finish_turn_time(WHITE, not was_human)
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
        if not is_ai:
            self._record_human_move_time(color)
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
            self._abort_active_search()
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
            self._abort_active_search()

    # ------------------------------------------------------------------
    # Worker process management (the AI search runs out of process)
    # ------------------------------------------------------------------
    def _ensure_worker(self):
        """(Re)start the persistent AI worker process if it is not running."""
        if self.ai_worker_proc is not None and self.ai_worker_proc.is_alive():
            return
        self.job_queue = self.mp_ctx.Queue()
        self.result_queue = self.mp_ctx.Queue()
        self.ai_worker_proc = self.mp_ctx.Process(
            target=ai_worker.worker_main,
            args=(self.job_queue, self.result_queue, self.worker_epoch_ctl),
            daemon=True,
        )
        self.ai_worker_proc.start()

    def _shutdown_worker(self):
        proc = self.ai_worker_proc
        self.ai_worker_proc = None
        self.job_queue = None
        self.result_queue = None
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass

    def _sync_worker_epoch(self):
        """Mirror the GUI's search epoch into the shared counter: every
        job whose epoch differs is aborted inside the worker."""
        try:
            self.worker_epoch_ctl.value = self.search_epoch
        except Exception:
            pass

    def _abort_active_search(self):
        """Interrupt the running search without invalidating its result:
        the worker commits the best completed depth and returns it."""
        try:
            self.worker_epoch_ctl.value += 1
        except Exception:
            pass

    def _stop_search(self):
        self.search_epoch += 1
        self.ai_thinking = False
        self._cancel_max_search_timer()
        self._sync_worker_epoch()

    def _poll_worker(self):
        """Recurring drain of the worker's result queue (main thread)."""
        try:
            if self.root.winfo_exists():
                self.root.after(self.worker_poll_ms, self._poll_worker)
        except Exception:
            return
        if self.result_queue is None:
            return
        refresh = False
        done_msgs = []
        try:
            while True:
                msg = self.result_queue.get_nowait()
                kind = msg.get("kind")
                if kind == "progress":
                    self._worker_progress(msg)
                elif kind == "refresh":
                    refresh = True
                elif kind == "done":
                    done_msgs.append(msg)
        except queue_mod.Empty:
            pass
        except Exception:
            return
        # Collapse refresh requests: at most one redraw per poll.
        if refresh:
            self.draw_board()
        for msg in done_msgs:
            self._handle_worker_done(msg)
        # A crashed worker must never leave the GUI in "thinking" state.
        if (self.ai_thinking and self.ai_worker_proc is not None
                and not self.ai_worker_proc.is_alive()):
            self._stop_search()
            self._show_search_error("AI 工作进程异常退出")

    def _worker_progress(self, msg):
        epoch = msg["epoch"]
        if epoch != self.search_epoch:
            return
        completed_depth = msg["completed_depth"]
        elapsed_layer = msg["elapsed_layer"]
        finished = msg["finished"]
        focused = msg["focused"]
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
        # Throttle actual Tk label updates: the state above is updated
        # immediately, but the main loop is poked at most twice per second
        # so depth-0 updates do not slow the UI.
        now = time.monotonic()
        if now - self._last_progress_ui_time >= 0.5:
            self._last_progress_ui_time = now
            self._update_search_progress(completed_depth, elapsed_layer)

    def _handle_worker_done(self, msg):
        epoch = msg["epoch"]
        if msg.get("replay"):
            self._handle_replay_done(msg)
            return
        if epoch != self.search_epoch or self.game_over:
            return
        self._cancel_max_search_timer()
        self.ai_thinking = False
        self._finish_finished_search(epoch, msg)

    def _handle_replay_done(self, msg):
        """A replay-mode black reply came back from the worker."""
        if not self.replay_mode or msg["epoch"] != self.search_epoch:
            return
        self.ai_thinking = False
        self.thinking_label.config(text="")
        if msg["error"] is not None:
            self._replay_failed("复盘无法继续：黑棋未能获胜。")
            return
        move = msg["move"]
        if move is None or not self.board.is_empty(*move):
            self._replay_failed("复盘无法继续：黑棋未能获胜。")
            return
        self._apply_replay_black_move(move)

    def _finish_finished_search(self, epoch, msg):
        """Apply a completed AI search: update clocks/labels and drop the
        stone (same logic as the former thread-side apply callback)."""
        color = msg["color"]
        move = msg["move"]
        depth = msg["depth"]
        error = msg["error"]
        assist = msg["assist"]
        if error is not None:
            self._show_search_error(error)
            return
        total = time.time() - self.search_start_time
        if assist:
            # AI helped the human: this time belongs to the human.
            self._record_human_move_time(color)
            self._finish_turn_time(color, False)
        else:
            # Automatic AI turn: clock it by the real search time (the same
            # figure the blue label reports).
            self._add_ai_search_time(color, total)
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
            # Replay-table data the search produced (if any).
            self.board._black_replay_map = msg["replay_map"]
            self.board._last_black_win_path = msg["win_path"]
            self.handle_no_move(color, self.board, msg["should_pass"])
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
            # If the AI reported a forced table win, switch Black to table
            # mode from now on.
            if msg["replay_map"] or msg["win_path"]:
                self.black_table_mode = True
                self.replay_map = dict(msg["replay_map"])
                self.replay_black_moves = list(msg["win_path"])
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

    def run_ai_move(self, color, assist=False):
        """Run a full AI search and drop the chosen stone.

        The search itself runs in the persistent worker process; this only
        submits the job and returns immediately, so the window stays fluid.

        assist=True means the AI moved on behalf of a human (right click):
        the time is charged to that colour's human clock and the search is
        not counted in the AI (thinking) row."""
        if self.game_over:
            return
        self.ai_thinking = True
        self.search_epoch += 1
        epoch = self.search_epoch
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

        self._ensure_worker()
        # Abort any still-running stale job, then submit this one.
        self._sync_worker_epoch()
        self.job_queue.put({
            "kind": "search", "epoch": epoch, "color": color,
            "assist": assist, "board": self.board.copy(),
            "max_depth": max_depth, "min_search_time": min_search_time,
            "replay": False,
        })

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

    def handle_no_move(self, color, board_copy=None, should_pass=False):
        if color == BLACK:
            self._prompt_black_resign()
        else:
            if should_pass or (board_copy is not None and
                               ai_search.white_should_pass(board_copy)):
                self._pass_turn()
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
        self.search_epoch += 1
        self._sync_worker_epoch()
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
        self._stop_search()
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

        # The player chose a move outside the searched replies.  No error is
        # shown while Black still has a solid circle or a triangle: follow
        # the fallback order (solid circle first, then triangle).  Only when
        # neither exists is the replay reported as failed.
        threats = self.board.compute_threats()
        five = ai_search._five_points(threats)
        if five:
            self._apply_replay_black_move(five[0])
            return
        tri = ai_search._triangles(threats)
        if tri:
            self._apply_replay_black_move(tri[0])
            return

        # No solid circle and no triangle available: the replay cannot go on.
        self._replay_failed("复盘查表无对应应手，且黑棋没有实心圆/三角形可落。")

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

    def _display_chain(self, cells):
        """Display indices for a line of cells, choosing wrapped copies that
        keep consecutive centres close together."""
        if not cells:
            return []
        def center(disp):
            return self._display_center(*disp)
        def mid():
            return (self.origin_x + self._grid_extent() / 2,
                    self.origin_y + self._grid_extent() / 2)
        mx, my = mid()
        chain = [min(self._display_copies(*cells[0]),
                     key=lambda p: abs(center(p)[0] - mx) +
                                   abs(center(p)[1] - my))]
        for cell in cells[1:]:
            px, py = center(chain[-1])
            chain.append(min(self._display_copies(*cell),
                             key=lambda p: abs(center(p)[0] - px) +
                                           abs(center(p)[1] - py)))
        return chain

    def _show_unblocked_lines(self):
        for line in self.board.get_unblocked_lines():
            chain = self._display_chain(line)
            pts = []
            for disp in chain:
                pts.extend(self._display_center(*disp))
            if len(pts) >= 4:
                self.canvas.create_line(*pts, fill="red", width=1)

    def end_game(self, text):
        self.game_over = True
        self._stop_search()
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
        win.transient(self.root)
        win.protocol("WM_DELETE_WINDOW", self._close_mode_window)

        # 棋盘样式 no longer lives here: it is on the main window, applied
        # immediately (style_point_var / style_cell_var / _on_style_* are
        # reused there).

        tk.Label(win, text="棋盘尺寸", font=("Arial", 11, "bold")).pack(
            anchor=tk.W, padx=10)
        size_frame = tk.Frame(win)
        size_frame.pack(fill=tk.X, padx=10)
        for n in BOARD_SIZES:
            tk.Checkbutton(size_frame, text=f"{n}×{n}",
                           variable=self.board_size_vars[n],
                           command=lambda n=n: self._on_size_check(n)
                           ).pack(side=tk.LEFT)

        tk.Label(win, text="先手", font=("Arial", 11, "bold")).pack(anchor=tk.W, padx=10)
        first_frame = tk.Frame(win)
        first_frame.pack(fill=tk.X, padx=10)
        tk.Radiobutton(first_frame, text="黑棋（五子棋规则）先手",
                       variable=self.first_player_var, value="black").pack(side=tk.LEFT)
        tk.Radiobutton(first_frame, text="白棋（围棋规则）先手",
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

        tk.Label(win, text="白棋获胜条件", font=("Arial", 11, "bold")).pack(
            anchor=tk.W, padx=10, pady=(10, 0))
        white_win_frame = tk.Frame(win)
        white_win_frame.pack(fill=tk.X, padx=10)
        tk.Radiobutton(white_win_frame, text="全线封堵",
                       variable=self.white_win_var,
                       value="line_block").pack(side=tk.LEFT)
        tk.Radiobutton(white_win_frame, text="占领全盘",
                       variable=self.white_win_var,
                       value="occupy").pack(side=tk.LEFT, padx=10)

        tk.Label(win, text="预留接口", font=("Arial", 11, "bold")).pack(
            anchor=tk.W, padx=10, pady=(10, 0))
        tk.Checkbutton(win, text="环面模式（新对局生效）",
                       variable=self.torus_mode_var,
                       command=self.update_mode_label).pack(anchor=tk.W,
                                                            padx=10)
        tk.Checkbutton(win, text="启用障碍",
                       variable=self.obstacle_enabled_var,
                       command=self._on_obstacle_toggle).pack(anchor=tk.W,
                                                              padx=10)
        obstacle_frame = tk.Frame(win)
        obstacle_frame.pack(fill=tk.X, padx=20)
        tk.Label(obstacle_frame, text="选择障碍个数:").pack(side=tk.LEFT)
        tk.Entry(obstacle_frame, textvariable=self.obstacle_count_var,
                 width=6).pack(side=tk.LEFT)

        bottom = tk.Frame(win)
        bottom.pack(side=tk.BOTTOM, fill=tk.X, pady=10)
        tk.Button(bottom, text="新对局", command=self._apply_mode_new_game).pack(
            side=tk.TOP)

        # Size the window to fit its content (width at least 440px).
        win.update_idletasks()
        want_w = max(440, win.winfo_reqwidth())
        want_h = max(440, win.winfo_reqheight())
        win.geometry(f"{want_w}x{want_h}")

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

    def _on_obstacle_toggle(self):
        if self.obstacle_enabled_var.get():
            # Obstacles are drawn as filled cells: default to the cell style.
            if self.board_style != "cell":
                self.style_cell_var.set(1)
                self._on_style_cell()
            try:
                count = int(self.obstacle_count_var.get())
            except ValueError:
                count = 0
            if count <= 0:
                self.obstacle_count_var.set("6")

    def _select_board_size_var(self, size):
        for n, var in self.board_size_vars.items():
            var.set(1 if n == size else 0)

    def _apply_canvas_size(self):
        """Resize the canvas / side panel for the current board size.

        In torus mode the shown grid is n + 4, so the canvas grows with the
        two wrapped rows/columns on every side.
        """
        self._fit_cell()
        new_size = self._display_size() * self.cell + 2 * MARGIN
        key = (new_size, self.cell, self._torus_pad(), bool(self.board.torus))
        if key == self._canvas_key:
            return
        self._canvas_key = key
        self.canvas_size = new_size
        self.canvas_height = new_size + self._band_height()
        self.canvas.configure(width=new_size, height=self.canvas_height)
        self.info.configure(height=max(self.canvas_height + 80,
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
        self.board.torus = bool(self.torus_mode_var.get())
        self.board._forbid_overline = bool(self.forbid_overline_var.get())
        self.board._forbid_44 = bool(self.forbid_44_var.get())
        self.board._forbid_33 = bool(self.forbid_33_var.get())
        if self.obstacle_enabled_var.get():
            try:
                count = int(self.obstacle_count_var.get())
            except ValueError:
                count = 0
            if count > 0:
                self.board.place_random_obstacles(count)
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
        self.last_human_move_sec = None
        self.replay_mode = False
        self.replay_new_stones = set()
        self.replay_map = {}
        self.replay_black_moves = []
        self.black_table_mode = False
        self.replay_start_history_len = 0
        self.replay_pre_ai = (True, True)
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
            self._select_board_size_var(self.size)
        # Re-apply the canvas geometry: the restored game may use a
        # different board size and/or torus mode.
        self._apply_canvas_size()
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
        self.last_human_move_sec = None
        self.moves_since_new_game = 0
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
