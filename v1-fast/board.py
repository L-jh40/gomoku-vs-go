"""
board.py - 棋盘状态与基础操作

混合规则:
  - 黑棋 (BLACK=1): 五子棋规则, 只下不吃, 目标是连五
  - 白棋 (WHITE=2): 围棋规则, 可吃黑棋组 (无气即提), 白棋不可被吃
  - 黑棋落子前检查自吃 (组无气则禁止落子, 5连例外)
  - 每次落子后全盘扫描, 清除任何残留 0 气黑组 (兜底)

约定:
  - 坐标 (x, y): x=行(0..size-1), y=列(0..size-1)
  - 棋盘用 numpy int8 数组: 0=空 / 1=黑 / 2=白

新增:
  - compute_threats(): 基于查表法的活 n / 眠 n 判定及红色位置计算
  - 蓝叉（禁手/无气）、白棋、棋盘边缘统一视为阻挡编码 '2'
"""

from __future__ import annotations
import numpy as np
from itertools import product

EMPTY = 0
BLACK = 1
WHITE = 2

BOARD_SIZE = 15

DIRECTIONS = [(1, 0), (0, 1), (1, 1), (1, -1)]

# ---------- 威胁查表模式 ----------
# 编码: 1=黑, 0=空, 2=蓝叉/白棋/边界
THREAT_ORDER = {
    "five_point": 0,
    "four_three": 1,
    "open_four": 2,
    "rush_four": 3,
    "open_three": 4,
    "sleep_three": 5,
    "open_two": 6,
    "sleep_two": 7,
    "open_one": 8,
    "sleep_one": 9,
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

# 红色标记分类：与 GUI 显示保持一致。
# five_point=实心圆, four_three/open_four=三角形,
# rush_four/open_three=大圆圈, sleep_three/open_two=小圆圈, sleep_two=红点。
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

# 空格红色位置的基础得分。领地不是红色位置，由候选/计分逻辑单独处理。
THREAT_SCORE = {
    "four_three": 2500,
    "open_four": 1250,
    "rush_four": 250,
    "open_three": 125,
    "sleep_three": 10,
    "open_two": 5,
    "sleep_two": 1,
}

# 白棋必须优先消除的红色位置：实心圆和三角形。
FORCED_THREAT_TYPES = {"five_point", "four_three", "open_four"}


def group_key(stones) -> tuple[tuple[int, int], ...]:
    """返回黑棋块的可哈希键，便于缓存上一步黑棋块得分。"""
    return tuple(sorted(stones))


class HybridBoard:
    """混合规则棋盘"""

    def __init__(self, size: int = BOARD_SIZE):
        self.size = size
        self.grid = np.zeros((size, size), dtype=np.int8)
        self.history: list[tuple] = []
        self.captured_count = {BLACK: 0, WHITE: 0}
        self._black_group_cache: list | None = None
        self._blue_cross_cache: set | None = None
        self._no_liberty_cache: set | None = None
        self._forbidden_cache: set | None = None
        self._update_forbidden_blue = True

    # ---------- 基础工具 ----------

    def copy(self) -> "HybridBoard":
        nb = HybridBoard(self.size)
        nb.grid = self.grid.copy()
        nb.history = list(self.history)
        nb.captured_count = dict(self.captured_count)
        nb._black_group_cache = (
            list(self._black_group_cache)
            if self._black_group_cache is not None
            else None
        )
        nb._blue_cross_cache = (
            set(self._blue_cross_cache)
            if self._blue_cross_cache is not None
            else None
        )
        nb._no_liberty_cache = (
            set(self._no_liberty_cache)
            if self._no_liberty_cache is not None
            else None
        )
        nb._forbidden_cache = (
            set(self._forbidden_cache)
            if self._forbidden_cache is not None
            else None
        )
        nb._update_forbidden_blue = self._update_forbidden_blue
        return nb

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.size and 0 <= y < self.size

    def is_empty(self, x: int, y: int) -> bool:
        return self.grid[x, y] == EMPTY

    def neighbors(self, x: int, y: int) -> list[tuple[int, int]]:
        result = []
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nx, ny = x + dx, y + dy
            if self.in_bounds(nx, ny):
                result.append((nx, ny))
        return result

    def get_group(self, x: int, y: int) -> tuple[set, set]:
        """返回 (组内棋子集合, 气集合) for 棋子 at (x, y)."""
        color = self.grid[x, y]
        if color == EMPTY:
            return set(), set()
        visited: set[tuple[int, int]] = set()
        stones: set[tuple[int, int]] = set()
        liberties: set[tuple[int, int]] = set()
        stack = [(x, y)]
        while stack:
            cx, cy = stack.pop()
            if (cx, cy) in visited:
                continue
            visited.add((cx, cy))
            if self.grid[cx, cy] == color:
                stones.add((cx, cy))
                for nx, ny in self.neighbors(cx, cy):
                    if (nx, ny) not in visited:
                        nv = self.grid[nx, ny]
                        if nv == color:
                            stack.append((nx, ny))
                        elif nv == EMPTY:
                            liberties.add((nx, ny))
        return stones, liberties

    def group_liberty_count(self, x: int, y: int) -> int:
        _, libs = self.get_group(x, y)
        return len(libs)

    def get_black_groups(self) -> list[tuple[set[tuple[int, int]], set[tuple[int, int]]]]:
        """枚举当前棋盘上所有黑棋块，返回 [(棋子集合, 气集合), ...]。"""
        groups: list[tuple[set[tuple[int, int]], set[tuple[int, int]]]] = []
        seen: set[tuple[int, int]] = set()
        for x in range(self.size):
            for y in range(self.size):
                if self.grid[x, y] != BLACK or (x, y) in seen:
                    continue
                stones, liberties = self.get_group(x, y)
                seen |= stones
                groups.append((stones, liberties))
        return groups

    def get_black_group_caches(self) -> list[tuple[tuple[tuple[int, int], ...], int, tuple[int, int] | None]]:
        """返回缓存的每个黑棋块：(棋子坐标元组, 气数, 只剩一气时的气位置)。"""
        if self._black_group_cache is not None:
            return self._black_group_cache

        groups: list[tuple[tuple[tuple[int, int], ...], int, tuple[int, int] | None]] = []
        seen: set[tuple[int, int]] = set()
        for x in range(self.size):
            for y in range(self.size):
                if self.grid[x, y] != BLACK or (x, y) in seen:
                    continue
                stones, liberties = self.get_group(x, y)
                seen |= stones
                single_liberty = next(iter(liberties)) if len(liberties) == 1 else None
                groups.append((tuple(sorted(stones)), len(liberties), single_liberty))
        self._black_group_cache = groups
        return groups

    def _invalidate_group_cache(self) -> None:
        self._black_group_cache = None

    def _invalidate_all_caches(self) -> None:
        self._black_group_cache = None
        self._blue_cross_cache = None
        self._no_liberty_cache = None
        self._forbidden_cache = None

    def capture_makes_all_solid_circles_disappear(self, x: int, y: int) -> bool:
        """白棋在 (x, y) 落子后，是否所有实心圆（连五点位）都消失。"""
        if not self.in_bounds(x, y) or self.grid[x, y] != EMPTY:
            return False
        board_after = self.copy()
        ok, _ = board_after.play_white(x, y)
        if not ok:
            return False
        threats_after = board_after.compute_threats()
        return not any(t == "five_point" for t in threats_after.values())

    def get_adjacent_black_groups(
        self, x: int, y: int
    ) -> list[tuple[set[tuple[int, int]], set[tuple[int, int]]]]:
        """返回候选点 (x, y) 上下左右紧邻的黑棋块（每个块只出现一次）。"""
        groups: list[tuple[set[tuple[int, int]], set[tuple[int, int]]]] = []
        seen: set[tuple[int, int]] = set()
        for nx, ny in self.neighbors(x, y):
            if self.grid[nx, ny] != BLACK or (nx, ny) in seen:
                continue
            stones, liberties = self.get_group(nx, ny)
            seen |= stones
            groups.append((stones, liberties))
        return groups

    def positions_on_lines(self, x: int, y: int, radius: int = 4) -> set[tuple[int, int]]:
        """返回以 (x, y) 为中心、四个棋盘方向各向外 radius 格的坐标集合。"""
        result: set[tuple[int, int]] = set()
        for dx, dy in DIRECTIONS:
            for step in range(-radius, radius + 1):
                nx, ny = x + dx * step, y + dy * step
                if self.in_bounds(nx, ny):
                    result.add((nx, ny))
        return result

    def affected_positions_around(
        self, cells, radius: int = 4
    ) -> set[tuple[int, int]]:
        """返回一组棋子周围、威胁判定可能受影响的坐标集合。"""
        affected: set[tuple[int, int]] = set()
        for x, y in cells:
            affected |= self.positions_on_lines(x, y, radius)
        return affected

    def adjacent_empty_to_black(self, radius: int = 1) -> set[tuple[int, int]]:
        """返回黑棋周围 radius 格内的空位，用于紧气/长气候选。"""
        candidates: set[tuple[int, int]] = set()
        for x in range(self.size):
            for y in range(self.size):
                if self.grid[x, y] != BLACK:
                    continue
                for dx in range(-radius, radius + 1):
                    for dy in range(-radius, radius + 1):
                        nx, ny = x + dx, y + dy
                        if self.in_bounds(nx, ny) and self.grid[nx, ny] == EMPTY:
                            candidates.add((nx, ny))
        return candidates

    def farthest_empty_positions(self) -> set[tuple[int, int]]:
        """没有黑棋时，选择距离已有棋子尽可能远的空位。"""
        stones = [
            (x, y)
            for x in range(self.size)
            for y in range(self.size)
            if self.grid[x, y] != EMPTY
        ]
        if not stones:
            return {(self.size // 2, self.size // 2)}

        best: set[tuple[int, int]] = set()
        best_dist = -1.0
        center_x = self.size // 2
        center_y = self.size // 2
        for x in range(self.size):
            for y in range(self.size):
                if self.grid[x, y] != EMPTY:
                    continue
                min_dist = min(abs(x - sx) + abs(y - sy) for sx, sy in stones)
                # 距离优先，距离相同时轻微偏向棋盘中央，保持结果稳定。
                value = min_dist - 0.01 * (abs(x - center_x) + abs(y - center_y))
                if value > best_dist:
                    best_dist = value
                    best = {(x, y)}
                elif value == best_dist:
                    best.add((x, y))
        return best

    def farthest_open_positions_from_stones_territory_edge(
        self, exclude_blue: bool = False
    ) -> set[tuple[int, int]]:
        """选择距离棋子、白棋领地、棋盘边缘都尽量远的空位。

        距离采用横竖斜均可走的 Chebyshev 距离：max(|dx|, |dy|)。
        """
        stones = [
            (x, y)
            for x in range(self.size)
            for y in range(self.size)
            if self.grid[x, y] != EMPTY
        ]
        territory = {
            (x, y)
            for x, y in self.get_dead_positions()
            if self.grid[x, y] == EMPTY
        }

        candidates = [
            (x, y)
            for x in range(self.size)
            for y in range(self.size)
            if self.grid[x, y] == EMPTY
        ]
        if exclude_blue:
            blue = self.get_blue_cross_positions(candidates)
            candidates = [pos for pos in candidates if pos not in blue]
        if not candidates:
            return set()

        def chebyshev(pos, target):
            return max(abs(pos[0] - target[0]), abs(pos[1] - target[1]))

        best: set[tuple[int, int]] = set()
        best_dist = -1
        center_x = self.size // 2
        center_y = self.size // 2
        for x, y in candidates:
            d_edge = min(x, y, self.size - 1 - x, self.size - 1 - y)
            d_stone = min(
                (chebyshev((x, y), stone) for stone in stones),
                default=self.size + 1,
            )
            d_territory = min(
                (chebyshev((x, y), cell) for cell in territory),
                default=self.size + 1,
            )
            d = min(d_edge, d_stone, d_territory)
            tie = -0.01 * (abs(x - center_x) + abs(y - center_y))
            value = d + tie
            if value > best_dist:
                best_dist = value
                best = {(x, y)}
            elif value == best_dist:
                    best.add((x, y))
        return best

    def farthest_by_directional_distance(
        self, candidates
    ) -> set[tuple[int, int]]:
        """在候选点中，选择横竖斜 4 个方向上线长最大者。

        每个方向取“该方向两侧到最近阻挡（棋子/白棋领地/边缘）距离的较小值”，
        再取 4 个方向中的最大值作为该点分数。
        """
        blockers = {
            (x, y)
            for x in range(self.size)
            for y in range(self.size)
            if self.grid[x, y] != EMPTY
        }
        blockers |= {
            (x, y)
            for x, y in self.get_dead_positions()
            if self.grid[x, y] == EMPTY
        }

        best: set[tuple[int, int]] = set()
        best_score = -1
        center_x = self.size // 2
        center_y = self.size // 2
        for x, y in candidates:
            direction_scores = []
            for dx, dy in DIRECTIONS:
                forward = 0
                nx, ny = x + dx, y + dy
                while (
                    self.in_bounds(nx, ny)
                    and (nx, ny) not in blockers
                ):
                    forward += 1
                    nx += dx
                    ny += dy
                backward = 0
                nx, ny = x - dx, y - dy
                while (
                    self.in_bounds(nx, ny)
                    and (nx, ny) not in blockers
                ):
                    backward += 1
                    nx -= dx
                    ny -= dy
                direction_scores.append(min(forward, backward))
            score = max(direction_scores)
            tie = -0.01 * (abs(x - center_x) + abs(y - center_y))
            value = score + tie
            if value > best_score:
                best_score = value
                best = {(x, y)}
            elif value == best_score:
                best.add((x, y))
        return best

    def would_self_capture(self, x: int, y: int) -> bool:
        """检查黑棋在 (x, y) 下子后是否自吃 (组无气)."""
        if not self.in_bounds(x, y) or self.grid[x, y] != EMPTY:
            return False
        self.grid[x, y] = BLACK
        _, libs = self.get_group(x, y)
        self.grid[x, y] = EMPTY
        return len(libs) == 0

    def black_move_is_next_capture(self, x: int, y: int) -> bool:
        """黑棋落在 (x, y) 后，若不是连五且只剩一口气，则下一手会被白棋吃。"""
        if not self.in_bounds(x, y) or self.grid[x, y] != EMPTY:
            return False
        self.grid[x, y] = BLACK
        try:
            if self.check_black_five(x, y):
                return False
            _, liberties = self.get_group(x, y)
            return len(liberties) == 1
        finally:
            self.grid[x, y] = EMPTY

    # ---------- 全盘扫描兜底 ----------

    def _capture_all_dead_black(self) -> list[tuple[int, int]]:
        """
        全盘扫描, 移除所有 0 气黑棋组.
        这是兜底机制: 无论 0 气是怎么来的, 都在此清除.
        返回被移除的棋子列表.
        """
        captured: list[tuple[int, int]] = []
        checked: set[tuple[int, int]] = set()
        for x in range(self.size):
            for y in range(self.size):
                if self.grid[x, y] == BLACK and (x, y) not in checked:
                    stones, libs = self.get_group(x, y)
                    checked |= stones
                    if len(libs) == 0:
                        for sx, sy in stones:
                            self.grid[sx, sy] = EMPTY
                            captured.append((sx, sy))
        return captured

    # ---------- 下子 ----------

    def play_black(self, x: int, y: int) -> tuple[bool, list]:
        """
        黑棋下子 (五子棋规则 + 自吃禁止):
          - 自吃禁止优先于一切 (即使能连五也不能自吃)
          - 下完后全盘扫描兜底, 清除任何残留 0 气黑组
        返回 (是否成功, 被吃列表).
        """
        if not self.in_bounds(x, y) or self.grid[x, y] != EMPTY:
            return False, []
        self._invalidate_group_cache()
        self.grid[x, y] = BLACK

        # 1. 自吃检查 (最高优先, 即使能连五也不能自吃)
        _, libs = self.get_group(x, y)
        if len(libs) == 0:
            self.grid[x, y] = EMPTY
            return False, []

        # 2. 5连胜利 (仅在非自吃时)
        if self.check_black_five(x, y):
            extra = self._capture_all_dead_black()
            for sx, sy in extra:
                if (sx, sy) == (x, y):
                    self.grid[x, y] = BLACK
                    extra = [(sx2, sy2) for sx2, sy2 in extra if (sx2, sy2) != (x, y)]
                    break
            if extra:
                self.captured_count[BLACK] += len(extra)
            if self._update_forbidden_blue:
                self._update_blue_cross_after_black()
            self.history.append((BLACK, x, y, extra))
            return True, extra

        # 3. 全盘扫描兜底 (清除任何残留0气黑组)
        extra = self._capture_all_dead_black()
        if extra:
            self.captured_count[BLACK] += len(extra)
        if self._update_forbidden_blue:
            self._update_blue_cross_after_black()
        self.history.append((BLACK, x, y, extra))
        return True, extra

    def play_white(self, x: int, y: int) -> tuple[bool, list]:
        """
        白棋下子 (围棋规则):
          - 任意空位皆可下 (白棋不可被吃, 故允许"无气"着法)
          - 下完后全盘扫描, 移除所有 0 气黑棋组
        """
        if not self.in_bounds(x, y) or self.grid[x, y] != EMPTY:
            return False, []
        self._invalidate_group_cache()
        self.grid[x, y] = WHITE
        captured = self._capture_all_dead_black()
        self.captured_count[WHITE] += len(captured)
        self._update_blue_cross_after_white(x, y)
        self.history.append((WHITE, x, y, captured))
        return True, captured

    def undo(self) -> bool:
        """撤销最后一手."""
        if not self.history:
            return False
        self._invalidate_all_caches()
        last = self.history.pop()
        color, x, y, captured = last
        self.grid[x, y] = EMPTY
        if captured:
            for sx, sy in captured:
                self.grid[sx, sy] = BLACK
            if color == WHITE:
                self.captured_count[WHITE] -= len(captured)
            else:
                self.captured_count[BLACK] -= len(captured)
        return True

    # ---------- 胜负检查 ----------

    def check_black_five(self, x: int, y: int) -> bool:
        """黑棋是否在 (x, y) 处形成正好 5 连 (不含 6+)."""
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
            if run == 5:
                return True
        return False

    def check_black_overline(self, x: int, y: int) -> bool:
        """黑棋是否在 (x, y) 处形成 6+ 连 (长连禁手)."""
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
            if run >= 6:
                return True
        return False

    def white_wins_by_capture(self) -> bool:
        """白棋是否吃光黑棋 (所有黑子被提)."""
        return not np.any(self.grid == BLACK)

    def white_wins_by_occupy(self) -> bool:
        """白棋是否占领整个棋盘 (所有格子都是白棋)."""
        return not np.any(self.grid != WHITE)

    def white_wins_by_line_block(self) -> bool:
        """白棋是否封堵所有可能的 5 连线路.
        即: 每个 5 格窗口 (4 方向) 都至少有 1 个白子或蓝叉阻挡.
        """
        blue = self._get_blue_cross_positions()
        for dx, dy in DIRECTIONS:
            for x in range(self.size):
                for y in range(self.size):
                    end_x = x + 4 * dx
                    end_y = y + 4 * dy
                    if not (0 <= end_x < self.size and 0 <= end_y < self.size):
                        continue
                    blocked = False
                    for i in range(5):
                        cx, cy = x + i * dx, y + i * dy
                        if self.grid[cx, cy] == WHITE or (cx, cy) in blue:
                            blocked = True
                            break
                    if not blocked:
                        return False
        return True

    # ---------- 死位检测 ----------

    def is_dead_position(self, x: int, y: int) -> bool:
        """检查 (x, y) 是否永远无法成为 5 连的一部分.
        即: 所有方向的所有 5 格窗口都有白子或蓝叉 (或窗口超出棋盘),
        或者该位置是自吃 (黑棋下子后组无气, 无法落子).
        """
        blue = self._get_blue_cross_positions()
        if self.grid[x, y] == EMPTY:
            self.grid[x, y] = BLACK
            _, libs = self.get_group(x, y)
            self.grid[x, y] = EMPTY
            if len(libs) == 0:
                return True
        for dx, dy in DIRECTIONS:
            for offset in range(-4, 1):
                cells = [(x + (offset + i) * dx, y + (offset + i) * dy) for i in range(5)]
                valid = all(0 <= cx < self.size and 0 <= cy < self.size for cx, cy in cells)
                if not valid:
                    continue
                blocked = any(
                    self.grid[cx, cy] == WHITE or (cx, cy) in blue
                    for cx, cy in cells
                )
                if not blocked:
                    return False
        return True

    def get_dead_positions(self) -> set[tuple[int, int]]:
        """返回所有空位和黑子中永远无法成为 5 连一部分的位置."""
        dead: set[tuple[int, int]] = set()
        for x in range(self.size):
            for y in range(self.size):
                if self.grid[x, y] in (EMPTY, BLACK):
                    if self.is_dead_position(x, y):
                        dead.add((x, y))
        return dead

    # ---------- 黑棋领地检测 ----------

    def is_black_territory(
        self, x: int, y: int, blue_crosses: set | None = None
    ) -> bool:
        """检查 (x, y) 是否为黑棋领地.
        即: 所有方向的所有 5 格窗口 (含此位) 都至少有 1 个黑子且无白子/蓝叉.
        """
        if blue_crosses is None:
            blue_crosses = self._get_blue_cross_positions()
        for dx, dy in DIRECTIONS:
            for offset in range(-4, 1):
                cells = [(x + (offset + i) * dx, y + (offset + i) * dy) for i in range(5)]
                valid = all(0 <= cx < self.size and 0 <= cy < self.size for cx, cy in cells)
                if not valid:
                    continue
                has_black = False
                blocked = False
                for cx, cy in cells:
                    v = self.grid[cx, cy]
                    if v == BLACK:
                        has_black = True
                    elif v == WHITE or (cx, cy) in blue_crosses:
                        blocked = True
                if not has_black or blocked:
                    return False
        return True

    def get_black_territory(self) -> set[tuple[int, int]]:
        """返回所有空位中属于黑棋领地的位置."""
        blue = self._get_blue_cross_positions()
        territory: set[tuple[int, int]] = set()
        for x in range(self.size):
            for y in range(self.size):
                if self.grid[x, y] == EMPTY and self.is_black_territory(x, y, blue):
                    territory.add((x, y))
        return territory

    # ---------- 威胁检测（新查表法） ----------

    def _get_blue_cross_positions(self) -> set[tuple[int, int]]:
        """返回所有蓝叉位置（禁手、无气位置），这些位置黑棋不能落子，视为阻挡。"""
        if self._blue_cross_cache is not None:
            return self._blue_cross_cache
        self._recompute_blue_cross_caches()
        return self._blue_cross_cache

    def _recompute_blue_cross_caches(self) -> None:
        """全量重建无气/禁手缓存。"""
        import rules

        no_liberty: set[tuple[int, int]] = set()
        forbidden: set[tuple[int, int]] = set()
        for x in range(self.size):
            for y in range(self.size):
                if self.grid[x, y] != EMPTY:
                    continue
                ok, ftype = rules.is_black_legal_move(self, x, y)
                if not ok:
                    if ftype == "self_capture":
                        no_liberty.add((x, y))
                    else:
                        forbidden.add((x, y))
        self._no_liberty_cache = no_liberty
        self._forbidden_cache = forbidden
        self._blue_cross_cache = no_liberty | forbidden

    def _update_blue_cross_after_white(self, x: int, y: int) -> None:
        """白棋落子后更新蓝叉缓存：无气位置只增不减，禁手位置可能减少。"""
        if self._blue_cross_cache is None:
            self._recompute_blue_cross_caches()
            return

        for pos in self.positions_on_lines(x, y, radius=4):
            if self.grid[pos] != EMPTY:
                continue
            if self.would_self_capture(*pos):
                self._no_liberty_cache.add(pos)

        if self._update_forbidden_blue:
            import rules

            forbidden: set[tuple[int, int]] = set()
            for px in range(self.size):
                for py in range(self.size):
                    if self.grid[px, py] != EMPTY:
                        continue
                    ok, ftype = rules.is_black_legal_move(self, px, py)
                    if not ok and ftype != "self_capture":
                        forbidden.add((px, py))
            self._forbidden_cache = forbidden
        self._blue_cross_cache = (
            self._no_liberty_cache | (self._forbidden_cache or set())
        )

    def _update_blue_cross_after_black(self) -> None:
        """黑棋落子后更新蓝叉缓存：无气位置不变，禁手位置可能减少。"""
        if not self._update_forbidden_blue:
            return
        if self._blue_cross_cache is None:
            self._recompute_blue_cross_caches()
            return

        import rules

        forbidden: set[tuple[int, int]] = set()
        for px in range(self.size):
            for py in range(self.size):
                if self.grid[px, py] != EMPTY:
                    continue
                ok, ftype = rules.is_black_legal_move(self, px, py)
                if not ok and ftype != "self_capture":
                    forbidden.add((px, py))
        self._forbidden_cache = forbidden
        self._blue_cross_cache = self._no_liberty_cache | forbidden

    def get_blue_cross_positions(
        self, positions: set[tuple[int, int]] | list[tuple[int, int]] | None = None
    ) -> set[tuple[int, int]]:
        """返回指定位置（或全盘空位）中的蓝叉位置。

        蓝叉指黑棋禁手或落子后自吃的空位；白棋领地与白子/边界一样会在威胁编码中
        视为阻挡，但本方法只关心真正不能落子的空位。
        """
        import rules

        if positions is None:
            positions = [
                (x, y)
                for x in range(self.size)
                for y in range(self.size)
                if self.grid[x, y] == EMPTY
            ]
        blue: set[tuple[int, int]] = set()
        for x, y in positions:
            if not self.in_bounds(x, y) or self.grid[x, y] != EMPTY:
                continue
            ok, _ = rules.is_black_legal_move(self, x, y)
            if not ok:
                blue.add((x, y))
        return blue

    def compute_threats_for_positions(
        self,
        positions,
        blue_crosses: set[tuple[int, int]] | None = None,
    ) -> dict[tuple[int, int], str]:
        """仅对给定位置做威胁分类，避免不必要的全盘重算。"""
        if blue_crosses is None:
            blue_crosses = self.get_blue_cross_positions(positions)
        threats: dict[tuple[int, int], str] = {}
        for x, y in positions:
            if self.grid[x, y] != EMPTY:
                continue
            if (x, y) in blue_crosses:
                continue
            threat = self._classify_empty(x, y, blue_crosses)
            if threat is not None:
                threats[(x, y)] = threat
        return threats

    def get_red_positions(
        self, threats: dict[tuple[int, int], str] | None = None
    ) -> set[tuple[int, int]]:
        """返回所有 GUI 会显示红色标记的合法空位。"""
        if threats is None:
            threats = self.compute_threats()
        return {
            pos
            for pos, threat in threats.items()
            if THREAT_MARKER.get(threat) is not None
        }

    def get_red_scores(
        self, threats: dict[tuple[int, int], str] | None = None
    ) -> dict[tuple[int, int], int]:
        """返回红色空位 -> 基础得分。未显示的 open_one/sleep_one 不计分。"""
        if threats is None:
            threats = self.compute_threats()
        return {
            pos: score
            for pos, threat in threats.items()
            if (score := THREAT_SCORE.get(threat, 0)) > 0
        }

    def compute_threats(self) -> dict[tuple[int, int], str]:
        """
        使用查表法计算所有合法空位的威胁类别。
        返回: {(x,y): threat_type}
        threat_type 包括: five_point, four_three, open_four, rush_four,
                          open_three, sleep_three, open_two, sleep_two,
                          open_one, sleep_one
        """
        blue_crosses = self._get_blue_cross_positions()
        threats: dict[tuple[int, int], str] = {}
        for x in range(self.size):
            for y in range(self.size):
                if self.grid[x, y] != EMPTY:
                    continue
                if (x, y) in blue_crosses:
                    continue  # 蓝叉位置本身不是红色位置
                threat = self._classify_empty(x, y, blue_crosses)
                if threat is not None:
                    threats[(x, y)] = threat
        # 蓝叉位置永远不是红色位置：无法落子，红色位置得分一并清除。
        threats = {
            pos: threat
            for pos, threat in threats.items()
            if pos not in blue_crosses
        }
        return threats

    def _classify_empty(self, x: int, y: int, blue_crosses: set) -> str | None:
        """在(x,y)临时落黑子，判断形成的最高威胁（含四三组合）"""
        self.grid[x, y] = BLACK
        try:
            if self._has_five(x, y):
                return "five_point"

            # 红色位置计算必须考虑落子后新产生的禁手/无气：
            # 把这些位置也编码为阻挡，避免把“落子后只剩蓝叉”的空位当威胁。
            line_positions = self.positions_on_lines(x, y, radius=4)
            black_near = sum(
                self.in_bounds(*pos) and self.grid[pos] == BLACK
                for pos in line_positions
            )
            if black_near >= 4:
                local_blue = self.get_blue_cross_positions(line_positions)
                blue_crosses = blue_crosses | local_blue

            line_threats = [
                threat for _, _, threat in self._line_threats_at(x, y, blue_crosses)
            ]

            if not line_threats:
                return None

            # 四三组合：至少一条四类（活四/冲四）和一条活三
            high = {"open_four", "rush_four", "open_three"}
            high_lines = [t for t in line_threats if t in high]
            if len(high_lines) >= 2:
                has_four = any(t in ("open_four", "rush_four") for t in high_lines)
                has_three = any(t == "open_three" for t in high_lines)
                if has_four and has_three:
                    return "four_three"

            # 返回最高单线威胁
            return min(line_threats, key=lambda t: THREAT_ORDER.get(t, 99))
        finally:
            self.grid[x, y] = EMPTY

    def _line_threats_at(
        self, x: int, y: int, blue_crosses: set
    ) -> list[tuple[int, int, str]]:
        """返回临时落子后每个方向形成的最高威胁。

        调用前必须已将 grid[x][y] 临时置为 BLACK。
        """
        result: list[tuple[int, int, str]] = []
        for dx, dy in DIRECTIONS:
            threat = self._match_line(x, y, dx, dy, blue_crosses)
            if threat is not None:
                result.append((dx, dy, threat))
        return result

    def _match_line(self, x: int, y: int, dx: int, dy: int, blue_crosses: set) -> str | None:
        """提取以(x,y)为中心的9格编码，滑动窗口匹配查表模式"""
        R = 4
        chars = []
        for step in range(1, R + 1):
            nx, ny = x - dx * step, y - dy * step
            chars.append(self._cell_code(nx, ny, blue_crosses))
        chars.reverse()
        chars.append('1')  # 落子位置已经是黑
        for step in range(1, R + 1):
            nx, ny = x + dx * step, y + dy * step
            chars.append(self._cell_code(nx, ny, blue_crosses))
        s = ''.join(chars)

        best = None
        best_priority = 999
        for threat_type, pattern_list in PATTERNS.items():
            for pattern in pattern_list:
                rev = pattern[::-1]
                L = len(pattern)
                for i in range(len(s) - L + 1):
                    window = s[i:i + L]
                    if window == pattern or window == rev:
                        prio = THREAT_ORDER.get(threat_type, 99)
                        if prio < best_priority:
                            best_priority = prio
                            best = threat_type
        if (
            best in ("rush_four", "open_three")
            and s.count('1') >= 5
            and not self._line_has_legal_five_window(s)
        ):
            return None
        return best

    def _line_has_legal_five_window(self, s: str) -> bool:
        """9 格编码串中是否存在一个 5 格窗口，黑棋填满后正好 5 连且不超长连。"""
        for start in range(len(s) - 4):
            window = s[start:start + 5]
            if '2' in window:
                continue
            test = list(s)
            for i in range(start, start + 5):
                if test[i] == '0':
                    test[i] = '1'
            max_run = 0
            cur = 0
            for ch in test:
                if ch == '1':
                    cur += 1
                    max_run = max(max_run, cur)
                else:
                    cur = 0
            if max_run == 5:
                return True
        return False

    def _cell_code(self, x: int, y: int, blue_crosses: set) -> str:
        """将棋盘格点编码为字符: '1'=黑, '0'=空, '2'=蓝叉/白棋/边界"""
        if not self.in_bounds(x, y):
            return '2'
        val = self.grid[x, y]
        if val == BLACK:
            return '1'
        if val == WHITE:
            return '2'
        # EMPTY
        if (x, y) in blue_crosses:
            return '2'  # 蓝叉视为阻挡
        return '0'

    def _has_five(self, x: int, y: int) -> bool:
        """检查临时落子后是否形成连五（≥5）"""
        for dx, dy in DIRECTIONS:
            cnt = 1
            tx, ty = x + dx, y + dy
            while self.in_bounds(tx, ty) and self.grid[tx, ty] == BLACK:
                cnt += 1
                tx += dx
                ty += dy
            tx, ty = x - dx, y - dy
            while self.in_bounds(tx, ty) and self.grid[tx, ty] == BLACK:
                cnt += 1
                tx -= dx
                ty -= dy
            if cnt >= 5:
                return True
        return False

    def find_black_threats(self) -> dict[tuple[int, int], str]:
        """兼容旧接口：返回所有红色位置及威胁类别（新查表法）"""
        return self.compute_threats()

    # ---------- 黑棋块计分与局部增量评估 ----------

    def _red_score_total(
        self,
        positions,
        red_scores: dict[tuple[int, int], int] | None = None,
    ) -> float:
        """计算一组空位的红色位置得分总和。

        传入 red_scores 时直接引用已算好的全局红色得分；否则只对给定位置做局部威胁计算。
        """
        positions = set(positions)
        if red_scores is None:
            blue_crosses = self.get_blue_cross_positions(positions)
            threats = self.compute_threats_for_positions(positions, blue_crosses)
            red_scores = self.get_red_scores(threats)

        total = 0.0
        for x, y in positions:
            if self.grid[x, y] == EMPTY:
                total += red_scores.get((x, y), 0.0)
        return total

    def compute_group_capture_loss(
        self,
        stones,
        red_scores: dict[tuple[int, int], int] | None = None,
    ) -> float:
        """计算某黑棋块立即消失时失去的红色位置得分 A。

        只重算该黑棋块周围半径 4 格内的空位，且不计算领地变化。
        黑棋块是最大正交连通块，移除它不会递归带走其它黑棋块。
        """
        stones = set(stones)
        if not stones:
            return 0.0

        affected = self.affected_positions_around(stones, radius=4)
        old_total = self._red_score_total(affected, red_scores=red_scores)

        saved = {pos: self.grid[pos] for pos in stones}
        for pos in stones:
            self.grid[pos] = EMPTY
        try:
            new_total = self._red_score_total(affected, red_scores=None)
        finally:
            for pos, value in saved.items():
                self.grid[pos] = value

        # A 是“消失后失去的分数”，若移除后反而不损失，则按 0 计。
        return max(0.0, old_total - new_total)

    def compute_group_score(
        self,
        stones,
        liberties=None,
        red_scores: dict[tuple[int, int], int] | None = None,
    ) -> float:
        """计算黑棋块价值：A * (1 - 1 / 2^n)，n 为气数。"""
        stones = set(stones)
        if not stones:
            return 0.0
        if liberties is None:
            _, liberties = self.get_group(next(iter(stones)))
        n = len(liberties)
        if n <= 0:
            return 0.0
        a_value = self.compute_group_capture_loss(stones, red_scores=red_scores)
        return a_value * (1.0 - 0.5 ** n)

    def compute_all_group_scores(
        self, red_scores: dict[tuple[int, int], int] | None = None
    ) -> dict[tuple[tuple[int, int], ...], float]:
        """计算并缓存式返回所有黑棋块得分，供候选点增量相减。"""
        return {
            group_key(stones): self.compute_group_score(
                stones, liberties, red_scores=red_scores
            )
            for stones, liberties in self.get_black_groups()
        }

    def evaluate_black_move_delta(
        self,
        x: int,
        y: int,
        old_group_scores: dict | None = None,
        red_scores: dict[tuple[int, int], int] | None = None,
    ) -> float:
        """计算黑棋落在 (x, y) 后的净得分增量。

        相邻黑棋块落子后会合并成一块，因此：
            delta = 新合并块得分 - 上一步相邻黑棋块得分之和。
        """
        if not self.in_bounds(x, y) or self.grid[x, y] != EMPTY:
            return -float("inf")

        import rules

        ok, _ = rules.is_black_legal_move(self, x, y)
        if not ok:
            return -float("inf")

        old_groups = self.get_adjacent_black_groups(x, y)
        old_sum = 0.0
        for stones, liberties in old_groups:
            key = group_key(stones)
            if old_group_scores is not None and key in old_group_scores:
                old_sum += old_group_scores[key]
            else:
                old_sum += self.compute_group_score(
                    stones, liberties, red_scores=red_scores
                )

        board_after = self.copy()
        ok_after, _ = board_after.play_black(x, y)
        if not ok_after:
            return -float("inf")

        merged_stones, merged_liberties = board_after.get_group(x, y)
        new_score = board_after.compute_group_score(merged_stones, merged_liberties)
        return new_score - old_sum

    def evaluate_white_move_delta(
        self,
        x: int,
        y: int,
        old_group_scores: dict | None = None,
        red_scores: dict[tuple[int, int], int] | None = None,
    ) -> float:
        """计算白棋落在 (x, y) 后的黑棋局面价值增量。

        白棋不会生成新黑棋块，但可能阻挡威胁、减少相邻黑棋块气，或直接吃掉
        黑棋块。只重算落子点直线半径 4 格内受影响的黑棋块。
        """
        if not self.in_bounds(x, y) or self.grid[x, y] != EMPTY:
            return -float("inf")

        affected = self.positions_on_lines(x, y, radius=4)
        affected_groups: list[tuple[set[tuple[int, int]], set[tuple[int, int]]]] = []
        seen: set[tuple[int, int]] = set()
        for ax, ay in affected:
            if self.grid[ax, ay] != BLACK or (ax, ay) in seen:
                continue
            stones, liberties = self.get_group(ax, ay)
            seen |= stones
            affected_groups.append((stones, liberties))

        old_sum = 0.0
        for stones, liberties in affected_groups:
            key = group_key(stones)
            if old_group_scores is not None and key in old_group_scores:
                old_sum += old_group_scores[key]
            else:
                old_sum += self.compute_group_score(
                    stones, liberties, red_scores=red_scores
                )

        board_after = self.copy()
        ok_after, _ = board_after.play_white(x, y)
        if not ok_after:
            return -float("inf")

        new_sum = 0.0
        for stones, _liberties in affected_groups:
            first = next(iter(stones))
            if board_after.grid[first] != BLACK:
                continue
            stones_after, liberties_after = board_after.get_group(*first)
            new_sum += board_after.compute_group_score(stones_after, liberties_after)

        return new_sum - old_sum

    def black_position_value(
        self, red_scores: dict[tuple[int, int], int] | None = None
    ) -> float:
        """从黑棋视角计算当前局面静态价值。

        价值 = 所有黑棋块得分之和 - 白棋领地数。白棋领地数在候选生成中通常
        保持常量，但保留它是为了对齐原始计分规则。
        """
        group_total = sum(self.compute_all_group_scores(red_scores=red_scores).values())
        territory = {
            (x, y)
            for x, y in self.get_dead_positions()
            if self.grid[x, y] == EMPTY
        }
        territory |= {
            (x, y)
            for x, y in self.get_black_territory()
            if self.grid[x, y] == EMPTY
        }
        return group_total - len(territory)

    # ---------- 黑棋候选与三角形攻势安全 ----------

    def get_black_candidate_moves(
        self, threats: dict[tuple[int, int], str] | None = None
    ) -> list[tuple[int, int]]:
        """生成候选落子点，排除蓝叉和白色领地。

        优先级：有红色位置时 = 红色位置 + 黑棋旁空位；否则 = 黑棋旁空位；
        再否则 = 远离棋子的空位。
        """
        if not np.any(self.grid != EMPTY):
            return [(self.size // 2, self.size // 2)]

        if threats is None:
            threats = self.compute_threats()

        red_positions = self.get_red_positions(threats)
        adjacent = self.adjacent_empty_to_black(radius=1)

        if red_positions:
            candidates = red_positions | adjacent
        elif adjacent:
            candidates = set(adjacent)
        else:
            candidates = self.farthest_empty_positions()

        dead = self.get_dead_positions()
        legal: list[tuple[int, int]] = []
        import rules

        for x, y in candidates:
            if self.grid[x, y] != EMPTY or (x, y) in dead:
                continue
            ok, _ = rules.is_black_legal_move(self, x, y)
            if ok and not self.black_move_is_next_capture(x, y):
                legal.append((x, y))
        return sorted(legal)

    def get_white_candidate_moves(
        self, threats: dict[tuple[int, int], str] | None = None
    ) -> list[tuple[int, int]]:
        """生成白棋候选落子点。

        有红色位置时 = 红色位置 + 黑棋旁空位；无红色位置时 = 黑棋旁空位；
        无黑棋时 = 远离棋子的空位。蓝叉和白色领地不思考。
        """
        if not np.any(self.grid != EMPTY):
            return [(self.size // 2, self.size // 2)]

        if threats is None:
            threats = self.compute_threats()

        red_positions = self.get_red_positions(threats)
        adjacent = self.adjacent_empty_to_black(radius=1)

        if red_positions:
            candidates = red_positions | adjacent
        elif adjacent:
            candidates = set(adjacent)
        else:
            candidates = self.farthest_empty_positions()

        dead = self.get_dead_positions()
        legal: list[tuple[int, int]] = []
        for x, y in candidates:
            if self.grid[x, y] != EMPTY or (x, y) in dead:
                continue
            legal.append((x, y))

        # 白棋可以搜索禁手位置，但排除黑棋落子后无气的位置。
        return sorted(pos for pos in legal if not self.would_self_capture(*pos))

    def get_white_blocking_candidates(
        self, threats: dict[tuple[int, int], str] | None = None
    ) -> list[tuple[int, int]]:
        """生成可用来挡住或吃掉实心圆/三角形攻势的白棋候选点。"""
        if threats is None:
            threats = self.compute_threats()

        forced = [
            pos for pos, threat in threats.items() if threat in FORCED_THREAT_TYPES
        ]
        candidates: set[tuple[int, int]] = set(forced)

        for tx, ty in forced:
            # 当前局面中组成攻势的黑棋块：只剩一气时，把那一口气加入候选。
            line_positions = self.positions_on_lines(tx, ty, radius=4)
            seen: set[tuple[int, int]] = set()
            for ax, ay in line_positions:
                if self.grid[ax, ay] != BLACK or (ax, ay) in seen:
                    continue
                stones, liberties = self.get_group(ax, ay)
                seen |= stones
                if len(liberties) == 1:
                    candidates.add(next(iter(liberties)))

            # 黑棋实际落下后形成的攻势块：也只加入只剩一气的块的气。
            board_after = self.copy()
            ok_after, _ = board_after.play_black(tx, ty)
            if not ok_after:
                continue
            for stones, liberties in board_after._attack_groups_after_move(tx, ty):
                if len(liberties) == 1:
                    candidates.add(next(iter(liberties)))

        dead = self.get_dead_positions()
        legal: list[tuple[int, int]] = []
        for x, y in candidates:
            if self.grid[x, y] != EMPTY or (x, y) in dead:
                continue
            legal.append((x, y))

        return sorted(pos for pos in legal if not self.would_self_capture(*pos))

    def white_move_eliminates_forced_threats(
        self, x: int, y: int
    ) -> bool:
        """判断白棋下在 (x, y) 后，是否能消除所有实心圆和三角形。"""
        if not self.in_bounds(x, y) or self.grid[x, y] != EMPTY:
            return False
        board_after = self.copy()
        ok_after, _ = board_after.play_white(x, y)
        if not ok_after:
            return False
        threats_after = board_after.compute_threats()
        return all(
            threat not in FORCED_THREAT_TYPES
            for threat in threats_after.values()
        )

    def _attack_groups_after_move(
        self, x: int, y: int
    ) -> list[tuple[set[tuple[int, int]], set[tuple[int, int]]]]:
        """在已经落下 (x, y) 黑子的棋盘上，找出参与四/三攻势的黑棋块。"""
        line_positions = self.positions_on_lines(x, y, radius=4)
        blue_crosses = self.get_blue_cross_positions(line_positions)
        line_threats = self._line_threats_at(x, y, blue_crosses)

        attack_types = {"open_four", "rush_four", "open_three", "five_point"}
        attack_cells: set[tuple[int, int]] = set()
        for dx, dy, threat in line_threats:
            if threat not in attack_types:
                continue
            for step in range(-4, 5):
                nx, ny = x + dx * step, y + dy * step
                if self.in_bounds(nx, ny) and self.grid[nx, ny] == BLACK:
                    attack_cells.add((nx, ny))

        groups: list[tuple[set[tuple[int, int]], set[tuple[int, int]]]] = []
        seen: set[tuple[int, int]] = set()
        for ax, ay in attack_cells:
            if (ax, ay) in seen:
                continue
            stones, liberties = self.get_group(ax, ay)
            seen |= stones
            groups.append((stones, liberties))
        return groups

    def triangle_move_survives_capture(self, x: int, y: int) -> bool:
        """判断一个三角形候选点是否会因白棋下一手吃棋而失去胜势。"""
        if not self.in_bounds(x, y) or self.grid[x, y] != EMPTY:
            return False

        import rules

        ok, _ = rules.is_black_legal_move(self, x, y)
        if not ok:
            return False

        board_after = self.copy()
        ok_after, _ = board_after.play_black(x, y)
        if not ok_after:
            return False
        if board_after.check_black_five(x, y):
            return True

        attack_groups = board_after._attack_groups_after_move(x, y)
        vulnerable = [
            (stones, next(iter(liberties)))
            for stones, liberties in attack_groups
            if len(liberties) == 1
        ]
        if not vulnerable:
            return True

        for _stones, white_pos in vulnerable:
            board_test = board_after.copy()
            ok_white, _ = board_test.play_white(*white_pos)
            if not ok_white:
                continue
            threats_after_capture = board_test.compute_threats()
            still_winning = any(
                threat in ("five_point", "four_three", "open_four")
                for threat in threats_after_capture.values()
            )
            if not still_winning:
                return False
        return True

    def get_dead_black_stones(self) -> set[tuple[int, int]]:
        """返回所有在死位的黑棋 (无法参与连五的黑子)."""
        dead: set[tuple[int, int]] = set()
        for x in range(self.size):
            for y in range(self.size):
                if self.grid[x, y] == BLACK and self.is_dead_position(x, y):
                    dead.add((x, y))
        return dead

    def find_blocking_moves(self) -> tuple[list[tuple[int, int]], bool]:
        """找出白棋可阻断所有黑棋"连五威胁"的着法.
        返回 (阻断着法列表, 黑是否必胜).
        """
        threats = self.compute_threats()
        five_points = {pos for pos, t in threats.items() if t == "five_point"}
        if not five_points:
            return [], False

        blocking: list[tuple[int, int]] = []
        for x in range(self.size):
            for y in range(self.size):
                if self.grid[x, y] != EMPTY:
                    continue
                # 模拟白下此处
                self.grid[x, y] = WHITE
                still_threat = False
                for (tx, ty) in five_points:
                    if (tx, ty) == (x, y):
                        continue  # 白占了黑要下的位
                    # 检查黑下 (tx,ty) 是否仍能连五
                    self.grid[tx, ty] = BLACK
                    if self.check_black_five(tx, ty):
                        still_threat = True
                    self.grid[tx, ty] = EMPTY
                    if still_threat:
                        break
                self.grid[x, y] = EMPTY
                if not still_threat:
                    blocking.append((x, y))
        black_wins = len(blocking) == 0
        return blocking, black_wins

    # ---------- 未封堵线路 ----------

    def get_unblocked_lines(self) -> list[list[tuple[int, int]]]:
        """返回所有没有白子/蓝叉的 5 格窗口 (用于红线显示)."""
        blue = self._get_blue_cross_positions()
        lines: list[list[tuple[int, int]]] = []
        for dx, dy in DIRECTIONS:
            for x in range(self.size):
                for y in range(self.size):
                    end_x = x + 4 * dx
                    end_y = y + 4 * dy
                    if not (0 <= end_x < self.size and 0 <= end_y < self.size):
                        continue
                    blocked = False
                    cells = [(x + i * dx, y + i * dy) for i in range(5)]
                    for cx, cy in cells:
                        if self.grid[cx, cy] == WHITE or (cx, cy) in blue:
                            blocked = True
                            break
                    if not blocked:
                        lines.append(cells)
        return lines

    # ---------- 手数追踪 ----------

    def get_move_numbers(self) -> dict[tuple[int, int], int]:
        move_numbers: dict[tuple[int, int], int] = {}
        for i, (color, x, y, captured) in enumerate(self.history):
            move_num = i + 1
            move_numbers[(x, y)] = move_num
            if captured:
                for cx, cy in captured:
                    move_numbers.pop((cx, cy), None)
        return move_numbers

    def black_stone_count(self) -> int:
        return int(np.sum(self.grid == BLACK))

    def white_stone_count(self) -> int:
        return int(np.sum(self.grid == WHITE))

    def empty_count(self) -> int:
        return int(np.sum(self.grid == EMPTY))

    def __repr__(self) -> str:
        return f"<HybridBoard {self.size}x{self.size} black={self.black_stone_count()} white={self.white_stone_count()}>"
