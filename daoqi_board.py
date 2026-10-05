"""daoqi_board.py - standalone torus Go (daoqi) board, pure Go rules.

道棋 = 围棋下在 n×n 环面上：四个方向的邻居都按取模回绕，黑白双方一样。
本模块只实现纯围棋规则，与本项目其他任何文件零依赖：

- 双方都可以提对方无气的棋块（回绕感知的泛洪填充）
- 禁自杀（落子后己块无气）
- 全局禁同形（positional superko）：一手棋不得复现任何出现过的盘面，
  自然涵盖简单劫与三劫循环等所有打劫循环
- 虚手（pass）：连续两次虚手对局结束
- 悔棋（undo）：完整还原盘面、提子数、同形集
- 数子：中国规则式区域计分（棋子 + 仅由一色包围的空点，回绕感知），
  不做死子判断——终局精确评估交给 KataGo 的 ownership

鸭子类型接口（供 katago_client 使用）：``size``（int）与 ``grid``
（二维可索引，值 0 空 / 1 黑 / 2 白）。
"""

from __future__ import annotations

import numpy as np

EMPTY, BLACK, WHITE = 0, 1, 2
NEIGHBOURS = ((1, 0), (-1, 0), (0, 1), (0, -1))


class IllegalMove(Exception):
    """A rejected move; str(exc) is a short reason (occupied/suicide/superko)."""


class DaoqiBoard:
    """Torus Go board: grid[x, y] int8, 0 empty / 1 black / 2 white."""

    def __init__(self, size: int):
        self.size = int(size)
        self.grid = np.zeros((self.size, self.size), dtype=np.int8)
        self.turn = BLACK
        # ("move", color, x, y, captured, key) 或 ("pass", color)
        self.history: list = []
        self.positions: set = {self._key()}   # positional-superko set
        self.passes = 0
        self.captured_by = {BLACK: 0, WHITE: 0}

    # ------------------------------------------------------------------
    # 基础
    # ------------------------------------------------------------------
    def _key(self) -> bytes:
        """Positional-superko key: the stone arrangement only."""
        return self.grid.tobytes()

    def _wrap(self, x, y):
        return x % self.size, y % self.size

    def is_empty(self, x, y) -> bool:
        return self.grid[x % self.size, y % self.size] == EMPTY

    @property
    def is_over(self) -> bool:
        return self.passes >= 2

    @property
    def last_move(self):
        """(x, y) of the last stone, or None after a pass / empty history."""
        if not self.history:
            return None
        entry = self.history[-1]
        return None if entry[0] == "pass" else (entry[2], entry[3])

    def move_numbers(self) -> dict:
        """{(x, y): 手数}，被提掉的子从显示中移除。"""
        out = {}
        for i, entry in enumerate(self.history, start=1):
            if entry[0] == "pass":
                continue
            _, color, x, y, captured, _key = entry
            for cx, cy in captured:
                out.pop((cx, cy), None)
            out[(x, y)] = i
        return out

    # ------------------------------------------------------------------
    # 棋块与气（回绕感知）
    # ------------------------------------------------------------------
    def _group(self, grid, x, y):
        """(stones set, liberties set) of the group at (x, y) on `grid`."""
        color = int(grid[x, y])
        stones = {(x, y)}
        libs = set()
        stack = [(x, y)]
        while stack:
            cx, cy = stack.pop()
            for dx, dy in NEIGHBOURS:
                nx, ny = self._wrap(cx + dx, cy + dy)
                v = int(grid[nx, ny])
                if v == EMPTY:
                    libs.add((nx, ny))
                elif v == color and (nx, ny) not in stones:
                    stones.add((nx, ny))
                    stack.append((nx, ny))
        return stones, libs

    # ------------------------------------------------------------------
    # 落子合法性 / 提子
    # ------------------------------------------------------------------
    def _captures_for(self, grid, x, y, color):
        """Zero-liberty opponent groups adjacent to (x, y) after placing
        `color` there (grid already has the stone).  Returns [(stones)]."""
        opponent = WHITE if color == BLACK else BLACK
        captured = []
        seen = set()
        for dx, dy in NEIGHBOURS:
            nx, ny = self._wrap(x + dx, y + dy)
            if int(grid[nx, ny]) != opponent or (nx, ny) in seen:
                continue
            stones, libs = self._group(grid, nx, ny)
            seen |= stones
            if not libs:
                captured.append(stones)
        return captured

    def try_move(self, x, y, color):
        """Validate (x, y) for `color` without committing.

        Returns (True, reason "") or (False, short reason).  Checks: empty
        point, not suicide (after wrap-aware captures), positional superko.
        """
        x, y = self._wrap(int(x), int(y))
        if self.grid[x, y] != EMPTY:
            return False, "occupied"
        trial = self.grid.copy()
        trial[x, y] = color
        for stones in self._captures_for(trial, x, y, color):
            for sx, sy in stones:
                trial[sx, sy] = EMPTY
        _, libs = self._group(trial, x, y)
        if not libs:
            return False, "suicide"
        if trial.tobytes() in self.positions:
            return False, "superko"
        return True, ""

    def play(self, x, y, color=None):
        """Commit a stone; raises IllegalMove on any rule violation."""
        color = self.turn if color is None else color
        x, y = self._wrap(int(x), int(y))
        ok, reason = self.try_move(x, y, color)
        if not ok:
            raise IllegalMove(reason)
        trial = self.grid.copy()
        trial[x, y] = color
        captured = []
        for stones in self._captures_for(trial, x, y, color):
            captured.extend(stones)
            for sx, sy in stones:
                self.grid[sx, sy] = EMPTY
        self.grid[x, y] = color
        self.captured_by[color] += len(captured)
        key = self._key()
        self.positions.add(key)
        self.history.append(("move", color, x, y, captured, key))
        self.passes = 0
        self.turn = WHITE if color == BLACK else BLACK
        return captured

    def pass_move(self, color=None):
        color = self.turn if color is None else color
        self.history.append(("pass", color))
        self.passes += 1
        self.turn = WHITE if color == BLACK else BLACK

    def undo(self) -> bool:
        """Take back the last move or pass (False when history is empty)."""
        if not self.history:
            return False
        entry = self.history.pop()
        if entry[0] == "pass":
            self.passes = max(0, self.passes - 1)
        else:
            _, color, x, y, captured, key = entry
            self.grid[x, y] = EMPTY
            for sx, sy in captured:
                self.grid[sx, sy] = color
            self.captured_by[color] -= len(captured)
            self.positions.discard(key)
            self.passes = 0
        self.turn = entry[1]
        return True

    # ------------------------------------------------------------------
    # 数目（朴素区域法，回绕感知；终局精确值以 KataGo ownership 为准）
    # ------------------------------------------------------------------
    def area_score(self, komi: float):
        """(black_area, white_area): stones + singly-bordered empty regions.

        Empty regions touching both colors count for nobody (dame).  Dead
        stones are NOT removed - this is the naive fallback score; the GUI
        shows KataGo's ownership-based scoreLead as the authoritative
        evaluation."""
        black = int((self.grid == BLACK).sum())
        white = int((self.grid == WHITE).sum())
        seen = set()
        for x in range(self.size):
            for y in range(self.size):
                if self.grid[x, y] != EMPTY or (x, y) in seen:
                    continue
                region = {(x, y)}
                stack = [(x, y)]
                borders = set()
                while stack:
                    cx, cy = stack.pop()
                    for dx, dy in NEIGHBOURS:
                        nx, ny = self._wrap(cx + dx, cy + dy)
                        v = int(self.grid[nx, ny])
                        if v == EMPTY:
                            if (nx, ny) not in region:
                                region.add((nx, ny))
                                stack.append((nx, ny))
                        else:
                            borders.add(v)
                seen |= region
                if borders == {BLACK}:
                    black += len(region)
                elif borders == {WHITE}:
                    white += len(region)
        return black, white + komi

    def result_text(self, komi: float) -> str:
        """Naive area result, e.g. "黑 89 : 白 84.5，黑胜 4.5 目"."""
        black, white = self.area_score(komi)
        diff = black - white
        if diff > 0:
            return f"黑 {black:g} : 白 {white:g}，黑胜 {diff:g} 目"
        if diff < 0:
            return f"黑 {black:g} : 白 {white:g}，白胜 {-diff:g} 目"
        return f"黑 {black:g} : 白 {white:g}，和棋"
