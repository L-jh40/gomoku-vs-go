import subprocess, os, re
import board_tools as bt

RAPFI_DIR = r"C:\Users\lin\Desktop\gomoku-vs-go\tools\rapfi"
cands = [
  os.path.join(RAPFI_DIR, "yixin-gui", "engine.exe"),
  os.path.join(RAPFI_DIR, "engine", "pbrain-rapfi-windows-sse.exe"),
  os.path.join(RAPFI_DIR, "engine", "pbrain-rapfi-windows-avx2.exe"),
  os.path.join(RAPFI_DIR, "engine", "pbrain-rapfi-windows-avx512.exe"),
  os.path.join(RAPFI_DIR, "engine", "pbrain-rapfi-windows-avx512vnni.exe"),
  os.path.join(RAPFI_DIR, "engine", "pbrain-rapfi-windows-avxvnni.exe"),
]

def query(engine, stones, size=15, rule=2, cwd=None, extra_pass=True):
    next_color = 3 - stones[-1][2]
    cmds = ["INFO rule %d" % rule, "START %d" % size, "YXBOARD"]
    for (x,y,c) in stones:
        cmds.append("%d,%d,%d" % (x,y,c))
    if len(stones) % 2 == 1 and extra_pass:
        cmds.append("-1,-1,%d" % next_color)
    cmds += ["DONE", "YXSHOWFORBID"]
    try:
        out = subprocess.run([engine], input="\n".join(cmds)+"\n", capture_output=True, text=True, timeout=120, cwd=cwd or os.path.dirname(engine))
    except Exception as e:
        return "ERR " + str(e)
    lines = [l for l in out.stdout.splitlines() if l.strip().upper().startswith("FORBID")]
    if not lines:
        return "NO-FORBID-LINE rc=%s out=%s" % (out.returncode, out.stdout[-200:])
    body = lines[-1].split(" ",1)[1].strip()
    digits = re.sub(r"[^0-9]", "", body)
    return sorted(bt.coord_to_code(int(digits[i:i+2]), int(digits[i+2:i+4]), size)
                  for i in range(0, len(digits)-3, 4))

def stones_from(codes):
    toks = bt.split_codes(codes, 15)
    stones, color = [], 1
    for t in toks:
        if t in ("p0","pass"):
            color = 3 - color; continue
        x,y = bt.code_to_coord(t, 15)
        stones.append((x,y,color)); color = 3-color
    return stones

c12 = stones_from("h9 i9 i8 j7 i7 f11 i6 f6 h6 p0 f10 p0 f9 p0 f8 p0 f7")
c14 = stones_from("h9g10g9f7g8g6g7k8i8o15h7n15d10o14e7n14e6o13")
print("case12 expect recorded ['g9','h8','h9']; case14 expect ['e9','f8','f9','h10']")
for e in cands:
    if not os.path.exists(e):
        print("missing", e); continue
    print(os.path.basename(e), "case12:", query(e, c12), " case14:", query(e, c14))
