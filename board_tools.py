# -*- coding: utf-8 -*-
"""Board dump / analysis tool (for reporting positions and testing rules).

Usage:
    python board_tools.py board_dump.txt
    python board_tools.py board_dump.txt --ai black --depth 2
    python board_tools.py board_dump.txt --torus

The file is the text produced by the GUI "导出棋盘(复制)" button (or any rows
using 1=black, 2=white, 0=empty, X=obstacle, and letters such as A for empty
points you want to test by name).
"""
from __future__ import annotations

import sys

from board import HybridBoard, BLACK, WHITE, EMPTY, OBSTACLE

MARKERS = {
    "five_point": "solid-circle",
    "four_three": "triangle",
    "open_four": "triangle",
    "rush_four": "large-circle",
    "open_three": "large-circle",
    "sleep_three": "small-circle",
    "open_two": "small-circle",
    "sleep_two": "red-dot",
}


def load_board(path, torus=False):
    """Parse a dump file into a HybridBoard.  Returns (board, named_points)."""
    rows = []
    named = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\r\n")
            if not line or line.startswith("#"):
                continue
            rows.append(line)
    if not rows:
        raise SystemExit("no board rows found in " + path)
    size = max(len(r) for r in rows)
    board = HybridBoard(max(size, len(rows)))
    board.torus = torus
    r0 = (board.size - len(rows)) // 2
    c0 = (board.size - size) // 2
    for i, row in enumerate(rows):
        for j, ch in enumerate(row):
            up = ch.upper()
            x, y = r0 + i, c0 + j
            if up == "1":
                board.grid[x, y] = BLACK
            elif up == "2":
                board.grid[x, y] = WHITE
            elif up == "X":
                board.grid[x, y] = OBSTACLE
            elif up.isalpha():
                named[up] = (x, y)
    board._invalidate_caches()
    return board, named


def render(board):
    chars = {EMPTY: ".", BLACK: "1", WHITE: "2", OBSTACLE: "X"}
    return chr(10).join("".join(chars[int(board.grid[x, y])]
                                for y in range(board.size))
                        for x in range(board.size))


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    path = argv[0]
    torus = "--torus" in argv
    board, named = load_board(path, torus=torus)

    print("board (size=%d torus=%s):" % (board.size, board.torus))
    print(render(board))
    threats = board.compute_threats()
    hollow = board.get_hollow_triangles(threats)
    print()
    print("threats:")
    for pos, threat in sorted(threats.items()):
        extra = " (hollow)" if pos in hollow else ""
        print("  %s %s%s" % (pos, MARKERS.get(threat, threat), extra))
    print()
    print("blue crosses (forbidden / self-capture):",
          sorted(board.get_blue_cross_positions()))
    print()
    print("foul check for every empty point / named letter:")
    for x in range(board.size):
        for y in range(board.size):
            if not board.is_empty(x, y):
                continue
            ok, ftype = __import__("rules").is_black_legal_move(board, x, y)
            if not ok and ftype in ("three_three", "four_four", "overline"):
                print("  (%d,%d) -> %s" % (x, y, ftype))
    for name, pos in sorted(named.items()):
        ok, ftype = __import__("rules").is_black_legal_move(board, *pos)
        print("  %s %s -> ok=%s foul=%s" % (name, pos, ok, ftype))

    if "--ai" in argv:
        idx = argv.index("--ai")
        side = argv[idx + 1] if idx + 1 < len(argv) else "black"
        depth = 2
        if "--depth" in argv:
            depth = int(argv[argv.index("--depth") + 1])
        if side.startswith("w"):
            import ai_white
            move = ai_white.best_white_move(board, max_depth=depth)
        else:
            import ai_black
            move = ai_black.best_black_move(board, max_depth=depth)
        print()
        print("%s AI move (depth %d): %s" % (side, depth, move))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
