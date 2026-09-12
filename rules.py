"""
rules.py - Renju foul judgement and exact one-line threat classification.

Only the three fouls requested by the task are used:
    overline    : a black move creates 6 or more connected black stones
    four-four   : a black move creates two or more fours (open/rush)
    three-three : a black move creates two or more open threes

A move which creates an exact five is legal and wins, even if the same
stone would otherwise be a four-four / three-three foul.

The pattern table below is the standard 9-character local window table
used by the reference implementation.  '1'=black, '0'=empty, '2'=blocker
(white / edge / blue cross / territory).
"""

from __future__ import annotations

from board import (
    EMPTY,
    BLACK,
    WHITE,
    OBSTACLE,
    DIRECTIONS,
    THREAT_SCORE,
    THREAT_MARKER,
    FORCED_THREAT_TYPES,
)

THREAT_PRIORITY = {
    "open_four": 1,
    "rush_four": 2,
    "open_three": 3,
    "sleep_three": 4,
    "open_two": 5,
    "sleep_two": 6,
    "open_one": 7,
    "sleep_one": 8,
}

PATTERNS = {
    "open_four":   ["011110"],
    "rush_four":   ["211110", "11101", "11011"],
    "open_three":  ["011100", "011010"],
    "sleep_three": ["211100", "211010", "210110", "2011102", "10101", "11001"],
    "open_two":    ["001100", "011000", "010100", "010010"],
    "sleep_two":   ["211000", "210100", "210010", "2011002", "2010102", "10001"],
    "open_one":    ["001000", "010000"],
    "sleep_one":   ["210000", "2010002", "2001002"],
}


def line_code(board, x: int, y: int, dx: int, dy: int,
              blockers: set | None = None, half: int = 4) -> str:
    """9-character window centred on (x,y) along direction (dx,dy).

    Black cells are '1'.  White, obstacle / out-of-board cells and cells
    listed in `blockers` are '2'.  Every other empty cell is '0'.
    Caller must already have placed the temporary black stone at (x,y).
    """
    blockers = blockers or set()
    torus = bool(getattr(board, "torus", False))
    size = board.size
    chars: list[str] = []
    for step in range(-half, half + 1):
        if torus:
            cx, cy = (x + step * dx) % size, (y + step * dy) % size
        else:
            cx, cy = x + step * dx, y + step * dy
            if not board.in_bounds(cx, cy):
                chars.append("2")
                continue
        value = int(board.grid[cx, cy])
        if value == BLACK:
            chars.append("1")
        elif value in (WHITE, OBSTACLE):
            chars.append("2")
        elif (cx, cy) in blockers:
            chars.append("2")
        else:
            chars.append("0")
    return "".join(chars)


def match_line_threat(code: str) -> str | None:
    best = None
    best_priority = 999
    for threat_type, patterns in PATTERNS.items():
        priority = THREAT_PRIORITY[threat_type]
        if priority >= best_priority:
            continue
        for pattern in patterns:
            rev = pattern[::-1]
            length = len(pattern)
            for start in range(len(code) - length + 1):
                window = code[start:start + length]
                if window == pattern or window == rev:
                    best_priority = priority
                    best = threat_type
                    break
            if best == threat_type:
                break
    return best


def classify_direction_after_move(board, x: int, y: int, dx: int, dy: int,
                                  blockers: set | None = None) -> str | None:
    """Classify the threat on one direction after black has been placed at
    (x,y).  Returns 'five' / 'overline' / a threat-type or None."""
    torus = bool(getattr(board, "torus", False))
    size = board.size
    run = 1
    for sign in (-1, 1):
        i = 1
        while i < size:
            if torus:
                cx, cy = (x + sign * i * dx) % size, (y + sign * i * dy) % size
            else:
                cx, cy = x + sign * i * dx, y + sign * i * dy
                if not board.in_bounds(cx, cy):
                    break
            if board.grid[cx, cy] == BLACK:
                run += 1
                i += 1
            else:
                break
    if torus and run > size:
        run = size

    if run == 5:
        return "five"
    if run >= 6:
        return "overline"

    code = line_code(board, x, y, dx, dy, blockers=blockers)
    threat = match_line_threat(code)
    if threat in ("rush_four", "open_three") and code.count("1") >= 5:
        # A 9-window containing five or more black cells cannot be a
        # meaningful four/open-three; it is either a five (handled above)
        # or a longer blocked shape.
        return None

    if threat in ("open_four", "rush_four"):
        # Validate every claimed four by counting legal completing moves.
        # A gapped pattern such as 11101 is only a real four when filling
        # its gap creates an exact five and the filling move is legal.
        # Otherwise shapes like 21111AB (where completing A would be
        # self-capture or overline) must not be reported as a four.
        completions = 0
        for step in range(-4, 5):
            if torus:
                cx, cy = (x + step * dx) % size, (y + step * dy) % size
            else:
                cx, cy = x + step * dx, y + step * dy
                if not board.in_bounds(cx, cy):
                    continue
            if board.grid[cx, cy] != EMPTY:
                continue
            board.grid[cx, cy] = BLACK
            try:
                if board.black_run_length(cx, cy) == 5:
                    _stones, liberties = board.get_group(cx, cy)
                    if liberties:
                        completions += 1
            finally:
                board.grid[cx, cy] = EMPTY
        if completions >= 2:
            return "open_four"
        if completions == 1:
            return "rush_four"
        return None
    return threat


def classify_position_after_move(board, x: int, y: int,
                                 blockers: set | None = None) -> str | None:
    """Combined classification for the temporary black stone at (x,y)."""
    direction_threats: list[str] = []
    for dx, dy in DIRECTIONS:
        t = classify_direction_after_move(board, x, y, dx, dy, blockers=blockers)
        if t is not None:
            direction_threats.append(t)

    if not direction_threats:
        return None
    if "five" in direction_threats:
        return "five_point"

    # If long-connection foul is disabled, a 6+ line is treated as a
    # large-circle threat (the move is legal).
    if "overline" in direction_threats:
        if getattr(board, "_forbid_overline", True):
            return None
        direction_threats = [
            "rush_four" if t == "overline" else t for t in direction_threats
        ]

    fours = [t for t in direction_threats if t in ("open_four", "rush_four")]
    open_threes = [t for t in direction_threats if t == "open_three"]

    # If three-three / four-four fouls are disabled, the combined shape is
    # strong enough to display as a triangle.
    if not getattr(board, "_forbid_33", True) and len(open_threes) >= 2:
        return "four_three"
    if not getattr(board, "_forbid_44", True) and len(fours) >= 2:
        return "four_three"

    if any(t == "open_four" for t in fours):
        return "open_four"
    if fours and open_threes:
        return "four_three"
    if fours:
        return "rush_four"
    if open_threes:
        return "open_three"

    priority = ["sleep_three", "open_two", "sleep_two", "open_one", "sleep_one"]
    for threat in priority:
        if threat in direction_threats:
            return threat
    return None


# Legality cache for top-level queries.  The AI threat pre-filter calls this
# function for very many empty cells, so results are memoised by board state.
_LEGAL_CACHE: dict = {}
_LEGAL_CACHE_LIMIT = 200000


def _legal_cache_key(board, x: int, y: int):
    return (board.size, bool(getattr(board, "torus", False)),
            bool(getattr(board, "_forbid_overline", True)),
            bool(getattr(board, "_forbid_44", True)),
            bool(getattr(board, "_forbid_33", True)),
            x, y, board.grid.tobytes())


def _extension_is_viable(board, ex: int, ey: int, dx: int, dy: int,
                         stack: set) -> bool:
    """Rapfi-style check for one open-three extension point.

    The point counts as a live-three extension when, with Black there, the
    direction becomes a flexible four (or a five), the new group is not
    immediately capturable by White (>= 2 liberties), and the point is not a
    real forbidden point (a pseudo-forbidden point that is not actually
    forbidden still counts, exactly as Rapfi does).
    """
    board.grid[ex, ey] = BLACK
    try:
        _stones, liberties = board.get_group(ex, ey)
        threat = classify_direction_after_move(board, ex, ey, dx, dy)
        if threat == "five":
            return True
        if threat != "open_four":
            return False
        if len(liberties) <= 1:
            # White captures this group next, so the four is not durable.
            return False
    finally:
        board.grid[ex, ey] = EMPTY
    if (ex, ey) in stack:
        return True
    ok, _ = is_black_legal_move(board, ex, ey, _stack=stack | {(ex, ey)})
    return ok


def _live_three(board, x: int, y: int, dx: int, dy: int,
                stack: set) -> bool:
    """Is the open three at (x, y) in direction (dx, dy) genuine?

    Exactly Rapfi's scan: on each side, step over Black stones and inspect the
    first empty point; if placing there makes a flexible four, the three is a
    real open three.  Opponent stones, obstacles and the board edge stop the
    scan.  Forbidden or immediately capturable extension points do not make
    the three genuine.
    """
    for sign in (-1, 1):
        for step in range(1, 5):
            cx = x + sign * step * dx
            cy = y + sign * step * dy
            if not board.in_bounds(cx, cy):
                break
            value = int(board.grid[cx, cy])
            if value == BLACK:
                continue
            if value != EMPTY:
                break
            if _extension_is_viable(board, cx, cy, dx, dy, stack):
                return True
            break
    return False


def _count_foul_shapes(board, x: int, y: int, stack: set):
    """(fours, genuine open threes) for the Black stone already at (x, y)."""
    threats = [classify_direction_after_move(board, x, y, dx, dy)
               for dx, dy in DIRECTIONS]
    fours = sum(1 for t in threats if t in ("open_four", "rush_four"))
    threes = 0
    if getattr(board, "_forbid_33", True):
        for (dx, dy), threat in zip(DIRECTIONS, threats):
            if threat == "open_three" and _live_three(board, x, y, dx, dy,
                                                      stack):
                threes += 1
    return fours, threes


def _black_one_liberty_liberties(board):
    """All liberties of Black groups that have exactly one liberty."""
    out = []
    seen = set()
    for x in range(board.size):
        for y in range(board.size):
            if board.grid[x, y] != BLACK or (x, y) in seen:
                continue
            stones, liberties = board.get_group(x, y)
            seen |= stones
            if len(liberties) == 1:
                out.append(next(iter(liberties)))
    return out


def is_black_legal_move(board, x: int, y: int, _stack: set | None = None):
    """Return (ok, foul_type).  The board is never mutated.

    The forbidden judgement follows Rapfi's checkForbiddenPoint and then adds
    this game's capture rule:
      * exact five wins at once (checked first); overline is a foul;
      * a four-four needs no recursive foul check (five has priority and only
        White's capture can block a four);
      * a three-three needs two genuine open threes; each must be extendable
        into a flexible four at a point that is itself playable;
      * any shape that White can erase by capturing a one-liberty Black group
        right now is not a lasting foul.
    """
    if not board.in_bounds(x, y) or not board.is_empty(x, y):
        return False, "occupied"

    top_level = _stack is None
    stack = _stack or set()
    cache_key = None
    if top_level:
        cache_key = _legal_cache_key(board, x, y)
        cached = _LEGAL_CACHE.get(cache_key)
        if cached is not None:
            return cached

    def finish(result):
        if cache_key is not None:
            if len(_LEGAL_CACHE) > _LEGAL_CACHE_LIMIT:
                _LEGAL_CACHE.clear()
            _LEGAL_CACHE[cache_key] = result
        return result

    forbid44 = bool(getattr(board, "_forbid_44", True))
    forbid33 = bool(getattr(board, "_forbid_33", True))

    board.grid[x, y] = BLACK
    try:
        _stones, liberties = board.get_group(x, y)
        if len(liberties) == 0:
            return finish((False, "self_capture"))

        run = board.black_run_length(x, y)
        if run == 5:
            return finish((True, None))
        if getattr(board, "_forbid_overline", True) and run >= 6:
            return finish((False, "overline"))

        # The played group itself can be captured next move: nothing lasts.
        if not (forbid44 or forbid33):
            return finish((True, None))

        fours, threes = _count_foul_shapes(board, x, y, stack)
        four_foul = forbid44 and fours >= 2
        three_foul = forbid33 and threes >= 2
        if not (four_foul or three_foul):
            return finish((True, None))

        # Capture defence: if White can take a one-liberty Black group now and
        # the foul disappears with it, the move is not a lasting foul.
        for liberty in _black_one_liberty_liberties(board):
            if board.grid[liberty] != EMPTY:
                continue
            work = board.copy()
            work.grid[liberty] = WHITE
            work._capture_zero_liberty_black_groups()
            if work.grid[x, y] != BLACK:
                return finish((True, None))
            f2, t2 = _count_foul_shapes(work, x, y, stack)
            if not ((forbid44 and f2 >= 2) or (forbid33 and t2 >= 2)):
                return finish((True, None))

        if four_foul:
            return finish((False, "four_four"))
        return finish((False, "three_three"))
    finally:
        board.grid[x, y] = EMPTY


def all_legal_black_moves(board) -> list[tuple[int, int]]:
    out = []
    for x in range(board.size):
        for y in range(board.size):
            if board.is_empty(x, y):
                ok, _ = is_black_legal_move(board, x, y)
                if ok:
                    out.append((x, y))
    return out


def find_all_threats(board) -> dict:
    """Compatibility wrapper used by older callers."""
    return board.compute_threats()


def cell_char(v: int) -> str:
    if v == BLACK:
        return "B"
    if v == WHITE:
        return "W"
    if v == EMPTY:
        return "."
    return "X"
