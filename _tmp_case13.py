import subprocess, os, re
import board_tools as bt

ENGINE = r"C:\Users\lin\Desktop\gomoku-vs-go\tools\rapfi\yixin-gui\engine.exe"
PROJ = "cpp/build/engine.exe"

def rapfi_forbid(codes, size=15, rule=2):
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
    body = lines[-1].split(" ", 1)[1].strip()
    digits = re.sub(r"[^0-9]", "", body)
    return sorted(bt.coord_to_code(int(digits[i:i+2]), int(digits[i+2:i+4]), size)
                  for i in range(0, len(digits)-3, 4))

def proj_forbid(codes, size=15):
    b, _ = bt.board_from_code(codes, size=size, first=bt.BLACK, gomoku=True)
    p = subprocess.Popen([PROJ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
    def send(c):
        p.stdin.write(c + "\n"); p.stdin.flush()
    send("size %d" % size); send("clear")
    for x in range(size):
        for y in range(size):
            v = int(b.grid[x, y])
            if v == 1: send("set %d %d b" % (x, y))
            elif v == 2: send("set %d %d w" % (x, y))
            elif v == 3: send("set %d %d o" % (x, y))
    send("checkforbidden")
    out = []
    while True:
        line = p.stdout.readline().strip()
        if line == "end": break
        a, bb = line.split()
        out.append(bt.coord_to_code(int(a), int(bb), size))
    send("quit")
    return sorted(out)

cases = {
 "case13": "h9 i9 i8 j7 i7 f11 i6 f6 h6 p0 f10 p0 f9 p0 f8 p0 f7",
 "case14": "h9g10g9f7g8g6g7k8i8o15h7n15d10o14e7n14e6o13",
 "case8typo": "h9 f11 g10 j9 j10 j7 i8 p0 g8 p0 h7 p0 k8",
}
for name, codes in cases.items():
    print(name)
    print("  rapfi :", rapfi_forbid(codes))
    print("  engine:", proj_forbid(codes))
