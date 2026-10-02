import subprocess
import board_tools as bt
PROJ = "cpp/build/engine.exe"
toks = bt.split_codes("h9 i9 i8 j7 i7 f11 i6 f6 h6 p0 f10 p0 f9 p0 f8 p0 f7", 15)
stones, color = [], 1
for t in toks:
    if t in ("p0","pass"):
        color = 3-color; continue
    x,y = bt.code_to_coord(t,15); stones.append((x,y,color)); color = 3-color
target = set(bt.code_to_coord(c,15) for c in ["g9","h8","h9"])

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

print("remove one stone (colors preserved):")
for i,(x,y,c) in enumerate(stones):
    st = stones[:i]+stones[i+1:]
    f = forbid(st)
    print("  remove %-4s (%d,%d,%s): %s %s" % (bt.coord_to_code(x,y,15), x,y,"bw"[c-1], sorted(f), "<== MATCH" if f==target else ""))
print("add one stone on an empty cell:")
found=[]
for x in range(15):
    for y in range(15):
        if any(sx==x and sy==y for sx,sy,_ in stones): continue
        for c in (1,2):
            f = forbid(stones+[(x,y,c)])
            if f == target: found.append((x,y,c))
print("  matches:", [(bt.coord_to_code(x,y,15), c) for (x,y,c) in found])
send("quit")
