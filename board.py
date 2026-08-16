"""
board.py - Gomoku (black) versus Go (white) hybrid board.

Coordinates are (x, y) where x is the row and y is the column.
Cell values:
    0 = empty
    1 = black (Gomoku side, cannot capture white)
    2 = white (Go side, captures zero-liberty black groups)

Black search-space exclusions
----------------------------
* forbidden moves (overline / four-four / three-three)  -> blue cross
* white territory: only cells with no white-free five window and
  no-liberty (self-capture) cells                        -> grey square
  A one-step-capturable cell is NOT territory.
* positions which, after a black move, leave exactly one liberty and
  do not complete an exact five are excluded separately from Black's
  candidates.

Excluded territory points are added back when they orthogonally touch a
black group which is not entirely white territory (at least one stone in
that group is alive).
"""

from __future__ import annotations

import numpy as np

EMPTY = 0
BLACK = 1
WHITE = 2
BOARD_SIZE = 15

DIRECTIONS = ((1, 0), (0, 1), (1, 1), (1, -1))

THREAT_MARKER = {
    "five_point": "solid",
    "four_three": "triangle",
    "open_four": "triangle",
    "rush_four": "large",
    "open_three": "large",
    "sleep_three": "small",
    "open_two": "small",
    "sleep_two": "dot",
}

# Exact scores from the task specification.
THREAT_SCORE = {
    "five_point": 0,      # handled before scoring
    "four_three": 625,
    "open_four": 625,
    "rush_four": 125,
    "open_three": 125,
    "sleep_three": 25,
    "open_two": 25,
    "sleep_two": 1,
}

FORCED_THREAT_TYPES = {"five_point", "four_three", "open_four"}

# A fragile triangle which White can neutralise by capturing an attacking
# one-liberty black group is still a forced threat, but scores 500 rather
# than the normal triangle score.
HOLLOW_TRIANGLE_SCORE = 100

# Red-position priority used when no solid circle/triangle exists.
RED_LEVEL_GROUPS = (
    ("rush_four", "open_three"),
    ("sleep_three", "open_two"),
    ("sleep_two",),
)

# n in "live/sleep n".  B = 6 - n is the largest liberty count of an
# associated black group whose liberties are added as candidates.
THREAT_N = {
    "open_four": 4,
    "rush_four": 4,
    "open_three": 3,
    "sleep_three": 3,
    "open_two": 2,
    "sleep_two": 2,
}

RED_LEVEL_RANK = {
    "rush_four": 3,
    "open_three": 3,
    "sleep_three": 2,
    "open_two": 2,
    "sleep_two": 1,
}


def b_limit_for_threat(threat_type: str) -> int:
    return 6 - THREAT_N.get(threat_type, 5)


class HybridBoard:
    def __init__(self, size: int = 15):
        self.size = int(size)
        self.grid = np.zeros((self.size, self.size), dtype=np.int8)
        self.history: list[tuple[int, int, int, list]] = []
        self.captured_count = {BLACK: 0, WHITE: 0}
        self.turn = BLACK

        # Caches.  They are invalidated by every real move.
        self._blue_cross_cache: set | None = None
        self._dead_cache: set | None = None
        self._group_cache: list | None = None
        self._threats_cache: dict | None = None
        self._black_territory_cache: set | None = None
        self._eval_cache: float | None = None
        self._black_group_info_cache: list | None = None
        self._hollow_triangles_cache: set | None = None

        # Attributes used by the AI / GUI to communicate a forced win.
        self._last_black_win_path: list[tuple[int, int]] = []
        self._black_replay_map: dict = {}
        self._white_pass_pending = False
        self.pattern_positions: dict[str, tuple[int, int]] = {}
        self._update_forbidden_blue = True

    # ------------------------------------------------------------------
    # Basic helpers
    # ------------------------------------------------------------------
    def copy(self) -> "HybridBoard":
        nb = HybridBoard(self.size)
        nb.grid = self.grid.copy()
        nb.history = list(self.history)
        nb.captured_count = dict(self.captured_count)
        nb.turn = self.turn
        nb._update_forbidden_blue = self._update_forbidden_blue
        if self._blue_cross_cache is not None:
            nb._blue_cross_cache = set(self._blue_cross_cache)
        if self._dead_cache is not None:
            nb._dead_cache = set(self._dead_cache)
        if self._group_cache is not None:
            nb._group_cache = list(self._group_cache)
        if self._threats_cache is not None:
            nb._threats_cache = dict(self._threats_cache)
        if self._black_territory_cache is not None:
            nb._black_territory_cache = set(self._black_territory_cache)
        if self._hollow_triangles_cache is not None:
            nb._hollow_triangles_cache = set(self._hollow_triangles_cache)
        nb._eval_cache = self._eval_cache
        if self._black_group_info_cache is not None:
            nb._black_group_info_cache = [
                dict(info) for info in self._black_group_info_cache
            ]
        nb._last_black_win_path = list(self._last_black_win_path)
        nb._black_replay_map = dict(self._black_replay_map)
        nb._white_pass_pending = self._white_pass_pending
        nb.pattern_positions = dict(self.pattern_positions)
        return nb

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.size and 0 <= y < self.size

    def is_empty(self, x: int, y: int) -> bool:
        return self.in_bounds(x, y) and self.grid[x, y] == EMPTY

    def neighbors(self, x: int, y: int) -> list[tuple[int, int]]:
        out: list[tuple[int, int]] = []
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nx, ny = x + dx, y + dy
            if self.in_bounds(nx, ny):
                out.append((nx, ny))
        return out

    def get_group(self, x: int, y: int):
        """Return (stones, liberties) for the group containing (x, y)."""
        color = int(self.grid[x, y])
        if color == EMPTY:
            return set(), set()
        stones: set[tuple[int, int]] = set()
        liberties: set[tuple[int, int]] = set()
        stack = [(int(x), int(y))]
        seen: set[tuple[int, int]] = set()
        while stack:
            cx, cy = stack.pop()
            if (cx, cy) in seen:
                continue
            seen.add((cx, cy))
            if self.grid[cx, cy] != color:
                continue
            stones.add((cx, cy))
            for nx, ny in self.neighbors(cx, cy):
                if (nx, ny) in seen:
                    continue
                nv = int(self.grid[nx, ny])
                if nv == color:
                    stack.append((nx, ny))
                elif nv == EMPTY:
                    liberties.add((nx, ny))
        return stones, liberties

    def get_black_groups(self):
        groups: list[tuple[set, set]] = []
        seen: set[tuple[int, int]] = set()
        for x in range(self.size):
            for y in range(self.size):
                if self.grid[x, y] != BLACK or (x, y) in seen:
                    continue
                stones, liberties = self.get_group(x, y)
                seen |= stones
                groups.append((stones, liberties))
        return groups

    def get_black_group_caches(self):
        if self._group_cache is None:
            cache = []
            for stones, liberties in self.get_black_groups():
                single = next(iter(sorted(liberties))) if len(liberties) == 1 else None
                cache.append((tuple(sorted(stones)), len(liberties), single))
            self._group_cache = cache
        return self._group_cache

    def get_black_group_infos(self, threats=None) -> list[dict]:
        """Cached black-group information required by the task.

        Each entry stores:
          stones              : sorted tuple of black coordinates
          liberties           : sorted tuple of liberty coordinates
          liberty_count       : number of liberties
          affected            : empty cells whose red status depends on the group
          max_threat_level    : highest associated red marker level
          score               : A * (1 - 0.5 ** n)
        """
        if self._black_group_info_cache is not None:
            return [dict(info) for info in self._black_group_info_cache]
        if threats is None:
            threats = self.compute_threats()
        red_scores = self.get_red_scores(threats)

        infos: list[dict] = []
        for stones, liberties in self.get_black_groups():
            stones_t = tuple(sorted(stones))
            libs_t = tuple(sorted(liberties))
            affected = self.affected_positions_around(stones, radius=4)
            max_level = 0
            for pos, threat_type in threats.items():
                if pos in affected:
                    max_level = max(max_level,
                                    RED_LEVEL_RANK.get(threat_type, 0))
            score = self.compute_group_score(
                set(stones_t), liberties=set(libs_t), red_scores=red_scores
            )
            infos.append({
                "stones": stones_t,
                "liberties": libs_t,
                "liberty_count": len(libs_t),
                "affected": affected,
                "max_threat_level": max_level,
                "score": score,
            })
        self._black_group_info_cache = infos
        return [dict(info) for info in infos]

    def _invalidate_caches(self) -> None:
        self._blue_cross_cache = None
        self._dead_cache = None
        self._group_cache = None
        self._threats_cache = None
        self._black_territory_cache = None
        self._eval_cache = None
        self._black_group_info_cache = None
        self._hollow_triangles_cache = None

    def positions_on_lines(self, x: int, y: int, radius: int = 4):
        out: set[tuple[int, int]] = set()
        for dx, dy in DIRECTIONS:
            for step in range(-radius, radius + 1):
                nx, ny = x + step * dx, y + step * dy
                if self.in_bounds(nx, ny):
                    out.add((nx, ny))
        return out

    def affected_positions_around(self, cells, radius: int = 4):
        out: set[tuple[int, int]] = set()
        for x, y in cells:
            out |= self.positions_on_lines(x, y, radius)
        return out

    def relevant_empty_positions(self, radius: int = 4) -> set[tuple[int, int]]:
        """Empty cells that can possibly be a red threat or a blue cross.

        A black stone can only influence a cell if that cell lies on one of
        the four Renju lines within `radius` of the stone.  This is the
        candidate pre-filter required by the task; empty cells far from all
        black stones never need a full legal/pattern check.
        """
        if not np.any(self.grid == BLACK):
            return set()
        out: set[tuple[int, int]] = set()
        for x in range(self.size):
            for y in range(self.size):
                if self.grid[x, y] == BLACK:
                    out |= self.positions_on_lines(x, y, radius)
        return {(x, y) for x, y in out if self.grid[x, y] == EMPTY}

    # ------------------------------------------------------------------
    # Move execution
    # ------------------------------------------------------------------
    def _capture_zero_liberty_black_groups(self) -> list[tuple[int, int]]:
        captured: list[tuple[int, int]] = []
        checked: set[tuple[int, int]] = set()
        for x in range(self.size):
            for y in range(self.size):
                if self.grid[x, y] != BLACK or (x, y) in checked:
                    continue
                stones, liberties = self.get_group(x, y)
                checked |= stones
                if not liberties:
                    for sx, sy in stones:
                        self.grid[sx, sy] = EMPTY
                    captured.extend(sorted(stones))
        return captured

    def play_black(self, x: int, y: int, check_rules: bool = True):
        """Play a black stone.  Renju forbidden moves and self-capture are
        enforced; internal simulations that already validated legality may
        pass check_rules=False for speed."""
        if not self.in_bounds(x, y) or self.grid[x, y] != EMPTY:
            return False, []
        if check_rules:
            import rules
            ok, _ftype = rules.is_black_legal_move(self, x, y)
            if not ok:
                return False, []

        self._invalidate_caches()
        self.grid[x, y] = BLACK
        stones, liberties = self.get_group(x, y)
        if not liberties:
            self.grid[x, y] = EMPTY
            self._invalidate_caches()
            return False, []

        captured = self._capture_zero_liberty_black_groups()
        if (x, y) in captured:
            # A black move can never capture its own just-placed stone; this
            # is only a safety net and should not happen.
            self.grid[x, y] = BLACK
            captured = [p for p in captured if p != (x, y)]
        if captured:
            self.captured_count[BLACK] += len(captured)
        self.history.append((BLACK, x, y, captured))
        self.turn = WHITE
        return True, captured

    def play_white(self, x: int, y: int):
        if not self.in_bounds(x, y) or self.grid[x, y] != EMPTY:
            return False, []
        self._invalidate_caches()
        self.grid[x, y] = WHITE
        captured = self._capture_zero_liberty_black_groups()
        self.captured_count[WHITE] += len(captured)
        self.history.append((WHITE, x, y, captured))
        self.turn = BLACK
        return True, captured

    def undo(self) -> bool:
        if not self.history:
            return False
        self._invalidate_caches()
        color, x, y, captured = self.history.pop()
        self.grid[x, y] = EMPTY
        for sx, sy in captured:
            self.grid[sx, sy] = BLACK
        if color == WHITE:
            self.captured_count[WHITE] -= len(captured)
        else:
            self.captured_count[BLACK] -= len(captured)
        self.turn = color
        return True

    def pass_turn(self):
        """Flip the side to move (used by text tests / GUI pass)."""
        self.turn = WHITE if self.turn == BLACK else BLACK

    # ------------------------------------------------------------------
    # Five / overline
    # ------------------------------------------------------------------
    def black_run_length(self, x: int, y: int) -> int:
        best = 1
        for dx, dy in DIRECTIONS:
            run = 1
            i = 1
            while True:
                cx, cy = x - i * dx, y - i * dy
                if self.in_bounds(cx, cy) and self.grid[cx, cy] == BLACK:
                    run += 1
                    i += 1
                else:
                    break
            i = 1
            while True:
                cx, cy = x + i * dx, y + i * dy
                if self.in_bounds(cx, cy) and self.grid[cx, cy] == BLACK:
                    run += 1
                    i += 1
                else:
                    break
            best = max(best, run)
        return best

    def check_black_five(self, x: int, y: int) -> bool:
        """Exact five wins for black.  Six or more is the overline foul."""
        if not self.in_bounds(x, y) or self.grid[x, y] != BLACK:
            return False
        return self.black_run_length(x, y) == 5

    def check_black_overline(self, x: int, y: int) -> bool:
        if not self.in_bounds(x, y) or self.grid[x, y] != BLACK:
            return False
        return self.black_run_length(x, y) >= 6

    # ------------------------------------------------------------------
    # Liberty tests used by search-space exclusion
    # ------------------------------------------------------------------
    def would_self_capture(self, x: int, y: int) -> bool:
        if not self.is_empty(x, y):
            return False
        self.grid[x, y] = BLACK
        try:
            _stones, liberties = self.get_group(x, y)
            return len(liberties) == 0
        finally:
            self.grid[x, y] = EMPTY

    def black_move_leaves_one_liberty_nonfive(self, x: int, y: int) -> bool:
        """True when a black move at (x,y) is not a winning exact five and
        the resulting black group has exactly one liberty."""
        if not self.is_empty(x, y):
            return False
        self.grid[x, y] = BLACK
        try:
            if self.check_black_five(x, y):
                return False
            _stones, liberties = self.get_group(x, y)
            return len(liberties) == 1
        finally:
            self.grid[x, y] = EMPTY

    # ------------------------------------------------------------------
    # White territory / dead positions
    # ------------------------------------------------------------------
    def _has_open_five_window(self, x: int, y: int) -> bool:
        """True if there exists an in-board 5-cell window containing (x,y)
        with no white stone.  This is the geometric part of 'can this cell
        ever be part of a black five'."""
        for dx, dy in DIRECTIONS:
            for offset in range(-4, 1):
                cells = [(x + (offset + i) * dx, y + (offset + i) * dy)
                         for i in range(5)]
                if not all(self.in_bounds(cx, cy) for cx, cy in cells):
                    continue
                if any(self.grid[cx, cy] == WHITE for cx, cy in cells):
                    continue
                return True
        return False

    def is_dead_position(self, x: int, y: int) -> bool:
        """White-territory membership.

        A one-step-capturable cell is NOT territory.  Territory is only:
          * a no-liberty (self-capture) empty cell, or
          * a cell with no white-free five window.
        """
        if not self.in_bounds(x, y):
            return False
        if self.grid[x, y] == EMPTY:
            if self.would_self_capture(x, y):
                return True
            return not self._has_open_five_window(x, y)
        if self.grid[x, y] == BLACK:
            return not self._has_open_five_window(x, y)
        return False

    def _recompute_dead_positions(self) -> set[tuple[int, int]]:
        """Window-scan implementation of white territory.

        Mark every cell that belongs to at least one white-free 5-cell
        window as geometrically alive.  Then only the small set of empty
        cells near black stones needs the additional no-liberty /
        one-liberty-nonfive / overline checks.
        """
        alive = np.zeros((self.size, self.size), dtype=bool)
        for dx, dy in DIRECTIONS:
            for x in range(self.size):
                for y in range(self.size):
                    end_x, end_y = x + 4 * dx, y + 4 * dy
                    if not self.in_bounds(end_x, end_y):
                        continue
                    cells = [(x + i * dx, y + i * dy) for i in range(5)]
                    if any(self.grid[cx, cy] == WHITE for cx, cy in cells):
                        continue
                    for cx, cy in cells:
                        alive[cx, cy] = True

        dead: set[tuple[int, int]] = set()
        for x in range(self.size):
            for y in range(self.size):
                if self.grid[x, y] in (EMPTY, BLACK) and not alive[x, y]:
                    dead.add((x, y))

        # Extra empty-cell checks are only meaningful next to black stones.
        # Only no-liberty cells are territory; one-step-capturable cells
        # are deliberately NOT territory.
        for x, y in self.relevant_empty_positions():
            if (x, y) in dead:
                continue
            if self.would_self_capture(x, y):
                dead.add((x, y))
        return dead

    def get_dead_positions(self) -> set[tuple[int, int]]:
        if self._dead_cache is not None:
            return set(self._dead_cache)
        self._dead_cache = self._recompute_dead_positions()
        return set(self._dead_cache)

    def get_white_territory_empty_positions(self) -> set[tuple[int, int]]:
        dead = self.get_dead_positions()
        return {(x, y) for x, y in dead if self.grid[x, y] == EMPTY}

    def get_black_territory(self) -> set[tuple[int, int]]:
        """Empty cells where every in-board 5-window through the cell contains
        at least one black stone and no white / blue-cross blocker."""
        if self._black_territory_cache is not None:
            return set(self._black_territory_cache)
        blue = self.get_blue_cross_positions()
        total = np.zeros((self.size, self.size), dtype=np.int16)
        good = np.zeros((self.size, self.size), dtype=np.int16)
        for dx, dy in DIRECTIONS:
            for x in range(self.size):
                for y in range(self.size):
                    end_x, end_y = x + 4 * dx, y + 4 * dy
                    if not self.in_bounds(end_x, end_y):
                        continue
                    cells = [(x + i * dx, y + i * dy) for i in range(5)]
                    for cx, cy in cells:
                        total[cx, cy] += 1
                    has_black = any(self.grid[cx, cy] == BLACK
                                    for cx, cy in cells)
                    blocked = any(
                        self.grid[cx, cy] == WHITE or
                        (self.grid[cx, cy] == EMPTY and (cx, cy) in blue)
                        for cx, cy in cells
                    )
                    if has_black and not blocked:
                        for cx, cy in cells:
                            good[cx, cy] += 1
        out: set[tuple[int, int]] = set()
        for x in range(self.size):
            for y in range(self.size):
                if self.grid[x, y] == EMPTY and total[x, y] > 0 and \
                        good[x, y] == total[x, y]:
                    out.add((x, y))
        self._black_territory_cache = set(out)
        return out

    # ------------------------------------------------------------------
    # Blue crosses
    # ------------------------------------------------------------------
    def get_blue_cross_positions(self) -> set[tuple[int, int]]:
        """All empty cells where a black move is illegal for any reason."""
        if self._blue_cross_cache is not None:
            return set(self._blue_cross_cache)
        import rules
        blue: set[tuple[int, int]] = set()
        for x, y in self.relevant_empty_positions():
            ok, ftype = rules.is_black_legal_move(self, x, y)
            if not ok:
                if not self._update_forbidden_blue and ftype != "self_capture":
                    continue
                blue.add((x, y))
        self._blue_cross_cache = set(blue)
        return set(blue)

    def get_no_liberty_positions(self) -> set[tuple[int, int]]:
        import rules
        out = set()
        for x, y in self.get_blue_cross_positions():
            ok, ftype = rules.is_black_legal_move(self, x, y)
            if not ok and ftype == "self_capture":
                out.add((x, y))
        return out

    # ------------------------------------------------------------------
    # Candidate generation (the task's exact search ranges)
    # ------------------------------------------------------------------
    def _territory_addbacks(self, territory: set[tuple[int, int]]) -> set[tuple[int, int]]:
        """Excluded territory points which touch a black group that is not
        entirely white territory (at least one stone in the group is alive).
        Even if the orthogonally adjacent black stone itself is territory,
        another stone in the same group being alive makes this point a
        candidate."""
        add: set[tuple[int, int]] = set()
        for x, y in territory:
            if not self.is_empty(x, y):
                continue
            seen: set[tuple[int, int]] = set()
            useful = False
            for nx, ny in self.neighbors(x, y):
                if self.grid[nx, ny] != BLACK or (nx, ny) in seen:
                    continue
                stones, _liberties = self.get_group(nx, ny)
                seen |= stones
                if any(stone not in territory for stone in stones):
                    useful = True
                    break
            if useful:
                add.add((x, y))
        return add

    def get_black_candidate_moves(self, threats=None) -> list[tuple[int, int]]:
        """Black search range:
        empty cells - white territory - blue crosses - one-liberty-nonfive
        moves, then territory add-backs next to groups with a non-territory
        liberty."""
        blue = self.get_blue_cross_positions()
        territory = self.get_dead_positions()
        addbacks = self._territory_addbacks(territory)
        relevant = self.relevant_empty_positions()
        candidates: list[tuple[int, int]] = []
        import rules
        for x in range(self.size):
            for y in range(self.size):
                if not self.is_empty(x, y):
                    continue
                pos = (x, y)
                if pos in addbacks and pos not in blue and \
                        not self.black_move_leaves_one_liberty_nonfive(x, y):
                    ok, _ = rules.is_black_legal_move(self, x, y)
                    if ok:
                        candidates.append(pos)
                    continue
                if pos in territory or pos in blue:
                    continue
                if pos in relevant:
                    ok, _ = rules.is_black_legal_move(self, x, y)
                    if not ok:
                        continue
                    if self.black_move_leaves_one_liberty_nonfive(x, y):
                        continue
                candidates.append(pos)
        return sorted(candidates)

    def get_white_candidate_moves(self, threats=None) -> list[tuple[int, int]]:
        """White search range: empty cells - white territory, then the
        territory add-backs described above."""
        territory = self.get_dead_positions()
        addbacks = self._territory_addbacks(territory)
        candidates: list[tuple[int, int]] = []
        for x in range(self.size):
            for y in range(self.size):
                if not self.is_empty(x, y):
                    continue
                pos = (x, y)
                if pos in addbacks or pos not in territory:
                    candidates.append(pos)
        return sorted(candidates)

    def _priority_red_positions(self, threats) -> set[tuple[int, int]]:
        """Only the currently highest red threat level is considered."""
        for group in RED_LEVEL_GROUPS:
            positions = {pos for pos, t in threats.items() if t in group}
            if positions:
                return positions
        return set()

    def _one_liberty_black_group_liberties(self) -> set[tuple[int, int]]:
        out: set[tuple[int, int]] = set()
        for stones, liberties in self.get_black_groups():
            if len(liberties) == 1:
                out.add(next(iter(liberties)))
        return out

    def _associated_group_liberties(self, threats, selected,
                                    territory=None) -> set[tuple[int, int]]:
        """Liberties of black groups associated with `selected` red cells.

        A group is associated when removing it would make one of the selected
        red cells disappear.  Its liberties are added when its liberty count
        is <= B(red cell), where B = 6 - n for a live/sleep-n red cell.
        If `territory` is supplied, groups whose stones are all territory are
        ignored (an associated group must contain at least one live stone).
        """
        out: set[tuple[int, int]] = set()
        territory = territory or set()
        for info in self.get_black_group_infos(threats):
            associated = info["affected"] & selected
            if not associated:
                continue
            if territory and all(stone in territory for stone in info["stones"]):
                continue
            if any(info["liberty_count"] <= b_limit_for_threat(threats[pos])
                   for pos in associated):
                out.update(info["liberties"])
        return out

    def get_black_priority_candidates(self, threats=None) -> list[tuple[int, int]]:
        """No-solid/no-triangle candidate set for Black.

        Select the strongest existing red level (large > small > dot), add
        liberties of associated black groups with <= B liberties, then apply
        Black's territory / blue-cross / one-liberty-nonfive exclusions and
        the territory add-backs.
        """
        if threats is None:
            threats = self.compute_threats()
        territory = self.get_dead_positions()
        blue = self.get_blue_cross_positions()
        import rules

        def valid_black(pos):
            if not self.is_empty(*pos):
                return False
            if pos in territory or pos in blue:
                return False
            ok, _ = rules.is_black_legal_move(self, *pos)
            if not ok:
                return False
            return not self.black_move_leaves_one_liberty_nonfive(*pos)

        def valid_black_liberty(pos):
            # Associated group liberties may lie in white territory: these
            # are the add-back points.  They still must be legal and must
            # not be one-liberty-nonfive moves for Black.
            if not self.is_empty(*pos) or pos in blue:
                return False
            ok, _ = rules.is_black_legal_move(self, *pos)
            if not ok:
                return False
            return not self.black_move_leaves_one_liberty_nonfive(*pos)

        for group in RED_LEVEL_GROUPS:
            selected = {pos for pos, t in threats.items() if t in group}
            if not selected:
                continue
            assoc = self._associated_group_liberties(threats, selected,
                                                     territory)
            out = {p for p in selected if valid_black(p)}
            out |= {p for p in assoc if valid_black_liberty(p)}
            if out:
                return sorted(out)
        return []

    def get_white_priority_candidates(self, threats=None) -> list[tuple[int, int]]:
        """No-solid/no-triangle candidate set for White.

        Same strongest-to-weakest red-level scan.  White may play on
        forbidden points, so only white territory is removed before the
        territory add-backs.
        """
        if threats is None:
            threats = self.compute_threats()
        territory = self.get_dead_positions()

        for group in RED_LEVEL_GROUPS:
            selected = {pos for pos, t in threats.items() if t in group}
            if not selected:
                continue
            assoc = self._associated_group_liberties(threats, selected,
                                                     territory)
            # Selected red positions are never territory.  Associated group
            # liberties may be territory; those are exactly the allowed
            # add-back points and are therefore included.
            out = {p for p in selected if self.is_empty(*p)}
            out |= {p for p in assoc if self.is_empty(*p)}
            if out:
                return sorted(out)
        return []

    # ------------------------------------------------------------------
    # Threat classification
    # ------------------------------------------------------------------
    def compute_threats(self) -> dict[tuple[int, int], str]:
        if self._threats_cache is not None:
            return dict(self._threats_cache)

        blue = self.get_blue_cross_positions()
        dead = self.get_dead_positions()
        # Pattern classification uses only real white stones and board edges
        # as blockers.  Empty cells which are currently blue/dead may change
        # status after the hypothetical black move; treating them statically
        # as blockers caused false negatives / false positives for gapped
        # four shapes such as 2101102 and 2110012.
        blockers: set[tuple[int, int]] = set()

        threats: dict[tuple[int, int], str] = {}
        import rules
        # Candidate pre-filter: only cells near existing black stones can
        # possibly become a red threat.
        for x, y in sorted(self.relevant_empty_positions()):
            if (x, y) in blue or (x, y) in dead:
                continue  # territory and blue crosses are never red
            ok, _ = rules.is_black_legal_move(self, x, y)
            if not ok:
                continue
            self.grid[x, y] = BLACK
            try:
                threat = rules.classify_position_after_move(
                    self, x, y, blockers=blockers
                )
            finally:
                self.grid[x, y] = EMPTY
            if threat is not None:
                threats[(x, y)] = threat
        self._threats_cache = dict(threats)
        return dict(threats)

    def compute_threats_for_positions(self, positions) -> dict[tuple[int, int], str]:
        positions = [p for p in positions if self.is_empty(*p)]
        if not positions:
            return {}
        blue = self.get_blue_cross_positions()
        dead = self.get_dead_positions()
        blockers: set[tuple[int, int]] = set()
        threats: dict[tuple[int, int], str] = {}
        import rules
        for x, y in positions:
            if (x, y) in blue or (x, y) in dead:
                continue
            self.grid[x, y] = BLACK
            try:
                threat = rules.classify_position_after_move(
                    self, x, y, blockers=blockers
                )
            finally:
                self.grid[x, y] = EMPTY
            if threat is not None:
                threats[(x, y)] = threat
        return threats

    def get_red_positions(self, threats=None) -> set[tuple[int, int]]:
        if threats is None:
            threats = self.compute_threats()
        return {pos for pos, t in threats.items() if t in THREAT_MARKER}

    def get_hollow_triangles(self, threats=None) -> set[tuple[int, int]]:
        """Triangles which are fragile.

        A triangle is hollow when, after Black plays it, one of the attacking
        one-liberty black groups can be captured and that capture removes all
        solid circles AND all triangles.  Such triangles still count as
        forced threats, but their score is 500 instead of 625.
        """
        if self._hollow_triangles_cache is not None:
            return set(self._hollow_triangles_cache)
        if threats is None:
            threats = self.compute_threats()
        hollow: set[tuple[int, int]] = set()
        triangle_types = ("four_three", "open_four")
        for pos, t in threats.items():
            if t not in triangle_types:
                continue
            after_black = self.copy()
            ok, _ = after_black.play_black(*pos)
            if not ok:
                continue
            for stones, liberties in after_black.get_black_groups():
                if len(liberties) != 1:
                    continue
                liberty = next(iter(liberties))
                after_capture = after_black.copy()
                ok_w, _ = after_capture.play_white(*liberty)
                if not ok_w:
                    continue
                remaining = after_capture.compute_threats()
                if not any(tt in FORCED_THREAT_TYPES
                           for tt in remaining.values()):
                    hollow.add(pos)
                    break
        self._hollow_triangles_cache = set(hollow)
        return set(hollow)

    def is_hollow_triangle(self, pos, threat_type=None) -> bool:
        if threat_type is not None and \
                threat_type not in ("four_three", "open_four"):
            return False
        threats = self.compute_threats()
        return pos in self.get_hollow_triangles(threats)

    def get_threat_score(self, pos, threat_type) -> int:
        if threat_type in ("four_three", "open_four") and \
                pos in self.get_hollow_triangles():
            return HOLLOW_TRIANGLE_SCORE
        return THREAT_SCORE.get(threat_type, 0)

    def get_red_scores(self, threats=None) -> dict[tuple[int, int], int]:
        if threats is None:
            threats = self.compute_threats()
        hollow = self.get_hollow_triangles(threats)
        scores: dict[tuple[int, int], int] = {}
        for pos, t in threats.items():
            base = THREAT_SCORE.get(t, 0)
            if base <= 0:
                continue
            if t in ("four_three", "open_four") and pos in hollow:
                base = HOLLOW_TRIANGLE_SCORE
            scores[pos] = base
        return scores

    def evaluate_black_move_delta(self, x, y, old_group_scores=None,
                                  red_scores=None) -> float:
        """Compatibility helper: full-board value change after a black move."""
        import rules
        if not self.is_empty(x, y):
            return -float("inf")
        ok, _ = rules.is_black_legal_move(self, x, y)
        if not ok:
            return -float("inf")
        old_value = self.evaluate_black_position()
        child = self.copy()
        ok, _ = child.play_black(x, y)
        if not ok:
            return -float("inf")
        return child.evaluate_black_position() - old_value

    def evaluate_white_move_delta(self, x, y, old_group_scores=None,
                                  red_scores=None) -> float:
        """Compatibility helper: full-board value change after a white move."""
        if not self.is_empty(x, y):
            return -float("inf")
        old_value = self.evaluate_black_position()
        child = self.copy()
        ok, _ = child.play_white(x, y)
        if not ok:
            return -float("inf")
        return child.evaluate_black_position() - old_value

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------
    def compute_group_capture_loss(self, stones, old_red_scores=None) -> float:
        """A = the amount of red-position score that would disappear if this
        black group instantly vanished."""
        stones = set(stones)
        if not stones:
            return 0.0
        affected = self.affected_positions_around(stones, radius=4)
        if old_red_scores is None:
            old_red_scores = self.get_red_scores()
        old_total = sum(
            old_red_scores.get((x, y), 0)
            for x, y in affected
            if self.grid[x, y] == EMPTY
        )
        if old_total <= 0:
            return 0.0

        work = HybridBoard(self.size)
        work.grid = self.grid.copy()
        for x, y in stones:
            work.grid[x, y] = EMPTY
        new_threats = work.compute_threats()
        new_scores = work.get_red_scores(new_threats)
        new_total = sum(
            new_scores.get((x, y), 0)
            for x, y in affected
            if work.grid[x, y] == EMPTY
        )
        return max(0.0, old_total - new_total)

    def compute_group_score(self, stones, liberties=None, red_scores=None) -> float:
        stones = set(stones)
        if not stones:
            return 0.0
        if liberties is None:
            _s, liberties = self.get_group(next(iter(stones)))
        n = len(liberties)
        if n <= 0:
            return 0.0
        if red_scores is None:
            red_scores = self.get_red_scores()
        a_value = self.compute_group_capture_loss(stones, red_scores)
        return a_value * (1.0 - 0.5 ** n)

    def evaluate_black_position(self) -> float:
        """Static black-perspective value:
        sum of group scores + red-position scores - territory count."""
        if self._eval_cache is not None:
            return self._eval_cache
        threats = self.compute_threats()
        red_scores = self.get_red_scores(threats)
        red_total = float(sum(red_scores.values()))
        dead = self.get_dead_positions()
        territory_penalty = 0
        for x, y in dead:
            if self.grid[x, y] == EMPTY:
                territory_penalty += 1
            elif self.grid[x, y] == BLACK:
                territory_penalty += 1
        territory_penalty += len(self.get_black_territory())

        group_total = 0.0
        for stones, liberties in self.get_black_groups():
            group_total += self.compute_group_score(
                stones, liberties=liberties, red_scores=red_scores
            )
        value = group_total + red_total - territory_penalty
        self._eval_cache = value
        return value

    # ------------------------------------------------------------------
    # Farthest-open-point fallback
    # ------------------------------------------------------------------
    def farthest_open_positions(self, candidates) -> set[tuple[int, int]]:
        candidates = [p for p in candidates if self.is_empty(*p)]
        if not candidates:
            return set()
        blockers = {
            (x, y)
            for x in range(self.size)
            for y in range(self.size)
            if self.grid[x, y] != EMPTY
        }
        territory = self.get_white_territory_empty_positions()
        blockers |= territory

        best: set[tuple[int, int]] = set()
        best_score = -1.0
        center = self.size / 2.0
        for x, y in candidates:
            direction_scores = []
            for dx, dy in DIRECTIONS:
                forward = 0
                nx, ny = x + dx, y + dy
                while self.in_bounds(nx, ny) and (nx, ny) not in blockers:
                    forward += 1
                    nx += dx
                    ny += dy
                backward = 0
                nx, ny = x - dx, y - dy
                while self.in_bounds(nx, ny) and (nx, ny) not in blockers:
                    backward += 1
                    nx -= dx
                    ny -= dy
                direction_scores.append(min(forward, backward))
            score = max(direction_scores) if direction_scores else 0
            tie = -0.001 * (abs(x - center) + abs(y - center))
            value = score + tie
            if value > best_score:
                best_score = value
                best = {(x, y)}
            elif abs(value - best_score) < 1e-12:
                best.add((x, y))
        return best

    # ------------------------------------------------------------------
    # White defence candidates (forced threats + capture liberties)
    # ------------------------------------------------------------------
    def _attack_groups_around(self, board, x: int, y: int):
        """Black groups touching the four lines around (x,y)."""
        cells = board.positions_on_lines(x, y, radius=4)
        black_cells = {(cx, cy) for cx, cy in cells if board.grid[cx, cy] == BLACK}
        groups: list[tuple[set, set]] = []
        seen: set[tuple[int, int]] = set()
        for cx, cy in sorted(black_cells):
            if (cx, cy) in seen:
                continue
            stones, liberties = board.get_group(cx, cy)
            seen |= stones
            groups.append((stones, liberties))
        return groups

    def get_white_defense_candidates(self, threats=None) -> list[tuple[int, int]]:
        """Candidate set used when black has solid circles or triangles.

        1. every solid circle / triangle position.
        2. For attacking groups on live-four/rush-four/five lines:
           if the group has one liberty, add that liberty.
        3. For attacking groups on live-three lines:
           if the group has one or two liberties, add all its liberties.
        """
        if threats is None:
            threats = self.compute_threats()
        forced = {pos for pos, t in threats.items() if t in FORCED_THREAT_TYPES}
        candidates = set(forced)
        import rules

        for tx, ty in sorted(forced):
            board_after = self.copy()
            ok, _ = board_after.play_black(tx, ty)
            if not ok:
                continue

            seen: set[tuple[int, int]] = set()
            for dx, dy in DIRECTIONS:
                threat = rules.classify_direction_after_move(
                    board_after, tx, ty, dx, dy
                )
                if threat == "open_three":
                    limit = 2
                elif threat in ("five", "open_four", "rush_four"):
                    limit = 1
                else:
                    continue

                line_black: set[tuple[int, int]] = set()
                for step in range(-4, 5):
                    nx, ny = tx + step * dx, ty + step * dy
                    if board_after.in_bounds(nx, ny) and \
                            board_after.grid[nx, ny] == BLACK:
                        line_black.add((nx, ny))

                for ax, ay in sorted(line_black):
                    if (ax, ay) in seen:
                        continue
                    stones, liberties = board_after.get_group(ax, ay)
                    seen |= stones
                    if 0 < len(liberties) <= limit:
                        candidates.update(liberties)

        return sorted(p for p in candidates if self.is_empty(*p))

    def get_white_blocking_candidates(self, threats=None) -> list[tuple[int, int]]:
        """Compatibility alias."""
        return self.get_white_defense_candidates(threats)

    def black_position_value(self) -> float:
        """Compatibility alias for the black-perspective static value."""
        return self.evaluate_black_position()

    def black_move_keeps_group_above_one_liberty(self, x: int, y: int) -> bool:
        if not self.is_empty(x, y):
            return False
        import rules
        ok, _ = rules.is_black_legal_move(self, x, y)
        if not ok:
            return False
        child = self.copy()
        ok, _ = child.play_black(x, y)
        if not ok:
            return False
        _stones, liberties = child.get_group(x, y)
        return len(liberties) > 1

    # ------------------------------------------------------------------
    # Win conditions
    # ------------------------------------------------------------------
    def white_wins_by_capture(self) -> bool:
        return not np.any(self.grid == BLACK)

    def white_wins_by_occupy(self) -> bool:
        return not np.any(self.grid != WHITE)

    def white_wins_by_line_block(self) -> bool:
        blue = self.get_blue_cross_positions()
        for dx, dy in DIRECTIONS:
            for x in range(self.size):
                for y in range(self.size):
                    end_x = x + 4 * dx
                    end_y = y + 4 * dy
                    if not (self.in_bounds(end_x, end_y)):
                        continue
                    cells = [(x + i * dx, y + i * dy) for i in range(5)]
                    blocked = False
                    for cx, cy in cells:
                        if self.grid[cx, cy] == WHITE:
                            blocked = True
                            break
                        if self.grid[cx, cy] == EMPTY and (cx, cy) in blue:
                            blocked = True
                            break
                    if not blocked:
                        return False
        return True

    def get_unblocked_lines(self) -> list[list[tuple[int, int]]]:
        """Return every white/blue-free 5-cell window (used for GUI display)."""
        blue = self.get_blue_cross_positions()
        lines: list[list[tuple[int, int]]] = []
        for dx, dy in DIRECTIONS:
            for x in range(self.size):
                for y in range(self.size):
                    end_x, end_y = x + 4 * dx, y + 4 * dy
                    if not self.in_bounds(end_x, end_y):
                        continue
                    cells = [(x + i * dx, y + i * dy) for i in range(5)]
                    if any(self.grid[cx, cy] == WHITE or
                           (self.grid[cx, cy] == EMPTY and (cx, cy) in blue)
                           for cx, cy in cells):
                        continue
                    lines.append(cells)
        return lines

    # ------------------------------------------------------------------
    # Misc / test helpers
    # ------------------------------------------------------------------
    def get_move_numbers(self) -> dict[tuple[int, int], int]:
        out: dict[tuple[int, int], int] = {}
        for i, (color, x, y, captured) in enumerate(self.history):
            out[(x, y)] = i + 1
            for cx, cy in captured:
                out.pop((cx, cy), None)
        return out

    def black_stone_count(self) -> int:
        return int(np.sum(self.grid == BLACK))

    def white_stone_count(self) -> int:
        return int(np.sum(self.grid == WHITE))

    def empty_count(self) -> int:
        return int(np.sum(self.grid == EMPTY))

    def set_grid(self, grid):
        grid = np.asarray(grid, dtype=np.int8)
        if grid.shape != (self.size, self.size):
            raise ValueError(f"grid shape must be ({self.size},{self.size})")
        self.grid = grid.copy()
        self.history = []
        self.captured_count = {BLACK: 0, WHITE: 0}
        self.turn = BLACK
        self._invalidate_caches()

    def load_centered(self, rows):
        """Load a small rectangular pattern into the middle of the board.
        '0' and uppercase letters are empty cells, '1' is black and '2' is
        white / board edge, exactly as in the test-pattern notation."""
        self.grid = np.zeros((self.size, self.size), dtype=np.int8)
        self.history = []
        self.captured_count = {BLACK: 0, WHITE: 0}
        self.turn = BLACK
        self.pattern_positions: dict[str, tuple[int, int]] = {}
        self._update_forbidden_blue = True
        self._invalidate_caches()
        h = len(rows)
        w = max(len(r) for r in rows)
        r0 = (self.size - h) // 2
        c0 = (self.size - w) // 2
        for i, row in enumerate(rows):
            for j, ch in enumerate(row):
                ch = ch.upper()
                if ch == "1":
                    self.grid[r0 + i, c0 + j] = BLACK
                elif ch == "2":
                    self.grid[r0 + i, c0 + j] = WHITE
                elif ch.isalpha() and ch != "0":
                    self.pattern_positions[ch] = (r0 + i, c0 + j)
        return self

    def __repr__(self) -> str:
        return (f"<HybridBoard {self.size}x{self.size} "
                f"black={self.black_stone_count()} white={self.white_stone_count()}>")
