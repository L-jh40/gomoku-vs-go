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
out = subprocess.run([ENGINE], input="\n".join(cmds) + "\n", capture_output=True, text=True, timeout=120, cwd=os.path.dirname(ENGINE))
for line in out.stdout.splitlines():
    if line.startswith("FORBID") or "FORBID" in line.upper():
        print("RAW:", repr(line))
        body = line.split(" ", 1)[1].strip() if " " in line else ""
        digits = re.sub(r"[^0-9]", "", body)
        pts = []
        for i in range(0, len(digits) - 3, 4):
            cx = int(digits[i:i+2]); cy = int(digits[i+2:i+4])
            pts.append(bt.coord_to_code(cx, cy, 15))
        print("forbid:", sorted(pts))
print("--- recorded:", ["e9","f8","f9","h10"])
print("--- project :", sorted(c for c,_ in bt.forbidden_codes(b)))
