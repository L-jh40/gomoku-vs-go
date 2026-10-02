import subprocess, os, re
RAPFI = r"C:\Users\lin\Desktop\gomoku-vs-go\tools\rapfi\yixin-gui\engine.exe"
cmds = ["INFO rule 2", "START 15", "YXBOARD",
        "7,7,1", "7,7,1",  # placeholder replaced below
        ]
cmds = ["INFO rule 2", "START 15", "YXBOARD"]
# case1: black h8(7,7)? compute: h8 -> x=15-8=7, y=7 ; i7 -> x=8,y=8 ; g7->x=8,y=6 ; g8->x=7,y=6
for (x,y,c) in [(7,7,1),(8,8,1),(8,6,1),(7,6,1)]:
    cmds.append("%d,%d,%d" % (x,y,c))
cmds += ["-1,-1,2", "DONE", "YXSHOWFORBID"]
out = subprocess.run([RAPFI], input="\n".join(cmds) + "\n", capture_output=True, text=True, timeout=60, cwd=os.path.dirname(RAPFI))
print(out.stdout)
