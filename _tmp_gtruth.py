# -*- coding: utf-8 -*-
"""Independent check: our forbidden judgement vs Rapfi-verified data."""
import os, subprocess, sys
APP = r"C:\Users\lin\Desktop\gomoku-vs-go\gomoku-vs-go2"
sys.path.insert(0, APP)
import board_tools as bt, rules
from board import BLACK, WHITE, EMPTY, OBSTACLE

DATA = os.path.join(APP, "导出", "粘贴板-备份.md")
ENGINE = os.path.join(APP, "cpp", "build", "engine.exe")

text = open(DATA, encoding="utf-8").read()
pairs = bt.blocks_from_text(text)
cases = [(c, bt.forbidden_list(v)) for c, v in pairs if v.strip()]
print("cases with a Rapfi verdict: %d" % len(cases))

def our_fouls(board):
    return set(code for code, _t in bt.forbidden_codes(board))

def our_self_capture(board):
    return set(bt.coord_to_code(x, y, board.size)
               for (x, y) in board.get_no_liberty_positions())

def engine_check(board):
    """Ask cpp/build/engine.exe for its illegal black points."""
    if not os.path.exists(ENGINE):
        return None
    lines = ["size %d" % board.size]
    for x in range(board.size):
        for y in range(board.size):
            v = int(board.grid[x, y])
            if v == BLACK:
                lines.append("set %d %d b" % (x, y))
            elif v == WHITE:
                lines.append("set %d %d w" % (x, y))
            elif v == OBSTACLE:
                lines.append("set %d %d o" % (x, y))
    lines.append("checkforbidden")
    lines.append("quit")
    try:
        out = subprocess.run([ENGINE], input=chr(10).join(lines) + chr(10),
                             capture_output=True, text=True, timeout=60)
    except Exception as exc:
        return "error: %s" % exc
    result = set()
    started = False
    for raw in out.stdout.splitlines():
        s = raw.strip()
        if s == "checkforbidden":
            started = True
            continue
        if started:
            if s == "end":
                break
            parts = s.split()
            if len(parts) == 2 and all(p.lstrip("-").isdigit() for p in parts):
                x, y = int(parts[0]), int(parts[1])
                if 0 <= x < board.size and 0 <= y < board.size:
                    result.add(bt.coord_to_code(x, y, board.size))
    return result

print()
py_ok = py_bad = eng_ok = eng_bad = 0
engine_available = None
for codes, rapfi in cases:
    block, board, info, fouls = bt.position_block(codes, size=15, gomoku=True)
    ours = our_fouls(board)
    rapfiset = set(rapfi)
    same_py = (ours == rapfiset)
    py_ok += 1 if same_py else 0
    py_bad += 0 if same_py else 1
    eng = engine_check(board)
    if isinstance(eng, str):
        engine_available = eng
        same_eng = None
    else:
        engine_available = True
        self_cap = our_self_capture(board)
        eng_foul = set(eng) - self_cap
        same_eng = (eng_foul == rapfiset)
        eng_ok += 1 if same_eng else 0
        eng_bad += 0 if same_eng else 1
    print(("PY=OK  " if same_py else "PY=DIFF") + "  "
          + ("ENG=OK" if same_eng else ("ENG=DIFF" if same_eng is False else "ENG=n/a"))
          + "  " + codes[:46])
    if not same_py:
        print("     Rapfi : " + ",".join(sorted(rapfiset)))
        print("     Python: " + ",".join(sorted(ours)))
    if same_eng is False:
        print("     Engine: " + ",".join(sorted(eng if isinstance(eng, set) else [])))

print()
print("python  : %d ok / %d diff" % (py_ok, py_bad))
if engine_available is True:
    print("cpp(old): %d ok / %d diff" % (eng_ok, eng_bad))
else:
    print("cpp engine not usable:", engine_available)
