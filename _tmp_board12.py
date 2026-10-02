import os, sys
sys.path.insert(0, os.getcwd())
import board_tools as bt
codes = "h9 i9 i8 j7 i7 f11 i6 f6 h6 p0 f10 p0 f9 p0 f8 p0 f7"
b, _ = bt.board_from_code(codes, size=15, first=bt.BLACK, gomoku=True)
print("history colors:", [(bt.coord_to_code(x,y,15), c) for (c,x,y,_) in b.history])
print()
hdr = "    " + " ".join("abcdefghijklmno")
print(hdr)
for x in range(15):
    row = "".join({0:".",1:"X",2:"O",3:"#"}[int(b.grid[x,y])] for y in range(15))
    print("%2d  %s   (row %d)" % (x, row, 15-x))
print()
print("h9 =", bt.code_to_coord("h9",15), "value", int(b.grid[bt.code_to_coord("h9",15)]))
print("g9 =", bt.code_to_coord("g9",15), "value", int(b.grid[bt.code_to_coord("g9",15)]))
print("h8 =", bt.code_to_coord("h8",15), "value", int(b.grid[bt.code_to_coord("h8",15)]))
print("engine/rules forbidden:", sorted(c for c,_ in bt.forbidden_codes(b)))
