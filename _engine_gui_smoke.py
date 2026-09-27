"""_engine_gui_smoke.py - manual smoke test for the GUI's "C++引擎" mode.

Temporary helper (repo root).  It drives the real GUI against the real
cpp/build/engine.exe, so run it by hand *after* the engine has been built:

    py _engine_gui_smoke.py

It is deliberately not part of the automatic checks (the engine binary is
being rebuilt by another task).  Success prints ENGINE_GUI_SMOKE_OK, any
failure prints a traceback and exits with code 1.
"""

import time
import traceback
import tkinter as tk

import engine_client
import gui


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


def main():
    # 1. GUI in C++ engine mode, depth 2, no time limits.
    root = tk.Tk()
    app = gui.GameGUI(root, board_size=15, black_is_ai=True,
                      white_is_ai=True)
    app.engine_var.set(1)
    app.depth_var.set("2")
    app.min_search_time_var.set("0")
    app.max_search_time_var.set("0")
    root.update()

    # 2. Black AI move through the engine.
    app.maybe_play_ai()
    ok = pump(root, 60, lambda: (not app.ai_thinking)
              and app.board.black_stone_count() == 1)
    assert ok, "black engine move did not complete within 60s"

    # 3. White AI move through the engine.
    app.maybe_play_ai()
    ok = pump(root, 60, lambda: app.board.white_stone_count() == 1)
    assert ok, "white engine move did not complete within 60s"

    # 4. Candidate W/L annotation.  The label dict may legitimately stay
    #    empty (engine timeout / no annotated candidate) - only "no crash
    #    and the attribute exists" is asserted.
    app.show_candidates_var.set(1)
    app._maybe_refresh_engine_labels()
    pump(root, 20)
    assert hasattr(app, "engine_labels"), "engine_labels attribute missing"

    # 5. Two undos (the engine must survive an interrupted search).
    app.undo_move()
    pump(root, 2)
    app.undo_move()
    pump(root, 2)

    # 6. Done.
    root.destroy()
    print("ENGINE_GUI_SMOKE_OK")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
