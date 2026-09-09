# -*- coding: utf-8 -*-
"""Torus-mode tests: wrapped liberties/fives (rules) and the extended
n+4 display with wrapped copies (GUI).

Run from this folder:  python tests_torus.py
"""
from __future__ import annotations

import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from board import HybridBoard, BLACK, WHITE, EMPTY, OBSTACLE
import rules


def test_rules_torus():
    """Wrapped liberties, captures, fives and overlines."""
    ok = []
    def check(name, cond, detail=""):
        ok.append((name, bool(cond)))
        print(("PASS" if cond else "FAIL"), "-", name, detail)

    def torus_board(n=9):
        b = HybridBoard(n)
        b.torus = True
        b._invalidate_caches()
        return b

    # 1. five across the wrap
    b = torus_board()
    for y in (6, 7, 8, 0, 1):
        b.grid[0, y] = BLACK
    b._invalidate_caches()
    five = all(b.check_black_five(0, y) for y in (6, 7, 8, 0, 1))
    check("torus: five across wrap detected", five)
    nb = HybridBoard(9)
    for y in (6, 7, 8, 0, 1):
        nb.grid[0, y] = BLACK
    nb._invalidate_caches()
    check("non-torus: same shape is not a five", not any(nb.check_black_five(0, y)
          for y in (6, 7, 8, 0, 1)))

    # 2. overline across wrap
    b2 = torus_board()
    for y in (5, 6, 7, 8, 0, 1):
        b2.grid[0, y] = BLACK
    b2._invalidate_caches()
    check("torus: overline across wrap", all(b2.check_black_overline(0, y)
          for y in (5, 6, 7, 8, 0, 1)) and
          not any(b2.check_black_five(0, y) for y in (5, 6, 7, 8, 0, 1)))

    # 3. liberties wrap: black at (0,4) has only the wrapped liberty (8,4)
    b3 = torus_board()
    for cell in ((0, 3), (0, 5), (1, 4)):
        b3.grid[cell] = WHITE
    b3._invalidate_caches()
    ok_play, _ = b3.play_black(0, 4)
    check("torus: wrapped liberty allows the move", ok_play)
    stones, libs = b3.get_group(0, 4)
    check("torus: wrapped liberty counted", libs == {(8, 4)}, str(libs))
    nb3 = HybridBoard(9)
    for cell in ((0, 3), (0, 5), (1, 4)):
        nb3.grid[cell] = WHITE
    nb3._invalidate_caches()
    ok_play2, _ = nb3.play_black(0, 4)
    check("non-torus: same move is self-capture (rejected)", not ok_play2)

    # 4. capture across the wrap
    b4 = torus_board()
    b4.grid[0, 4] = BLACK
    for cell in ((0, 3), (0, 5), (1, 4)):
        b4.grid[cell] = WHITE
    b4._invalidate_caches()
    ok_w, captured = b4.play_white(8, 4)
    check("torus: capture via wrapped liberty", ok_w and (0, 4) in captured,
          str(captured))

    # 5. five point threat across wrap
    b5 = torus_board()
    for y in (6, 7, 8, 0):
        b5.grid[0, y] = BLACK
    b5._invalidate_caches()
    th = b5.compute_threats()
    check("torus: five_point at wrapped completion",
          th.get((0, 1)) == "five_point", str(th.get((0, 1))))

    # 6. rules.line_code wraps (no edge blocker)
    code = rules.line_code(b5, 0, 1, 0, 1) if b5.grid[0, 1] == EMPTY else None
    if code is None:
        b5.grid[0, 1] = BLACK
        code = rules.line_code(b5, 0, 1, 0, 1)
        b5.grid[0, 1] = EMPTY
    check("torus: line_code has no edge blockers (no leading/trailing 2 from edges)",
          code.count("2") == 0, code)

    # 7. farthest fallback uses cyclic distance
    b7 = torus_board()
    b7.grid[4, 4] = BLACK
    b7._invalidate_caches()
    cand = b7.get_black_candidate_moves()
    best = b7.farthest_open_positions(cand)
    def cyc_cheb(p, q):
        dx = abs(p[0] - q[0]); dx = min(dx, 9 - dx)
        dy = abs(p[1] - q[1]); dy = min(dy, 9 - dy)
        return max(dx, dy)
    check("torus: farthest uses cyclic Chebyshev", best and
          cyc_cheb(best[0], (4, 4)) == 4, str(best[:3]))

    # 8. white line-block windows wrap
    b8 = HybridBoard(9)
    b8.torus = True
    b8.grid.fill(WHITE)
    for y in (6, 7, 8, 0, 1):
        b8.grid[0, y] = EMPTY
    b8._invalidate_caches()
    check("torus: unblocked wrapped window detected",
          any(len(line) == 5 for line in b8.get_unblocked_lines()))

    # 9. non-torus regression: ordinary five still works
    b9 = HybridBoard(9)
    for y in (2, 3, 4, 5, 6):
        b9.grid[4, y] = BLACK
    b9._invalidate_caches()
    check("non-torus: ordinary five still detected", b9.check_black_five(4, 4))

    print()
    fails = [x for x in ok if not x[1]]
    print("TOTAL:", len(ok), "FAILED:", len(fails))
    assert not fails

def test_gui_torus():
    """Extended n+4 display, wrapped copies and click mapping."""
    import tkinter as tk
    import gui as gui_mod
    # The multiprocessing worker cannot start in some environments; this
    # display-only test does not need it.
    gui_mod.GameGUI._ensure_worker = lambda self: None
    gui_mod.GameGUI._poll_worker = lambda self: None
    from gui import GameGUI, CELL, MARGIN
    from gui import GameGUI, CELL, MARGIN
    from board import BLACK, WHITE

    ok = []
    def check(name, cond, detail=""):
        ok.append((name, bool(cond)))
        print(("PASS" if cond else "FAIL"), "-", name, detail)

    root = tk.Tk()
    g = GameGUI(root, black_is_ai=False, white_is_ai=False)
    root.update_idletasks(); root.update()

    # enable torus and start a new game
    g.torus_mode_var.set(1)
    g.new_game()
    root.update()
    check("board.torus set by new game", g.board.torus)
    check("display size = n + 4", g._display_size() == g.size + 4,
          f"{g._display_size()} vs {g.size}")
    check("canvas size follows display grid (dynamic cell)",
          g.canvas_size == g._display_size() * g.cell + 2 * MARGIN,
          str(g.canvas_size))
    check("cell size fitted into the window (<= base, >= 50%)",
          15 <= g.cell <= CELL, str(g.cell))

    # grid lines: point style draws one line per display index per direction
    lines = [i for i in g.canvas.find_all() if g.canvas.type(i) == "line"]
    dn = g._display_size()
    check("grid drawn as ring-coloured segments over the extended grid",
          len(lines) == 2 * dn * (dn - 1), str(len(lines)))

    # copies of an actual cell
    copies = g._display_copies(0, 0)
    check("corner cell has 4 wrapped copies (2 per axis)",
          len(copies) == 4, str(copies))

    # place a stone on the actual board and count its drawn copies
    g.board.grid[0, 0] = BLACK
    g.board._invalidate_caches()
    g.draw_board()
    stones = [i for i in g.canvas.find_all()
              if g.canvas.type(i) == "oval"
              and g.canvas.itemcget(i, "fill") == "black"
              and (g.canvas.bbox(i)[2] - g.canvas.bbox(i)[0]) > 8]
    check("real stone drawn once (ring copies are faded)",
          len(stones) == 1, str(len(stones)))

    # screen -> actual mapping through a wrapped copy
    disp = copies[-1]
    cx, cy = g._display_center(*disp)
    ev = types.SimpleNamespace(x=int(cx), y=int(cy))
    check("click on a wrapped copy maps to the actual cell",
          g._screen_to_point(ev) == (0, 0), str(g._screen_to_point(ev)))

    # hover uses the copy under the mouse
    g._on_mouse_move(ev)
    check("hover stores actual cell and display copy",
          g.hover_point == (0, 0) and g.hover_display == disp,
          f"{g.hover_point} {g.hover_display}")

    # clicking a wrapped copy of an empty cell plays on the actual cell
    g.board.grid[0, 0] = 0
    g.board._invalidate_caches()
    g.draw_board()
    disp2 = g._display_copies(7, 7)[-1]
    cx2, cy2 = g._display_center(*disp2)
    ev2 = types.SimpleNamespace(x=int(cx2), y=int(cy2))
    g.on_click(ev2)
    root.update()
    check("clicking a wrapped copy plays on the actual cell",
          g.board.grid[7, 7] == BLACK, str(g.board.grid[7, 7]))

    # --- mirror / faded ring rendering ---
    g.board.grid.fill(0)
    g.board.grid[0, 0] = BLACK
    g.board._invalidate_caches()
    g.hover_point = None
    g.draw_board()
    bg = g.board_bg
    fake_black = g._mix_colors("#000000", bg, 0.5)
    def stone_ovals(fill):
        out = []
        for i in g.canvas.find_all():
            if g.canvas.type(i) != "oval":
                continue
            if g.canvas.itemcget(i, "fill") != fill:
                continue
            x1, y1, x2, y2 = g.canvas.bbox(i)
            if x2 - x1 > 8:
                out.append(i)
        return out
    fake_stones = stone_ovals(fake_black)
    real_stones = stone_ovals("black")
    check("ring stones use 50% stone + 50% board background",
          len(fake_stones) == 3 and len(real_stones) == 1,
          f"fake={len(fake_stones)} real={len(real_stones)}")
    line_colors = {g.canvas.itemcget(i, "fill")
                   for i in g.canvas.find_all()
                   if g.canvas.type(i) == "line"}
    check("ring grid lines fade to white",
          "black" in line_colors and len(line_colors) > 1,
          str(sorted(line_colors)))
    frames = [i for i in g.canvas.find_all()
              if g.canvas.type(i) == "rectangle"
              and g.canvas.itemcget(i, "outline") in ("#f2f2f2", "#cfcfcf")]
    check("mirror frame drawn around the real board", len(frames) == 2,
          str(len(frames)))
    ext_fills = {g.canvas.itemcget(i, "fill")
                 for i in g.canvas.find_all()
                 if g.canvas.type(i) == "rectangle"
                 and g.canvas.itemcget(i, "outline") == ""}
    check("ring background fades towards white",
          any(f and f != bg for f in ext_fills), str(sorted(ext_fills)))
    # ghost appears on the real cell even when hovering a ring copy
    g.board.grid[0, 0] = 0
    g.board._invalidate_caches()
    g.current = BLACK
    g.game_over = False
    g.ai_thinking = False
    disp3 = g._display_copies(3, 3)[0]
    cx3, cy3 = g._display_center(*disp3)
    g._on_mouse_move(types.SimpleNamespace(x=int(cx3), y=int(cy3)))
    g.draw_board()
    ghost_fill = g._mix_colors("#000000", bg, 0.25)
    off = g._display_offset()
    gx, gy = g._display_center(3 + off, 3 + off)
    ghosts = []
    for i in g.canvas.find_all():
        if g.canvas.type(i) != "oval":
            continue
        if g.canvas.itemcget(i, "fill") != ghost_fill:
            continue
        x1, y1, x2, y2 = g.canvas.bbox(i)
        if abs((x1 + x2) / 2 - gx) <= 2 and abs((y1 + y2) / 2 - gy) <= 2:
            ghosts.append(i)
    check("ghost shown on the real cell for ring hover", len(ghosts) == 1,
          str(len(ghosts)))
    check("board model stays n x n (AI never sees the ring)",
          g.board.grid.shape == (g.size, g.size), str(g.board.grid.shape))
    # torus off: back to n grid and n canvas
    g.torus_mode_var.set(0)
    g.new_game()
    root.update()
    check("torus off restores normal display",
          (not g.board.torus and g._display_size() == g.size
           and g.canvas_size == g.size * g.cell + 2 * MARGIN),
          f"{g._display_size()} {g.canvas_size}")

    # --- hint ring switch: off / 4 cells / small-window fallback ---
    g.torus_mode_var.set(1)
    g.torus_hint_var.set(0)
    g.new_game()
    root.update()
    check("hint off: no mirrored ring",
          g._display_size() == g.size and g._torus_pad() == 0,
          f"{g._display_size()} pad={g._torus_pad()}")
    g.torus_hint_var.set(1)
    g.torus_hint_width_var.set(4)
    g.new_game()
    root.update()
    check("hint 4 cells: display n + 8",
          g._display_size() == g.size + 8 and g._torus_pad() == 4,
          f"{g._display_size()} pad={g._torus_pad()}")
    ring_cells = [i for i in g.canvas.find_all()
                  if g.canvas.type(i) == "rectangle"
                  and g.canvas.itemcget(i, "outline") == ""
                  and g.canvas.itemcget(i, "fill")
                  == g._mix_colors(g.board_bg, "#ffffff", 0.72)]
    check("4-cell ring fills all wrapped cells",
          len(ring_cells) == (g.size + 8) ** 2 - g.size ** 2,
          str(len(ring_cells)))

    # small window: board shrinks to 50% and the readout moves to the panel
    g._available_area = lambda: (150, 150)
    g._fit_cell()
    g._apply_canvas_size()
    g.draw_board()
    g.update_info()
    root.update()
    check("tiny window: cell shrinks to 50% floor", g.cell == 15, str(g.cell))
    check("tiny window: readout moves beside the board",
          g.header_in_panel and "黑棋时间" in g.stats_var.get()
          and not [i for i in g.canvas.find_all()
                   if "topband" in g.canvas.gettags(i)],
          g.stats_var.get().replace(chr(10), " / "))
    del g._available_area
    g.torus_hint_width_var.set(2)

    root.destroy()
    fails = [x for x in ok if not x[1]]
    print()
    print("TOTAL:", len(ok), "FAILED:", len(fails))
    assert not fails

if __name__ == "__main__":
    test_rules_torus()
    test_gui_torus()
    print("All torus checks passed.")
