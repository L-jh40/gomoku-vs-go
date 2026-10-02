import subprocess, os, re
ENGINE = r"C:\Users\lin\Desktop\gomoku-vs-go\tools\rapfi\yixin-gui\engine.exe"

def query(seq, size=15, rule=2):
    # seq: list of (x, y, color) already in alternating order
    cmds = ["START %d" % size, "INFO rule %d" % rule, "YXBOARD"]
    for (x, y, c) in seq:
        cmds.append("%d,%d,%d" % (x, y, c))
    cmds += ["DONE", "YXSHOWFORBID"]
    out = subprocess.run([ENGINE], input="\n".join(cmds) + "\n", capture_output=True, text=True, timeout=60, cwd=os.path.dirname(ENGINE))
    lines = [l for l in out.stdout.splitlines() if l.strip().upper().startswith("FORBID")]
    return lines, out.stdout

# three-three test: black (7,5),(7,6),(5,7),(6,7); black to move
seq = [(7,5,1),(0,0,2),(7,6,1),(0,1,2),(5,7,1),(0,2,2),(6,7,1)]
lines, raw = query(seq)
print("3-3 test lines:", lines)
print("raw tail:", raw.splitlines()[-6:])
