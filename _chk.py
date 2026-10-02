import subprocess, sys, os
ENG = "cpp/build/engine.exe"
PAT = {0:"DEAD",1:"OL",2:"B1",3:"F1",4:"B2",5:"F2",6:"F2A",7:"F2B",8:"B3",9:"B3S",10:"F3",11:"F3S",12:"B4",13:"B4S",14:"F4",15:"F5"}
P4 = {0:"NONE",1:"FORBID",2:"L_FLEX2",3:"K_BLOCK3",4:"J_FLEX2_2X",5:"I_BLOCK3_PLUS",6:"H_FLEX3",7:"G_FLEX3_PLUS",8:"F_FLEX3_2X",9:"E_BLOCK4",10:"D_BLOCK4_PLUS",11:"C_BLOCK4_FLEX3",12:"B_FLEX4",13:"A_FIVE"}
import board_tools as bt

def run(codes, cmds):
    b,_ = bt.board_from_code(codes, size=15, first=bt.BLACK, gomoku=True)
    p = subprocess.Popen([ENG], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
    def send(c):
        p.stdin.write(c+"\n"); p.stdin.flush()
    send("size 15"); send("clear")
    for x in range(15):
        for y in range(15):
            v = int(b.grid[x,y])
            if v==1: send("set %d %d b" % (x,y))
            elif v==2: send("set %d %d w" % (x,y))
    out=[]
    for c in cmds:
        send(c)
        if c.startswith("pat"):
            line = p.stdout.readline().strip()
            vals=[int(v) for v in line.split()[:8]]
            out.append("pat %s: dirs=%s p4=%s fours=%d threes=%d forbid=%d" % (c[4:], [PAT.get(v,v) for v in vals[:4]], P4.get(vals[4],vals[4]), vals[5], vals[6], vals[7]))
        elif c.startswith("candidates"):
            while True:
                l = p.stdout.readline().strip()
                if l=="end": break
                out.append("cand "+l)
    send("quit")
    return out

print("=== case2 position ===")
for line in run("h8 p0 g7 p0 j10 p0 l12", ["candidates w 11 5"]):
    print(" ", line)
print("=== pat at i9 (6,8) ===")
for line in run("h8 p0 g7 p0 j10 p0 l12", ["pat 6 8", "pat 5 9"]):
    print(" ", line)
