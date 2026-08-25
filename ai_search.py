"""
ai_search.py - exact black/white AI entry points.

Priority order implemented here follows TaskAndRule.md exactly:

Black:
  1. solid circle        -> play it immediately
  2. triangles           -> Algorithm A; if a candidate forces White to
                            resign, play it; otherwise keep the surviving
                            candidates (or all red candidates) and minimax
  3. red positions       -> minimax
  4. otherwise           -> farthest open point

White:
  1. solid circle/triangle present:
       candidates = forced points + capture liberties of one-liberty
       attacking black groups.  Keep only moves which can eliminate all
       solid circles within minimax_depth + 2 plies.  If none: resign and
       store a black win path / replay table.
       If exactly one survives, play it; otherwise minimax.
  2. no solid/triangle   -> minimax on red positions
  3. no red positions    -> farthest open point; no candidates => pass
"""

from __future__ import annotations

import time
import threading

import numpy as np

import rules
from board import (
    EMPTY,
    BLACK,
    WHITE,
    HybridBoard,
    THREAT_SCORE,
    FORCED_THREAT_TYPES,
)

WIN_SCORE = 1_000_000_000.0
LOSE_SCORE = -WIN_SCORE
EVEN_DEPTHS = (2, 4, 6, 8)


class SearchTimeout(Exception):
    pass


def _check_interrupt(interrupt_event: threading.Event | None, deadline: float | None):
    if interrupt_event is not None and interrupt_event.is_set():
        raise SearchTimeout
    if deadline is not None and time.monotonic() > deadline:
        raise SearchTimeout


def _record_replay_move(replay_map, key, move):
    entry = replay_map.get(key)
    if entry is None:
        replay_map[key] = [move]
    elif isinstance(entry, list):
        if move not in entry:
            entry.append(move)
    else:
        replay_map[key] = [entry, move]


def _board_signature(board: HybridBoard) -> tuple:
    black = tuple(
        (x, y)
        for x in range(board.size)
        for y in range(board.size)
        if board.grid[x, y] == BLACK
    )
    white = tuple(
        (x, y)
        for x in range(board.size)
        for y in range(board.size)
        if board.grid[x, y] == WHITE
    )
    return (board.turn, black, white)


# ----------------------------------------------------------------------
# Threat helpers
# ----------------------------------------------------------------------
def _five_points(threats: dict) -> list[tuple[int, int]]:
    return sorted(pos for pos, t in threats.items() if t == "five_point")


def _triangles(threats: dict) -> list[tuple[int, int]]:
    return sorted(
        pos for pos, t in threats.items() if t in ("four_three", "open_four")
    )


def _large_circles(threats: dict) -> list[tuple[int, int]]:
    return sorted(
        pos for pos, t in threats.items() if t in ("rush_four", "open_three")
    )


def _forced(threats: dict) -> list[tuple[int, int]]:
    return sorted(pos for pos, t in threats.items() if t in FORCED_THREAT_TYPES)


def _terminal_value(board: HybridBoard) -> float | None:
    if board.white_wins_by_capture():
        return LOSE_SCORE
    if board.white_wins_by_occupy():
        return LOSE_SCORE
    if board.white_wins_by_line_block():
        return LOSE_SCORE
    return None


def _apply_move(board: HybridBoard, move: tuple[int, int], black_turn: bool):
    if black_turn:
        ok, _ = rules.is_black_legal_move(board, *move)
        if not ok:
            return None, False
        ok, _ = board.play_black(*move)
        if not ok:
            return None, False
        if board.check_black_five(*move):
            return WIN_SCORE, True
        terminal = _terminal_value(board)
        return terminal, True
    else:
        ok, _ = board.play_white(*move)
        if not ok:
            return None, False
        terminal = _terminal_value(board)
        return terminal, True


# ----------------------------------------------------------------------
# White forced-defence search
# ----------------------------------------------------------------------
def _white_defense(board: HybridBoard, depth: int,
                   black_path: list | None = None,
                   replay_map: dict | None = None,
                   interrupt_event=None,
                   progress_callback=None,
                   start_time: float | None = None,
                   initial_depth: int | None = None):
    """Return a list of white moves which, within `depth` plies, can ensure
    that no black solid circle survives.  None means no such move exists.

    The recursion follows the task description:
      * after a white reply, black's triangles and large circles are the
        only moves that can create a new solid circle/triangle;
      * for every such black move which really creates a forced threat,
        White must again have a clearing move.
    """
    threats = board.compute_threats()
    _check_interrupt(interrupt_event, None)
    if start_time is None:
        start_time = time.monotonic()
    if initial_depth is None:
        initial_depth = depth

    def finish(result):
        if progress_callback is not None and depth >= 0:
            progress_callback(depth, time.monotonic() - start_time, False, True)
        return result

    forced = _forced(threats)
    if not forced:
        return []
    if depth <= 0:
        # Search budget exhausted.  Only a position where black already has
        # multiple five points and White cannot remove all of them in one
        # move is a proven loss.  Otherwise keep the remaining candidates
        # instead of resigning on incomplete evidence.
        five = _five_points(threats)
        candidates = board.get_white_defense_candidates(threats)
        if five:
            clearing: list[tuple[int, int]] = []
            for pos in candidates:
                _check_interrupt(interrupt_event, None)
                child = board.copy()
                ok, _ = child.play_white(*pos)
                if ok and not _five_points(child.compute_threats()):
                    clearing.append(pos)
            if not clearing:
                return finish(None)
        return finish(sorted(candidates))

    candidates = board.get_white_defense_candidates(threats)
    if not candidates:
        return finish(None)
    if len(candidates) == 1:
        # Task: one candidate stops the search immediately.
        return finish(list(candidates))

    safe_moves: list[tuple[int, int]] = []
    last_fail_path: list[tuple[int, int]] = []

    for white_move in candidates:
        _check_interrupt(interrupt_event, None)
        child = board.copy()
        ok, _ = child.play_white(*white_move)
        if not ok:
            continue
        # If White has already reached her winning condition, the move is
        # trivially safe.
        if child.white_wins_by_capture() or child.white_wins_by_line_block():
            safe_moves.append(white_move)
            continue

        child_threats = child.compute_threats()
        if _five_points(child_threats):
            # Black simply plays an existing winning point.
            black_reply = _five_points(child_threats)[0]
            if replay_map is not None:
                _record_replay_move(replay_map, _board_signature(child), black_reply)
            last_fail_path = [black_reply]
            continue

        tri_moves = _triangles(child_threats)
        tri_set = set(tri_moves)
        large_moves = [p for p in _large_circles(child_threats) if p not in tri_set]
        # Triangles are stronger than large circles.  The reply ordering below
        # also prefers a black move that immediately leaves solid circles, so
        # replay always picks a direct winning move when one exists.
        black_moves = sorted(tri_moves) + sorted(large_moves)
        child_is_safe = True
        child_fail_path: list[tuple[int, int]] = []

        black_replies: list[tuple[int, tuple, "HybridBoard", dict]] = []
        for black_move in black_moves:
            _check_interrupt(interrupt_event, None)
            after_black = child.copy()
            ok_b, _ = after_black.play_black(*black_move)
            if not ok_b:
                continue
            after_threats = after_black.compute_threats()
            if not _forced(after_threats):
                # This black move did not create a solid circle or triangle,
                # so it is not part of the forced line to check.
                continue
            strength = 0
            five_count = len(_five_points(after_threats))
            if five_count:
                # More immediate winning points means a shorter forced win.
                strength += 100 + five_count * 10
            if _triangles(after_threats):
                strength += 10
            if black_move in tri_set:
                strength += 1
            black_replies.append((strength, black_move, after_black, after_threats))
        black_replies.sort(key=lambda item: (-item[0], item[1]))

        for _strength, black_move, after_black, _after_threats in black_replies:
            sub_path: list[tuple[int, int]] = []
            sub_safe = _white_defense(
                after_black, depth - 1, sub_path, replay_map, interrupt_event,
                progress_callback, start_time, initial_depth
            )
            if sub_safe is None:
                # White cannot clear everything after this black move.
                # The replies are already ordered from fastest forced win to
                # slower forced win, so the first winning reply is kept and
                # the search for this white move stops immediately.
                if replay_map is not None:
                    _record_replay_move(
                        replay_map, _board_signature(child), black_move
                    )
                if not child_fail_path:
                    child_fail_path = [black_move] + sub_path
                child_is_safe = False
                break

        if child_is_safe:
            safe_moves.append(white_move)
        else:
            last_fail_path = child_fail_path or last_fail_path

    if safe_moves:
        return finish(sorted(safe_moves))
    if black_path is not None:
        black_path[:] = last_fail_path
    return finish(None)


def white_safe_move_set(board: HybridBoard, depth: int,
                        black_path: list | None = None,
                        replay_map: dict | None = None,
                        interrupt_event=None,
                        progress_callback=None,
                        start_time=None,
                        initial_depth=None):
    return _white_defense(board, depth, black_path, replay_map,
                          interrupt_event, progress_callback, start_time,
                          initial_depth)


def find_black_win_path(board: HybridBoard, depth: int,
                        interrupt_event=None) -> list[tuple[int, int]]:
    """Fallback used when no replay map was built but a path is requested.

    `_white_defense` itself records a losing line in `black_path`, so this
    helper simply re-runs that exact search on the white-to-move board.
    """
    path: list[tuple[int, int]] = []
    replay_map: dict = {}
    _white_defense(board, depth, path, replay_map, interrupt_event)
    return path


# ----------------------------------------------------------------------
# Black Algorithm A
# ----------------------------------------------------------------------
def _black_algorithm_a_candidates(board: HybridBoard, threats: dict):
    triangles = sorted(_triangles(threats))
    candidates = set(triangles)
    for pos in board.get_white_defense_candidates(threats):
        if pos in candidates:
            continue
        if board.black_move_keeps_group_above_one_liberty(*pos):
            candidates.add(pos)
    extra = sorted(p for p in candidates if p not in set(triangles))
    return triangles + extra


def black_algorithm_a(board: HybridBoard, depth: int,
                      replay_map: dict | None = None,
                      black_path: list | None = None,
                      interrupt_event=None,
                      progress_callback=None,
                      start_time: float | None = None,
                      initial_depth: int | None = None):
    """Returns (immediate_winning_move_or_None, surviving_candidate_moves)."""
    if depth <= 0:
        return None, []

    threats = board.compute_threats()
    _check_interrupt(interrupt_event, None)
    if start_time is None:
        start_time = time.monotonic()
    if initial_depth is None:
        initial_depth = depth

    def finish(win, surviving_moves):
        if progress_callback is not None and depth > 0:
            progress_callback(depth, time.monotonic() - start_time, False, True)
        return win, surviving_moves

    candidates = _black_algorithm_a_candidates(board, threats)
    if not candidates:
        return finish(None, [])
    if len(candidates) == 1:
        # Task: one candidate stops the search immediately.
        return finish(candidates[0], [])

    surviving: list[tuple[int, int]] = []

    for black_move in candidates:
        _check_interrupt(interrupt_event, None)
        child = board.copy()
        ok, _ = child.play_black(*black_move)
        if not ok:
            continue
        if child.check_black_five(*black_move):
            return finish(black_move, [])

        sub_path: list[tuple[int, int]] = []
        sub_map: dict = replay_map if replay_map is not None else {}
        safe_white = _white_defense(child, depth, sub_path, sub_map,
                                    interrupt_event, progress_callback,
                                    start_time, initial_depth)
        if safe_white is None:
            # White resigns after this black move: immediate table win.
            if replay_map is not None:
                replay_map.update(sub_map)
            if black_path is not None:
                black_path[:] = [black_move] + sub_path
            return finish(black_move, [])

        if not safe_white:
            # No forced threat after this black move; not a winning candidate.
            continue

        candidate_survives = True
        for white_move in safe_white:
            after_white = child.copy()
            ok_w, _ = after_white.play_white(*white_move)
            if not ok_w:
                candidate_survives = False
                break
            threats_after = after_white.compute_threats()
            if not _triangles(threats_after):
                # Task: candidates whose continuation has no triangle are
                # removed from the candidate set.
                candidate_survives = False
                break
            win2, _ = black_algorithm_a(
                after_white, depth - 1, replay_map, black_path, interrupt_event,
                progress_callback, start_time, initial_depth
            )
            if win2 is None:
                candidate_survives = False
                break

        if candidate_survives:
            surviving.append(black_move)

    return finish(None, surviving)


# ----------------------------------------------------------------------
# Move generation / ordering for minimax
# ----------------------------------------------------------------------
def _order_moves(board: HybridBoard, moves: list, threats: dict,
                 black_turn: bool) -> list:
    def key(pos):
        threat_type = threats.get(pos)
        threat_score = board.get_threat_score(pos, threat_type) \
            if threat_type is not None else 0
        bonus = 0
        # Prefer saving / attacking a one-liberty black group.
        seen = set()
        for nx, ny in board.neighbors(*pos):
            if board.grid[nx, ny] != BLACK or (nx, ny) in seen:
                continue
            stones, liberties = board.get_group(nx, ny)
            seen |= stones
            if len(liberties) == 1 and pos in liberties:
                bonus = 2000
                break
        center = abs(pos[0] - board.size // 2) + abs(pos[1] - board.size // 2)
        return (-(threat_score + bonus), center, pos)
    return sorted(moves, key=key)


def _moves_for_player(board: HybridBoard, black_turn: bool,
                      threats: dict | None = None,
                      defense_depth: int = 4,
                      interrupt_event=None) -> list:
    if threats is None:
        threats = board.compute_threats()

    if black_turn:
        five = _five_points(threats)
        if five:
            return five
        triangles = _triangles(threats)
        if triangles:
            candidates = set(triangles)
            for pos in board.get_white_defense_candidates(threats):
                if board.black_move_keeps_group_above_one_liberty(*pos):
                    candidates.add(pos)
            return _order_moves(board, sorted(candidates), threats, True)

        candidates = board.get_black_priority_candidates(threats)
        if not candidates:
            far = _farthest_move(board, True)
            return [far] if far is not None else []
        return _order_moves(board, candidates, threats, True)

    # White to move.
    forced = _forced(threats)
    if forced:
        safe = _white_defense(board, defense_depth,
                              interrupt_event=interrupt_event)
        if safe is None:
            return []
        return _order_moves(board, sorted(safe), threats, False)

    candidates = board.get_white_priority_candidates(threats)
    if not candidates:
        far = _farthest_move(board, False)
        return [far] if far is not None else []
    return _order_moves(board, candidates, threats, False)


# ----------------------------------------------------------------------
# Minimax (exact scores from the task)
# ----------------------------------------------------------------------
def _alphabeta(board: HybridBoard, depth: int, alpha: float, beta: float,
               black_turn: bool, interrupt_event, deadline,
               defense_depth: int = 4) -> float:
    _check_interrupt(interrupt_event, deadline)

    terminal = _terminal_value(board)
    if terminal is not None:
        return terminal

    if depth <= 0:
        return board.evaluate_black_position()

    # Depth n, layer k: when this minimax node encounters a forced threat,
    # the forced-defence proof is only expanded to (n - k + 2) plies.
    # Here `depth` is the remaining minimax depth, so local_defense_depth
    # equals depth + 2.
    local_defense_depth = depth + 2
    threats = board.compute_threats()
    moves = _moves_for_player(board, black_turn, threats, local_defense_depth,
                              interrupt_event=interrupt_event)
    if not moves:
        # No legal candidate for the side to move.
        if black_turn:
            return LOSE_SCORE
        # White passes when she has no candidate.  If forced threats exist
        # and no safe defence exists she has already resigned: black wins.
        if _forced(board.compute_threats()):
            return WIN_SCORE
        return board.evaluate_black_position()

    if black_turn:
        value = -float("inf")
        for move in moves:
            _check_interrupt(interrupt_event, deadline)
            child = board.copy()
            terminal_after, ok = _apply_move(child, move, True)
            if not ok:
                continue
            if terminal_after is not None:
                child_value = terminal_after
            else:
                child_value = _alphabeta(
                    child, depth - 1, alpha, beta, False,
                    interrupt_event, deadline, local_defense_depth
                )
            value = max(value, child_value)
            alpha = max(alpha, value)
            if beta <= alpha:
                break
        return value

    value = float("inf")
    for move in moves:
        _check_interrupt(interrupt_event, deadline)
        child = board.copy()
        terminal_after, ok = _apply_move(child, move, False)
        if not ok:
            continue
        if terminal_after is not None:
            child_value = terminal_after
        else:
            child_value = _alphabeta(
                child, depth - 1, alpha, beta, True,
                interrupt_event, deadline, local_defense_depth
            )
        value = min(value, child_value)
        beta = min(beta, value)
        if beta <= alpha:
            break
    return value


def _best_root_move_at_depth(board: HybridBoard, black_turn: bool, depth: int,
                             moves: list, interrupt_event, deadline,
                             defense_depth: int = 4,
                             progress_callback=None,
                             start_time: float | None = None):
    if start_time is None:
        start_time = time.monotonic()
    threats = board.compute_threats()
    ordered = _order_moves(board, list(moves), threats, black_turn)
    if not ordered:
        return None, True

    best_move = None
    best_value = -float("inf") if black_turn else float("inf")
    found = False
    complete = True

    for move in ordered:
        try:
            _check_interrupt(interrupt_event, deadline)
        except SearchTimeout:
            complete = False
            break
        child = board.copy()
        terminal_after, ok = _apply_move(child, move, black_turn)
        if not ok:
            continue
        try:
            if terminal_after is not None:
                value = terminal_after
            else:
                if depth <= 0:
                    value = child.evaluate_black_position()
                else:
                    value = _alphabeta(
                        child, depth - 1,
                        -float("inf"), float("inf"),
                        not black_turn,
                        interrupt_event, deadline, defense_depth
                    )
        except SearchTimeout:
            complete = False
            break

        if not found or (black_turn and value > best_value) or \
                (not black_turn and value < best_value):
            best_value = value
            best_move = move
            found = True
            # One full subtree is now known, so the current partial layer is
            # available for display and for an interrupted search.  Depth 0
            # also reports layer 0 after each evaluated candidate so b can
            # update before the whole depth-0 pass finishes.
            if progress_callback is not None:
                progress_callback(max(0, depth - 1),
                                  time.monotonic() - start_time,
                                  False)

    if not found:
        best_move = None
    return best_move, complete


def _iterative_minimax(board: HybridBoard, black_turn: bool, max_depth: int,
                       moves: list, time_limit: float | None = None,
                       interrupt_event=None, progress_callback=None,
                        min_search_time: float = 0.0):
    """Even-depth iterative deepening.

    There is no fixed wall-clock deadline.  A depth is committed only when
    it finishes.  Search stops when the requested `max_depth` has finished
    and `min_search_time` has elapsed; if the minimum time is reached while
    a partial deeper search is running, that even depth is still finished
    first.  Interrupting returns the best move from the deepest completed
    layer; odd partial layers are reported and reused as well.
    """
    start = time.monotonic()
    threats = board.compute_threats()
    ordered = _order_moves(board, list(moves), threats, black_turn)
    best_move = ordered[0] if ordered else None
    completed = 0
    defense_depth = max(2, max_depth + 2)

    if max_depth <= 0:
        depths = [0]
    else:
        # Depth 0 is a completed search layer too.  If a deeper layer is
        # interrupted, the best move from the previous completed layer
        # (possibly depth 0) is used.
        depths = [0] + list(EVEN_DEPTHS)

    try:
        for depth in depths:
            _check_interrupt(interrupt_event, None)
            move, complete = _best_root_move_at_depth(
                board, black_turn, depth, ordered,
                interrupt_event, None, defense_depth,
                progress_callback=progress_callback,
                start_time=start
            )
            if not complete:
                # Interrupted while this depth was still being searched.
                if depth <= 0:
                    # Depth 0 interrupted: use the best move among the
                    # candidates already evaluated (semi-finished best).
                    best_move = move if move is not None else (
                        ordered[0] if ordered else None
                    )
                    completed = 0
                elif move is not None:
                    # A deeper search interrupted at ~1.5 layers exposes
                    # the current odd-layer best (layer 1 for depth 2).
                    best_move = move
                    completed = max(completed, max(0, depth - 1))
                break
            if move is not None:
                best_move = move
                completed = depth
                if progress_callback is not None:
                    progress_callback(depth, time.monotonic() - start, True)

            elapsed = time.monotonic() - start
            if max_depth <= 0:
                break
            if completed >= max_depth and elapsed >= min_search_time:
                break
            if depth >= EVEN_DEPTHS[-1]:
                break
    except SearchTimeout:
        pass

    return best_move, completed


# ----------------------------------------------------------------------
# Farthest fallback
# ----------------------------------------------------------------------
def _farthest_move(board: HybridBoard, black_turn: bool):
    if black_turn:
        candidates = board.get_black_candidate_moves()
    else:
        candidates = board.get_white_candidate_moves()
    if not candidates:
        return None
    best = board.farthest_open_positions(candidates)
    if not best:
        return None
    return best[0]


# ----------------------------------------------------------------------
# Public black entry points
# ----------------------------------------------------------------------
def best_black_move_info(board: HybridBoard, time_limit: float | None = None,
                         max_depth: int = 2, min_search_time: float = 0.0,
                         interrupt_event=None, progress_callback=None):
    if not np.any(board.grid != EMPTY):
        return (board.size // 2, board.size // 2), 0

    threats = board.compute_threats()
    five = _five_points(threats)
    if five:
        return five[0], 0

    triangles = _triangles(threats)
    if triangles:
        replay_map: dict = {}
        black_path: list = []
        try:
            win, surviving = black_algorithm_a(
                board, max_depth + 2, replay_map, black_path, interrupt_event,
                progress_callback
            )
        except SearchTimeout:
            fallback = board.get_black_priority_candidates(threats) or triangles
            return (fallback[0] if fallback else None), 0
        if win is not None:
            if not black_path:
                black_path = [win]
            board._black_replay_map = replay_map
            board._last_black_win_path = black_path
            return win, 0
        if len(surviving) == 1:
            return surviving[0], 0
        if surviving:
            # Task: after Algorithm A stops, multiple survivors are decided
            # by a depth-0 minimax.
            move, depth = _iterative_minimax(
                board, True, 0, surviving,
                None, interrupt_event, progress_callback,
                min_search_time=0.0
            )
            return move, depth

    candidates = board.get_black_priority_candidates(threats)
    if len(candidates) == 1:
        return candidates[0], 0
    if candidates:
        return _iterative_minimax(
            board, True, max_depth, candidates,
            None, interrupt_event, progress_callback,
            min_search_time=min_search_time
        )

    return _farthest_move(board, True), 0


def best_black_move(board: HybridBoard, time_limit: float | None = None,
                    max_depth: int = 2, min_search_time: float = 0.0,
                    interrupt_event=None, progress_callback=None):
    return best_black_move_info(
        board, time_limit=time_limit, max_depth=max_depth,
        min_search_time=min_search_time, interrupt_event=interrupt_event,
        progress_callback=progress_callback
    )[0]


# ----------------------------------------------------------------------
# Public white entry points
# ----------------------------------------------------------------------
def white_should_pass(board: HybridBoard) -> bool:
    threats = board.compute_threats()
    if _forced(threats):
        return False
    return not board.get_white_candidate_moves(threats)


def best_white_move_info(board: HybridBoard, time_limit: float | None = None,
                         max_depth: int = 2, min_search_time: float = 0.0,
                         interrupt_event=None, progress_callback=None):
    board._white_pass_pending = False
    if not np.any(board.grid != EMPTY):
        return (board.size // 2, board.size // 2), 0

    threats = board.compute_threats()
    forced = _forced(threats)

    if forced:
        defense_candidates = board.get_white_defense_candidates(threats)
        if len(defense_candidates) == 1:
            # Task: one candidate stops the search immediately.
            return defense_candidates[0], 0

        black_path: list = []
        replay_map: dict = {}
        try:
            safe = _white_defense(
                board, max_depth + 2, black_path, replay_map, interrupt_event,
                progress_callback
            )
        except SearchTimeout:
            return (defense_candidates[0] if defense_candidates else None), 0
        if not safe:
            board._last_black_win_path = black_path or find_black_win_path(
                board, max_depth + 2, interrupt_event
            )
            board._black_replay_map = replay_map
            board._white_pass_pending = False
            return None, 0
        if len(safe) == 1:
            return safe[0], 0
        # Task: multiple safe defence points are decided by depth-0 minimax.
        return _iterative_minimax(
            board, False, 0, safe,
            None, interrupt_event, progress_callback,
            min_search_time=0.0
        )

    candidates = board.get_white_priority_candidates(threats)
    if len(candidates) == 1:
        return candidates[0], 0
    if candidates:
        return _iterative_minimax(
            board, False, max_depth, candidates,
            None, interrupt_event, progress_callback,
            min_search_time=min_search_time
        )

    board._white_pass_pending = not board.get_white_candidate_moves(threats)
    if board._white_pass_pending:
        return None, 0
    return _farthest_move(board, False), 0


def best_white_move(board: HybridBoard, time_limit: float | None = None,
                    max_depth: int = 2, min_search_time: float = 0.0,
                    interrupt_event=None, progress_callback=None):
    return best_white_move_info(
        board, time_limit=time_limit, max_depth=max_depth,
        min_search_time=min_search_time, interrupt_event=interrupt_event,
        progress_callback=progress_callback
    )[0]
