"""katago_client.py - KataGo (daoqi / torus-go model) analysis client.

The engine files live in ``daoqi_katago/``:

    katago_opencl.exe / katago_eigen.exe   KataGo v1.18.1 official builds
    model.bin.gz                           daoqi club network (DAOQI-daoqi-...)
    analysis_daoqi.cfg                     analysis-server config

The daoqi (环面围棋) knowledge lives in the network weights: the daoqi club
(https://github.com/daoqiclub/katrain_daoqi) trained it on torus positions
projected onto a flat board and drives a stock KataGo engine with them.  In
torus mode board.py has already applied the wrapped captures, so this client
sends the current stone arrangement as ``initialStones`` with an empty move
list and ``initialPlayer`` = side to move.

initialStones (instead of replaying the move history) is deliberate: torus
captures, black's gomoku moves that are torus-legal but flat-suicide, and the
game's no-ko rule would all make a flat replay illegal or diverge from the
real board.  A/B checks show stones-mode evals match replay-mode evals for
the same side to move.

Winrate / scoreLead are reported from BLACK's perspective (the bundled
analysis_daoqi.cfg sets reportAnalysisWinratesAs = BLACK).

This module is standalone: it imports nothing from the gomoku project.  A
board is anything exposing ``size`` (int) and ``grid`` (2-indexable, values
0 empty / 1 black / 2 white / 3 obstacle) - e.g. daoqi_board.DaoqiBoard or
the main project's HybridBoard.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time

# Same values as the main project's board.py, redefined locally so this
# module has no dependency on it.
EMPTY = 0
BLACK = 1
WHITE = 2
OBSTACLE = 3

# Repository root = the directory holding this file.
_ROOT = os.path.dirname(os.path.abspath(__file__))
DAOQI_DIR = os.path.join(_ROOT, "daoqi_katago")
MODEL_PATH = os.path.join(DAOQI_DIR, "model.bin.gz")
CONFIG_PATH = os.path.join(DAOQI_DIR, "analysis_daoqi.cfg")

# Preferred first; the other is the automatic fallback.
BACKENDS = (
    ("OpenCL", "katago_opencl.exe", 300),   # first-ever start runs autotuning
    ("Eigen", "katago_eigen.exe", 120),
)

# Longest wait for a single query reply before the engine is killed.
QUERY_TIMEOUT = 180


class KataGoError(Exception):
    """Engine spawn / pipe / reply failure, mirroring engine_client."""


def _exe_path(name):
    return os.path.join(DAOQI_DIR, name)


def available():
    """True when the model and at least one backend binary are installed."""
    if not os.path.exists(MODEL_PATH) or not os.path.exists(CONFIG_PATH):
        return False
    return any(os.path.exists(_exe_path(name)) for _, name, _ in BACKENDS)


def gtp_to_xy(move, size):
    """GTP "Q16" -> (col, row) in this project's grid indices.

    Columns are A..T skipping I (left to right); GTP rows count from the
    bottom, while grid y counts from the top, so y = size - row.
    Returns None for "pass".
    """
    if not move or move.lower() == "pass":
        return None
    letter = move[0].upper()
    if not ("A" <= letter <= "T") or letter == "I":
        raise KataGoError(f"bad GTP move: {move!r}")
    try:
        row = int(move[1:])
    except ValueError:
        raise KataGoError(f"bad GTP move: {move!r}")
    col = ord(letter) - ord("A")
    if letter > "I":
        col -= 1
    if not (0 <= col < size and 1 <= row <= size):
        raise KataGoError(f"GTP move out of board: {move!r}")
    return col, size - row


def xy_to_gtp(x, y, size):
    """(col, row) grid indices -> GTP vertex string (inverse of gtp_to_xy)."""
    if not (0 <= x < size and 0 <= y < size):
        raise KataGoError(f"point out of board: {(x, y)}")
    letter = chr(ord("A") + x + (1 if x >= 8 else 0))   # skip I
    row = size - y
    return f"{letter}{row}"


class KataGoClient:
    """One KataGo analysis subprocess, auto-falling back between backends.

    Same locking shape as engine_client.EngineClient: the lock serialises
    whole queries, abort()/quit() stay outside it so an interrupt never
    waits for a running search.
    """

    def __init__(self):
        self.proc = None
        self.backend = None            # chosen backend name ("OpenCL"/"Eigen")
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._spawn_error = None
        self._query_id = 0

    # ------------------------------------------------------------------
    # Process plumbing
    # ------------------------------------------------------------------
    def _pump_stderr(self, proc):
        """Watch stderr: signal readiness, remember the last fatal line."""
        try:
            for line in proc.stderr:
                line = line.strip()
                if "Started, ready to begin handling requests" in line:
                    self._ready.set()
                elif line.startswith("Uncaught exception") or \
                        line.startswith("ERROR:") or \
                        "error:" in line.lower()[:40]:
                    self._spawn_error = line
        except Exception:
            pass

    def _spawn(self, backend_name, exe, ready_timeout):
        self._ready.clear()
        self._spawn_error = None
        try:
            proc = subprocess.Popen(
                [exe, "analysis", "-model", MODEL_PATH, "-config", CONFIG_PATH],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, encoding="utf-8",
                bufsize=1, cwd=DAOQI_DIR,
            )
        except OSError as exc:
            raise KataGoError(f"cannot start {backend_name} engine: {exc}")
        threading.Thread(target=self._pump_stderr, args=(proc,),
                         daemon=True).start()
        if not self._ready.wait(timeout=ready_timeout):
            proc.kill()
            detail = self._spawn_error or "engine did not become ready"
            raise KataGoError(f"{backend_name} engine: {detail}")
        self.backend = backend_name
        return proc

    def _ensure(self):
        """(Re)start the engine; prefer the remembered backend, then probe
        the remaining ones in order."""
        if self.proc is not None and self.proc.poll() is None:
            return self.proc
        order = []
        if self.backend is not None:
            order.append(self.backend)
        order.extend(name for name, _, _ in BACKENDS if name not in order)
        by_name = {name: (exe, tmo) for name, exe, tmo in BACKENDS}
        errors = []
        for name in order:
            exe, timeout = by_name[name]
            if not os.path.exists(_exe_path(exe)):
                errors.append(f"{name}: binary missing")
                continue
            try:
                self.proc = self._spawn(name, _exe_path(exe), timeout)
                return self.proc
            except KataGoError as exc:
                errors.append(str(exc))
        raise KataGoError("; ".join(errors) or "no KataGo backend available")

    def _send(self, text):
        proc = self.proc
        if proc is None or proc.poll() is not None:
            raise KataGoError("engine closed")
        try:
            proc.stdin.write(text + "\n")
            proc.stdin.flush()
        except (OSError, ValueError) as exc:
            raise KataGoError(f"engine write failed: {exc}")

    def _readline(self, timeout):
        proc = self.proc
        if proc is None or proc.poll() is not None:
            raise KataGoError("engine closed")
        timer = threading.Timer(timeout, proc.kill)
        timer.start()
        try:
            line = proc.stdout.readline()
        except (OSError, ValueError) as exc:
            raise KataGoError(f"engine read failed: {exc}")
        finally:
            timer.cancel()
        if line == "":
            raise KataGoError("engine closed")
        return line.strip()

    # ------------------------------------------------------------------
    # Analysis query
    # ------------------------------------------------------------------
    def analyze(self, board, color, max_visits=256, komi=5.5):
        """Evaluate the current position for `color` to move.

        `board` is any board snapshot exposing ``size`` and ``grid`` (torus
        captures already applied;
        obstacle cells are projected as white stones, the closest go
        equivalent of a wall nobody can use).  Returns:

            {"verdict": "move"|"pass", "move": (x, y) | None,
             "winrate": float,       # BLACK view
             "scoreLead": float,     # BLACK view
             "visits": int,
             "candidates": [(x, y, winrate, scoreLead)],   # top moves
             "backend": str}
        """
        with self._lock:
            proc = self._ensure()
            size = board.size
            stones = []
            for x in range(size):
                for y in range(size):
                    v = int(board.grid[x, y])
                    if v == BLACK:
                        stones.append(["B", xy_to_gtp(x, y, size)])
                    elif v in (WHITE, OBSTACLE):
                        # Obstacles are projected as white stones: the closest
                        # go equivalent of a wall nobody can play on.
                        stones.append(["W", xy_to_gtp(x, y, size)])
            self._query_id += 1
            query = {
                "id": f"daoqi-{self._query_id}",
                "initialStones": stones,
                "moves": [],
                "initialPlayer": "B" if color == BLACK else "W",
                "rules": "chinese",
                "komi": float(komi),
                "boardXSize": size,
                "boardYSize": size,
                "maxVisits": max(1, int(max_visits)),
                "includePolicy": False,
                "includeOwnership": False,
            }
            self._send(json.dumps(query))
            t0 = time.time()
            while True:
                line = self._readline(QUERY_TIMEOUT)
                if not line:
                    continue
                try:
                    resp = json.loads(line)
                except ValueError:
                    continue
                if resp.get("id") != query["id"]:
                    continue                        # warning / other reply
                if "error" in resp:
                    raise KataGoError(f"engine error: {resp['error']}")
                root = resp.get("rootInfo")
                if root is None:
                    raise KataGoError(f"engine reply missing rootInfo: {line[:200]}")
                break

            candidates = []
            for info in resp.get("moveInfos", []):
                try:
                    xy = gtp_to_xy(info.get("move"), size)
                except KataGoError:
                    continue
                if xy is None:
                    continue
                candidates.append((xy[0], xy[1],
                                   float(info.get("winrate", root.get("winrate", 0.0))),
                                   float(info.get("scoreLead", root.get("scoreLead", 0.0)))))
            result = {
                "winrate": float(root.get("winrate", 0.0)),
                "scoreLead": float(root.get("scoreLead", 0.0)),
                "visits": int(root.get("visits", 0)),
                "candidates": candidates,
                "backend": self.backend,
                "seconds": time.time() - t0,
            }
            if not candidates:
                # Nothing but a pass (or an empty reply): treat as pass.
                result["verdict"] = "pass"
                result["move"] = None
                return result
            result["verdict"] = "move"
            result["move"] = (candidates[0][0], candidates[0][1])
            return result

    # ------------------------------------------------------------------
    # Teardown
    # ------------------------------------------------------------------
    def abort(self):
        """Kill the engine (interrupt); the next query restarts it."""
        proc, self.proc = self.proc, None
        if proc is not None:
            try:
                proc.kill()
            except Exception:
                pass

    def quit(self):
        """Ask the engine to exit, then make sure the process is gone."""
        proc = self.proc
        if proc is None:
            return
        try:
            if proc.poll() is None:
                try:
                    self._send('{"action":"terminate","terminateId":"bye"}')
                except Exception:
                    pass
                try:
                    proc.wait(timeout=3)
                except Exception:
                    pass
                if proc.poll() is None:
                    proc.kill()
        finally:
            self.proc = None
