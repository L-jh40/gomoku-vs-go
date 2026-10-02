import subprocess, itertools
import board_tools as bt
PROJ = "cpp/build/engine.exe"

toks = bt.split_codes("h9 i9 i8 j7 i7 f11 i6 f6 h6 p0 f10 p0 f9 p0 f8 p0 f7", 15)
target = set(bt.code_to_coord(c, 15) for c in ["g9","h8","h9"])

def build_stones(tokens):
    stones, color = [], 1
    for t in tokens:
        if t in ("p0","pass"):
            color = 3 - color; continue
        x, y = bt.code_to_coord(t, 15)
        stones.append((x, y, color)); color = 3 - color
    return stones

p = subprocess.Popen([PROJ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
def send(c):
    p.stdin.write(c + "\n"); p.stdin.flush()
def forbid(stones):
    grid = [[0]*15 for _ in range(15)]
    for (x,y,c) in stones: grid[x][y] = c
    send("size 15"); send("clear")
    for x in range(15):
        for y in range(15):
            v = grid[x][y]
            if v: send("set %d %d %s" % (x,y,{1:"b",2:"w"}[v]))
    send("checkforbidden")
    out = set()
    while True:
        line = p.stdout.readline().strip()
        if line == "end": break
        a,b = line.split(); out.add((int(a),int(b)))
    return out

def report(label, tokens):
    s = build_stones(tokens)
    f = forbid(s)
    mark = " <== MATCH" if f == target else ""
    print("%-22s stones=%2d  %s%s" % (label, len(s), sorted(f), mark))

report("as-is", toks)
for i, t in enumerate(toks):
    report("drop[%d]=%s" % (i, t), toks[:i] + toks[i+1:])
send("quit")
