"""
ai_black.py - 黑棋 AI 入口（原 v2，已删除旧 v1）。

黑棋与白棋共用的威胁/计分逻辑在 board.py，minimax 与 alpha-beta 搜索
在 ai_search.py。这里只保留黑棋侧对外接口。
"""

from __future__ import annotations

import threading

from board import HybridBoard
import ai_search


def best_black_move(
    board: HybridBoard,
    time_limit: float = 1.0,
    max_depth: int = 4,
    min_search_time: float = 0.0,
    interrupt_event: threading.Event | None = None,
    progress_callback=None,
) -> tuple[int, int] | None:
    return ai_search.best_black_move(
        board,
        time_limit=time_limit,
        max_depth=max_depth,
        min_search_time=min_search_time,
        interrupt_event=interrupt_event,
        progress_callback=progress_callback,
    )


def best_black_move_with_info(
    board: HybridBoard,
    time_limit: float = 1.0,
    max_depth: int = 4,
    min_search_time: float = 0.0,
    interrupt_event: threading.Event | None = None,
    progress_callback=None,
) -> tuple[tuple[int, int] | None, int]:
    return ai_search.best_black_move_info(
        board,
        time_limit=time_limit,
        max_depth=max_depth,
        min_search_time=min_search_time,
        interrupt_event=interrupt_event,
        progress_callback=progress_callback,
    )


def get_move_scores(board: HybridBoard) -> dict[tuple[int, int], float]:
    """返回黑棋候选点的增量得分，供调试或以后 GUI 使用。"""
    threats = board.compute_threats()
    red_scores = board.get_red_scores(threats)
    previous_group_scores = board.compute_all_group_scores(red_scores=red_scores)

    scores: dict[tuple[int, int], float] = {}
    for pos in board.get_black_candidate_moves(threats=threats):
        delta = board.evaluate_black_move_delta(
            *pos,
            old_group_scores=previous_group_scores,
            red_scores=red_scores,
        )
        if delta != -float("inf"):
            scores[pos] = delta
    return scores
