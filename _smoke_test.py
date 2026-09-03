"""Temporary smoke test for the new board size / board style GUI features."""
import tkinter as tk

import gui
from board import HybridBoard

CELL = gui.CELL
MARGIN = gui.MARGIN

root = tk.Tk()
app = gui.GameGUI(root, board_size=15, black_is_ai=False, white_is_ai=False)

# --- defaults ---
assert app.size == 15
assert app.board_style == "point"
assert app._selected_board_size() == 15
assert app.style_point_var.get() == 1 and app.style_cell_var.get() == 0
app.draw_board()
# Unmapped window: fallback origin centers grid inside the requested canvas.
assert app.origin_x == (app.canvas_size - app._grid_extent()) // 2, app.origin_x
assert app.origin_y == (app.canvas_size - app._grid_extent()) // 2

# --- map the window, re-check real centering ---
root.update()
app.draw_board()
w, h = app.canvas.winfo_width(), app.canvas.winfo_height()
assert w > 1 and h > 1, (w, h)
assert app.origin_x == (w - app._grid_extent()) // 2, (app.origin_x, w)
assert app.origin_y == (h - app._grid_extent()) // 2, (app.origin_y, h)
assert app.origin_x + app._grid_extent() <= w
assert app.origin_y + app._grid_extent() <= h

# --- intersection-mode click mapping (same math as on_click) ---
class E:
    pass

e = E()
e.x, e.y = app.origin_x + 5 * CELL + 2, app.origin_y + 7 * CELL - 3
assert (round((e.y - app.origin_y) / CELL),
        round((e.x - app.origin_x) / CELL)) == (7, 5)

# --- cell style toggle ---
app.style_cell_var.set(1)
app._on_style_cell()
assert app.board_style == "cell"
assert app.style_point_var.get() == 0
assert app._grid_extent() == 15 * CELL
assert app.origin_x + 15 * CELL <= w, "cell grid overflows canvas"
assert app.origin_y + 15 * CELL <= h
cx, cy = app._point_center(4, 6)
e.x, e.y = int(cx), int(cy)
assert (int((e.y - app.origin_y) // CELL),
        int((e.x - app.origin_x) // CELL)) == (4, 6)

# --- back to point style (simulate clicking the 交叉点 checkbox) ---
app.style_point_var.set(1)
app._on_style_point()
assert app.board_style == "point" and app.style_cell_var.get() == 0

# unchecking the only selected style just restores it, style unchanged
app.style_cell_var.set(0)
app._on_style_cell()
assert app.style_cell_var.get() == 1 and app.board_style == "point"
app.style_point_var.set(1)
app._on_style_point()
assert app.style_point_var.get() == 1 and app.style_cell_var.get() == 0

# --- size checkbox exclusivity ---
app._on_size_check(9)
assert app._selected_board_size() == 9
assert all(v.get() == (n == 9) for n, v in app.board_size_vars.items())
app.board_size_vars[9].set(0)
app._on_size_check(9)
assert app.board_size_vars[9].get() == 1, "cannot deselect the only size"

# --- new game applies the selected size ---
app._on_size_check(13)
app.new_game()
assert app.size == 13 and app.board.size == 13
assert app.board.grid.shape == (13, 13)
assert app.canvas_size == 13 * CELL + 2 * MARGIN
assert int(app.canvas["width"]) == app.canvas_size
assert "13x13" in root.title(), root.title()
app.draw_board()

# --- play a stone, switch size, undo restores the old game ---
app.try_play_black(3, 4)
assert len(app.board.history) == 1
app._on_size_check(9)
app.new_game()
assert app.size == 9
app.undo_move()
assert app.size == 15, app.size
assert app.board.size == 15
assert len(app.board.history) == 1
assert app._selected_board_size() == 15

# --- stones + hints render in both styles on every size ---
app.hint_var.set(1)
app.show_candidates_var.set(1)
for size in gui.BOARD_SIZES:
    app._select_board_size_var(size)
    app.size = size
    app.board = HybridBoard(size)
    for (sx, sy) in gui.STAR_POINTS[size]:
        assert 0 <= sx < size and 0 <= sy < size
        mirror = (size - 1 - sx, size - 1 - sy)
        assert mirror in gui.STAR_POINTS[size], (size, sx, sy)
    b = app.board
    b.play_black(7, 7)
    b.play_white(8, 7)
    b.play_black(7, 8)
    b.play_white(8, 8)
    b.play_black(7, 9)
    app.last_move = (7, 9)
    for style in ("point", "cell"):
        app.board_style = style
        app.draw_board()
        app.draw_board(with_hints=False)
app.board_style = "point"

root.destroy()
print("SMOKE_TEST_PASS")
