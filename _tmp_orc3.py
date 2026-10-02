import subprocess, os, re
import board_tools as bt
RAPFI = r"C:\Users\lin\Desktop\gomoku-vs-go\tools\rapfi\yixin-gui\engine.exe"

def rapfi_forbid(stones, total_moves, size=15, rule=2):
    next_color = 3 - stones[-1][2]
    cmds = ["INFO rule %d" % rule, "START %d" % size, "YXBOARD"]
    for (x, y, c) in stones:
        cmds.append("%d,%d,%d" % (x, y, c))
    if total_moves % 2 == 1:
        cmds.append("-1,-1,%d" % next_color)
    cmds += ["DONE", "YXSHOWFORBID"]
    out = subprocess.run([RAPFI], input="\n".join(cmds) + "\n", capture_output=True, text=True, timeout=120, cwd=os.path.dirname(RAPFI))
    lines = [l for l in out.stdout.splitlines() if l.strip().upper().startswith("FORBID")]
    body = lines[-1].split(" ", 1)[1].strip()
    digits = re.sub(r"[^0-9]", "", body)
    return sorted(bt.coord_to_code(int(digits[i:i+2]), int(digits[i+2:i+4]), size)
                  for i in range(0, len(digits)-3, 4))

def build(codes, use_passes=True):
    toks = bt.split_codes(codes, 15)
    stones, color, passes = [], 1, 0
    for t in toks:
        if t in ("p0", "pass"):
            if use_passes:
                passes += 1; color = 3 - color
            continue
        x, y = bt.code_to_coord(t, 15)
        stones.append((x, y, color)); color = 3 - color
    total = len(stones) + passes if use_passes else len(stones)
    return stones, total, passes

codes12 = "h9 i9 i8 j7 i7 f11 i6 f6 h6 p0 f10 p0 f9 p0 f8 p0 f7"
s, t, p = build(codes12)
print("with passes: stones=%d total=%d passes=%d" % (len(s), t, p))
print("  rapfi:", rapfi_forbid(s, t))
s2, t2, p2 = build(codes12, use_passes=False)
print("ignoring p0 (pure alternation): stones=%d" % len(s2))
print("  rapfi:", rapfi_forbid(s2, t2))
print("  recorded: ['g9', 'h8', 'h9']")
