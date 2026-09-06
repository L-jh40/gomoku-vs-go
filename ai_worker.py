"""
ai_worker.py - persistent AI search worker process.

The GUI submits search jobs through `job_queue`; the worker runs the
existing ai_black / ai_white search functions and streams progress and the
final move back through `result_queue`.  Running the search outside the GUI
process keeps the Tk main loop free of GIL contention, so the window stays
fluid and buttons (AI 立即落子 / 悔棋 / Pass) act immediately while the AI
thinks.

Interrupts: `_check_interrupt` in ai_search only polls
`interrupt_event.is_set()`.  The GUI owns a shared epoch counter
(`epoch_ctl`, an inherited multiprocessing.Value) which always mirrors the
GUI's current search epoch; the worker wraps it in `_EpochInterrupt`, which
reports "set" as soon as the GUI's epoch has moved past the job's own
epoch.  Each job carries its epoch, so two consecutive searches can never
mis-synchronise the way a single shared event would (clearing an event for
the next search would otherwise un-interrupt the previous one).
"""

import time

from board import BLACK, WHITE
import ai_black
import ai_white
import ai_search

# Seconds between re-reads of the shared epoch counter.  Interrupts are
# honoured within ~50 ms while the per-node overhead stays negligible
# (a raw read would lock a shared semaphore on every search node).
EPOCH_CHECK_INTERVAL = 0.05


class _EpochInterrupt:
    """ai_search-compatible interrupt: set once the GUI has moved on."""

    def __init__(self, epoch_ctl, epoch: int):
        self._ctl = epoch_ctl
        self._epoch = epoch
        self._next_check = 0.0
        self._cached = False

    def is_set(self) -> bool:
        now = time.monotonic()
        if now >= self._next_check:
            self._next_check = now + EPOCH_CHECK_INTERVAL
            try:
                self._cached = self._ctl.value != self._epoch
            except Exception:
                self._cached = False
        return self._cached


def _progress_sender(result_queue, epoch: int):
    def progress_callback(completed_depth, elapsed_layer, finished=True,
                          focused=False):
        try:
            if completed_depth == -1:
                # Candidate-filtering debug refresh.
                result_queue.put({"kind": "refresh", "epoch": epoch})
                return
            result_queue.put({
                "kind": "progress", "epoch": epoch,
                "completed_depth": completed_depth,
                "elapsed_layer": elapsed_layer,
                "finished": finished, "focused": focused,
            })
        except Exception:
            pass

    return progress_callback


def worker_main(job_queue, result_queue, epoch_ctl):
    """Run one search job at a time forever.  A None job stops the worker."""
    while True:
        job = job_queue.get()
        if job is None:
            return
        try:
            _run_job(job, result_queue, epoch_ctl)
        except Exception as exc:  # never leave the GUI waiting
            try:
                result_queue.put({
                    "kind": "done", "epoch": job.get("epoch", -1),
                    "color": job.get("color"), "move": None, "depth": 0,
                    "error": str(exc), "replay": job.get("replay", False),
                    "assist": job.get("assist", False),
                    "should_pass": False, "replay_map": {}, "win_path": [],
                })
            except Exception:
                pass


def _run_job(job, result_queue, epoch_ctl):
    epoch = job["epoch"]
    interrupt = _EpochInterrupt(epoch_ctl, epoch)
    board = job["board"]
    progress = _progress_sender(result_queue, epoch)
    color = job["color"]
    move, depth, error = None, 0, None
    try:
        if color == BLACK:
            move, depth = ai_black.best_black_move_with_info(
                board, time_limit=None, max_depth=job["max_depth"],
                min_search_time=job["min_search_time"],
                interrupt_event=interrupt, progress_callback=progress
            )
        else:
            move, depth = ai_white.best_white_move_with_info(
                board, time_limit=None, max_depth=job["max_depth"],
                min_search_time=job["min_search_time"],
                interrupt_event=interrupt, progress_callback=progress
            )
    except ai_search.SearchTimeout:
        move, depth = None, 0
    except Exception as exc:
        move, depth = None, 0
        error = str(exc)

    should_pass = False
    if move is None and color == WHITE and error is None:
        try:
            should_pass = bool(ai_search.white_should_pass(board))
        except Exception:
            should_pass = False

    result_queue.put({
        "kind": "done", "epoch": epoch, "color": color, "move": move,
        "depth": depth, "error": error, "replay": job.get("replay", False),
        "assist": job.get("assist", False), "should_pass": should_pass,
        "replay_map": dict(getattr(board, "_black_replay_map", None) or {}),
        "win_path": list(getattr(board, "_last_black_win_path", None) or []),
    })
