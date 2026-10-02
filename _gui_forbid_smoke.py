"""_gui_forbid_smoke.py - smoke test for the engine-mode forbidden blue crosses.

Temporary helper (repo root).  It drives the real GUI against the real
cpp/build/engine.exe, so run it by hand after the engine has been built:

    py _gui_forbid_smoke.py

Position: the user's position from 导出/粘贴板 - 禁手.md line 39, whose Rapfi
禁手行 (line 40) is "forbid:h10,f9,f8,e9" - i.e. exactly the set the engine's
`checkforbidden` reports, while Python rules.py additionally (wrongly) marks
h8.  Success prints FORBID_SMOKE_OK, any failure prints a traceback and exits
with code 1.
"""

import subprocess
import time
import traceback
import tkinter as tk

import board
import board_tools as bt
import engine_client
import gui

SIZE = 15
BLACK_CODES = "h9 g9 g8 g7 i8 h7 d10 e7 e6"
WHITE_CODES = "g10 f7 g6 k8 o15 n15 o14 n14 o13"
# Rapfi / engine checkforbidden for this position (导出/粘贴板 - 禁手.md:40).
FORBID_CODES = ("h10", "f9", "f8", "e9")


def pump(root, seconds, predicate=None):
    """Tk main loop for at most `seconds`: update + sleep 0.01 per step.

    Stops as soon as `predicate()` is true and returns that final check."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        root.update()
        if predicate is not None and predicate():
            return True
        time.sleep(0.01)
    return predicate() if predicate is not None else True


def blue_cross_lines(app):
    """Canvas lines drawn in blue by draw_hints (2 per blue cross)."""
    count = 0
    for item in app.canvas.find_all():
        if app.canvas.type(item) != "line":
            continue
        if str(app.canvas.itemcget(item, "fill")).strip().lower() == "blue":
            count += 1
    return count


def engine_oracle(grid):
    """Independent engine query (fresh subprocess) for a raw grid - the
    expected forbidden set of the *new* position after a move."""
    cmds = [f"size {SIZE}"]
    for x in range(SIZE):
        for y in range(SIZE):
            value = int(grid[x, y]) if hasattr(grid, "shape") else grid[x][y]
            if value == board.BLACK:
                cmds.append(f"set {x} {y} b")
            elif value == board.WHITE:
                cmds.append(f"set {x} {y} w")
    cmds.append("checkforbidden")
    proc = subprocess.run(
        [engine_client.ENGINE_PATH], input="\n".join(cmds) + "\nquit\n",
        capture_output=True, text=True, encoding="utf-8")
    out = set()
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2:
            out.add((int(parts[0]), int(parts[1])))
    return out


def main():
    # 1. GUI in C++ engine mode, both sides human, hints on (blue crosses are
    #    part of the hint overlay).
    root = tk.Tk()
    app = gui.GameGUI(root, board_size=SIZE, black_is_ai=False,
                      white_is_ai=False)
    app.engine_var.set(1)
    app.hint_var.set(1)
    root.update()

    # 2. The user's position straight into the grid (no move history).
    grid = [[board.EMPTY] * SIZE for _ in range(SIZE)]
    for code in BLACK_CODES.split():
        x, y = bt.code_to_coord(code, SIZE)
        grid[x][y] = board.BLACK
    for code in WHITE_CODES.split():
        x, y = bt.code_to_coord(code, SIZE)
        grid[x][y] = board.WHITE
    app.board.set_grid(grid)

    expected = {bt.code_to_coord(code, SIZE) for code in FORBID_CODES}
    h8 = bt.code_to_coord("h8", SIZE)
    assert h8 == (7, 7), f"h8 mapped to {h8!r}"

    # 3. Engine refresh -> engine_forbidden == the Rapfi forbidden set.
    app._maybe_refresh_engine_forbidden()
    ok = pump(root, 15, lambda: app.engine_forbidden == expected)
    assert ok, (f"engine_forbidden={sorted(app.engine_forbidden)!r} "
                f"!= {sorted(expected)!r}")
    assert h8 not in app.engine_forbidden, \
        "h8 must not be forbidden (Rapfi semantics)"
    print("engine_forbidden (engine checkforbidden):",
          sorted(app.engine_forbidden))
    print("expected (code_to_coord of %s):" % ",".join(FORBID_CODES),
          sorted(expected))

    # 4. For reference: what the Python rules.py path says for the same
    #    position (it agrees with the engine here; the reported h8 false
    #    positive is not reproducible on this tree).
    python_crosses = app.board.get_blue_cross_positions()
    print("python blue crosses (rules.py):", sorted(python_crosses))

    # 5. draw_board paints the blue crosses from the engine set (not from
    #    Python rules.py): a synthetic single-point set must give 2 lines.
    saved = set(app.engine_forbidden)
    app.engine_forbidden = {(0, 0)}
    app.draw_board()
    synth = blue_cross_lines(app)
    print("blue cross lines, engine_forbidden={(0,0)}:", synth)
    assert synth == 2, f"engine-mode crosses ignored engine_forbidden: {synth}"

    # ... and with the engine off, the untouched Python path paints its own
    # set (this is the pre-existing behaviour, unchanged).
    app.engine_forbidden = saved
    app.engine_var.set(0)
    app.draw_board()
    off_lines = blue_cross_lines(app)
    print("blue cross lines, engine_var=0 (Python path):", off_lines)
    assert off_lines == 2 * len(python_crosses), \
        f"Python cross count changed: {off_lines}"

    # 6. Back in engine mode, the real set is drawn again.
    app.engine_var.set(1)
    app.draw_board()
    lines = blue_cross_lines(app)
    print("blue cross lines, engine mode:", lines)
    assert lines == 2 * len(app.engine_forbidden), \
        f"expected {2 * len(app.engine_forbidden)} blue lines, got {lines}"

    # 7. Call-site wiring: real moves through try_play_black / try_play_white
    #    must re-trigger the engine refresh (thread -> engine_ui_queue ->
    #    _poll_worker).  Each new position is compared against an independent
    #    engine subprocess query of the same grid.
    app.try_play_black(*bt.code_to_coord("h8", SIZE))
    assert app.board.grid[7, 7] == board.BLACK, "try_play_black did not apply"
    want = engine_oracle(app.board.grid)
    assert want, "oracle set is empty - the check would be vacuous"
    ok = pump(root, 15, lambda: app.engine_forbidden == want)
    print("after try_play_black(h8): engine_forbidden =",
          sorted(app.engine_forbidden), "oracle =", sorted(want))
    assert ok, "try_play_black did not refresh the engine forbidden set"

    app.try_play_white(*bt.code_to_coord("f8", SIZE))
    assert app.board.grid[7, 5] == board.WHITE, "try_play_white did not apply"
    want = engine_oracle(app.board.grid)
    ok = pump(root, 15, lambda: app.engine_forbidden == want)
    print("after try_play_white(f8): engine_forbidden =",
          sorted(app.engine_forbidden), "oracle =", sorted(want))
    assert ok, "try_play_white did not refresh the engine forbidden set"

    root.destroy()
    print("FORBID_SMOKE_OK")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
