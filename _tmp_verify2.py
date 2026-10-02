import subprocess, os, re
import board_tools as bt
RAPFI = r"C:\Users\lin\Desktop\gomoku-vs-go\tools\rapfi\yixin-gui\engine.exe"

def rapfi_forbid(codes, size=15, rule=2):
    toks = bt.split_codes(codes, size)
    stones, color = [], 1
    for t in toks:
        if t in ("p0","pass"): color = 3-color; continue
        x,y = bt.code_to_coord(t,size)
        stones.append((x,y,color)); color = 3-color
    cmds = ["INFO rule %d" % rule, "START %d" % size, "YXBOARD"]
    for (x,y,c) in stones: cmds.append("%d,%d,%d" % (x,y,c))
    if len(stones) % 2 == 1:
        cmds.append("-1,-1,%d" % (3-stones[-1][2]))
    cmds += ["DONE","YXSHOWFORBID"]
    out = subprocess.run([RAPFI], input="\n".join(cmds)+"\n", capture_output=True, text=True, timeout=90, cwd=os.path.dirname(RAPFI))
    lines = [l for l in out.stdout.splitlines() if l.strip().upper().startswith("FORBID")]
    body = lines[-1].split(" ",1)[1].strip()
    d = re.sub(r"[^0-9]", "", body)
    return sorted(bt.coord_to_code(int(d[i:i+2]), int(d[i+2:i+4]), size) for i in range(0, len(d)-3, 4))

cases = {
  "GUI import test (e8 f8 j8 k8, h8 considered)": "e8 o15 f8 o14 j8 o13 k8 o12",
  "two threes in different dirs": "h8 p0 i7 p0 g7 p0 g8",          # h8 played? no: this is the h8-first line
  "test_forbidden two open threes (7,5)(7,6)(5,7)(6,7)": None,
}
print("GUI import position (black e8,f8,j8,k8 + whites):")
print("  rapfi forbid:", rapfi_forbid("e8 o15 f8 o14 j8 o13 k8 o12"))

# build the tests_torus two-open-three board manually via codes:
# black (7,5)=h8? no. x=row from top. (7,5) -> row 8, col f -> f8 ; (7,6) -> g8 ;
# (5,7) -> row 10, col h -> h10 ; (6,7) -> h9
print("tests_torus double-three board (f8 g8 h10 h9, place h8):")
print("  rapfi forbid:", rapfi_forbid("f8 g8 h10 h9"))
# the old rule-book example 0110A0110
print("0110A0110 (black e8 f8 j8 k8):")
print("  rapfi forbid:", rapfi_forbid("e8 f8 j8 k8"))
print("1110A0111 (black d8 e8 f8 j8 k8 l8):")
print("  rapfi forbid:", rapfi_forbid("d8 e8 f8 j8 k8 l8"))
