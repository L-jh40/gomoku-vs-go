# Faithful Python model of Rapfi checkForbiddenPoint (from tools/rapfi source)
import sys, os
sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.join(os.getcwd(), "cpp", "tests"))
import diff_forbidden as D
from board import HybridBoard, BLACK, WHITE, EMPTY, OBSTACLE, DIRECTIONS
import board_tools as bt

DEAD, OL, B1, F1, B2, F2, F2A, F2B, B3, B3S, F3, F3S, B4, B4S, F4, F5 = range(16)
(P4_NONE, FORBID, L_FLEX2, K_BLOCK3, J_FLEX2_2X, I_BLOCK3_PLUS, H_FLEX3,
 G_FLEX3_PLUS, F_FLEX3_2X, E_BLOCK4, D_BLOCK4_PLUS, C_BLOCK4_FLEX3,
 B_FLEX4, A_FIVE) = range(14)

def dirpat(board, x, y, d):
    dx, dy = DIRECTIONS[d]
    return D.dir_pattern_py(board, x, y, dx, dy)

def pat4(board, x, y):
    return D.combine4_forbid(*[dirpat(board, x, y, d) for d in range(4)])

DEPTH_LIMIT = 64

def check_forbidden(board, x, y, depth=0):
    if not board.in_bounds(x, y) or not board.is_empty(x, y):
        return False
    if depth >= DEPTH_LIMIT:
        return False
    if pat4(board, x, y) != FORBID:
        return False
    winFour = 0
    for d in range(4):
        p = dirpat(board, x, y, d)
        if p == OL:
            return True
        elif p in (B4, B4S, F4):
            winFour += 1
            if winFour >= 2:
                return True
    board.grid[x, y] = BLACK
    try:
        winThree = 0
        for d in range(4):
            p = dirpat(board, x, y, d)
            if p not in (F3, F3S):
                continue
            dx, dy = DIRECTIONS[d]
            for sgn in (-1, 1):
                cx, cy = x, y
                for _ in range(4):
                    cx += sgn * dx; cy += sgn * dy
                    if not board.in_bounds(cx, cy):
                        break
                    v = int(board.grid[cx, cy])
                    if v == EMPTY:
                        p4 = pat4(board, cx, cy)
                        pc = dirpat(board, cx, cy, d)
                        ok = (p4 == B_FLEX4) or (pc == F5) or (
                            p4 == FORBID and pc == F4 and
                            not check_forbidden(board, cx, cy, depth + 1))
                        if ok:
                            winThree += 1
                        break
                    elif v != BLACK:
                        break
            if winThree >= 2:
                break
        return winThree >= 2
    finally:
        board.grid[x, y] = EMPTY

codes = "h9g10g9f7g8g6g7k8i8o15h7n15d10o14e7n14e6o13"
b, _ = bt.board_from_code(codes, size=15, first=bt.BLACK, gomoku=True)
out = []
for x in range(15):
    for y in range(15):
        if b.is_empty(x, y) and check_forbidden(b, x, y):
            out.append(bt.coord_to_code(x, y, 15))
print("model rapfi forbid:", sorted(out))
print("recorded ground truth: ['e9','f8','f9','h10']")
print("project (rules.py):", [c for c,_ in bt.forbidden_codes(b)])

# diag for h8
h8 = bt.code_to_coord("h8", 15)
print("h8 coord", h8)
print("dirs at h8:", [D.PAT_NAME[dirpat(b, *h8, d)] for d in range(4)])
print("pat4 at h8:", D.P4_NAME[pat4(b, *h8)])
b.grid[h8] = BLACK
try:
    print("dirs after placing:", [D.PAT_NAME[dirpat(b, *h8, d)] for d in range(4)])
finally:
    b.grid[h8] = EMPTY
