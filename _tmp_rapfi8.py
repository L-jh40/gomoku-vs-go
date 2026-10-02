import subprocess, os, re, sys
import board_tools as bt
ENGINE = r"C:\Users\lin\Desktop\gomoku-vs-go\tools\rapfi\yixin-gui\engine.exe"

def query_codes(codes, size=15, rule=2):
    toks = bt.split_codes(codes, size)
    cmds = ["INFO rule %d" % rule, "START %d" % size, "YXBOARD"]
    color = 1
    for t in toks:
        if t in ("p0", "pass"):
            color = 3 - color
            continue
        x, y = bt.code_to_coord(t, size)
        cmds.append("%d,%d,%d" % (x, y, color))
        color = 3 - color
    cmds += ["DONE", "YXSHOWFORBID"]
    out = subprocess.run([ENGINE], input="\n".join(cmds) + "\n", capture_output=True, text=True, timeout=60, cwd=os.path.dirname(ENGINE))
    lines = [l for l in out.stdout.splitlines() if l.strip().upper().startswith("FORBID")]
    if not lines:
        return None
    body = lines[-1].split(" ", 1)[1].strip()
    digits = re.sub(r"[^0-9]", "", body)
    pts = []
    for i in range(0, len(digits) - 3, 4):
        cx = int(digits[i:i+2]); cy = int(digits[i+2:i+4])
        pts.append(bt.coord_to_code(cx, cy, size))
    return sorted(pts)

codes = "h9g10g9f7g8g6g7k8i8o15h7n15d10o14e7n14e6o13"
print("engine forbid:", query_codes(codes))
print("recorded    :", ["e9","f8","f9","h10"])
b, _ = bt.board_from_code(codes, size=15, first=bt.BLACK, gomoku=True)
print("project     :", sorted(c for c,_ in bt.forbidden_codes(b)))
