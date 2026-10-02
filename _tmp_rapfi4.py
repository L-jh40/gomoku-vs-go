import subprocess, os, re
import board_tools as bt
codes = "h9g10g9f7g8g6g7k8i8o15h7n15d10o14e7n14e6o13"
b, _ = bt.board_from_code(codes, size=15, first=bt.BLACK, gomoku=True)
ENGINE = r"C:\Users\lin\Desktop\gomoku-vs-go\tools\rapfi\yixin-gui\engine.exe"
cmds = ["START 15", "INFO rule 2", "BOARD"]
for x in range(b.size):
    for y in range(b.size):
        v = int(b.grid[x, y])
        if v == 1:
            cmds.append("%d,%d,1" % (x, y))
        elif v == 2:
            cmds.append("%d,%d,2" % (x, y))
cmds += ["DONE", "YXSHOWFORBID"]
print("CMDS:", cmds[:5], "...", cmds[-3:])
out = subprocess.run([ENGINE], input="\n".join(cmds) + "\n", capture_output=True, text=True, timeout=120, cwd=os.path.dirname(ENGINE))
print("=== full stdout ===")
print(out.stdout)
print("=== stderr ===")
print(out.stderr[:3000])
