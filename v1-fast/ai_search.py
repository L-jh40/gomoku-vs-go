"""
ai_search.py - 黑白共用的 minimax + alpha-beta 搜索。

优先级按 if-else / 类别判断，不使用计分选类别：
  黑棋：实心圆 -> 三角形（胜势直接下，否则在三角形内搜索）-> 红色位置
        -> 尽量远离棋子/领地/边缘。
  白棋：实心圆/三角形（只考虑堵点与吃攻势黑棋，先消除强制威胁，再排除
        黑棋下一步仍有胜势的点）-> 红色位置 -> 远离棋子/领地/边缘。

搜索只对偶数层 2/4/6/8 计数；min_search_time 为最短搜索时间，未达到时会
继续往更深偶数层搜索；手动“立即落子”通过 interrupt_event 打断，返回上一层
已完成偶数层的最优解。progress_callback 用于 GUI 显示每个偶数层完成时间。
"""

from __future__ import annotations

import time

import numpy as np
import rules
import threading

from board import (
    EMPTY,
    BLACK,
    WHITE,
    HybridBoard,
    THREAT_SCORE,
    FORCED_THREAT_TYPES,
)


WIN_SCORE = 1_000_000_000
LOSE_SCORE = -WIN_SCORE
DEFAULT_MAX_DEPTH = 4
EVEN_DEPTHS = (2, 4, 6, 8)
SEARCH_MOVES_ROOT = 3
SEARCH_MOVES_INTERNAL = 1


class SearchTimeout(Exception):
    pass


def _check_interrupt(interrupt_event: threading.Event | None) -> None:
    if interrupt_event is not None and interrupt_event.is_set():
        raise SearchTimeout


def _board_signature(board: HybridBoard) -> tuple:
    """棋盘签名：黑棋坐标 + 白棋坐标，用于复盘路径查表。"""
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
    return (black, white)


def _terminal_value(board: HybridBoard) -> float | None:
    if (
        board.white_wins_by_capture()
        or board.white_wins_by_occupy()
        or board.white_wins_by_line_block()
    ):
        return LOSE_SCORE
    return None


def _apply_move(
    board: HybridBoard, move: tuple[int, int], black_turn: bool
) -> tuple[float | None, bool]:
    if black_turn:
        ok, _ = board.play_black(*move)
        if not ok:
            return None, False
        if board.check_black_five(*move):
            return WIN_SCORE, True
        return None, True

    ok, _ = board.play_white(*move)
    if not ok:
        return None, False
    terminal = _terminal_value(board)
    if terminal is not None:
        return terminal, True
    return None, True


def _five_points(
    threats: dict[tuple[int, int], str],
) -> list[tuple[int, int]]:
    return sorted(pos for pos, t in threats.items() if t == "five_point")


def _triangles(
    threats: dict[tuple[int, int], str],
) -> list[tuple[int, int]]:
    return sorted(
        pos for pos, t in threats.items() if t in ("four_three", "open_four")
    )


def _forced_positions(
    threats: dict[tuple[int, int], str],
) -> list[tuple[int, int]]:
    return sorted(pos for pos, t in threats.items() if t in FORCED_THREAT_TYPES)


def _safe_black_positions(
    board: HybridBoard,
    positions,
) -> list[tuple[int, int]]:
    """过滤黑棋落子后下一手会被白棋直接吃掉的候选点。"""
    result = []
    dead = board.get_dead_positions()
    for pos in positions:
        if not board.in_bounds(*pos) or board.grid[pos] != EMPTY:
            continue
        if pos in dead:
            continue
        if board.black_move_is_next_capture(*pos):
            continue
        ok, _ = rules.is_black_legal_move(board, *pos)
        if ok:
            result.append(pos)
    return sorted(result)


def _candidate_positions(
    board: HybridBoard,
    black_turn: bool,
) -> list[tuple[int, int]]:
    """先取所有空格，排除领地和蓝叉，得到候选点集合。

    黑棋排除全部蓝叉；白棋只排除无气位置，保留禁手位置。
    """
    dead = board.get_dead_positions()
    candidates = [
        (x, y)
        for x in range(board.size)
        for y in range(board.size)
        if board.grid[x, y] == EMPTY and (x, y) not in dead
    ]
    if black_turn:
        blue = board._get_blue_cross_positions()
        candidates = [pos for pos in candidates if pos not in blue]
    else:
        candidates = [pos for pos in candidates if not board.would_self_capture(*pos)]
    return candidates


def white_should_pass(board: HybridBoard) -> bool:
    """白棋没有任何候选点时只应 Pass，而不是投子认负。"""
    return not _candidate_positions(board, False)


def _black_forced_candidates(
    board: HybridBoard,
    threats: dict[tuple[int, int], str],
) -> list[tuple[int, int]]:
    """黑棋遇到三角形时的候选点：三角形本身 + 白棋能吃的攻击块气位置。"""
    forced = set(_triangles(threats))
    white_capture = [
        pos
        for pos in board.get_white_blocking_candidates(threats=threats)
        if pos not in forced
    ]
    return _safe_black_positions(board, list(forced) + white_capture)


def triangle_is_hollow(board: HybridBoard, pos: tuple[int, int]) -> bool:
    """空心三角形：黑棋落在该三角形后，白棋可吃掉某个只剩一气的黑棋块，
    使所有实心圆（连五点位）消失。"""
    if not board.in_bounds(*pos) or board.grid[pos] != EMPTY:
        return False
    ok, _ = rules.is_black_legal_move(board, *pos)
    if not ok:
        return False
    board_after = board.copy()
    ok_after, _ = board_after.play_black(*pos)
    if not ok_after:
        return False

    for _stones, liberty_count, single_liberty in board_after.get_black_group_caches():
        if liberty_count == 1 and single_liberty is not None:
            if board_after.capture_makes_all_solid_circles_disappear(*single_liberty):
                return True
    return False


def black_triangle_is_winning(
    board: HybridBoard,
    pos: tuple[int, int],
    defense_depth: int = 4,
) -> bool:
    """胜势三角形 = 非空心三角形（简化版，速度优先）。"""
    if not board.in_bounds(*pos) or board.grid[pos] != EMPTY:
        return False
    return not triangle_is_hollow(board, pos)


def black_has_winning_position(board: HybridBoard) -> bool:
    """黑棋当前是否存在白棋一步无法消除的实心圆/胜势三角形。"""
    threats = board.compute_threats()
    if _five_points(threats):
        return True
    for pos in _triangles(threats):
        if black_triangle_is_winning(board, pos):
            return True
    return False


def _black_threat_moves(
    board: HybridBoard,
    threats: dict[tuple[int, int], str] | None = None,
) -> list[tuple[int, int]]:
    """黑棋下一步能形成实心圆、三角形或大圆圈的着法。"""
    if threats is None:
        threats = board.compute_threats()
    big_circles = [
        pos for pos, t in threats.items() if t in ("rush_four", "open_three")
    ]
    return sorted(set(_five_points(threats) + _triangles(threats) + big_circles))


def _white_after_move_black_safe(
    board_after_white: HybridBoard,
    depth: int,
    black_path: list[tuple[int, int]] | None = None,
    replay_map: dict | None = None,
) -> bool:
    """白棋刚落完子、轮到黑棋：黑棋所有能形成实心圆/三角形的着法，
    白棋都能在剩余深度内清除全部实心圆，才返回 True。"""
    threats = board_after_white.compute_threats()
    black_moves = _black_threat_moves(board_after_white, threats)
    if not black_moves:
        return True
    if depth <= 0:
        return False

    for bm in black_moves:
        board_after_black = board_after_white.copy()
        ok, _ = board_after_black.play_black(*bm)
        if not ok:
            continue
        threats_after_black = board_after_black.compute_threats()
        if not _forced_positions(threats_after_black):
            continue  # 该大圆圈/三角形落子后不能形成实心圆或三角形，不继续防守
        if not white_can_clear_solid_circles(
            board_after_black,
            depth - 1,
            black_path,
            replay_map,
        ):
            if black_path is not None:
                black_path.append(bm)
            if replay_map is not None:
                replay_map[_board_signature(board_after_white)] = bm
            return False
    return True


def white_safe_move_set(
    board: HybridBoard,
    depth: int,
    black_path: list[tuple[int, int]] | None = None,
    replay_map: dict | None = None,
) -> list[tuple[int, int]] | None:
    """返回白棋在 depth 内能清除全部实心圆的安全点位集合。

    有强制威胁但没有任何安全点返回 None（等价于白棋投子认负）；
    没有强制威胁返回空列表（无需防守，不是认负）。
    """
    if depth <= 0:
        return None

    threats = board.compute_threats()
    if not _forced_positions(threats):
        return []

    candidates = board.get_white_blocking_candidates(threats=threats)
    safe: list[tuple[int, int]] = []
    last_fail_path: list[tuple[int, int]] = []
    for pos in candidates:
        board_after_white = board.copy()
        ok, _ = board_after_white.play_white(*pos)
        if not ok:
            continue
        threats_after = board_after_white.compute_threats()
        if _five_points(threats_after):
            remaining_five = _five_points(threats_after)
            last_fail_path = remaining_five[:1]
            if replay_map is not None:
                replay_map[_board_signature(board_after_white)] = remaining_five[0]
            continue
        candidate_path: list[tuple[int, int]] = []
        if _white_after_move_black_safe(
            board_after_white,
            depth,
            candidate_path,
            replay_map,
        ):
            safe.append(pos)
        else:
            last_fail_path = candidate_path
    # 投子认负：有强制威胁但搜索深度内找不到任何能清除实心圆的落子点。
    if not safe and black_path is not None:
        black_path[:] = last_fail_path
    return safe or None


def white_can_clear_solid_circles(
    board: HybridBoard,
    depth: int,
    black_path: list[tuple[int, int]] | None = None,
    replay_map: dict | None = None,
) -> bool:
    """白棋到走，判断 depth 层内是否总能清除全部实心圆。"""
    if depth <= 0:
        return False

    threats = board.compute_threats()
    if not _forced_positions(threats):
        return True
    return white_safe_move_set(board, depth, black_path, replay_map) is not None


def find_black_win_path(
    board: HybridBoard,
    depth: int,
) -> list[tuple[int, int]]:
    """白棋被迫认负时，找一条黑棋能获胜的落子路径（仅黑棋落子）。"""
    threats = board.compute_threats()
    for white_move in board.get_white_blocking_candidates(threats=threats):
        board_after_white = board.copy()
        ok, _ = board_after_white.play_white(*white_move)
        if not ok:
            continue
        if _five_points(board_after_white.compute_threats()):
            continue
        black_path: list[tuple[int, int]] = []
        if not _white_after_move_black_safe(board_after_white, depth, black_path):
            return black_path
    return []


def get_black_winning_positions(
    board: HybridBoard,
) -> list[tuple[int, int]]:
    """返回所有“胜势位置”：黑棋落子后白棋一步无法消除一步胜利的点。"""
    threats = board.compute_threats()
    result = list(_five_points(threats))
    for pos in _triangles(threats):
        if black_triangle_is_winning(board, pos):
            result.append(pos)
    return result


def white_move_is_safe_against_black_win(
    board: HybridBoard,
    x: int,
    y: int,
    defense_depth: int = 4,
) -> bool:
    """白棋落在 (x, y) 后，黑棋没有必胜位置才算安全（简化版，速度优先）。"""
    if not board.in_bounds(x, y) or board.grid[x, y] != EMPTY:
        return False
    board_after = board.copy()
    ok, _ = board_after.play_white(x, y)
    if not ok:
        return False
    return not black_has_winning_position(board_after)


def _white_move_clears_solid_circles(
    board: HybridBoard, x: int, y: int
) -> bool:
    """白棋落在 (x, y) 后，棋盘上不再有实心圆（连五点位）。"""
    if not board.in_bounds(x, y) or board.grid[x, y] != EMPTY:
        return False
    board_after = board.copy()
    ok, _ = board_after.play_white(x, y)
    if not ok:
        return False
    threats_after = board_after.compute_threats()
    return not _five_points(threats_after)


def black_algorithm_a(
    board: HybridBoard,
    depth: int,
) -> tuple[tuple[int, int] | None, list[tuple[int, int]]]:
    """黑棋无实心圆、有三角形时的算法 A。

    返回 (直接获胜点或 None, 进入 minimax 的落子点位集合)。
    对每个黑棋候选点调用白棋算法；若白棋返回 None 则黑棋直接获胜；
    否则要求白棋的每个安全应手之后仍存在三角形，并递归检查黑棋能否获胜。
    """
    if depth <= 0:
        return None, []

    threats = board.compute_threats()
    candidates = _black_forced_candidates(board, threats)
    if not candidates:
        return None, []

    remaining: list[tuple[int, int]] = []
    for black_move in candidates:
        board_after_black = board.copy()
        ok, _ = board_after_black.play_black(*black_move)
        if not ok:
            continue
        if board_after_black.check_black_five(*black_move):
            return black_move, []

        safe_white = white_safe_move_set(board_after_black, depth)
        if safe_white is None:
            # 投子认负：白棋在搜索深度内无法清除实心圆，黑棋直接获胜。
            return black_move, []
        if not safe_white:
            continue

        survives = True
        for white_move in safe_white[:10]:
            board_after_white = board_after_black.copy()
            ok_white, _ = board_after_white.play_white(*white_move)
            if not ok_white:
                survives = False
                break
            threats_after = board_after_white.compute_threats()
            if not _triangles(threats_after):
                survives = False
                break
            win, _ = black_algorithm_a(board_after_white, depth - 1)
            if win is None:
                survives = False
                break
        if survives:
            remaining.append(black_move)

    return None, remaining


def _moves_for_player(
    board: HybridBoard,
    black_turn: bool,
    threats: dict[tuple[int, int], str] | None = None,
    defense_depth: int = 4,
) -> list[tuple[int, int]]:
    """按类别生成候选，不做计分排序。"""
    if threats is None:
        threats = board.compute_threats()

    if black_turn:
        dead = board.get_dead_positions()
        five = [pos for pos in _five_points(threats) if pos not in dead]
        if five:
            return five
        triangles = _black_forced_candidates(board, threats)
        if triangles:
            win, remaining = black_algorithm_a(board, defense_depth)
            if win is not None:
                return [win]
            return remaining
        red = _safe_black_positions(
            board, [pos for pos in board.get_red_positions(threats) if pos not in dead]
        )
        return red

    forced = _forced_positions(threats)
    if forced:
        safe = white_safe_move_set(board, defense_depth)
        if safe is None:
            # 防误认负：深度搜索判负时，仍先保留能消除实心圆的候选点。
            fallback = [
                pos
                for pos in board.get_white_blocking_candidates(threats=threats)
                if _white_move_clears_solid_circles(board, *pos)
            ]
            return sorted(fallback)
        return sorted(safe) if safe else []

    candidates = set(_candidate_positions(board, False))
    return sorted(
        pos for pos in board.get_red_positions(threats) if pos in candidates
    )


def _order_moves(
    moves: list[tuple[int, int]],
    threats: dict[tuple[int, int], str],
    board_size: int,
) -> list[tuple[int, int]]:
    """同一类别内按威胁分排序，再按中心偏好破平。"""
    def key(pos: tuple[int, int]) -> int:
        center = abs(pos[0] - board_size // 2) + abs(pos[1] - board_size // 2)
        return (-THREAT_SCORE.get(threats.get(pos), 0), center)

    return sorted(moves, key=key)


def _alphabeta(
    board: HybridBoard,
    depth: int,
    alpha: float,
    beta: float,
    black_turn: bool,
    accumulated_value: float,
    interrupt_event: threading.Event | None = None,
    defense_depth: int = 4,
) -> float:
    _check_interrupt(interrupt_event)

    terminal = _terminal_value(board)
    if terminal is not None:
        return terminal

    if depth == 0:
        return accumulated_value

    threats = board.compute_threats()
    moves = _order_moves(
        _moves_for_player(board, black_turn, threats, defense_depth),
        threats,
        board.size,
    )
    moves = moves[:SEARCH_MOVES_INTERNAL]

    if not moves:
        if black_turn:
            return LOSE_SCORE
        return WIN_SCORE

    red_scores = board.get_red_scores(threats)
    old_group_scores = board.compute_all_group_scores(red_scores=red_scores)

    if black_turn:
        value = -float("inf")
        for move in moves:
            _check_interrupt(interrupt_event)
            child = board.copy()
            terminal_after, ok = _apply_move(child, move, True)
            if not ok:
                continue
            if terminal_after is not None:
                child_value = terminal_after
            else:
                delta = board.evaluate_black_move_delta(
                    *move,
                    old_group_scores=old_group_scores,
                    red_scores=red_scores,
                )
                if delta == -float("inf"):
                    continue
                child_value = _alphabeta(
                    child,
                    depth - 1,
                    alpha,
                    beta,
                    False,
                    accumulated_value + delta,
                    interrupt_event,
                    defense_depth,
                )
            value = max(value, child_value)
            alpha = max(alpha, value)
            if beta <= alpha:
                break
        return value

    value = float("inf")
    for move in moves:
        _check_interrupt(interrupt_event)
        child = board.copy()
        terminal_after, ok = _apply_move(child, move, False)
        if not ok:
            continue
        if terminal_after is not None:
            child_value = terminal_after
        else:
            delta = board.evaluate_white_move_delta(
                *move,
                old_group_scores=old_group_scores,
                red_scores=red_scores,
            )
            if delta == -float("inf"):
                continue
            child_value = _alphabeta(
                child,
                depth - 1,
                alpha,
                beta,
                    True,
                    accumulated_value + delta,
                    interrupt_event,
                    defense_depth,
                )
        value = min(value, child_value)
        beta = min(beta, value)
        if beta <= alpha:
            break
    return value


def _best_move_at_depth(
    board: HybridBoard,
    black_turn: bool,
    depth: int,
    interrupt_event: threading.Event | None = None,
    moves: list[tuple[int, int]] | None = None,
    defense_depth: int = 4,
) -> tuple[int, int] | None:
    threats = board.compute_threats()
    if moves is None:
        moves = _moves_for_player(board, black_turn, threats, defense_depth)
    moves = _order_moves(moves, threats, board.size)
    moves = moves[:SEARCH_MOVES_ROOT]
    if not moves:
        return None

    red_scores = board.get_red_scores(threats)
    old_group_scores = board.compute_all_group_scores(red_scores=red_scores)

    if black_turn:
        best_value = -float("inf")
        best_move = moves[0]
        for move in moves:
            _check_interrupt(interrupt_event)
            child = board.copy()
            terminal_after, ok = _apply_move(child, move, True)
            if not ok:
                continue
            if terminal_after is not None:
                value = terminal_after
            else:
                delta = board.evaluate_black_move_delta(
                    *move,
                    old_group_scores=old_group_scores,
                    red_scores=red_scores,
                )
                if delta == -float("inf"):
                    continue
                value = _alphabeta(
                    child,
                    depth - 1,
                    -float("inf"),
                    float("inf"),
                    False,
                    delta,
                    interrupt_event,
                    defense_depth,
                )
            if value > best_value:
                best_value = value
                best_move = move
        return best_move

    best_value = float("inf")
    best_move = moves[0]
    for move in moves:
        _check_interrupt(interrupt_event)
        child = board.copy()
        terminal_after, ok = _apply_move(child, move, False)
        if not ok:
            continue
        if terminal_after is not None:
            value = terminal_after
        else:
            delta = board.evaluate_white_move_delta(
                *move,
                old_group_scores=old_group_scores,
                red_scores=red_scores,
            )
            if delta == -float("inf"):
                continue
            value = _alphabeta(
                child,
                depth - 1,
                -float("inf"),
                float("inf"),
                True,
                delta,
                interrupt_event,
                defense_depth,
            )
        if value < best_value:
            best_value = value
            best_move = move
    return best_move


def _iterative_deepening(
    board: HybridBoard,
    black_turn: bool,
    max_depth: int = DEFAULT_MAX_DEPTH,
    min_search_time: float = 0.0,
    interrupt_event: threading.Event | None = None,
    moves: list[tuple[int, int]] | None = None,
    progress_callback=None,
) -> tuple[tuple[int, int] | None, int]:
    start = time.monotonic()
    defense_depth = max_depth + 2
    best_move: tuple[int, int] | None = None
    completed_depth = 0

    fallback_moves = moves
    if fallback_moves is None:
        fallback_threats = board.compute_threats()
        fallback_moves = _moves_for_player(
            board, black_turn, fallback_threats, defense_depth
        )
    if fallback_moves:
        best_move = _order_moves(
            fallback_moves, board.compute_threats(), board.size
        )[0]

    try:
        for depth in EVEN_DEPTHS:
            if min_search_time <= 0 and max_depth == 0:
                break
            if min_search_time <= 0 and depth > max_depth:
                break
            _check_interrupt(interrupt_event)
            result = _best_move_at_depth(
                board,
                black_turn,
                depth,
                interrupt_event,
                moves,
                defense_depth,
            )
            if result is not None:
                best_move = result
                completed_depth = depth
                if progress_callback is not None:
                    progress_callback(depth, time.monotonic() - start)

            elapsed = time.monotonic() - start
            if min_search_time <= 0 and completed_depth >= max_depth:
                break
            if min_search_time > 0 and elapsed >= min_search_time and completed_depth >= max_depth:
                break
            if depth >= EVEN_DEPTHS[-1]:
                break
    except SearchTimeout:
        pass

    return best_move, completed_depth


def _farthest_black_move(board: HybridBoard) -> tuple[int, int] | None:
    candidates = _candidate_positions(board, True)
    if not candidates:
        return None
    best = board.farthest_by_directional_distance(candidates)
    return sorted(best)[0]


def _farthest_white_move(board: HybridBoard) -> tuple[int, int] | None:
    candidates = _candidate_positions(board, False)
    if not candidates:
        return None
    best = board.farthest_by_directional_distance(candidates)
    return sorted(best)[0]


def best_black_move_info(
    board: HybridBoard,
    time_limit: float | None = None,
    max_depth: int = DEFAULT_MAX_DEPTH,
    min_search_time: float = 0.0,
    interrupt_event: threading.Event | None = None,
    progress_callback=None,
) -> tuple[tuple[int, int] | None, int]:
    if not np.any(board.grid != EMPTY):
        return (board.size // 2, board.size // 2), 0

    threats = board.compute_threats()
    dead = board.get_dead_positions()

    five = [pos for pos in _five_points(threats) if pos not in dead]
    if five:
        return five[0], 0

    triangles = [pos for pos in _triangles(threats) if pos not in dead]
    if triangles:
        win, remaining = black_algorithm_a(board, max_depth + 2)
        if win is not None:
            return win, 0
        if remaining:
            move, depth = _iterative_deepening(
                board,
                black_turn=True,
                max_depth=max_depth,
                min_search_time=min_search_time,
                interrupt_event=interrupt_event,
                moves=remaining,
                progress_callback=progress_callback,
            )
            if move is None:
                depth = 0
            return move, depth

    red = _safe_black_positions(
        board, [pos for pos in board.get_red_positions(threats) if pos not in dead]
    )
    if red:
        return _iterative_deepening(
            board,
            black_turn=True,
            max_depth=max_depth,
            min_search_time=min_search_time,
            interrupt_event=interrupt_event,
            moves=red,
            progress_callback=progress_callback,
        )

    return _farthest_black_move(board), 0


def best_black_move(
    board: HybridBoard,
    time_limit: float | None = None,
    max_depth: int = DEFAULT_MAX_DEPTH,
    min_search_time: float = 0.0,
    interrupt_event: threading.Event | None = None,
    progress_callback=None,
) -> tuple[int, int] | None:
    return best_black_move_info(
        board,
        time_limit=time_limit,
        max_depth=max_depth,
        min_search_time=min_search_time,
        interrupt_event=interrupt_event,
        progress_callback=progress_callback,
    )[0]


def best_white_move_info(
    board: HybridBoard,
    time_limit: float | None = None,
    max_depth: int = DEFAULT_MAX_DEPTH,
    min_search_time: float = 0.0,
    interrupt_event: threading.Event | None = None,
    progress_callback=None,
) -> tuple[tuple[int, int] | None, int]:
    if not np.any(board.grid != EMPTY):
        return (board.size // 2, board.size // 2), 0

    threats = board.compute_threats()
    forced = _forced_positions(threats)
    if forced:
        win_path: list[tuple[int, int]] = []
        replay_map: dict = {}
        safe = white_safe_move_set(
            board, max_depth + 2, win_path, replay_map
        )
        if not safe:
            fallback = [
                pos
                for pos in board.get_white_blocking_candidates(threats=threats)
                if _white_move_clears_solid_circles(board, *pos)
            ]
            if fallback:
                safe = fallback
            else:
                # 投子认负：有强制威胁但搜索深度内找不到能清除全部实心圆的落子点。
                board._last_black_win_path = (
                    win_path
                    or find_black_win_path(board, max_depth + 2)
                )
                board._black_replay_map = replay_map
                return None, 0
        if len(safe) == 1:
            return safe[0], 0
        return _iterative_deepening(
            board,
            black_turn=False,
            max_depth=max_depth,
            min_search_time=min_search_time,
            interrupt_event=interrupt_event,
            moves=safe,
            progress_callback=progress_callback,
        )

    white_candidates = set(_candidate_positions(board, False))
    red = sorted(
        pos for pos in board.get_red_positions(threats) if pos in white_candidates
    )
    if red:
        return _iterative_deepening(
            board,
            black_turn=False,
            max_depth=max_depth,
            min_search_time=min_search_time,
            interrupt_event=interrupt_event,
            moves=red,
            progress_callback=progress_callback,
        )

    return _farthest_white_move(board), 0


def best_white_move(
    board: HybridBoard,
    time_limit: float | None = None,
    max_depth: int = DEFAULT_MAX_DEPTH,
    min_search_time: float = 0.0,
    interrupt_event: threading.Event | None = None,
    progress_callback=None,
) -> tuple[int, int] | None:
    return best_white_move_info(
        board,
        time_limit=time_limit,
        max_depth=max_depth,
        min_search_time=min_search_time,
        interrupt_event=interrupt_event,
        progress_callback=progress_callback,
    )[0]
