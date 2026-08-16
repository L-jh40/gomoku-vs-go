"""ai_white.py - thin wrapper around ai_search for the white side."""

from __future__ import annotations

import threading

from board import HybridBoard
import ai_search


def best_white_move(board: HybridBoard, time_limit: float | None = None,
                    max_depth: int = 2, min_search_time: float = 0.0,
                    interrupt_event: threading.Event | None = None,
                    progress_callback=None):
    return ai_search.best_white_move(
        board, time_limit=time_limit, max_depth=max_depth,
        min_search_time=min_search_time, interrupt_event=interrupt_event,
        progress_callback=progress_callback
    )


def best_white_move_with_info(board: HybridBoard, time_limit: float | None = None,
                              max_depth: int = 2, min_search_time: float = 0.0,
                              interrupt_event: threading.Event | None = None,
                              progress_callback=None):
    return ai_search.best_white_move_info(
        board, time_limit=time_limit, max_depth=max_depth,
        min_search_time=min_search_time, interrupt_event=interrupt_event,
        progress_callback=progress_callback
    )


def white_should_pass(board: HybridBoard) -> bool:
    return ai_search.white_should_pass(board)
