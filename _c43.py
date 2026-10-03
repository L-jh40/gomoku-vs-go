import subprocess
ENG="cpp/build/engine.exe"
def wcand(blacks, whites):
    p=subprocess.Popen([ENG],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
    def send(c): p.stdin.write(c+"\n"); p.stdin.flush()
    send("size 15"); send("clear")
    for (x,y) in blacks: send("set %d %d b"%(x,y))
    for (x,y) in whites: send("set %d %d w"%(x,y))
    send("wcand")
    out=[]
    while True:
        l=p.stdout.readline().strip()
        if l=="end": break
        out.append(l)
    # candidates w too
    send("candidates w 11 5")
    cands=[]
    while True:
        l=p.stdout.readline().strip()
        if l=="end": break
        if l.startswith("cand"): cands.append(l)
    send("quit")
    return out, cands
# open three in row 7 (7,6..8) + diagonal two (5,7),(6,8) -> (7,9) is a 43 kill
blacks=[(7,6),(7,7),(7,8),(5,7),(6,8)]
out,cands = wcand(blacks,[])
print("wcand:")
for l in out: print("  ",l)
print("candidates w:", cands)
