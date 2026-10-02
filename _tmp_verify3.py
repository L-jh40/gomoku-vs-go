import subprocess, os, re
import board_tools as bt
RAPFI = r"C:\Users\lin\Desktop\gomoku-vs-go\tools\rapfi\yixin-gui\engine.exe"
DUMMY = [(14,0),(14,1),(14,2),(14,3),(14,4),(14,5),(14,6),(14,7)]

def rapfi(blacks, whites):
    cmds = ["INFO rule 2", "START 15", "YXBOARD"]
    for (x,y) in blacks: cmds.append("%d,%d,1" % (x,y))
    for (x,y) in whites: cmds.append("%d,%d,2" % (x,y))
    if (len(blacks)+len(whites)) % 2 == 1:
        cmds.append("-1,-1,%d" % (1 if len(blacks) > len(whites) else 2))
    cmds += ["DONE","YXSHOWFORBID"]
    out = subprocess.run([RAPFI], input="\n".join(cmds)+"\n", capture_output=True, text=True, timeout=90, cwd=os.path.dirname(RAPFI))
    lines = [l for l in out.stdout.splitlines() if l.strip().upper().startswith("FORBID")]
    body = lines[-1].split(" ",1)[1].strip()
    d = re.sub(r"[^0-9]", "", body)
    return sorted(bt.coord_to_code(int(d[i:i+2]), int(d[i+2:i+4]), 15) for i in range(0, len(d)-3, 4))

tests = {
  "double-three two dirs (place h8)": ([(7,5),(7,6),(5,7),(6,7)], None),
  "0110A0110 (place h8)": ([(7,4),(7,5),(7,9),(7,10)], None),
  "1110A0111 (place h8)": ([(7,3),(7,4),(7,5),(7,9),(7,10),(7,11)], None),
  "two fours two dirs (place h8)": ([(7,4),(7,5),(7,6),(4,7),(5,7),(6,7)], None),
  "user position": ([(7,8),(6,6),(7,6),(8,6),(8,8),(9,7),(5,3),(8,4),(9,4)],
                    [(5,6),(8,5),(9,6),(7,10),(0,14),(0,13),(1,14),(1,13),(2,14)]),
}
for name, (bl, wh) in tests.items():
    w = wh if wh is not None else DUMMY[: (len(bl) if len(bl) % 2 == 0 else len(bl)+1)]
    if (len(bl)+len(w)) % 2 == 1:
        w = w + [DUMMY[len(w)]]
    print("%-34s rapfi forbid: %s" % (name, rapfi(bl, w)))
