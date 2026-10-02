# -*- coding: utf-8 -*-
"""Board code / dump tools (reporting positions, import, analysis).

Coordinate code (one token per move, colours alternate from the first player):
    letter = column, a..  (left to right)
    number = row counted from the bottom, 1..size  (Renju style)
    so on 15x15 the centre is "h8"; a pass is "p0".

Export format (produced by the GUI "导出棋盘(复制)" / G key):
    # header lines (size, torus, first, forbid, obstacles, no-liberty)
    moves: a15 b14 p0 c13 ...
    <size rows of 0/1/2>   (2 = white, obstacle or no-liberty point)

The GUI writes board_dump.txt and appends the bare coordinate line to
粘贴板.md inside its export folder (程序目录/导出 by default), so several
positions can be kept in one file (one line each) and re-imported later.

Usage:
    python board_tools.py board_dump.txt
    python board_tools.py board_dump.txt --ai black --depth 2
    python board_tools.py --code "h8 h7 g7 p0" --size 15
    python board_tools.py --code-file 粘贴板.md
"""
from __future__ import annotations

import os
import sys

from board import HybridBoard, BLACK, WHITE, EMPTY, OBSTACLE
import rules

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
ROW_CHARS = set("0123456789Xx")
PASS_WORDS = ("p0", "pass", "p")
CODE_LABELS = ("moves:", "moves=", "move:", "code:", "code=",
               "board:", "board=", "局面:", "坐标:", "着法:")
FORBIDDEN_LABELS = ("forbidden:", "forbidden=", "禁手:", "禁手=")


def split_codes(text: str, size: int = 15) -> list:
    """Split a coordinate string into move tokens (spaces optional).

    Rapfi / Yixin copy a position without any separator, so the reader has
    to chunk the string itself; the same helper also accepts our own
    exports and hand-written lists:

        "h8 i9 p0"    -> ["h8", "i9", "p0"]
        "h8i9j10"     -> ["h8", "i9", "j10"]   (Rapfi, no spaces)
        "H8,I9;J10"   -> ["h8", "i9", "j10"]
        "a15b14"      -> ["a15", "b14"]         (two-digit rows)
        "1.h8 2.i9"   -> ["h8", "i9"]           (move numbers dropped)

    A leading "moves:" / "board=" label is ignored, separators and
    decorations (quotes, brackets, dots) are skipped, and pieces that
    cannot be a coordinate (a lone letter, a bare number when real tokens
    exist) are dropped instead of breaking the whole read.
    """
    s = str(text).strip()
    low = s.lower()
    for label in CODE_LABELS:
        if low.startswith(label):
            s = s[len(label):]
            break

    raw = []
    i = 0
    n = len(s)
    limit = int(size) if int(size) > 0 else 15
    while i < n:
        ch = s[i]
        ascii_alpha = ch.isascii() and ch.isalpha()
        if ascii_alpha:
            j = i + 1
            digits = ""
            while j < n and s[j].isdigit() and len(digits) < 2:
                digits += s[j]
                j += 1
            if not digits:
                raw.append(ch)          # lone letter: dropped below
                i = j
                continue
            if len(digits) == 2 and int(digits) > limit:
                # "a15" on a 9x9 board: keep the first digit only.
                digits = digits[0]
                j = i + 2
            raw.append(ch.lower() + digits)
            i = j
            continue
        if ch.isdigit():
            j = i
            while j < n and s[j].isdigit():
                j += 1
            raw.append(s[i:j])
            i = j
            continue
        i += 1                          # separator or decoration

    coords = [t for t in raw if t[:1].isalpha() and len(t) > 1]
    if coords:
        raw = coords                     # drop move numbers / row digits
    return raw


def coord_to_code(x: int, y: int, size: int) -> str:
    """(row, col) -> Renju-style code, e.g. (0, 0) on 15x15 -> "a15"."""
    return "%s%d" % (chr(ord("a") + int(y)), int(size) - int(x))


def code_to_coord(code: str, size: int):
    """Code -> (row, col); returns None for a pass token."""
    token = code.strip().lower()
    if token in (PASS_CODE, "pass", "p"):
        return None
    if len(token) < 2 or not token[0].isalpha() or not token[1:].isdigit():
        raise ValueError("bad move code: " + code)
    y = ord(token[0]) - ord("a")
    number = int(token[1:])
    x = int(size) - number
    if not (0 <= x < size and 0 <= y < size):
        raise ValueError("move code out of board: " + code)
    return x, y


def is_pass(token: str) -> bool:
    return code_to_coord(token, 15) is None


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


def codes_line(codes) -> str:
    return " ".join(codes)


def pass_records_from_codes(codes) -> list:
    """Rebuild the GUI pass list (stones played before each pass)."""
    out = []
    played = 0
    for token in codes:
        if is_pass(token):
            out.append(played)
        else:
            played += 1
    return out


def _line_value(line: str, labels) -> str:
    """Value of a labelled line ("moves: h8" -> "h8")."""
    for sep in (":", "="):
        if sep in line:
            return line.split(sep, 1)[1].strip()
    return ""


def codes_from_text(text: str) -> str:
    """Last move-code line of a dump / coordinates file.

    Header lines, board rows and "forbidden:" lines are skipped, so the
    same helper works for board_dump.txt, for 粘贴板.md written by the GUI
    and for the two-line blocks written by the Rapfi plugin.
    """
    candidate = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        lower = line.lower()
        if any(lower.startswith(l) for l in FORBIDDEN_LABELS):
            continue
        if any(lower.startswith(l) for l in CODE_LABELS):
            candidate = _line_value(line, CODE_LABELS)
            continue
        stripped = line.replace(" ", "")
        if stripped and all(ch in ROW_CHARS for ch in stripped):
            continue  # board row of a dump
        candidate = line
    return candidate


def forbidden_from_text(text: str) -> str:
    """Last "forbidden:" line of a file written by the Rapfi plugin."""
    out = ""
    for raw in text.splitlines():
        line = raw.strip()
        lower = line.lower()
        if any(lower.startswith(l) for l in FORBIDDEN_LABELS):
            out = _line_value(line, FORBIDDEN_LABELS)
    return out


def codes_from_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return codes_from_text(f.read())


def append_position(path: str, block: str) -> str:
    """Append one block (one position) on its own lines and return path.

    A newline is added in front when the file does not end with one, so
    every block keeps its own line and can be read back line by line.
    """
    prefix = ""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            old = f.read()
        if old and not old.endswith("\n"):
            prefix = "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(prefix + block.rstrip("\n") + "\n")
    return path


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
                  first: str = "black", extra=()) -> str:
    """Full dump text: header + move code line + board rows."""
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
        "# no_liberty=" + ",".join("(%d,%d)" % p
                                   for p in sorted(no_liberty)),
    ]
    for line in extra:
        lines.append(str(line))
    lines.append("moves: " + codes_line(moves))
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
                    torus: bool = False, obstacles=None,
                    check_rules: bool = True, gomoku: bool = False):
    """Replay a move-code string and return (board, side_to_move).

    The string may be spaced or not (Rapfi / Yixin copies it without any
    separator; see split_codes).  Illegal moves (forbidden / self-capture
    / occupied) are NOT played when check_rules is on; they are collected
    as (token, foul_type) tuples on board.import_errors so callers can
    report them.  The turn still passes, so the remaining moves keep their
    colour.

    gomoku=True places the stones directly (no Go capture, no self-capture
    check), which is what an external gomoku / Renju position needs: those
    positions may contain shapes our Go layer would refuse to play.
    """
    board = HybridBoard(int(size))
    board.torus = bool(torus)
    board.import_errors = []
    color = first
    for token in split_codes(text, board.size):
        if not token:
            continue
        coord = code_to_coord(token, board.size)
        if coord is None:
            color = WHITE if color == BLACK else BLACK
            continue
        x, y = coord
        if gomoku:
            if not board.is_empty(x, y):
                board.import_errors.append((token, "occupied"))
            else:
                board.grid[x, y] = color
                board.history.append((color, x, y, []))
            color = WHITE if color == BLACK else BLACK
            continue
        if color == BLACK:
            if check_rules:
                legal, ftype = rules.is_black_legal_move(board, x, y)
                if not legal:
                    board.import_errors.append((token, ftype))
                    color = WHITE if color == BLACK else BLACK
                    continue
            ok, _captured = board.play_black(x, y, check_rules=False)
            fail_type = "occupied" if not ok else None
        else:
            ok, _captured = board.play_white(x, y)
            fail_type = "occupied" if not ok else None
        if not ok:
            board.import_errors.append((token, fail_type))
        color = WHITE if color == BLACK else BLACK
    board.turn = color
    for cell in (obstacles or []):
        if board.in_bounds(*cell):
            board.grid[cell] = OBSTACLE
    board._invalidate_caches()
    return board, color


def parse_dump(text: str, torus=None, size=None, first=None,
               check_rules: bool = True):
    """Parse dump text or a bare code line.

    Returns (board, named_points, info).  Header values win; torus/size/
    first are only fallbacks for files that carry no header.
    """
    header = {}
    moves_line = None
    rows = []
    named = {}
    for raw in text.splitlines():
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
        stripped = line.replace(" ", "")
        if stripped and all(ch in ROW_CHARS for ch in stripped):
            rows.append(line)
            continue
        moves_line = line.strip()  # a bare coordinate line
    fallback_size = int(size or 0)
    row_size = max([len(r) for r in rows] + [len(rows), 0])
    size_value = int(header.get("size", 0)) or fallback_size or row_size or 15
    # A header written by board_to_text wins; torus/size/first are only
    # fallbacks for bare coordinate lines (no header).
    if "torus" in header:
        torus_flag = bool(int(header["torus"]))
    else:
        torus_flag = bool(torus) if torus is not None else False
    if "first" in header:
        first_value = (WHITE if str(header["first"]).lower().startswith("w")
                       else BLACK)
    elif first is not None:
        first_value = first
    else:
        first_value = BLACK
    obstacles = _parse_obstacles(header.get("obstacles", ""))
    # Empty points where black has no liberty are printed as 2 as well,
    # so remember them to keep the row import from reading them as white.
    no_liberty = _parse_obstacles(header.get("no_liberty", ""))

    if moves_line:
        board, _side = board_from_code(moves_line, size=size_value,
                                       first=first_value, torus=torus_flag,
                                       obstacles=obstacles,
                                       check_rules=check_rules)
        info = {"size": size_value, "torus": torus_flag,
                "first": first_value, "obstacles": obstacles,
                "no_liberty": no_liberty,
                "moves": moves_line, "source": "moves",
                "errors": list(getattr(board, "import_errors", []))}
        return _finish_dump(board, named, info, header)

    board = HybridBoard(max(size_value, row_size or size_value))
    board.torus = torus_flag
    r0 = (board.size - len(rows)) // 2
    c0 = (board.size - size_value) // 2
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
    info = {"size": board.size, "torus": torus_flag,
            "first": first_value, "obstacles": obstacles,
            "no_liberty": no_liberty,
            "moves": "", "source": "rows", "errors": []}
    return _finish_dump(board, named, info, header)


def _finish_dump(board, named, info, header):
    """Apply # forbid: flags from the header and finish a parse."""
    forbid = None
    if any(k in header for k in ("overline", "four_four", "three_three")):
        forbid = (bool(int(header.get("overline", 1))),
                  bool(int(header.get("four_four", 1))),
                  bool(int(header.get("three_three", 1))))
        board._forbid_overline, board._forbid_44, board._forbid_33 = forbid
    # A no-liberty point is empty, not a white stone: the row dump prints
    # it as 2, so undo that reading when the board is built from rows.
    for cell in (info.get("no_liberty") or []):
        if board.in_bounds(*cell):
            board.grid[cell] = EMPTY
    board._invalidate_caches()
    info["forbid"] = forbid
    return board, named, info


def load_board(path, torus=None, check_rules=True):
    """Parse a dump file into a HybridBoard.  Returns (board, named_points)."""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    board, named, _info = parse_dump(text, torus=torus,
                                     check_rules=check_rules)
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
    if argv[0] in ("--code", "--code-file"):
        if argv[0] == "--code":
            text = argv[1] if len(argv) > 1 else ""
        else:
            text = codes_from_file(argv[1])
        fallback_size = 15
        if "--size" in argv:
            fallback_size = int(argv[argv.index("--size") + 1])
        first = WHITE if "--white-first" in argv else None
        board, named, info = parse_dump(text, size=fallback_size, first=first,
                                        check_rules="--loose" not in argv)
    else:
        path = argv[0]
        torus = True if "--torus" in argv else None
        board, _named, info = parse_dump(
            open(path, "r", encoding="utf-8").read(), torus=torus,
            check_rules="--loose" not in argv)
        named = _named

    for token, ftype in info.get("errors") or []:
        print("skipped illegal move: %s (%s)" % (token, ftype))

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
