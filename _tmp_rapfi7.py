import subprocess, os, re
ENGINE = r"C:\Users\lin\Desktop\gomoku-vs-go\tools\rapfi\yixin-gui\engine.exe"

def query(seq, size=15, rule=2):
    cmds = ["INFO rule %d" % rule, "START %d" % size, "YXBOARD"]
    for (x, y, c) in seq:
        cmds.append("%d,%d,%d" % (x, y, c))
    cmds += ["DONE", "YXSHOWFORBID"]
    out = subprocess.run([ENGINE], input="\n".join(cmds) + "\n", capture_output=True, text=True, timeout=60, cwd=os.path.dirname(ENGINE))
    lines = [l for l in out.stdout.splitlines() if l.strip().upper().startswith("FORBID")]
    return lines, out.stdout

# 3-3 test: black (7,5),(7,6),(5,7),(6,7), white 4 far, 8 tokens -> black to move
seq = [(7,5,1),(0,0,2),(7,6,1),(0,1,2),(5,7,1),(0,2,2),(6,7,1),(0,3,2)]
lines, raw = query(seq)
print("lines:", lines)
print("tail:", raw.splitlines()[-4:])
