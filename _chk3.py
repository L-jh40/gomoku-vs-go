import subprocess
ENG="cpp/build/engine.exe"
def run(blacks, qs):
    p=subprocess.Popen([ENG],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
    def send(c): p.stdin.write(c+"\n"); p.stdin.flush()
    send("size 15"); send("clear")
    for (x,y) in blacks: send("set %d %d b"%(x,y))
    out=[]
    for q in qs:
        send("pat %d %d"%q)
        out.append((q, p.stdout.readline().strip()))
    send("quit")
    return out
# open three (7,5..7) -> playing (7,8) makes an open four (F4?)
for q,line in run([(7,5),(7,6),(7,7)], [(7,8),(7,4)]):
    print("cell",q,"pat:",line)
# open four already: black (7,5..8), pat at (7,4) -> five
for q,line in run([(7,5),(7,6),(7,7),(7,8)], [(7,4),(7,9)]):
    print("cell",q,"pat:",line)
