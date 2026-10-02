import sys, os
sys.path.insert(0, os.getcwd())
import _tmp_port as P
from board import HybridBoard, BLACK, WHITE, EMPTY, OBSTACLE

def verdict(b, x, y):
    ctx = P.Ctx(b)
    if not b.is_empty(x, y):
        return (False, "occupied")
    if b.would_self_capture(x, y):
        return (False, "self_capture")
    b.grid[x, y] = BLACK
    try:
        run = b.black_run_length(x, y)
    finally:
        b.grid[x, y] = EMPTY
    if run == 5: return (True, None)
    if run >= 6: return (False, "overline")
    # fours / threes via the port
    p4 = P.pattern4(ctx, x, y)
    if p4 != P.FORBID:
        return (True, None)
    fours = 0; ol = False
    for dx, dy in P.DIRECTIONS:
        p = P.dir_pattern(ctx, x, y, dx, dy)
        if p == P.OL: ol = True
        elif p in (P.B4, P.B4S, P.F4): fours += 1
    if ol: return (False, "overline")
    if fours >= 2: return (False, "four_four")
    if P.check_forbidden(ctx, x, y): return (False, "three_three")
    return (True, None)

def show(name, b, x, y):
    print("  %-46s -> %s" % (name, verdict(b, x, y)))

# tests_torus.test_forbidden cases
b = HybridBoard(15)
for cell in ((7,5),(7,6),(5,7),(6,7)): b.grid[cell] = BLACK
b._invalidate_caches()
show("two open threes (7,7)", b, 7, 7)

b2 = HybridBoard(15)
for cell in ((7,4),(7,5),(7,6),(4,7),(5,7),(6,7)): b2.grid[cell] = BLACK
b2._invalidate_caches()
show("two fours (7,7)", b2, 7, 7)

b3 = HybridBoard(15)
for cell in ((7,5),(7,6),(5,7),(6,7),(4,4),(4,5),(4,6),(8,4),(8,5),(8,6)): b3.grid[cell] = BLACK
b3._invalidate_caches()
b3a = b3.copy(); b3a.grid[7,7] = BLACK; b3a._invalidate_caches()
show("blocked ext (4,7)", b3a, 4, 7)
show("blocked ext (8,7)", b3a, 8, 7)
show("other open three (7,4)", b3a, 7, 4)
show("blocked open three does not foul (7,7)", b3, 7, 7)

def load_line(text):
    b = HybridBoard(15); row = 7; c0 = (15 - len(text)) // 2; center=None
    for j, ch in enumerate(text):
        if ch == "1": b.grid[row, c0+j] = BLACK
        elif ch.upper() == "A": center = (row, c0+j)
    b._invalidate_caches(); return b, center
b5, c5 = load_line("0110A0110"); show("0110A0110 -> ", b5, *c5)
b6, c6 = load_line("1110A0111"); show("1110A0111 -> ", b6, *c6)

def capture_board(extra):
    b = HybridBoard(15)
    for cell in ((7,4),(7,5),(7,8),(4,7),(5,7),(6,7)): b.grid[cell] = BLACK
    for cell in ((7,3),(6,4),(8,4),(6,5),(8,5)): b.grid[cell] = WHITE
    if extra: b.grid[(8,4)] = 0
    b._invalidate_caches(); return b
show("four-four with capturable group", capture_board(False), 7, 7)
show("four-four without extra liberty", capture_board(True), 7, 7)
