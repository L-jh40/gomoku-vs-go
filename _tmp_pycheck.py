import sys, os, time
sys.path.insert(0, os.getcwd())
import rules, board_tools as bt
from board import HybridBoard, BLACK

# 1. user position
codes = "h9g10g9f7g8g6g7k8i8o15h7n15d10o14e7n14e6o13"
b, _ = bt.board_from_code(codes, size=15, first=bt.BLACK, gomoku=True)
t0=time.perf_counter(); got = sorted(c for c,_ in bt.forbidden_codes(b)); dt=time.perf_counter()-t0
print("user position rules:", got, "%.3fs" % dt, "(expect e9,f8,f9,h10)")

# 2. all pasteboard blocks vs recorded
text = open(os.path.join("导出","粘贴板.md"), encoding="utf-8").read()
pairs = bt.blocks_from_text(text)
bad = []
for i,(c, fb) in enumerate(pairs):
    rec = sorted(bt.forbidden_list(fb))
    bb, _ = bt.board_from_code(c, size=15, first=bt.BLACK, gomoku=True)
    got = sorted(x for x,_ in bt.forbidden_codes(bb))
    if got != rec:
        bad.append((i+1, c, got, rec))
print("blocks:", len(pairs), "mismatching:", len(bad))
for (i,c,got,rec) in bad:
    print("  block", i, c)
    print("     rules:", got)
    print("     rec  :", rec)

# 3. tests_torus rule-book shapes
def verdict(b, x, y):
    return rules.is_black_legal_move(b, x, y)
b5 = HybridBoard(15)
for cell in ((7,4),(7,5),(7,9),(7,10)): b5.grid[cell] = BLACK
b5._invalidate_caches()
print("0110A0110 h8 ->", verdict(b5, 7, 7))
b6 = HybridBoard(15)
for cell in ((7,4),(7,5),(7,6),(4,7),(5,7),(6,7)): b6.grid[cell] = BLACK
b6._invalidate_caches()
print("two fours two dirs h8 ->", verdict(b6, 7, 7))
b7 = HybridBoard(15)
for cell in ((7,5),(7,6),(5,7),(6,7)): b7.grid[cell] = BLACK
b7._invalidate_caches()
print("two open threes two dirs h8 ->", verdict(b7, 7, 7))
