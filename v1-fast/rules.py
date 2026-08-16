"""
rules.py - 黑棋禁手判定 + 威胁分类 (查表重构版，API 完全兼容)
"""

from __future__ import annotations
import numpy as np
from board import EMPTY, BLACK, WHITE

# 方向向量后备（防止 board 中缺失）
try:
    from board import DIRECTIONS
except ImportError:
    DIRECTIONS = [(1, 0), (0, 1), (1, 1), (1, -1)]

# ---------- 威胁分值 ----------
THREAT_SCORE = {
    "five": 100_000,
    "open_four": 10_000,
    "four_three": 9_000,
    "rush_four": 8,
    "open_three": 8,
    "sleep_three": 4,
    "open_two": 4,
    "sleep_two": 2,
    "open_one": 2,
    "sleep_one": 1,
    "four_four": 0,
    "three_three": 0,
}

THREAT_LEVEL = {
    "five": 100,
    "open_four": 90,
    "four_three": 85,
    "rush_four": 80,
    "open_three": 70,
    "sleep_three": 50,
    "open_two": 40,
    "sleep_two": 30,
    "open_one": 20,
    "sleep_one": 10,
    "four_four": 0,
    "three_three": 0,
}

THREAT_SIZE = {
    "five": "solid",
    "four_three": "solid_triangle",
    "open_four": "solid",
    "rush_four": "large",
    "open_three": "large",
    "sleep_three": "medium",
    "open_two": "medium",
    "sleep_two": "small",
    "open_one": "small",
    "sleep_one": "dot",
}

# ---------- 查表模式 ----------
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

# 内部辅助：编码/查表
def _cell_code(grid: np.ndarray, x: int, y: int) -> str:
    """0=空, 1=黑, 2=阻挡（白棋/边界）"""
    size = grid.shape[0]
    if not (0 <= x < size and 0 <= y < size):
        return '2'
    v = grid[x, y]
    if v == EMPTY: return '0'
    if v == BLACK: return '1'
    return '2'

def _line_code(grid: np.ndarray, x: int, y: int, dx: int, dy: int, half: int = 4) -> str:
    """获取以(x,y)为中心、方向(dx,dy)、半径half的线段编码"""
    chars = []
    for step in range(-half, half + 1):
        cx, cy = x + step * dx, y + step * dy
        chars.append(_cell_code(grid, cx, cy))
    return ''.join(chars)

def _match_pattern(s: str) -> str | None:
    """在字符串s中滑动匹配所有模式，返回最高威胁类型（数字越小优先级越高）"""
    PRIORITY = {
        "open_four": 1, "rush_four": 2,
        "open_three": 3, "sleep_three": 4,
        "open_two": 5, "sleep_two": 6,
        "open_one": 7, "sleep_one": 8,
    }
    best_prio = 999
    best = None
    for t, pat_list in PATTERNS.items():
        for pat in pat_list:
            rev = pat[::-1]
            L = len(pat)
            for i in range(len(s) - L + 1):
                w = s[i:i+L]
                if w == pat or w == rev:
                    prio = PRIORITY[t]
                    if prio < best_prio:
                        best_prio = prio
                        best = t
    return best

# ---------- 保留的公共辅助函数（与原有完全一致）----------
def cell_char(v: int) -> str:
    if v == BLACK: return "B"
    if v == WHITE: return "W"
    if v == EMPTY: return "."
    return "X"

def get_line(grid: np.ndarray, x: int, y: int, dx: int, dy: int, half: int = 5) -> tuple[str, list[tuple[int, int] | None]]:
    size = grid.shape[0]
    s: list[str] = []
    pos: list[tuple[int, int] | None] = []
    for i in range(-half, half + 1):
        cx, cy = x + i * dx, y + i * dy
        if 0 <= cx < size and 0 <= cy < size:
            s.append(cell_char(grid[cx, cy]))
            pos.append((int(cx), int(cy)))
        else:
            s.append("X")
            pos.append(None)
    return "".join(s), pos

def _line_str(grid, x, y, dx, dy, half=4) -> str:
    """用于调试的线段字符串（B/W/.）"""
    size = grid.shape[0]
    ss = []
    for i in range(-half, half + 1):
        cx, cy = x + i * dx, y + i * dy
        if 0 <= cx < size and 0 <= cy < size:
            v = grid[cx, cy]
            if v == BLACK: ss.append("B")
            elif v == WHITE: ss.append("W")
            else: ss.append(".")
        else:
            ss.append("X")
    return "".join(ss)

def is_direction_alive(grid, x, y, dx, dy) -> bool:
    size = grid.shape[0]
    for offset in range(-4, 1):
        valid = True
        has_white = False
        for i in range(5):
            cx, cy = x + (offset + i) * dx, y + (offset + i) * dy
            if not (0 <= cx < size and 0 <= cy < size):
                valid = False
                break
            if grid[cx, cy] == WHITE:
                has_white = True
        if valid and not has_white:
            return True
    return False

def _count_completing_moves(grid: np.ndarray, x: int, y: int, dx: int, dy: int,
                            color: int = BLACK) -> set[tuple[int, int]]:
    """原 API：统计本方向上加 1 子可形成五的空位集合"""
    size = grid.shape[0]
    moves: set[tuple[int, int]] = set()
    for offset in range(-4, 1):
        cells = []
        valid = True
        for i in range(5):
            cx, cy = x + (offset + i) * dx, y + (offset + i) * dy
            if not (0 <= cx < size and 0 <= cy < size):
                valid = False
                break
            cells.append((cx, cy))
        if not valid: continue
        new_pos = -offset
        if not (0 <= new_pos < 5): continue
        values = [grid[cx, cy] for cx, cy in cells]
        if values[new_pos] != color: continue
        n_color = sum(1 for v in values if v == color)
        n_empty = sum(1 for v in values if v == EMPTY)
        if n_color == 4 and n_empty == 1:
            for i, v in enumerate(values):
                if v == EMPTY:
                    moves.add(cells[i])
                    break
    return moves

# ---------- 单方向威胁判定（改用查表）----------
def is_open_four(grid, x, y, dx, dy, color=BLACK) -> bool:
    return _match_pattern(_line_code(grid, x, y, dx, dy)) == "open_four"

def has_four(grid, x, y, dx, dy, color=BLACK) -> bool:
    t = _match_pattern(_line_code(grid, x, y, dx, dy))
    return t in ("open_four", "rush_four")

def is_open_three(grid, x, y, dx, dy, color=BLACK, _depth=0) -> bool:
    return _match_pattern(_line_code(grid, x, y, dx, dy)) == "open_three"

def is_sleep_three(grid, x, y, dx, dy, color=BLACK) -> bool:
    return _match_pattern(_line_code(grid, x, y, dx, dy)) == "sleep_three"

def is_open_two(grid, x, y, dx, dy, color=BLACK) -> bool:
    return _match_pattern(_line_code(grid, x, y, dx, dy)) == "open_two"

def is_sleep_two(grid, x, y, dx, dy, color=BLACK) -> bool:
    return _match_pattern(_line_code(grid, x, y, dx, dy)) == "sleep_two"

def is_open_one(grid, x, y, dx, dy, color=BLACK) -> bool:
    return _match_pattern(_line_code(grid, x, y, dx, dy)) == "open_one"

def is_sleep_one(grid, x, y, dx, dy, color=BLACK) -> bool:
    return _match_pattern(_line_code(grid, x, y, dx, dy)) == "sleep_one"

# ---------- 单方向威胁分类 ----------
def classify_threat_direction(grid, x, y, dx, dy, color=BLACK) -> str | None:
    """在 (x,y) 已落子后, 分类该方向的威胁类型."""
    # 检查连五/长连
    run = 1
    i = 1
    while True:
        cx, cy = x - i * dx, y - i * dy
        if 0 <= cx < grid.shape[0] and 0 <= cy < grid.shape[1] and grid[cx, cy] == color:
            run += 1; i += 1
        else: break
    i = 1
    while True:
        cx, cy = x + i * dx, y + i * dy
        if 0 <= cx < grid.shape[0] and 0 <= cy < grid.shape[1] and grid[cx, cy] == color:
            run += 1; i += 1
        else: break
    if run == 5: return "five"
    if run >= 6: return None

    # 查表获得威胁
    code = _line_code(grid, x, y, dx, dy)
    return _match_pattern(code)

# ---------- 全方向威胁分类 ----------
def classify_threat(grid, x, y, color=BLACK) -> str | None:
    dir_threats = []
    for dx, dy in DIRECTIONS:
        t = classify_threat_direction(grid, x, y, dx, dy, color)
        if t is not None:
            dir_threats.append(t)

    if not dir_threats:
        return None

    fours = sum(1 for t in dir_threats if t in ("open_four", "rush_four"))
    open_threes = sum(1 for t in dir_threats if t == "open_three")

    if "five" in dir_threats:
        return "five"
    if fours >= 2:
        return "four_four"
    if fours >= 1 and open_threes >= 1:
        return "four_three"
    if "open_four" in dir_threats:
        return "open_four"

    priority = ["rush_four", "open_three", "sleep_three",
                "open_two", "sleep_two", "open_one", "sleep_one"]
    for p in priority:
        if p in dir_threats:
            return p
    return None

# ---------- 禁手判定 ----------
def detect_forbidden(grid: np.ndarray, x: int, y: int, color: int = BLACK) -> str | None:
    # 长连
    for dx, dy in DIRECTIONS:
        run = 1
        i = 1
        while True:
            cx, cy = x - i * dx, y - i * dy
            if 0 <= cx < grid.shape[0] and 0 <= cy < grid.shape[1] and grid[cx, cy] == color:
                run += 1; i += 1
            else: break
        i = 1
        while True:
            cx, cy = x + i * dx, y + i * dy
            if 0 <= cx < grid.shape[0] and 0 <= cy < grid.shape[1] and grid[cx, cy] == color:
                run += 1; i += 1
            else: break
        if run >= 6:
            return "overline"

    four_dirs = sum(1 for dx, dy in DIRECTIONS if has_four(grid, x, y, dx, dy, color))
    if four_dirs >= 2:
        return "four_four"

    three_dirs = sum(1 for dx, dy in DIRECTIONS if is_open_three(grid, x, y, dx, dy, color))
    if three_dirs >= 2:
        return "three_three"

    return None

# ---------- 合法着法 ----------
def is_black_legal_move(board, x: int, y: int) -> tuple[bool, str | None]:
    if not board.in_bounds(x, y) or not board.is_empty(x, y):
        return False, "occupied"
    board.grid[x, y] = BLACK
    try:
        _, libs = board.get_group(x, y)
        if len(libs) == 0:
            return False, "self_capture"
        if hasattr(board, 'check_black_overline') and board.check_black_overline(x, y):
            return False, "overline"
        forbidden = detect_forbidden(board.grid, x, y, BLACK)
        if forbidden is not None:
            return False, forbidden
        if board.check_black_five(x, y):
            return True, None
        return True, None
    finally:
        board.grid[x, y] = EMPTY

def all_legal_black_moves(board) -> list[tuple[int, int]]:
    moves = []
    for x in range(board.size):
        for y in range(board.size):
            if board.is_empty(x, y):
                legal, _ = is_black_legal_move(board, x, y)
                if legal:
                    moves.append((x, y))
    return moves

# ---------- 威胁点位扫描 ----------
def find_all_threats(board) -> dict[tuple[int, int], str]:
    threats = {}
    for x in range(board.size):
        for y in range(board.size):
            if not board.is_empty(x, y):
                continue
            if hasattr(board, 'is_dead_position') and board.is_dead_position(x, y):
                continue
            ok, _ = is_black_legal_move(board, x, y)
            if not ok:
                continue
            board.grid[x, y] = BLACK
            try:
                t = classify_threat(board.grid, x, y, BLACK)
                if t is not None:
                    threats[(x, y)] = t
            finally:
                board.grid[x, y] = EMPTY
    return threats