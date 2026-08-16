"""
ai_white.py - 白棋 AI 入口。

白棋目标是最小化黑棋局面价值。强制消除实心圆和三角形的检查、minimax 搜索
均位于 ai_search.py；本模块保留白棋侧对外接口。
"""

from __future__ import annotations

import threading

from board import HybridBoard
import ai_search


def best_white_move(
    board: HybridBoard,
    time_limit: float = 1.0,
    max_depth: int = 4,
    min_search_time: float = 0.0,
    interrupt_event: threading.Event | None = None,
    progress_callback=None,
) -> tuple[int, int] | None:
    return ai_search.best_white_move(
        board,
        time_limit=time_limit,
        max_depth=max_depth,
        min_search_time=min_search_time,
        interrupt_event=interrupt_event,
        progress_callback=progress_callback,
    )


def best_white_move_with_info(
    board: HybridBoard,
    time_limit: float = 1.0,
    max_depth: int = 4,
    min_search_time: float = 0.0,
    interrupt_event: threading.Event | None = None,
    progress_callback=None,
) -> tuple[tuple[int, int] | None, int]:
    return ai_search.best_white_move_info(
        board,
        time_limit=time_limit,
        max_depth=max_depth,
        min_search_time=min_search_time,
        interrupt_event=interrupt_event,
        progress_callback=progress_callback,
    )
