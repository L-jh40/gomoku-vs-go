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
for code in ("e9","f9","h10","h6","i9","e5","g9","g11","d6","h5","i10"):
    x, y = bt.code_to_coord(code, 15)
    if int(b.grid[x,y]) != EMPTY:
        print("%s occupied" % code); continue
    print("%s pat4=%s dirs=%s" % (code, D.P4_NAME[pat4(b,x,y)],
          [D.PAT_NAME[dirpat(b,x,y,d)] for d in range(4)]))
