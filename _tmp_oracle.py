import subprocess, os, re
import board_tools as bt

RAPFI = r"C:\Users\lin\Desktop\gomoku-vs-go\tools\rapfi\yixin-gui\engine.exe"
PROJ = "cpp/build/engine.exe"

def rapfi_board_forbid(stones, size=15, rule=2):
    """stones: list of (x, y, color) in true game order (1=black,2=white)."""
    next_color = 1
    for (_x, _y, c) in stones:
        next_color = 3 - c
    cmds = ["INFO rule %d" % rule, "START %d" % size, "YXBOARD"]
    for (x, y, c) in stones:
        cmds.append("%d,%d,%d" % (x, y, c))
    # make black to move: append a pass of the color whose turn it is
    if len(stones) % 2 == 1:
        cmds.append("-1,-1,%d" % next_color)
    cmds += ["DONE", "YXSHOWFORBID"]
    out = subprocess.run([RAPFI], input="\n".join(cmds) + "\n", capture_output=True, text=True, timeout=120, cwd=os.path.dirname(RAPFI))
    lines = [l for l in out.stdout.splitlines() if l.strip().upper().startswith("FORBID")]
    body = lines[-1].split(" ", 1)[1].strip()
    digits = re.sub(r"[^0-9]", "", body)
    return sorted(bt.coord_to_code(int(digits[i:i+2]), int(digits[i+2:i+4]), size)
                  for i in range(0, len(digits)-3, 4))

def proj_forbid(stones, size=15):
    grid = [[0]*size for _ in range(size)]
    for (x, y, c) in stones:
        grid[x][y] = c
    p = subprocess.Popen([PROJ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
    def send(c):
        p.stdin.write(c + "\n"); p.stdin.flush()
    send("size %d" % size); send("clear")
    for x in range(size):
        for y in range(size):
            v = grid[x][y]
            if v: send("set %d %d %s" % (x, y, {1:"b",2:"w"}[v]))
    send("checkforbidden")
    out = []
    while True:
        line = p.stdout.readline().strip()
        if line == "end": break
        a, b2 = line.split()
        out.append(bt.coord_to_code(int(a), int(b2), size))
    send("quit")
    return sorted(out)

def parse_file(path):
    """Return [(codes, forbid_str)] with the forbid label typo tolerated."""
    cases = []
    pending = None
    for raw in open(path, encoding="utf-8"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        low = line.lower()
        if re.match(r"^f[oa]?r?b?id\s*[:=]", low) or low.startswith("forbid"):
            if pending is not None:
                pending["forbid"] = line.split(":", 1)[1].strip() if ":" in line else line.split("=",1)[1].strip()
                cases.append(pending); pending = None
            continue
        if pending is not None:
            cases.append(pending)
        pending = {"codes": line, "forbid": ""}
    if pending is not None: cases.append(pending)
    return cases

codes_path = os.path.join("导出", "粘贴板.md")
cases = parse_file(codes_path)
print("parsed", len(cases), "cases")
for i, c in enumerate(cases):
    toks = bt.split_codes(c["codes"], 15)
    stones = []
    color = 1
    for t in toks:
        if t in ("p0", "pass"):
            color = 3 - color
            continue
        x, y = bt.code_to_coord(t, 15)
        stones.append((x, y, color)); color = 3 - color
    recorded = sorted(bt.forbidden_list(c["forbid"]))
    rap = rapfi_board_forbid(stones)
    proj = proj_forbid(stones)
    ok_r = "OK " if rap == recorded else "DIFF"
    ok_p = "OK " if proj == recorded else "DIFF"
    print("%2d stones=%2d passes=%2d  rapfi=%s engine=%s  rec=%s" % (i+1, len(stones), len(toks)-len(stones), ok_r, ok_p, recorded))
    if rap != recorded:
        print("      rapfi  :", rap)
    if proj != recorded:
        print("      engine :", proj)
