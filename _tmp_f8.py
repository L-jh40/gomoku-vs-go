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
for tag, probe in (("without h8", None), ("with h8", bt.code_to_coord("h8", 15))):
    b, _ = bt.board_from_code(codes, size=15, first=bt.BLACK, gomoku=True)
    if probe: b.grid[probe] = BLACK
    f8 = bt.code_to_coord("f8", 15)
    print("== f8 %s ==" % tag)
    print("  pat4(f8) =", D.P4_NAME[pat4(b, *f8)])
    for d in range(4):
        print("   dir%d %s" % (d, D.PAT_NAME[dirpat(b, f8[0], f8[1], d)]))
    b.grid[f8] = BLACK
    print("  after placing f8:")
    for d in range(4):
        print("   dir%d %s" % (d, D.PAT_NAME[dirpat(b, f8[0], f8[1], d)]))
    b.grid[f8] = EMPTY
    if probe: b.grid[probe] = EMPTY
