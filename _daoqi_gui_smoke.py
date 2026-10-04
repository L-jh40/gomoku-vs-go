"""_daoqi_gui_smoke.py - manual smoke test for the GUI's "道棋AI" mode.

Temporary helper (repo root).  It drives the real GUI against the real
daoqi_katago engine in torus mode:

    python _daoqi_gui_smoke.py

Success prints DAOQI_GUI_SMOKE_OK, any failure prints a traceback and
exits with code 1.  Needs the OpenCL tuning cache (first ever start of
katago_opencl.exe tunes for ~4 minutes on its own).
"""

import time
import traceback
import tkinter as tk

import katago_client
import gui


def pump(root, seconds, predicate=None):
    """Tk main loop for at most `seconds`: update + sleep 0.01 per step."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        root.update()
        if predicate is not None and predicate():
            return True
        time.sleep(0.01)
    return predicate() if predicate is not None else True


def main():
    assert katago_client.available(), "daoqi_katago files missing"

    root = tk.Tk()
    app = gui.GameGUI(root, board_size=9, black_is_ai=True,
                      white_is_ai=True)
    app.depth_var.set("2")
    app.min_search_time_var.set("0")
    app.max_search_time_var.set("0")

    # 1. Torus 9x9 game with the daoqi AI on.
    app.torus_mode_var.set(1)
    app.new_game()
    assert app.board.torus
    app.daoqi_ai_var.set(1)
    app._on_daoqi_toggle()
    assert app.daoqi_ai_var.get()
    root.update()
    t0 = time.time()

    # 2. Eval readout for the initial position (black to move).
    ok = pump(root, 120, lambda: app.daoqi_eval is not None)
    assert ok, "initial daoqi evaluation did not arrive within 120s"
    print(f"eval0: {app.daoqi_label.cget('text')}")

    # 3. Black AI move (built-in gomoku engine, untouched by 道棋AI).
    app.maybe_play_ai()
    ok = pump(root, 90, lambda: (not app.ai_thinking)
              and app.board.black_stone_count() == 1)
    assert ok, "black move did not complete within 90s"

    # 4. White AI move through KataGo (first query may wait for the
    #    prewarmed engine).
    ok = pump(root, 120, lambda: (not app.ai_thinking)
              and app.board.white_stone_count() == 1)
    assert ok, "daoqi white move did not complete within 120s"
    assert app.last_move is not None
    print(f"white move {app.last_move} after {time.time()-t0:.1f}s total")
    assert app.daoqi_eval is not None and "winrate" in app.daoqi_eval
    print(f"eval1: {app.daoqi_label.cget('text')}")

    # 5. Candidate overlay: KataGo candidates + percentage texts.
    app.show_candidates_var.set(1)
    app._on_candidates_toggle()
    ok = pump(root, 60, lambda: bool(app.daoqi_candidates))
    assert ok, "daoqi candidates did not arrive within 60s"
    root.update()

    # 6. Another full round (engine is warm now - should be much faster).
    t1 = time.time()
    app.maybe_play_ai()
    ok = pump(root, 90, lambda: (not app.ai_thinking)
              and app.board.black_stone_count() == 2)
    assert ok, "second black move did not complete within 90s"
    ok = pump(root, 90, lambda: (not app.ai_thinking)
              and app.board.white_stone_count() == 2)
    assert ok, "second daoqi move did not complete within 90s"
    print(f"round 2 done in {time.time()-t1:.1f}s, "
          f"eval2: {app.daoqi_label.cget('text')}")

    # 7. Undo must not crash the KataGo client.
    app.undo_move()
    pump(root, 5, lambda: not app.ai_thinking)
    app.undo_move()
    pump(root, 5, lambda: not app.ai_thinking)

    root.destroy()
    print("DAOQI_GUI_SMOKE_OK")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
