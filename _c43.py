import subprocess
ENG="cpp/build/engine.exe"
def run(blacks, whites, label):
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
    send("candidates w 11 5")
    cands=[]
    while True:
        l=p.stdout.readline().strip()
        if l=="end": break
        if l.startswith("cand"): cands.append(l)
    send("quit"); p.wait(timeout=10)
    print("==", label)
    for l in out: print("   ",l)
    print("    candidates w:", cands)

# A: single threat line + 43 point (7,9)
run([(7,6),(7,7),(7,8),(5,7),(6,8)], [], "single line + 43 at (7,9)")
# B: two disjoint threat lines + same 43 point -> old code fell back to union and kept (7,5)
run([(7,6),(7,7),(7,8),(5,7),(6,8),(1,0),(2,0),(3,0)], [], "two disjoint lines + 43 at (7,9)")
