import sys, os, subprocess
sys.path.insert(0, os.getcwd())
import rules, board_tools as bt
from board import HybridBoard, BLACK

def load_line(text):
    b = HybridBoard(15); row = 7; c0 = (15 - len(text)) // 2; center=None
    for j, ch in enumerate(text):
        if ch == "1": b.grid[row, c0+j] = BLACK
        elif ch.upper() == "A": center = (row, c0+j)
    b._invalidate_caches(); return b, center
for text in ("0110A0110", "1110A0111"):
    b, c = load_line(text)
    print(text, "->", rules.is_black_legal_move(b, *c))

new_codes = "f8 o15 g8 o14 h10 o13 h9 o12 h8 i12"
b, _, info = bt.parse_dump(new_codes, size=15, first=BLACK)
print("new import codes errors:", info["errors"])
print("h8 grid:", int(b.grid[7,7]), "i12 grid:", int(b.grid[3,8]), "f8:", int(b.grid[7,5]), "k8?")
# engine cross-check of the position before h8
b2, _ = bt.board_from_code("f8 o15 g8 o14 h10 o13 h9 o12", size=15, first=bt.BLACK, gomoku=True)
print("rules forbid:", sorted(c for c,_ in bt.forbidden_codes(b2)))

p = subprocess.Popen(["cpp/build/engine.exe"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
def send(c):
    p.stdin.write(c+"\n"); p.stdin.flush()
send("size 15"); send("clear")
for x in range(15):
    for y in range(15):
        v = int(b2.grid[x,y])
        if v == 1: send("set %d %d b" % (x,y))
        elif v == 2: send("set %d %d w" % (x,y))
send("checkforbidden")
out=[]
while True:
    l = p.stdout.readline().strip()
    if l == "end": break
    a,bb = l.split(); out.append(bt.coord_to_code(int(a),int(bb),15))
print("engine forbid:", sorted(out))
send("quit")
