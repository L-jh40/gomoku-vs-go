import subprocess, itertools, time
import board_tools as bt
PROJ = "cpp/build/engine.exe"
base_toks = bt.split_codes("h9 i9 i8 j7 i7 f11 i6 f6 h6 p0 f10 p0 f9 p0 f8 p0 f7", 15)
target = set(bt.code_to_coord(c,15) for c in ["g9","h8","h9"])

def build(tokens):
    stones, color = [], 1
    for t in tokens:
        if t in ("p0","pass"):
            color = 3-color; continue
        c = bt.code_to_coord(t,15)
        if c is None: color = 3-color; continue
        stones.append((c[0],c[1],color)); color = 3-color
    return stones

p = subprocess.Popen([PROJ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
def send(c):
    p.stdin.write(c+"\n"); p.stdin.flush()
def forbid(st):
    grid = [[0]*15 for _ in range(15)]
    for (x,y,c) in st: grid[x][y]=c
    send("size 15"); send("clear")
    for x in range(15):
        for y in range(15):
            v=grid[x][y]
            if v: send("set %d %d %s" % (x,y,{1:"b",2:"w"}[v]))
    send("checkforbidden")
    out=set()
    while True:
        l=p.stdout.readline().strip()
        if l=="end": break
        a,b=l.split(); out.add((int(a),int(b)))
    return out

t0=time.time()
hits=[]
for i in range(len(base_toks)+1):
    for x in range(15):
        for y in range(15):
            tok = bt.coord_to_code(x,y,15)
            toks = base_toks[:i] + [tok] + base_toks[i:]
            st = build(toks)
            if len(st) != 14: continue
            if any(s[0]==x and s[1]==y and False for s in st): pass
            f = forbid(st)
            if f == target:
                hits.append((i, tok))
print("insert-one hits:", hits, "%.1fs" % (time.time()-t0))
send("quit")
