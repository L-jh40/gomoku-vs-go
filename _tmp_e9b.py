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

codes = "h9g10g9f7g8g6g7k8i8o15h7n15d10o14e7n14e6o13"
b, _ = bt.board_from_code(codes, size=15, first=bt.BLACK, gomoku=True)
b.grid[bt.code_to_coord("h8", 15)] = BLACK
b.grid[bt.code_to_coord("f8", 15)] = BLACK
e9 = bt.code_to_coord("e9", 15)
b.grid[e9] = BLACK
print("e9 with h8,f8,e9 placed:")
for d in range(4):
    dx, dy = DIRECTIONS[d]
    p = dirpat(b, e9[0], e9[1], d)
    if p not in (F3, F3S):
        print(" dir%d %s skip" % (d, D.PAT_NAME[p])); continue
    print(" dir%d %s:" % (d, D.PAT_NAME[p]))
    for sgn in (-1, 1):
        cx, cy = e9
        for i in range(4):
            cx += sgn*dx; cy += sgn*dy
            if not b.in_bounds(cx, cy):
                print("   sgn%+d off-board" % sgn); break
            v = int(b.grid[cx, cy])
            if v == EMPTY:
                p4 = pat4(b, cx, cy); pc = dirpat(b, cx, cy, d)
                print("   sgn%+d ext %s p4=%s pc=%s" % (sgn, bt.coord_to_code(cx,cy,15), D.P4_NAME[p4], D.PAT_NAME[pc]))
                break
            elif v != BLACK:
                print("   sgn%+d blocked" % sgn); break
            else:
                print("   sgn%+d black %s" % (sgn, bt.coord_to_code(cx,cy,15)))
b.grid[e9] = EMPTY
