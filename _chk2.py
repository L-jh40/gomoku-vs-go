import sys, os
sys.path.insert(0, os.getcwd())
import rules, board_tools as bt
from board import HybridBoard, BLACK, WHITE, EMPTY, DIRECTIONS
b,_ = bt.board_from_code("h8 p0 g7 p0 j10 p0 l12", size=15, first=BLACK, gomoku=True)
print("black stones:", sorted((x,y) for x in range(15) for y in range(15) if b.grid[x,y]==BLACK))
noli = rules._rapfi_no_liberty(b)
mid = rules._RAPFI_LINE_MID
for d,(dx,dy) in enumerate(DIRECTIONS):
    line=[]
    for i in range(-5,6):
        if i==0:
            line.append(rules._RAPFI_SELF); continue
        cell = b.step_from(6,8,dx,dy,i)
        line.append(rules._RAPFI_OPPO if cell is None else rules._rapfi_cell_flag(b,cell[0],cell[1],noli))
    names={0:"SELF",1:"OPPO",2:"EMPT"}
    pat = rules._rapfi_pattern(tuple(line))
    print("dir%d (%d,%d) line=%s -> %s" % (d,dx,dy,[names[v] for v in line], rules._PAT_NAMES.get(pat,pat) if hasattr(rules,'_PAT_NAMES') else pat))
