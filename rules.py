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


def _windows_containing(board, x: int, y: int, dx: int, dy: int):
    """Yield every in-board 5-cell window along (dx, dy) holding (x, y)."""
    for offset in range(-4, 1):
        cells = []
        valid = True
        for i in range(5):
            cell = board.step_from(x, y, dx, dy, offset + i)
            if cell is None or cell in cells:
                valid = False
                break
            cells.append(cell)
        if valid and (x, y) in cells:
            yield cells


def _four_sets(board, x: int, y: int, dx: int, dy: int) -> set:
    """Distinct fours created by the Black stone at (x, y).

    A four is a set of 4 Black stones in a 5-cell window whose empty cell
    completes an exact five.  Sets are deduplicated, so an open four
    (two completions of the same four stones) counts once, while two fours
    on the same line (one on each side of the new stone) count twice - this
    is the rule-book four-four case.
    """
    out = set()
    for cells in _windows_containing(board, x, y, dx, dy):
        values = [int(board.grid[c]) for c in cells]
        if values.count(BLACK) != 4 or values.count(EMPTY) != 1:
            continue
        empty_cell = cells[values.index(EMPTY)]
        board.grid[empty_cell] = BLACK
        try:
            makes_five = board.black_run_length(*empty_cell) == 5
        finally:
            board.grid[empty_cell] = EMPTY
        if makes_five:
            out.add(frozenset(c for c, v in zip(cells, values) if v == BLACK))
    return out


def _three_sets(board, x: int, y: int, dx: int, dy: int, stack: set,
                shallow: bool = False) -> set:
    """Distinct genuine open threes created by the Black stone at (x, y).

    A three is the 3-stone set of a window that can be extended by a usable
    move into a live four (both completions open).  Distinct sets are
    counted separately, so two threes on the same line - one on each side of
    the new stone - count twice, which is the rule-book three-three case.
    """
    out = set()
    patterns = ("011100", "011010")
    # Six-cell windows: only the real open-three shapes (straight 011100 or
    # broken 011010) count; a sleep three such as 10101 never matches.
    for offset in range(-4, 1):
        cells = []
        valid = True
        for i in range(6):
            cell = board.step_from(x, y, dx, dy, offset + i)
            if cell is None or cell in cells:
                valid = False
                break
            cells.append(cell)
        if not valid:
            continue
        code = "".join("1" if board.grid[c] == BLACK else
                       ("0" if board.grid[c] == EMPTY else "2")
                       for c in cells)
        if not any(code == p or code == p[::-1] for p in patterns):
            continue
        black_set = frozenset(c for c in cells if board.grid[c] == BLACK)
        if (x, y) not in black_set or black_set in out:
            continue
        empties = [c for c in cells if board.grid[c] == EMPTY]
        if len(empties) < 2:
            continue
        # Only a point directly next to the three's own stones can extend it
        # (Rapfi stops at the first empty cell past its stones); a farther
        # empty point cannot revive a blocked three.
        adjacent = []
        for cell in empties:
            for sign in (-1, 1):
                neighbour = board.step_from(cell[0], cell[1],
                                            sign * dx, sign * dy)
                if neighbour is not None and neighbour in black_set:
                    adjacent.append(cell)
                    break
        if not adjacent:
            continue
        for empty_cell in adjacent:
            board.grid[empty_cell] = BLACK
            live = False
            try:
                _stones, liberties = board.get_group(*empty_cell)
                # Only self-capture blocks a point (Black may not play
                # there); a one-liberty point is still playable.
                if len(liberties) > 0 and \
                        classify_direction_after_move(
                            board, empty_cell[0], empty_cell[1],
                            dx, dy) in ("open_four", "rush_four", "five"):
                    grown = frozenset(c for c in cells
                                      if board.grid[c] == BLACK)
                    live = black_set <= grown
            finally:
                board.grid[empty_cell] = EMPTY
            if not live:
                continue
            if shallow or not _simple_forbidden(board, empty_cell[0],
                                                empty_cell[1]):
                out.add(black_set)
                break
    return out


def _simple_forbidden(board, x: int, y: int) -> bool:
    """One-level forbidden test used for open-three extension points.

    Self-capture, overline and two fours make the point unusable; an exact
    five is always usable.  Deliberately does NOT recurse into three-three,
    which is what used to make the search explode.
    """
    if not board.in_bounds(x, y) or not board.is_empty(x, y):
        return False
    board.grid[x, y] = BLACK
    try:
        _stones, liberties = board.get_group(x, y)
        if len(liberties) == 0:
            return True
        run = board.black_run_length(x, y)
        if run == 5:
            return False
        if getattr(board, "_forbid_overline", True) and run >= 6:
            return True
        if not getattr(board, "_forbid_44", True):
            return False
        fours = 0
        for dx, dy in DIRECTIONS:
            if classify_direction_after_move(board, x, y, dx, dy) in \
                    ("open_four", "rush_four"):
                fours += 1
                if fours >= 2:
                    return True
        if getattr(board, "_forbid_33", True):
            # One bounded extra level: a point that is itself a three-three
            # foul cannot serve as a live-three extension.
            threes = 0
            for dx, dy in DIRECTIONS:
                threes += len(_three_sets(board, x, y, dx, dy, set(),
                                          shallow=True))
                if threes >= 2:
                    return True
        return False
    finally:
        board.grid[x, y] = EMPTY


def _count_foul_shapes(board, x: int, y: int, stack: set):
    """(number of fours, number of genuine open threes) for the stone."""
    fours = 0
    threes = 0
    check_three = bool(getattr(board, "_forbid_33", True))
    for dx, dy in DIRECTIONS:
        fours += len(_four_sets(board, x, y, dx, dy))
        if fours >= 2 or not check_three:
            continue
        threes += len(_three_sets(board, x, y, dx, dy, stack))
        if threes >= 2:
            break
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


# ----------------------------------------------------------------------
# Exact Rapfi checkForbiddenPoint (tools/rapfi source/Rapfi/game/board.cpp)
#
# Same algorithm as cpp/src/forbidden.cpp, so the Python path (GUI blue
# crosses, human move legality, board_tools) and the C++ engine agree:
#   1. pattern4(black) != FORBID  -> legal
#   2. any direction overline, or two fours -> forbidden
#   3. place the stone and count "true threes": for every direction whose
#      line pattern is F3/F3S walk outwards (through the contiguous black
#      stones, at most 4 cells) to the FIRST empty cell and test
#        a) pattern4 == B_FLEX4 (the point makes an open four), or
#        b) that direction's pattern == F5 (the point wins), or
#        c) pattern4 == FORBID and pattern == F4 and that point is itself
#           NOT forbidden (recursion).
#      Rapfi counts AT MOST ONE true three per direction (a successful first
#      side jumps straight to the next direction), so two threes on one line
#      are a single three - this is Rapfi's semantics, not the rule book's.
#
# The two documented project extensions live in _rapfi_cell_flag: an empty
# no-liberty point and an obstacle block exactly like a white stone, and the
# torus topology wraps the 11-cell window and the extension walk.
# ----------------------------------------------------------------------
_RAPFI_LINE_LEN = 11
_RAPFI_LINE_MID = 5
_RAPFI_SELF, _RAPFI_OPPO, _RAPFI_EMPT = 0, 1, 2
_RAPFI_MAX_FIND = 4
_RAPFI_MAX_DEPTH = 64

# Rapfi Pat enum (same numeric order as cpp/src/pattern_table.h).
(_PAT_DEAD, _PAT_OL, _PAT_B1, _PAT_F1, _PAT_B2, _PAT_F2, _PAT_F2A, _PAT_F2B,
 _PAT_B3, _PAT_B3S, _PAT_F3, _PAT_F3S, _PAT_B4, _PAT_B4S, _PAT_F4,
 _PAT_F5) = range(16)
# Rapfi Pattern4 enum.
(_P4_NONE, _P4_FORBID, _P4_L_FLEX2, _P4_K_BLOCK3, _P4_J_FLEX2_2X,
 _P4_I_BLOCK3_PLUS, _P4_H_FLEX3, _P4_G_FLEX3_PLUS, _P4_F_FLEX3_2X,
 _P4_E_BLOCK4, _P4_D_BLOCK4_PLUS, _P4_C_BLOCK4_FLEX3, _P4_B_FLEX4,
 _P4_A_FIVE) = range(14)

_RAPFI_PATTERN_MEMO: dict = {}
_RAPFI_PATTERN_MEMO_LIMIT = 500000
_NO_LIBERTY_CACHE: dict = {}
_NO_LIBERTY_CACHE_LIMIT = 8192


def _rapfi_count_line(line):
    real = full = 1
    inc = 1
    start = end = _RAPFI_LINE_MID
    for i in range(_RAPFI_LINE_MID - 1, -1, -1):
        v = line[i]
        if v == _RAPFI_SELF:
            real += inc
        elif v == _RAPFI_OPPO:
            break
        else:
            inc = 0
        full += 1
        start = i
    inc = 1
    for i in range(_RAPFI_LINE_MID + 1, _RAPFI_LINE_LEN):
        v = line[i]
        if v == _RAPFI_SELF:
            real += inc
        elif v == _RAPFI_OPPO:
            break
        else:
            inc = 0
        full += 1
        end = i
    return real, full, start, end


def _rapfi_shift(line, i):
    mid = _RAPFI_LINE_MID
    return tuple(line[j + i - mid] if 0 <= j + i - mid < _RAPFI_LINE_LEN
                 else _RAPFI_OPPO for j in range(_RAPFI_LINE_LEN))


def _rapfi_pattern(line):
    """Rapfi getPattern<RENJU, BLACK> for one 11-cell line (memoised)."""
    got = _RAPFI_PATTERN_MEMO.get(line)
    if got is not None:
        return got
    real, full, start, end = _rapfi_count_line(line)
    if real >= 6:
        p = _PAT_OL                       # overline (black rules only)
    elif real >= 5:
        p = _PAT_F5
    elif full < 5:
        p = _PAT_DEAD
    else:
        cnt = [0] * 16
        f5_idx = [0, 0]
        for i in range(start, end + 1):
            if line[i] != _RAPFI_EMPT:
                continue
            shifted = list(_rapfi_shift(line, i))
            shifted[_RAPFI_LINE_MID] = _RAPFI_SELF
            sp = _rapfi_pattern(tuple(shifted))
            if sp == _PAT_F5 and cnt[_PAT_F5] < 2:
                f5_idx[cnt[_PAT_F5]] = i
            cnt[sp] += 1
        if cnt[_PAT_F5] >= 2:
            p = _PAT_F4
            # Rapfi's renju "dirty fix": two five points on one line closer
            # than 5 (an in-line double four) are encoded as an overline.
            if f5_idx[1] - f5_idx[0] < 5:
                p = _PAT_OL
        elif cnt[_PAT_F5] == 1:
            blocked = list(line)
            blocked[f5_idx[0]] = _RAPFI_OPPO
            p = (_PAT_B4S if _rapfi_pattern(tuple(blocked)) >= _PAT_B3
                 else _PAT_B4)
        elif cnt[_PAT_F4] >= 2:
            p = _PAT_F3S
        elif cnt[_PAT_F4]:
            p = _PAT_F3
        elif cnt[_PAT_B4S]:
            p = _PAT_B3S
        elif cnt[_PAT_B4]:
            p = _PAT_B3
        elif cnt[_PAT_F3S] + cnt[_PAT_F3] >= 4:
            p = _PAT_F2B
        elif cnt[_PAT_F3S] + cnt[_PAT_F3] >= 3:
            p = _PAT_F2A
        elif cnt[_PAT_F3S] + cnt[_PAT_F3]:
            p = _PAT_F2
        elif cnt[_PAT_B3] + cnt[_PAT_B3S]:
            p = _PAT_B2
        elif cnt[_PAT_F2] + cnt[_PAT_F2A] + cnt[_PAT_F2B]:
            p = _PAT_F1
        elif cnt[_PAT_B2]:
            p = _PAT_B1
        else:
            p = _PAT_DEAD
    if len(_RAPFI_PATTERN_MEMO) > _RAPFI_PATTERN_MEMO_LIMIT:
        _RAPFI_PATTERN_MEMO.clear()
    _RAPFI_PATTERN_MEMO[line] = p
    return p


def _rapfi_combine4(p1, p2, p3, p4):
    """Rapfi getPattern4<Forbid=true> (chaining fours/threes folded in)."""
    n = [0] * 16
    for p in (p1, p2, p3, p4):
        n[p] += 1
    n[_PAT_B4] += n[_PAT_B4S]
    n[_PAT_B3] += n[_PAT_B3S]
    if n[_PAT_F5] >= 1:
        return _P4_A_FIVE
    if n[_PAT_OL] >= 1:
        return _P4_FORBID
    if n[_PAT_F4] + n[_PAT_B4] >= 2:
        return _P4_FORBID
    if n[_PAT_F3] + n[_PAT_F3S] >= 2:
        return _P4_FORBID
    if n[_PAT_B4] >= 2:
        return _P4_B_FLEX4
    if n[_PAT_F4] >= 1:
        return _P4_B_FLEX4
    return _P4_NONE


def _rapfi_no_liberty(board):
    """Empty points where a black stone would have no liberty (cached)."""
    key = (board.size, bool(getattr(board, "torus", False)),
           board.grid.tobytes())
    got = _NO_LIBERTY_CACHE.get(key)
    if got is None:
        got = frozenset(board.get_no_liberty_positions())
        if len(_NO_LIBERTY_CACHE) > _NO_LIBERTY_CACHE_LIMIT:
            _NO_LIBERTY_CACHE.clear()
        _NO_LIBERTY_CACHE[key] = got
    return got


def _rapfi_cell_flag(board, x, y, noli):
    """Black's view of one cell: white / obstacle / off-board / no-liberty
    empty all block (OPPO), black is SELF, any other empty is EMPT."""
    if not board.in_bounds(x, y):
        return _RAPFI_OPPO
    v = int(board.grid[x, y])
    if v == BLACK:
        return _RAPFI_SELF
    if v == WHITE or v == OBSTACLE:
        return _RAPFI_OPPO
    return _RAPFI_OPPO if (x, y) in noli else _RAPFI_EMPT


def _rapfi_dir_pattern(board, x, y, dx, dy, noli, cache):
    key = (x, y, dx, dy)
    got = cache.get(key)
    if got is not None:
        return got
    line = [_RAPFI_EMPT] * _RAPFI_LINE_LEN
    line[_RAPFI_LINE_MID] = _RAPFI_SELF
    for i in range(-_RAPFI_LINE_MID, _RAPFI_LINE_MID + 1):
        if i == 0:
            continue
        cell = board.step_from(x, y, dx, dy, i)
        line[i + _RAPFI_LINE_MID] = (
            _RAPFI_OPPO if cell is None
            else _rapfi_cell_flag(board, cell[0], cell[1], noli))
    p = _rapfi_pattern(tuple(line))
    cache[key] = p
    return p


def _rapfi_pattern4(board, x, y, noli, cache):
    return _rapfi_combine4(*[_rapfi_dir_pattern(board, x, y, dx, dy, noli,
                                                cache)
                             for dx, dy in DIRECTIONS])


def _rapfi_count_true_threes(board, x, y, dirs, depth):
    """Rapfi's third step: at most one true three per direction."""
    board.grid[x, y] = BLACK
    try:
        noli = _rapfi_no_liberty(board)
        threes = 0
        for d, (dx, dy) in enumerate(DIRECTIONS):
            if dirs[d] not in (_PAT_F3, _PAT_F3S):
                continue
            counted = False
            for sign in (-1, 1):
                if counted:
                    break
                for step in range(1, _RAPFI_MAX_FIND + 1):
                    cell = board.step_from(x, y, sign * dx, sign * dy, step)
                    if cell is None:
                        break
                    cx, cy = cell
                    v = int(board.grid[cx, cy])
                    if v == EMPTY:
                        cache: dict = {}
                        p4 = _rapfi_pattern4(board, cx, cy, noli, cache)
                        pc = _rapfi_dir_pattern(board, cx, cy, dx, dy, noli,
                                                cache)
                        if (p4 == _P4_B_FLEX4 or pc == _PAT_F5 or
                                (p4 == _P4_FORBID and pc == _PAT_F4 and
                                 not _rapfi_is_forbidden(board, cx, cy,
                                                         depth + 1))):
                            counted = True
                        break
                    if v != BLACK:
                        break
            if counted:
                threes += 1
                if threes >= 2:
                    break
        return threes
    finally:
        board.grid[x, y] = EMPTY


def _rapfi_is_forbidden(board, x, y, depth=0):
    """Exact Rapfi checkForbiddenPoint for Black (no GUI rule switches)."""
    if not board.is_empty(x, y) or depth >= _RAPFI_MAX_DEPTH:
        return False
    noli = _rapfi_no_liberty(board)
    cache: dict = {}
    dirs = [_rapfi_dir_pattern(board, x, y, dx, dy, noli, cache)
            for dx, dy in DIRECTIONS]
    if _rapfi_combine4(*dirs) != _P4_FORBID:
        return False
    fours = 0
    for p in dirs:
        if p == _PAT_OL:
            return True
        if p in (_PAT_B4, _PAT_B4S, _PAT_F4):
            fours += 1
            if fours >= 2:
                return True
    return _rapfi_count_true_threes(board, x, y, dirs, depth) >= 2


def _rapfi_verdict(board, x, y):
    """(fours, overline, true_threes) for the stone at (x, y).

    Rapfi encodes an in-line double four as the overline pattern (the "dirty
    fix"), which is also why the per-direction contiguous run is measured:
    a real overline (6+ in a row) reports overline, the dirty fix reports
    two fours, so the GUI can still label the foul as four-four.
    """
    noli = _rapfi_no_liberty(board)
    cache: dict = {}
    dirs = [_rapfi_dir_pattern(board, x, y, dx, dy, noli, cache)
            for dx, dy in DIRECTIONS]
    if _rapfi_combine4(*dirs) != _P4_FORBID:
        return 0, False, 0

    board.grid[x, y] = BLACK
    try:
        runs = []
        for dx, dy in DIRECTIONS:
            run = 1
            for sign in (-1, 1):
                for step in range(1, board.size):
                    cell = board.step_from(x, y, sign * dx, sign * dy, step)
                    if cell is None or int(board.grid[cell]) != BLACK:
                        break
                    run += 1
                    if run >= 6:
                        break
                if run >= 6:
                    break
            runs.append(run)
    finally:
        board.grid[x, y] = EMPTY

    overline = False
    fours = 0
    for d, p in enumerate(dirs):
        if p == _PAT_OL:
            if runs[d] >= 6:
                overline = True
            else:
                fours += 2          # two fours on one line (Rapfi's OL fix)
        elif p in (_PAT_B4, _PAT_B4S, _PAT_F4):
            fours += 1
    if overline or fours >= 2:
        return fours, overline, 0

    threes = 0
    if dirs.count(_PAT_F3) + dirs.count(_PAT_F3S) >= 2:
        threes = _rapfi_count_true_threes(board, x, y, dirs, 0)
    return fours, overline, threes


def is_black_legal_move(board, x: int, y: int, _stack: set | None = None):
    """Return (ok, foul_type).  The board is never mutated on return.

    Exact Rapfi checkForbiddenPoint semantics (see the port above): overline,
    two fours (including an in-line double four) and two genuine open threes
    are forbidden, an exact five wins, and a no-liberty point is the Go
    self-capture rule.  Obstacles and no-liberty empty points block exactly
    like white stones.
    """
    if not board.in_bounds(x, y) or not board.is_empty(x, y):
        return False, "occupied"

    top_level = _stack is None
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

    forbid_overline = bool(getattr(board, "_forbid_overline", True))
    forbid44 = bool(getattr(board, "_forbid_44", True))
    forbid33 = bool(getattr(board, "_forbid_33", True))

    if board.would_self_capture(x, y):
        return finish((False, "self_capture"))

    board.grid[x, y] = BLACK
    try:
        run = board.black_run_length(x, y)
    finally:
        board.grid[x, y] = EMPTY
    if run == 5:
        return finish((True, None))
    if run >= 6 and forbid_overline:
        return finish((False, "overline"))
    if not (forbid_overline or forbid44 or forbid33):
        return finish((True, None))

    fours, overline, threes = _rapfi_verdict(board, x, y)
    if overline and forbid_overline:
        return finish((False, "overline"))
    if fours >= 2 and forbid44:
        return finish((False, "four_four"))
    if threes >= 2 and forbid33:
        return finish((False, "three_three"))
    return finish((True, None))


def _ordered_along(board, cells, dx, dy):
    """Sort cells along direction (dx, dy) (used for drawing foul lines)."""
    def project(cell):
        return (cell[0] * dx + cell[1] * dy)
    return sorted(cells, key=project)


def _foul_lines_placed(board, x: int, y: int, foul_type: str):
    """Foul cells for a Black stone already placed at (x, y)."""
    lines = []
    if foul_type == "overline":
        for dx, dy in DIRECTIONS:
            cells = [(x, y)]
            for sign in (-1, 1):
                step = 1
                while True:
                    cell = board.step_from(x, y, sign * dx, sign * dy, step)
                    if cell is None or board.grid[cell] != BLACK:
                        break
                    cells.append(cell)
                    step += 1
            if len(cells) >= 6:
                lines.append(_ordered_along(board, cells, dx, dy))
    elif foul_type == "four_four":
        for dx, dy in DIRECTIONS:
            for four in _four_sets(board, x, y, dx, dy):
                ordered = _ordered_along(board, list(four), dx, dy)
                completion = None
                for cell in board.positions_on_lines(x, y, 4):
                    if board.grid[cell] != EMPTY:
                        continue
                    board.grid[cell] = BLACK
                    try:
                        if board.black_run_length(*cell) == 5:
                            completion = cell
                            break
                    finally:
                        board.grid[cell] = EMPTY
                if completion is not None:
                    ordered = _ordered_along(
                        board, list(four) + [completion], dx, dy)
                lines.append(ordered)
    elif foul_type == "three_three":
        for dx, dy in DIRECTIONS:
            for three in _three_sets(board, x, y, dx, dy, set()):
                ordered = _ordered_along(board, list(three), dx, dy)
                for cell in board.positions_on_lines(x, y, 4):
                    if board.grid[cell] != EMPTY:
                        continue
                    board.grid[cell] = BLACK
                    try:
                        grown = frozenset(
                            c for c in board.positions_on_lines(x, y, 4)
                            if board.grid[c] == BLACK)
                        if three <= grown and                                 classify_direction_after_move(
                                    board, cell[0], cell[1],
                                    dx, dy) in ("open_four", "rush_four",
                                                "five") and                                 not _simple_forbidden(board, *cell):
                            ordered = _ordered_along(
                                board, list(three) + [cell], dx, dy)
                            break
                    finally:
                        board.grid[cell] = EMPTY
                lines.append(ordered)
    elif foul_type == "self_capture":
        stones, liberties = board.get_group(x, y)
        lines.append(sorted(stones) + sorted(liberties))
    return lines


def foul_lines(board, x: int, y: int, foul_type: str):
    """Cells making up the foul at (x, y), for the GUI to draw.

    The stone is placed temporarily so the shape helpers see the position
    after the move (the board is restored before returning).
    """
    placed = board.is_empty(x, y)
    if placed:
        board.grid[x, y] = BLACK
    try:
        return _foul_lines_placed(board, x, y, foul_type)
    finally:
        if placed:
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
