import sys, os, subprocess
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

def check_forbidden(board, x, y, depth=0, trace=None):
    if not board.in_bounds(x, y) or not board.is_empty(x, y): return False
    if depth >= 64: return False
    if pat4(board, x, y) != FORBID: return False
    winFour = 0
    for d in range(4):
        p = dirpat(board, x, y, d)
        if p == OL: return True
        elif p in (B4, B4S, F4):
            winFour += 1
            if winFour >= 2: return True
    board.grid[x, y] = BLACK
    try:
        winThree = 0
        for d in range(4):
            p = dirpat(board, x, y, d)
            if p not in (F3, F3S): continue
            counted = False
            for passno in (0, 1):
                if counted: break
                sgn = -1 if passno == 0 else 1
                dx, dy = DIRECTIONS[d]
                cx, cy = x, y
                for _ in range(4):
                    cx += sgn*dx; cy += sgn*dy
                    if not board.in_bounds(cx, cy): break
                    v = int(board.grid[cx, cy])
                    if v == EMPTY:
                        p4 = pat4(board, cx, cy); pc = dirpat(board, cx, cy, d)
                        ok = (p4 == B_FLEX4) or (pc == F5) or (
                            p4 == FORBID and pc == F4 and not check_forbidden(board, cx, cy, depth+1))
                        if ok: counted = True
                        break
                    elif v != BLACK: break
            if counted: winThree += 1
        return winThree >= 2
    finally:
        board.grid[x, y] = EMPTY

blacks = [(3,3),(3,11),(5,5),(6,11),(7,4),(7,11),(8,8),(8,11),(9,6),(11,3),(11,8)]
whites = [(5,3),(8,4),(9,3),(9,5),(10,4)]
b = HybridBoard(15)
for (x,y) in blacks: b.grid[x,y] = BLACK
for (x,y) in whites: b.grid[x,y] = WHITE
pt = (9,4)
print("target pat4:", D.P4_NAME[pat4(b, *pt)])
for d in range(4):
    print("  dir%d %s" % (d, D.PAT_NAME[dirpat(b, *pt, d)]))
print("model check_forbidden:", check_forbidden(b, *pt))

# ask project engine for pat
p = subprocess.Popen(["cpp/build/engine.exe"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
def send(c):
    p.stdin.write(c+"\n"); p.stdin.flush()
send("size 15"); send("clear")
for (x,y) in blacks: send("set %d %d b" % (x,y))
for (x,y) in whites: send("set %d %d w" % (x,y))
send("pat 9 4"); print("engine pat (dir0..3 p4 fours threes forbidden):", p.stdout.readline().strip())
send("checkforbidden")
out=[]
while True:
    l=p.stdout.readline().strip()
    if l=="end": break
    out.append(l)
print("engine forbidden:", out)
send("quit")
