# -*- coding: utf-8 -*-
"""Board code / dump tools (reporting positions, import, analysis).

Coordinate code (one token per move, colours alternate from the first player):
    letter = column, a..  (left to right)
    number = row counted from the bottom, 1..size  (Renju style)
    so on 15x15 the centre is "h8"; a pass is "p0".

Export format (produced by the GUI "导出棋盘(复制)" / G key):
    # header lines (size, torus, first, forbid settings, obstacles)
    moves: a15 b14 p0 c13 ...
    <size rows of 0/1/2>   (2 = white, obstacle or no-liberty point)

Usage:
    python board_tools.py board_dump.txt
    python board_tools.py board_dump.txt --ai black --depth 2
    python board_tools.py --code "h8 h7 g7 p0" --size 15
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

PASS_CODE = "p0"


def coord_to_code(x: int, y: int, size: int) -> str:
    """(row, col) -> Renju-style code, e.g. (0, 0) on 15x15 -> "a15"."""
    return "%s%d" % (chr(ord("a") + int(y)), int(size) - int(x))


def code_to_coord(code: str, size: int):
    """Code -> (row, col); returns None for a pass token."""
    token = code.strip().lower()
    if token in (PASS_CODE, "pass", "p", "p0"):
        return None
    if len(token) < 2 or not token[0].isalpha() or not token[1:].isdigit():
        raise ValueError("bad move code: " + code)
    y = ord(token[0]) - ord("a")
    number = int(token[1:])
    x = int(size) - number
    if not (0 <= x < size and 0 <= y < size):
        raise ValueError("move code out of board: " + code)
    return x, y


def moves_from_board(board, pass_records=None) -> list:
    """Move codes for the board history, with passes interleaved.

    pass_records holds the number of stones played at the moment of each
    pass (so it can be interleaved back into the move list).
    """
    size = board.size
    passes = sorted(pass_records or [])
    codes = []
    pi = 0
    for i, (_color, x, y, _captured) in enumerate(board.history):
        while pi < len(passes) and passes[pi] <= i:
            codes.append(PASS_CODE)
            pi += 1
        codes.append(coord_to_code(x, y, size))
    while pi < len(passes):
        codes.append(PASS_CODE)
        pi += 1
    return codes


def _parse_obstacles(text: str):
    out = []
    i = 0
    while True:
        a = text.find("(", i)
        if a < 0:
            break
        b = text.find(")", a)
        if b < 0:
            break
        try:
            x, y = [int(t) for t in text[a + 1:b].split(",")]
            out.append((x, y))
        except Exception:
            pass
        i = b + 1
    return out


def board_to_text(board, pass_records=None, moves=None,
                  first: str = "black") -> str:
    """Full dump text: header + move code + board rows."""
    if moves is None:
        moves = moves_from_board(board, pass_records)
    obstacles = sorted(board.obstacle_positions())
    no_liberty = board.get_no_liberty_positions()
    lines = [
        "# Gomoku-vs-Go board dump",
        "# size=%d torus=%d first=%s" % (board.size, int(board.torus), first),
        "# forbid: overline=%d four_four=%d three_three=%d" % (
            int(board._forbid_overline), int(board._forbid_44),
            int(board._forbid_33)),
        "# obstacles=" + ",".join("(%d,%d)" % p for p in obstacles),
        "moves: " + " ".join(moves),
    ]
    for x in range(board.size):
        row = []
        for y in range(board.size):
            value = int(board.grid[x, y])
            if value == BLACK:
                row.append("1")
            elif value in (WHITE, OBSTACLE):
                row.append("2")
            elif (x, y) in no_liberty:
                row.append("2")
            else:
                row.append("0")
        lines.append("".join(row))
    return chr(10).join(lines)


def board_from_code(text: str, size: int = 15, first: int = BLACK,
                    torus: bool = False, obstacles=None):
    """Replay a move-code string and return (board, side_to_move).

    Moves that the engine refuses are skipped and listed on
    board.import_errors so callers can report them.
    """
    board = HybridBoard(int(size))
    board.torus = bool(torus)
    board.import_errors = []
    color = first
    for token in text.replace(",", " ").split():
        if not token:
            continue
        coord = code_to_coord(token, board.size)
        if coord is None:
            color = WHITE if color == BLACK else BLACK
            continue
        if color == BLACK:
            ok, _captured = board.play_black(coord[0], coord[1],
                                             check_rules=False)
        else:
            ok, _captured = board.play_white(coord[0], coord[1])
        if not ok:
            board.import_errors.append(token)
        color = WHITE if color == BLACK else BLACK
    board.turn = color
    for cell in (obstacles or []):
        if board.in_bounds(*cell):
            board.grid[cell] = OBSTACLE
    board._invalidate_caches()
    return board, color


def load_board(path, torus=None):
    """Parse a dump file into a HybridBoard.  Returns (board, named_points)."""
    header = {}
    moves_line = None
    rows = []
    named = {}
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\r\n")
            if not line:
                continue
            if line.startswith("#"):
                body = line.lstrip("#").strip()
                for token in body.split():
                    if "=" in token and ":" not in token:
                        key, value = token.split("=", 1)
                        header[key.strip().lower()] = value.strip()
                if body.lower().startswith("obstacles"):
                    header["obstacles"] = body.split("=", 1)[1].strip()
                continue
            if line.lower().startswith("moves:"):
                moves_line = line.split(":", 1)[1].strip()
                continue
            rows.append(line)
    size = int(header.get("size", 0)) or max(
        [len(r) for r in rows] + [len(rows), 15])
    torus_flag = bool(int(header.get("torus", 0))) if torus is None else torus
    first = WHITE if header.get("first", "black").startswith("w") else BLACK
    obstacles = _parse_obstacles(header.get("obstacles", ""))

    if moves_line:
        board, _side = board_from_code(moves_line, size=size, first=first,
                                       torus=torus_flag, obstacles=obstacles)
        for i, row in enumerate(rows):
            for j, ch in enumerate(row):
                if ch.isalpha() and not ch.isdigit():
                    # named test points on top of a replayed board
                    named[ch.upper()] = (i, j)
        return board, named

    if not rows:
        board, _side = board_from_code("", size=size, first=first,
                                       torus=torus_flag, obstacles=obstacles)
        return board, named
    board = HybridBoard(max(size, len(rows)))
    board.torus = torus_flag
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
    for cell in obstacles:
        if board.in_bounds(*cell):
            board.grid[cell] = OBSTACLE
    board._invalidate_caches()
    return board, named


def render(board):
    chars = {EMPTY: ".", BLACK: "1", WHITE: "2", OBSTACLE: "X"}
    return chr(10).join("".join(chars[int(board.grid[x, y])]
                                for y in range(board.size))
                        for x in range(board.size))


def analyse(board, named=None):
    named = named or {}
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
    import rules
    for x in range(board.size):
        for y in range(board.size):
            if not board.is_empty(x, y):
                continue
            ok, ftype = rules.is_black_legal_move(board, x, y)
            if not ok and ftype in ("three_three", "four_four", "overline"):
                print("  (%d,%d) -> %s" % (x, y, ftype))
    for name, pos in sorted(named.items()):
        ok, ftype = rules.is_black_legal_move(board, *pos)
        print("  %s %s -> ok=%s foul=%s" % (name, pos, ok, ftype))


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    if argv[0] == "--code":
        text = argv[1] if len(argv) > 1 else ""
        size = 15
        if "--size" in argv:
            size = int(argv[argv.index("--size") + 1])
        first = WHITE if "--white-first" in argv else BLACK
        board, _side = board_from_code(text, size=size, first=first)
        named = {}
    else:
        path = argv[0]
        torus = True if "--torus" in argv else None
        board, named = load_board(path, torus=torus)

    analyse(board, named)

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
