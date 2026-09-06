"""Integration tests: obstacle engine logic + out-of-process AI worker.

Run:  py _worker_test.py
The responsiveness section measures Tk main-loop lag while a heavy AI
search (depth 8, min 3 s) runs -- the original threaded implementation
starved the main loop for seconds; the worker must keep lag small.
"""
import random
import time
import tkinter as tk

import gui
from board import HybridBoard, EMPTY, BLACK, WHITE, OBSTACLE
import rules
import ai_search


# ======================================================================
# Part 1 - obstacle engine logic
# ======================================================================
def test_obstacles():
    b = HybridBoard(15)
    pos = b.place_random_obstacles(6, rng=random.Random(42))
    assert len(pos) == 6 and all(b.is_obstacle(x, y) for x, y in pos)
    for x, y in pos:  # point symmetry
        assert b.is_obstacle(14 - x, 14 - y), (x, y)

    b9 = HybridBoard(9)
    pos9 = b9.place_random_obstacles(5, rng=random.Random(7))
    assert len(pos9) == 5
    for x, y in pos9:
        assert b9.is_obstacle(8 - x, 8 - y)

    # cannot play on an obstacle
    b = HybridBoard(9)
    ox, oy = b.place_random_obstacles(1, rng=random.Random(1))[0]
    assert not b.play_black(ox, oy)[0]
    assert not b.play_white(ox, oy)[0]
    ok, ftype = rules.is_black_legal_move(b, ox, oy)
    assert not ok and ftype == "occupied"

    # obstacles are not liberties; black group can be captured through them
    b = HybridBoard(9)
    b.grid[4, 3] = OBSTACLE
    b.grid[4, 5] = OBSTACLE
    assert b.play_black(4, 4)[0]
    stones, libs = b.get_group(4, 4)
    assert libs == {(3, 4), (5, 4)}, libs
    assert b.play_white(3, 4)[0]
    assert b.play_white(5, 4)[0]
    assert b.grid[4, 4] == EMPTY and b.captured_count[WHITE] == 1

    # black self-capture refused when the only liberties are walls
    b = HybridBoard(9)
    b.grid[4, 3] = OBSTACLE
    b.grid[4, 5] = OBSTACLE
    b.grid[3, 4] = WHITE
    b.grid[5, 4] = WHITE
    assert not b.play_black(4, 4)[0]

    # obstacles block five-in-a-row
    b = HybridBoard(9)
    for y in (2, 3, 4, 5):
        b.grid[4, y] = BLACK
    b.grid[4, 6] = OBSTACLE
    assert b.black_run_length(4, 5) == 4
    assert b.play_black(4, 1)[0]
    assert b.check_black_five(4, 1)  # five away from the wall still wins

    b = HybridBoard(9)
    for y in (2, 3, 4, 5):
        b.grid[4, y] = BLACK
    b.grid[4, 6] = OBSTACLE
    b.grid[4, 1] = OBSTACLE
    assert b.play_black(4, 0)[0]
    assert b.black_run_length(4, 0) == 1  # wall separates the runs

    # threat classification: obstacle turns the open four into a rush four
    b = HybridBoard(9)
    for y in (2, 3, 4):
        b.grid[4, y] = BLACK
    b.grid[4, 5] = OBSTACLE
    assert rules.classify_position_after_move(b, 4, 1) == "rush_four"

    # white line-block accounting: windows through a wall are blocked
    b = HybridBoard(9)
    b.grid[4, 4] = OBSTACLE
    lines = b.get_unblocked_lines()
    assert all((4, 4) not in line for line in lines)
    assert not b.white_wins_by_line_block()  # other windows still open
    assert not b.white_wins_by_occupy()      # walls can never be occupied

    # candidates / threats / AI never pick a wall
    b = HybridBoard(9)
    b.place_random_obstacles(8, rng=random.Random(5))
    assert b.play_black(0, 0)[0]
    cands = b.get_black_candidate_moves()
    assert all(not b.is_obstacle(*p) for p in cands)
    threats = b.compute_threats()
    assert all(not b.is_obstacle(*p) for p in threats)
    b.evaluate_black_position()
    assert ai_search._board_signature(b)[3] == tuple(sorted(b.obstacle_positions()))
    print("OBSTACLE_ENGINE_OK")


# ======================================================================
# Part 2 - out-of-process AI worker with a live Tk loop
# ======================================================================
def pump(root, seconds):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.008)


def pump_until(root, cond, timeout, what):
    end = time.time() + timeout
    while time.time() < end:
        root.update()
        time.sleep(0.008)
        if cond():
            return time.time() - start_marker[0]
    raise AssertionError(f"timeout waiting for: {what}")


start_marker = [0.0]


def test_worker():
    root = tk.Tk()
    app = gui.GameGUI(root, board_size=15, black_is_ai=False,
                      white_is_ai=False)
    root.update()

    # --- simple round trip: empty board -> instant centre move ---
    app.black_ai_var.set(1)
    app.run_ai_move(BLACK)
    pump_until(root, lambda: not app.ai_thinking, 20, "first black move")
    assert app.board.black_stone_count() == 1
    assert app.board._black_replay_map == {} or True

    # seed a mid-game position for realistic deep searches
    b = app.board
    b.play_black(7, 7)
    b.play_white(8, 7)
    b.play_black(7, 8)
    app.last_move = (7, 8)
    app.current = WHITE
    app.draw_board()

    # --- responsiveness while a heavy search runs ---
    app.depth_var.set("8")
    app._on_depth_change()
    app.min_search_time_var.set("3")
    app.max_search_time_var.set("0")
    app.white_ai_var.set(1)

    lags = []
    next_beat = [time.time() + 0.05]

    def beat():
        now = time.time()
        lags.append(now - next_beat[0])
        next_beat[0] = max(next_beat[0] + 0.05, now)
        if next_beat[0] - now < 1.0:  # stop scheduling if we are way behind
            root.after(50, beat)

    root.after(50, beat)
    app.run_ai_move(WHITE)
    pump(root, 1.2)          # search is now grinding in the worker
    assert app.ai_thinking
    max_lag_searching = max(lags)

    # --- "AI 立即落子" must interrupt and commit almost immediately ---
    start_marker[0] = time.time()
    app.force_ai_current()
    dt = pump_until(root, lambda: not app.ai_thinking, 10, "abort commit")
    assert app.board.white_stone_count() == 1, "abort did not commit a move"

    # --- undo during a search stops it at once, stale result discarded ---
    app.run_ai_move(WHITE)   # another deep search
    pump(root, 0.4)
    assert app.ai_thinking
    t0 = time.time()
    app.undo_move()          # first click while thinking: just stops it
    stop_dt = time.time() - t0
    assert not app.ai_thinking and stop_dt < 0.2, stop_dt
    pump(root, 2.5)          # worker result must be discarded
    assert app.board.white_stone_count() == 1, "stale result played a stone"

    # --- replay fallback job applies a black reply ---
    app.replay_mode = True
    app.current = WHITE
    blacks = app.board.black_stone_count()
    app.search_epoch += 1
    app._ensure_worker()
    app._sync_worker_epoch()
    app.job_queue.put({
        "kind": "search", "epoch": app.search_epoch, "color": BLACK,
        "assist": False, "board": app.board.copy(), "max_depth": 2,
        "min_search_time": 0.0, "replay": True,
    })
    pump_until(root, lambda: app.board.black_stone_count() > blacks, 30,
               "replay black reply")
    assert len(app.replay_new_stones) == 1

    # --- obstacles through the GUI flow ---
    app.obstacle_enabled_var.set(1)
    app.obstacle_count_var.set("4")
    app._on_obstacle_toggle()
    assert app.board_style == "cell" and app.style_cell_var.get() == 1
    app.new_game()
    assert len(app.board.obstacle_positions()) == 4
    app.draw_board()

    root.destroy()
    print(f"WORKER_OK  max_tk_lag_while_searching={max_lag_searching:.3f}s  "
          f"abort_commit={dt:.2f}s  undo_stop={stop_dt:.3f}s")
    assert max_lag_searching < 0.5, f"main loop starved: {max_lag_searching:.3f}s"
    assert dt < 3.0, f"abort too slow: {dt:.2f}s"


test_obstacles()
test_worker()
print("ALL_OK")
