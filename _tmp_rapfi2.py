import subprocess, os
import board_tools as bt
codes = "h9g10g9f7g8g6g7k8i8o15h7n15d10o14e7n14e6o13"
b, _ = bt.board_from_code(codes, size=15, first=bt.BLACK, gomoku=True)
ENGINE = r"C:\Users\lin\Desktop\gomoku-vs-go\tools\rapfi\yixin-gui\engine.exe"
cmds = ["start 15", "INFO rule 2", "board"]
for x in range(b.size):
    for y in range(b.size):
        v = int(b.grid[x, y])
        if v == 1:
            cmds.append("%d,%d,1" % (x + 1, y + 1))
        elif v == 2:
            cmds.append("%d,%d,2" % (x + 1, y + 1))
cmds += ["done", "thinking stop", "yxshowforbid"]
out = subprocess.run([ENGINE], input="\n".join(cmds) + "\n", capture_output=True, text=True, timeout=120, cwd=os.path.dirname(ENGINE))
print("RC", out.returncode)
print("STDOUT:")
print(out.stdout)
print("STDERR:")
print(out.stderr[:2000])
