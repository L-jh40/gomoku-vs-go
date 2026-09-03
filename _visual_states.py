"""Temporary visual-check driver: opens the real GUI in a given state for
~30 s so window-scoped screenshots can be taken without stealing focus."""
import sys
import time

import tkinter as tk

import gui
from board import HybridBoard

state = sys.argv[1] if len(sys.argv) > 1 else "default"

root = tk.Tk()
app = gui.GameGUI(root, board_size=15, black_is_ai=False, white_is_ai=False)
root.update()

if state == "mode":
    app.open_mode_window()
elif state == "cell":
    # Simulate the user checking 落子格子.
    app.style_cell_var.set(1)
    app._on_style_cell()
    app.open_mode_window()
elif state == "cell9":
    app.style_cell_var.set(1)
    app._on_style_cell()
    app.board_size_vars[9].set(1)
    app._on_size_check(9)
    app.new_game()
    app.open_mode_window()
elif state == "stones":
    # Cell style with a small game and hints enabled.
    app.style_cell_var.set(1)
    app._on_style_cell()
    app.hint_var.set(1)
    b = app.board
    for i, (x, y) in enumerate([(7, 7), (8, 7), (7, 8), (6, 8), (7, 9)]):
        if i % 2 == 0:
            b.play_black(x, y)
        else:
            b.play_white(x, y)
    app.last_move = (7, 9)
    app.draw_board()

end = time.time() + 90
while time.time() < end:
    root.update()
    time.sleep(0.03)
root.destroy()
print("DRIVER_DONE", state)
