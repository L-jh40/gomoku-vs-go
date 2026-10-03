import subprocess
ENG="cpp/build/engine.exe"
def run(codes, cmds):
    import board_tools as bt, sys, os
    sys.path.insert(0, os.getcwd())
    b,_=bt.board_from_code(codes,size=15,first=1,gomoku=True)
    p=subprocess.Popen([ENG],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
    def send(c): p.stdin.write(c+"\n"); p.stdin.flush()
    send("size 15"); send("clear")
    for x in range(15):
        for y in range(15):
            v=int(b.grid[x,y])
            if v==1: send("set %d %d b"%(x,y))
            elif v==2: send("set %d %d w"%(x,y))
    for c in cmds:
        send(c)
        while True:
            l=p.stdout.readline().strip()
            print("  ", l)
            if l=="end" or (not c.startswith("wcand") and not c.startswith("candidates") and l!=""): break
    send("quit")
codes="h8 p0 h7 p0 h6 p0 i8 p0 j7 h5 p0"
print("new case:"); run(codes, ["wcand"])
print("old case:"); run("h8 p0 h7 p0 h6 p0 i8 p0 j7", ["wcand"])
