import subprocess, os, re
import board_tools as bt

ENGINE = r"C:\Users\lin\Desktop\gomoku-vs-go\tools\rapfi\yixin-gui\engine.exe"

def ask(b, off=0, cmd_board="YXBOARD"):
    cmds = ["START %d" % b.size, "INFO rule 2", cmd_board]
    for x in range(b.size):
        for y in range(b.size):
            v = int(b.grid[x, y])
            if v == 1:
                cmds.append("%d,%d,1" % (x + off, y + off))
            elif v == 2:
                cmds.append("%d,%d,2" % (x + off, y + off))
    cmds += ["DONE", "YXSHOWFORBID"]
    out = subprocess.run([ENGINE], input="\n".join(cmds) + "\n", capture_output=True, text=True, timeout=120, cwd=os.path.dirname(ENGINE))
    lines = [l for l in out.stdout.splitlines() if l.strip().upper().startswith("FORBID")]
    return lines, out.stdout

codes = "h9g10g9f7g8g6g7k8i8o15h7n15d10o14e7n14e6o13"
b, _ = bt.board_from_code(codes, size=15, first=bt.BLACK, gomoku=True)

def parse(line, off=0):
    body = line.split(" ", 1)[1].strip() if " " in line else ""
    digits = re.sub(r"[^0-9]", "", body)
    pts = []
    for i in range(0, len(digits) - 3, 4):
        cx = int(digits[i:i+2]) - off; cy = int(digits[i+2:i+4]) - off
        pts.append(bt.coord_to_code(cx, cy, 15))
    return sorted(pts)

for off, cb in ((0, "YXBOARD"),):
    lines, raw = ask(b, off, cb)
    print("off=%d cb=%s lines=%s" % (off, cb, lines))
    for l in lines:
        print("  parsed:", parse(l, off))
print("recorded:", ["e9","f8","f9","h10"])
