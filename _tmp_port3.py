import sys, os, subprocess, re
sys.path.insert(0, os.getcwd())
import _tmp_port as P
from board import HybridBoard, BLACK, WHITE, EMPTY
import board_tools as bt
RAPFI = r"C:\Users\lin\Desktop\gomoku-vs-go\tools\rapfi\yixin-gui\engine.exe"

def rapfi(blacks, whites):
    cmds = ["INFO rule 2", "START 15", "YXBOARD"]
    for (x,y) in blacks: cmds.append("%d,%d,1" % (x,y))
    for (x,y) in whites: cmds.append("%d,%d,2" % (x,y))
    if (len(blacks)+len(whites)) % 2 == 1:
        cmds.append("-1,-1,%d" % (2 if len(blacks)>=len(whites) else 1))
    cmds += ["DONE", "YXSHOWFORBID"]
    out = subprocess.run([RAPFI], input="\n".join(cmds)+"\n", capture_output=True, text=True, timeout=90, cwd=os.path.dirname(RAPFI))
    lines = [l for l in out.stdout.splitlines() if l.strip().upper().startswith("FORBID")]
    body = lines[-1].split(" ",1)[1].strip()
    d = re.sub(r"[^0-9]", "", body)
    return sorted(bt.coord_to_code(int(d[i:i+2]), int(d[i+2:i+4]), 15) for i in range(0, len(d)-3, 4))

def port(blacks, whites):
    b = HybridBoard(15)
    for (x,y) in blacks: b.grid[x,y] = BLACK
    for (x,y) in whites: b.grid[x,y] = WHITE
    b._invalidate_caches()
    return P.scan(b)[0]

def load_line(text):
    row = 7; c0 = (15-len(text))//2
    blacks = []
    for j,ch in enumerate(text):
        if ch == "1": blacks.append((row, c0+j))
    return blacks

for text in ("0110A0110", "1110A0111"):
    blacks = load_line(text)
    whites = [(0,0),(0,1),(0,2),(0,3),(14,14),(14,13),(14,12),(14,11)]
    # keep parity even -> black to move
    print(text, "blacks", blacks)
    print("   rapfi:", rapfi(blacks, whites))
    print("   port :", port(blacks, whites))
