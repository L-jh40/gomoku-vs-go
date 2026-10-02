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
              and g.canvas.itemcget(i, "outline") == "#f2f2f2"]
    check("single #f2f2f2 mirror frame around the real board",
          len(frames) == 1, str(len(frames)))
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
    # --- display-only shift with WASD / arrows ---
    g.board.grid.fill(0)
    g.board.grid[0, 0] = BLACK
    g.board._invalidate_caches()
    g.display_shift = [0, 0]
    g.draw_board()
    before = set(g._display_copies(0, 0))
    g._on_key(types.SimpleNamespace(keysym="w", widget=None))
    after = set(g._display_copies(0, 0))
    check("W moves the displayed board up one row",
          before != after and (1, 2) in after,
          f"{sorted(before)[:2]} -> {sorted(after)[:2]}")
    check("display shift does not change the board",
          g.board.grid[0, 0] == BLACK, str(g.board.grid[0, 0]))
    check("display_to_actual inverts the shift",
          g._display_to_actual(2, 2) == (1, 0),
          str(g._display_to_actual(2, 2)))
    g._on_key(types.SimpleNamespace(keysym="s", widget=None))
    check("S restores the original display",
          set(g._display_copies(0, 0)) == before,
          str(sorted(g._display_copies(0, 0))[:2]))
    g._on_key(types.SimpleNamespace(keysym="Right", widget=None))
    check("Right arrow shifts the columns",
          (2, 3) in set(g._display_copies(0, 0)),
          str(sorted(g._display_copies(0, 0))[:2]))
    g._on_key(types.SimpleNamespace(keysym="Left", widget=None))
    g.display_shift = [0, 0]
    # board export/import round-trip (the channel for reporting positions)
    import shutil
    import board_tools
    # Workspace-local scratch directory (the file sandbox allows writes
    # inside the workspace only).
    tmp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "_tmp_export")
    os.makedirs(tmp_dir, exist_ok=True)
    g.save_dir_var.set(tmp_dir)
    g.board.grid.fill(0)
    g.board.history = []
    g.pass_records = []
    g.board.grid[7, 7] = BLACK
    g.board.grid[7, 8] = WHITE
    g.board.grid[6, 6] = 3
    # white stones around the corner: (0, 0) becomes a dead (no-liberty)
    # empty point for black (the board is in torus mode here, so the
    # wrapped neighbours count as well)
    g.board.grid[0, 1] = WHITE
    g.board.grid[0, g.size - 1] = WHITE
    g.board.grid[1, 0] = WHITE
    g.board.grid[g.size - 1, 0] = WHITE
    g.board._invalidate_caches()
    dump_path = os.path.join(tmp_dir, "board_dump_test.txt")
    with open(dump_path, "w", encoding="utf-8") as fh:
        fh.write(g.export_board_text())
    b_rt, _named = board_tools.load_board(dump_path)
    check("board export/import round-trips",
          b_rt.grid.tobytes() == g.board.grid.tobytes()
          and b_rt.size == g.size, str(b_rt.size))
    dump_text = open(dump_path, encoding="utf-8").read()
    dump_lines = dump_text.split(chr(10))
    rows = [l for l in dump_lines
            if l and not l.startswith("#") and not l.startswith("moves:")]
    check("white and obstacle rows both export as 2",
          rows[7][7] == "1" and rows[7][8] == "2" and rows[6][6] == "2",
          rows[7][7] + rows[7][8] + rows[6][6])
    check("obstacles are recorded in the header",
          "(6,6)" in [l for l in dump_lines if l.startswith("# obstacles")][0],
          [l for l in dump_lines if l.startswith("# obstacles")][0])
    no_liberty_header = [l for l in dump_lines
                         if l.startswith("# no_liberty")][0]
    check("dead (no-liberty) empty points export as 2",
          rows[0][0] == "2" and "(0,0)" in no_liberty_header,
          rows[0][0] + " " + no_liberty_header)

    # a real game: G appends the coordinate line to 粘贴板.md
    g.new_game()
    root.update()
    g.try_play_black(7, 7)
    g.try_play_white(7, 8)
    g.human_pass()
    g.try_play_white(6, 6)
    root.update()
    g.thinking_label.config(text="")
    g._on_key(types.SimpleNamespace(keysym="g", widget=None))
    codes_path = os.path.join(tmp_dir, "粘贴板.md")
    last_line = ""
    if os.path.exists(codes_path):
        with open(codes_path, encoding="utf-8") as fh:
            text_lines = [l for l in fh.read().split(chr(10)) if l.strip()]
        last_line = text_lines[-1] if text_lines else ""
    check("G appends one coordinate line to 粘贴板.md",
          last_line == "h8 i8 p0 g9",
          repr(last_line) + " / " + g.thinking_label.cget("text"))
    check("G writes the dump into the chosen directory",
          os.path.exists(os.path.join(tmp_dir, "board_dump.txt")),
          tmp_dir)
    b_code, _n2, info_code = board_tools.parse_dump(last_line, size=g.size,
                                                    first=BLACK)
    check("the code line replays to the same position",
          b_code.grid.tobytes() == g.board.grid.tobytes(),
          info_code["source"])
    check("pass records are rebuilt from the code line",
          board_tools.pass_records_from_codes(last_line.split()) == [2],
          str(board_tools.pass_records_from_codes(last_line.split())))
    # importing through the GUI replays the codes into the board
    g.board.grid.fill(0)
    g.board.history = []
    g.new_game()
    root.update()
    g.board, _n3, info3 = board_tools.parse_dump(last_line, size=g.size,
                                                 first=BLACK)
    g._apply_imported_board(g.board, info3)
    root.update()
    check("imported board matches the exported position",
          g.board.grid.tobytes() == b_code.grid.tobytes()
          and g.pass_records == [2],
          str(g.pass_records) + " " + g.thinking_label.cget("text"))
    # forbid settings travel with the dump
    g.new_game()
    root.update()
    g.board._forbid_33 = False
    dump_ff = g.export_board_text()
    b_ff, _n4, info_ff = board_tools.parse_dump(dump_ff, size=g.size)
    check("forbid flags are read back from the dump header",
          info_ff["forbid"] == (True, True, False)
          and b_ff._forbid_33 is False,
          str(info_ff["forbid"]))
    g.forbid_33_var.set(1)
    g._apply_imported_board(b_ff, info_ff)
    root.update()
    check("importing a dump syncs the forbid check boxes",
          g.forbid_33_var.get() == 0 and g.board._forbid_33 is False,
          str(g.forbid_33_var.get()))
    # a bare code line keeps the current settings instead
    _b_bare, _n5, info_bare = board_tools.parse_dump("h8 i8", size=g.size)
    check("bare codes carry no forbid settings",
          info_bare["forbid"] is None, str(info_bare["forbid"]))
    g.forbid_33_var.set(1)
    g.board._forbid_33 = True

    # illegal moves in an imported code list are never played
    # three-three at h8: black e8/f8/j8/k8, white far away in row o
    codes_ff = "e8 o15 f8 o14 j8 o13 k8 o12 h8 i12"
    b_ill, _n6, info_ill = board_tools.parse_dump(codes_ff, size=15,
                                                  first=BLACK)
    check("forbidden move in a code list is rejected, not played",
          info_ill["errors"] == [("h8", "three_three")]
          and b_ill.grid[7, 7] == EMPTY
          and b_ill.grid[7, 4] == BLACK and b_ill.grid[7, 10] == BLACK,
          str(info_ill["errors"]) + " " + str(b_ill.grid[7, 7]))
    # i12 is white's move after the rejected h8 (the turn still passes)
    check("the legal moves after the rejected one still land",
          b_ill.grid[3, 8] == WHITE and b_ill.grid[7, 7] == EMPTY,
          str(b_ill.grid[3, 8]))
    # self-capture: (0, 0) is surrounded by white, the stone must not
    # appear at all (it used to be placed and then vanish)
    codes_sc = "f10 b15 g10 a14 a15"
    b_sc, _n7, info_sc = board_tools.parse_dump(codes_sc, size=15,
                                                first=BLACK)
    check("no-liberty move is rejected instead of vanishing",
          info_sc["errors"] == [("a15", "self_capture")]
          and b_sc.grid[0, 0] == EMPTY
          and b_sc.grid[5, 5] == BLACK,
          str(info_sc["errors"]) + " " + str(b_sc.grid[0, 0]))

    # the confirmation dialog decides whether the import happens
    asked = {"messages": []}
    original_ask = gui_mod.messagebox.askyesno
    def fake_ask(title, message, **kwargs):
        asked["title"] = title
        asked["messages"].append(message)
        return asked.pop("answer", False)
    gui_mod.messagebox.askyesno = fake_ask
    try:
        asked["answer"] = False
        declined = g._confirm_illegal_import([("h8", "three_three")], None)
        asked["answer"] = True
        accepted = g._confirm_illegal_import([("a15", "self_capture")], None)
    finally:
        gui_mod.messagebox.askyesno = original_ask
    check("rejected import is cancelled by default (No)", declined is False)
    all_text = "\n".join(asked["messages"])
    check("the dialog names every foul and coordinate",
          accepted is True and "h8：三三禁手" in all_text
          and "a15：自吃" in all_text,
          all_text.replace(chr(10), " / "))
    # applying a code list with a rejected move keeps the board consistent
    g.new_game()
    root.update()
    g._apply_imported_board(b_ill, info_ill)
    note_after_import = g.thinking_label.cget("text")
    root.update()
    check("imported illegal list leaves the board consistent",
          g.board.grid[7, 7] == EMPTY and g.board.grid[7, 4] == BLACK
          and "跳过 1 手" in note_after_import,
          note_after_import)

    # exports live in their own folder by default (never write into the
    # real folder here: only check the path, then use a scratch sub-folder)
    default_dir = g._default_save_dir()
    check("default export folder is a sub-folder",
          os.path.basename(default_dir) == "导出"
          and os.path.dirname(default_dir) == os.path.dirname(
              os.path.abspath(__file__)),
          default_dir)
    saved_dir = g.save_dir_var.get()
    scratch = os.path.join(tmp_dir, "导出", "_tmp_test")
    g.save_dir_var.set(scratch)
    created = g._save_dir()
    check("the export folder is created on demand",
          os.path.isdir(created) and created == scratch, created)
    # both export files are written into that folder
    g.new_game()
    root.update()
    g.try_play_black(7, 7)
    g.export_board()
    codes_in_folder = os.path.join(scratch, "粘贴板.md")
    dump_in_folder = os.path.join(scratch, "board_dump.txt")
    check("G writes both files into the export folder",
          os.path.exists(codes_in_folder) and os.path.exists(dump_in_folder),
          str(sorted(os.listdir(scratch))))
    check("the exported code line is the played move",
          open(codes_in_folder, encoding="utf-8").read().strip() == "h8",
          repr(open(codes_in_folder, encoding="utf-8").read()))
    g.save_dir_var.set(saved_dir)
    shutil.rmtree(tmp_dir, ignore_errors=True)

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



def test_forbidden():
    """Combat-based three-three / four-four judgement."""
    from board import HybridBoard, BLACK
    import rules
    results = []

    def check(name, cond, detail=""):
        results.append((name, bool(cond)))
        print(("PASS" if cond else "FAIL"), "-", name, detail)

    # A forms two open threes (horizontal + vertical): three-three foul.
    b = HybridBoard(15)
    for cell in ((7, 5), (7, 6), (5, 7), (6, 7)):
        b.grid[cell] = BLACK
    b._invalidate_caches()
    ok, ftype = rules.is_black_legal_move(b, 7, 7)
    check("two open threes is a three-three foul",
          (not ok) and ftype == "three_three", f"{ok} {ftype}")

    # A forms two fours: four-four foul.
    b2 = HybridBoard(15)
    for cell in ((7, 4), (7, 5), (7, 6), (4, 7), (5, 7), (6, 7)):
        b2.grid[cell] = BLACK
    b2._invalidate_caches()
    ok2, ftype2 = rules.is_black_legal_move(b2, 7, 7)
    check("two fours is a four-four foul",
          (not ok2) and ftype2 == "four_four", f"{ok2} {ftype2}")

    # One of the two open threes cannot be extended legally (both of its
    # extending points are four-four fouls), so it is not a real open
    # three and the move is legal.
    b3 = HybridBoard(15)
    for cell in ((7, 5), (7, 6), (5, 7), (6, 7),
                 (4, 4), (4, 5), (4, 6),
                 (8, 4), (8, 5), (8, 6)):
        b3.grid[cell] = BLACK
    b3._invalidate_caches()
    # With A already played, both vertical extensions become four-four
    # fouls (they complete A's vertical four and a horizontal four).
    b3a = b3.copy()
    b3a.grid[7, 7] = BLACK
    b3a._invalidate_caches()
    e1, f1 = rules.is_black_legal_move(b3a, 4, 7)
    e2, f2 = rules.is_black_legal_move(b3a, 8, 7)
    check("blocked extensions are illegal (four-four)",
          (not e1) and (not e2) and f1 == "four_four" and f2 == "four_four",
          f"{e1}/{f1} {e2}/{f2}")
    e3, f3 = rules.is_black_legal_move(b3a, 7, 4)
    check("the other open three can still be extended legally", e3,
          f"{e3} {f3}")
    ok3, ftype3 = rules.is_black_legal_move(b3, 7, 7)
    check("blocked open three does not cause a three-three foul",
          ok3 and ftype3 is None, f"{ok3} {ftype3}")

    # Recursive judgement must terminate (no infinite loop).
    b4 = HybridBoard(15)
    for cell in ((7, 5), (7, 6), (5, 7), (6, 7), (7, 8), (8, 7)):
        b4.grid[cell] = BLACK
    b4._invalidate_caches()
    rules.is_black_legal_move(b4, 7, 7)
    check("repeated foul judgement terminates", True)

    # Rule-book examples: one line, A in the middle, both sides of A form a
    # separate three / four (0 empty, 1 black).
    def load_line(text):
        b = HybridBoard(15)
        row = 7
        c0 = (15 - len(text)) // 2
        center = None
        for j, ch in enumerate(text):
            if ch == "1":
                b.grid[row, c0 + j] = BLACK
            elif ch.upper() == "A":
                center = (row, c0 + j)
        b._invalidate_caches()
        return b, center

    b5, c5 = load_line("0110A0110")
    ok5, f5 = rules.is_black_legal_move(b5, *c5)
    check("0110A0110: two open threes on one line -> three-three",
          (not ok5) and f5 == "three_three", f"{ok5} {f5}")
    b6, c6 = load_line("1110A0111")
    ok6, f6 = rules.is_black_legal_move(b6, *c6)
    check("1110A0111: two rush fours on one line -> four-four",
          (not ok6) and f6 == "four_four", f"{ok6} {f6}")

    # Speed: the rewritten check must stay cheap on a mid-game position.
    import time as _time
    b7 = HybridBoard(15)
    for cell in ((7, 5), (7, 6), (5, 7), (6, 7), (8, 8), (8, 9), (9, 8)):
        b7.grid[cell] = BLACK
    b7._invalidate_caches()
    t0 = _time.time()
    b7.compute_threats()
    dt = _time.time() - t0
    check("forbidden rewrite keeps compute_threats fast (<1.5s)",
          dt < 1.5, f"{dt:.3f}s")

    # Capture rule blocking: one of the two fours depends on a one-liberty
    # Black group, so White captures it and the four-four disappears.
    def capture_board(extra_liberty):
        b = HybridBoard(15)
        for cell in ((7, 4), (7, 5), (7, 8),
                     (4, 7), (5, 7), (6, 7)):
            b.grid[cell] = BLACK
        for cell in ((7, 3), (6, 4), (8, 4), (6, 5), (8, 5)):
            b.grid[cell] = WHITE
        if extra_liberty:
            b.grid[(8, 4)] = 0
        b._invalidate_caches()
        return b

    # The capture rule only blocks self-capture points (Black may not play
    # there); it never erases a four-four.
    b8 = capture_board(extra_liberty=False)
    ok8, f8 = rules.is_black_legal_move(b8, 7, 7)
    check("four-four stays a foul even with a capturable group",
          (not ok8) and f8 == "four_four", f"{ok8} {f8}")
    b9 = capture_board(extra_liberty=True)
    ok9, f9 = rules.is_black_legal_move(b9, 7, 7)
    check("four-four without the extra liberty", (not ok9)
          and f9 == "four_four", f"{ok9} {f9}")

    # Sleep-three patterns must not be counted as live threes.
    for text in ("0110010", "01100010"):
        b10, _ = load_line(text)
        spurious = []
        for i in range(15):
            for j in range(15):
                if b10.is_empty(i, j):
                    okc, ft = rules.is_black_legal_move(b10, i, j)
                    if ft in ("three_three", "four_four"):
                        spurious.append(((i, j), ft))
        check(text + ": no spurious 33/44 fouls", not spurious,
              str(spurious[:4]))


    # foul lines are reported for the GUI highlight
    b11, c11 = load_line("0110A0110")
    line_sets = rules.foul_lines(b11, c11[0], c11[1], "three_three")
    check("three-three reports its lines", len(line_sets) >= 2
          and all(len(ls) >= 3 for ls in line_sets), str(line_sets))
    check("foul_lines restores the board", b11.grid[c11[0], c11[1]] == 0)

    # incremental blue-cross cache matches a full recompute
    b12 = HybridBoard(15)
    b12.grid[7, 7] = BLACK
    for cell in ((6, 7), (8, 7), (7, 5), (6, 6), (8, 6)):
        b12.grid[cell] = WHITE
    b12._invalidate_caches()
    b12.get_blue_cross_positions()
    b12.play_white(7, 8)
    incremental = b12.get_blue_cross_positions()
    fresh = b12.copy()
    fresh._blue_cross_cache = None
    full = fresh.get_blue_cross_positions()
    check("incremental blue cache matches full recompute",
          incremental == full, f"{sorted(incremental)} vs {sorted(full)}")
    check("white move creates the self-capture blue cross",
          (7, 6) in incremental, str(sorted(incremental)))
    assert all(cond for _name, cond in results)


def test_rapfi_reader():
    """Rapfi/Yixin codes without spaces and the external plugin helpers."""
    import board_tools as bt
    ok = []
    def check(name, cond, detail=""):
        ok.append((name, bool(cond)))
        print(("PASS" if cond else "FAIL"), "-", name, detail)

    # --- auto chunking: with and without separators ---
    check("spaced codes split",
          bt.split_codes("h8 i9 p0") == ["h8", "i9", "p0"],
          str(bt.split_codes("h8 i9 p0")))
    check("Rapfi codes without spaces split",
          bt.split_codes("h8i9j10") == ["h8", "i9", "j10"],
          str(bt.split_codes("h8i9j10")))
    check("uppercase / commas / semicolons split",
          bt.split_codes("H8,I9;J10") == ["h8", "i9", "j10"],
          str(bt.split_codes("H8,I9;J10")))
    check("two-digit rows split",
          bt.split_codes("a15b14") == ["a15", "b14"],
          str(bt.split_codes("a15b14")))
    check("move numbers are dropped",
          bt.split_codes("1.h8 2.i9") == ["h8", "i9"],
          str(bt.split_codes("1.h8 2.i9")))
    check("pass in a spaceless list",
          bt.split_codes("h8i9p0j10") == ["h8", "i9", "p0", "j10"],
          str(bt.split_codes("h8i9p0j10")))
    check("a leading moves: label is ignored",
          bt.split_codes("moves: h8i9") == ["h8", "i9"],
          str(bt.split_codes("moves: h8i9")))
    check("9x9: a two-digit chunk falls back to one digit",
          bt.split_codes("e5f6", size=9) == ["e5", "f6"],
          str(bt.split_codes("e5f6", size=9)))

    # --- the same position with and without spaces ---
    spaced = "e8 o15 f8 o14 j8 o13 k8 o12"
    b1, _s1 = bt.board_from_code(spaced, size=15, first=bt.BLACK,
                                 gomoku=True)
    b2, _s2 = bt.board_from_code("e8o15f8o14j8o13k8o12", size=15,
                                 first=bt.BLACK, gomoku=True)
    check("spaceless and spaced codes give the same board",
          b1.grid.tobytes() == b2.grid.tobytes(),
          str(b1.grid.tobytes() == b2.grid.tobytes()))
    check("external (gomoku) mode keeps every stone",
          len(b2.history) == 8 and b2.grid[7, 4] == bt.BLACK,
          "%d stones" % len(b2.history))
    # a fouled position must be readable (the Go layer would refuse it)
    b3, _s3 = bt.board_from_code(spaced + " h8", size=15, first=bt.BLACK,
                                 gomoku=False)
    check("Go rules refuse the three-three stone (reference)",
          b3.grid[7, 7] == bt.EMPTY and b3.import_errors,
          str(b3.import_errors))
    b4, _s4 = bt.board_from_code(spaced + " h8", size=15, first=bt.BLACK,
                                 gomoku=True)
    check("gomoku mode accepts it (external position)",
          b4.grid[7, 7] == bt.BLACK, str(b4.grid[7, 7]))

    # --- the two output lines ---
    block, board, info, fouls = bt.position_block(spaced, size=15,
                                                  gomoku=True)
    lines = block.split(chr(10))
    check("block is code line + forbid line (粘贴板.md format)",
          lines[0] == spaced and lines[1] == "forbid:h8",
          repr(lines[:2]))
    check("the forbidden point and type are reported",
          fouls == [("h8", "three_three")], str(fouls))
    _b_ok, _s_ok = bt.board_from_code("h8 i9", size=15, first=bt.BLACK,
                                      gomoku=True)
    check("no forbidden point -> empty list",
          bt.forbidden_codes(_b_ok) == [], str(bt.forbidden_codes(_b_ok)))
    bare, _bd, _info, _f = bt.position_block(spaced, size=15, gomoku=True,
                                             forbidden_label=False)
    check("the forbidden label can be turned off",
          bare.split(chr(10))[1] == "h8", repr(bare))
    none_block, _nb, _ni, _nf = bt.position_block("h8 i9", size=15,
                                                  gomoku=True)
    check("no forbidden point is written as forbid:None",
          none_block.split(chr(10))[1] == "forbid:None", repr(none_block))
    check("forbid values are parsed",
          bt.forbidden_list("j10,h9,h8") == ["j10", "h9", "h8"]
          and bt.forbidden_list("forbid:None") == []
          and bt.forbidden_list("") == [],
          str(bt.forbidden_list("j10,h9,h8")))
    check("a forbid: line is not read as a move line",
          bt.parse_dump("h8 i9" + chr(10) + "forbid:g9")[0].history.__len__()
          == 2,
          "2 stones")

    # --- reading the file back ---
    import os as _os
    import shutil as _shutil
    tmp_dir = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                            "_tmp_rapfi")
    _shutil.rmtree(tmp_dir, ignore_errors=True)
    _os.makedirs(tmp_dir)
    path = _os.path.join(tmp_dir, "粘贴板.md")
    open(path, "w", encoding="utf-8").write("#basic" + chr(10))
    bt.append_position(path, block)
    bt.append_position(path, bt.position_block("h8i9", gomoku=True)[0])
    text = open(path, encoding="utf-8").read()
    check("each position is appended on its own lines + blank line",
          text == ("#basic" + chr(10)
                   + "e8 o15 f8 o14 j8 o13 k8 o12" + chr(10) + "forbid:h8"
                   + chr(10) + chr(10) + "h8 i9" + chr(10) + "forbid:None"
                   + chr(10) + chr(10)),
          repr(text))
    check("the last code line is found (forbid lines skipped)",
          bt.codes_from_text(text) == "h8 i9", bt.codes_from_text(text))
    check("the last forbid line is found",
          bt.forbidden_from_text(text) == "None",
          repr(bt.forbidden_from_text(text)))
    pairs = bt.blocks_from_text(text)
    check("file pairs are readable (code, forbid)",
          pairs == [(spaced, "h8"), ("h8 i9", "None")], str(pairs))
    _shutil.rmtree(tmp_dir, ignore_errors=True)

    fails = [x for x in ok if not x[1]]
    print()
    print("TOTAL:", len(ok), "FAILED:", len(fails))
    assert not fails


if __name__ == "__main__":
    test_rules_torus()
    test_gui_torus()
    test_forbidden()
    test_rapfi_reader()
    print("All torus checks passed.")
