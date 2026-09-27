"""engine_client.py - C++ engine (cpp/build/engine.exe) subprocess client.

The GUI's "C++引擎" mode drives the line-protocol engine described in
cpp/README.md through this class:

    size <n> / set <x> <y> <b|w|o> / play <b|w> <x> <y> -> ok|illegal
    winmode <0|1> / genmove <b|w> [max_depth] [min_sec] [max_sec] [winmode]
    candidates <b|w> [steps=11] [max_sec=10] [winmode=0] / quit

genmove and candidates are queries: they never change the engine's internal
board.  Every failure (cannot start, closed pipe, unparsable line) is
reported as EngineError.
"""

from __future__ import annotations

import os
import subprocess
import threading

from board import BLACK, OBSTACLE

# Repository root = the directory holding this file (also the engine's cwd).
_ROOT = os.path.dirname(os.path.abspath(__file__))

ENGINE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "cpp", "build", "engine.exe")


class EngineError(Exception):
    """Any engine failure: spawn problem, pipe closed, bad reply."""


class EngineClient:
    """One engine subprocess driven over stdin/stdout.

    The lock serialises complete command sequences: the GUI runs the search
    in one thread and the candidate W/L refresh in another, and two
    requests must never interleave on the same pipe.  abort()/quit() stay
    outside the lock on purpose - an interrupt must never wait for a
    running command to finish.
    """

    def __init__(self):
        self.proc = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Process plumbing
    # ------------------------------------------------------------------
    def _ensure(self):
        """(Re)start the engine subprocess when it is missing or dead."""
        proc = self.proc
        if proc is not None and proc.poll() is None:
            return proc
        try:
            self.proc = subprocess.Popen(
                [ENGINE_PATH],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                bufsize=1, cwd=_ROOT,
            )
        except OSError as exc:
            self.proc = None
            raise EngineError(f"cannot start engine: {exc}")
        return self.proc

    def _send(self, line):
        proc = self.proc
        if proc is None or proc.poll() is not None:
            raise EngineError("engine closed")
        try:
            proc.stdin.write(line + "\n")
            proc.stdin.flush()
        except (OSError, ValueError) as exc:
            raise EngineError(f"engine write failed: {exc}")

    def _readline(self, timeout=30):
        """One engine output line (stripped); a watchdog kills the engine
        and the empty read then surfaces as EngineError."""
        proc = self.proc
        if proc is None or proc.poll() is not None:
            raise EngineError("engine closed")
        timer = threading.Timer(timeout, proc.kill)
        timer.start()
        try:
            line = proc.stdout.readline()
        except (OSError, ValueError) as exc:
            raise EngineError(f"engine read failed: {exc}")
        finally:
            timer.cancel()
        if line == "":
            raise EngineError("engine closed")
        return line.strip()

    # ------------------------------------------------------------------
    # Board sync
    # ------------------------------------------------------------------
    def reset(self, board):
        """Load `board` into the engine: size, obstacles, then the history.

        `size` clears the engine board; every history move is replayed and
        must be accepted.  Obstacles are per-game constants, so re-setting
        them is harmless.  history entries are (color, x, y, captured).
        """
        with self._lock:
            self._ensure()
            self._send(f"size {board.size}")
            for x in range(board.size):
                for y in range(board.size):
                    if int(board.grid[x, y]) == OBSTACLE:
                        self._send(f"set {x} {y} o")
            for entry in board.history:
                color, x, y = entry[0], entry[1], entry[2]
                self._send(f"play {'b' if color == BLACK else 'w'} {x} {y}")
                reply = self._readline()
                if reply != "ok":
                    raise EngineError(f"play {x} {y} rejected: {reply!r}")

    # ------------------------------------------------------------------
    # Search / annotation queries
    # ------------------------------------------------------------------
    def genmove(self, color, max_depth, min_sec, max_sec, winmode,
                on_info=None):
        """Iterative-deepening search; returns {"verdict", "move"}.

        verdict is "move" (move = (x, y)), "pass" or "resign" (move None).
        on_info(depth, (x, y)) is called for every
        "info depth <d> move <x> <y> score <s>" progress line.
        """
        with self._lock:
            self._send(f"winmode {winmode}")
            self._send(f"genmove {'b' if color == BLACK else 'w'} "
                       f"{max_depth} {min_sec} {max_sec}")
            while True:
                line = self._readline(60)
                parts = line.split()
                if not parts:
                    continue
                head = parts[0]
                if head == "info":
                    if (len(parts) >= 8 and parts[1] == "depth"
                            and parts[3] == "move" and parts[6] == "score"):
                        try:
                            depth = int(parts[2])
                            x = int(parts[4])
                            y = int(parts[5])
                        except ValueError:
                            raise EngineError(f"bad info line: {line!r}")
                        if on_info is not None:
                            on_info(depth, (x, y))
                    continue
                if head == "move":
                    if len(parts) < 3:
                        raise EngineError(f"bad move line: {line!r}")
                    try:
                        x = int(parts[1])
                        y = int(parts[2])
                    except ValueError:
                        raise EngineError(f"bad move line: {line!r}")
                    return {"verdict": "move", "move": (x, y)}
                if head == "pass":
                    return {"verdict": "pass", "move": None}
                if head == "resign":
                    return {"verdict": "resign", "move": None}
                if head == "error":
                    raise EngineError(f"engine error: {line}")
                # Anything else is informational: ignore it.

    def candidates(self, color, steps=11, max_sec=10, winmode=0):
        """Candidate points with VCF/VCT W/L annotation.

        Returns a list of (x, y, tag, k) tuples read from the
        "cand <x> <y> <W|L><k>" lines; an optional "timeout" line is
        tolerated (and ignored), "end" terminates the reply.
        """
        with self._lock:
            self._send(f"winmode {winmode}")
            self._send(f"candidates {'b' if color == BLACK else 'w'} "
                       f"{steps} {max_sec}")
            out = []
            timed_out = False
            while True:
                line = self._readline()
                parts = line.split()
                if not parts:
                    continue
                head = parts[0]
                if head == "cand":
                    if len(parts) < 4:
                        raise EngineError(f"bad cand line: {line!r}")
                    try:
                        x = int(parts[1])
                        y = int(parts[2])
                    except ValueError:
                        raise EngineError(f"bad cand line: {line!r}")
                    tag_text = parts[3]
                    tag = tag_text[:1]
                    if tag not in ("W", "L"):
                        raise EngineError(f"bad cand tag: {line!r}")
                    try:
                        k = int(tag_text[1:])
                    except ValueError:
                        raise EngineError(f"bad cand line: {line!r}")
                    out.append((x, y, tag, k))
                    continue
                if head == "timeout":
                    timed_out = True
                    continue
                if head == "end":
                    return out
                if head == "error":
                    raise EngineError(f"engine error: {line}")
                # Anything else is informational: ignore it.

    # ------------------------------------------------------------------
    # Teardown
    # ------------------------------------------------------------------
    def abort(self):
        """Kill the engine (interrupt); the next call restarts it."""
        self._kill()
        self.proc = None

    def quit(self):
        """Ask the engine to exit, then make sure the process is gone."""
        proc = self.proc
        if proc is None:
            return
        try:
            if proc.poll() is None:
                try:
                    self._send("quit")
                except Exception:
                    pass
                try:
                    proc.wait(timeout=3)
                except Exception:
                    pass
                if proc.poll() is None:
                    self._kill()
        finally:
            self.proc = None

    def _kill(self):
        proc = self.proc
        if proc is None:
            return
        try:
            if proc.poll() is None:
                proc.kill()
        except Exception:
            pass
