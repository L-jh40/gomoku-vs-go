import subprocess, os, re
import board_tools as bt
ENGINE = r"C:\Users\lin\Desktop\gomoku-vs-go\tools\rapfi\yixin-gui\engine.exe"

def engine_forbid(seq, size=15, rule=2):
    cmds = ["INFO rule %d" % rule, "START %d" % size, "YXBOARD"]
    for (x, y, c) in seq:
        cmds.append("%d,%d,%d" % (x, y, c))
    cmds += ["DONE", "YXSHOWFORBID"]
    out = subprocess.run([ENGINE], input="\n".join(cmds) + "\n", capture_output=True, text=True, timeout=60, cwd=os.path.dirname(ENGINE))
    lines = [l for l in out.stdout.splitlines() if l.strip().upper().startswith("FORBID")]
    if not lines: return None
    body = lines[-1].split(" ", 1)[1].strip()
    digits = re.sub(r"[^0-9]", "", body)
    return sorted(bt.coord_to_code(int(digits[i:i+2]), int(digits[i+2:i+4]), size)
                  for i in range(0, len(digits)-3, 4))

base = "h9g10g9f7g8g6g7k8i8o15h7n15d10o14e7n14e6o13"
toks = bt.split_codes(base, 15)
b0, _ = bt.board_from_code(base, size=15, first=bt.BLACK, gomoku=True)
# rebuild strict alternating sequence from the game order
seq = []
color = 1
for t in toks:
    x, y = bt.code_to_coord(t, 15)
    seq.append((x, y, color)); color = 3 - color

def c(code):
    return bt.code_to_coord(code, 15)

d1 = (14, 0)  # a1
d2 = (14, 1)  # b1
print("base forbidden:", engine_forbid(seq))
print("base+h8+dummyW :", engine_forbid(seq + [c("h8") + (1,), d1 + (2,)]))
print("base+h8+dW+f8+dW:", engine_forbid(seq + [c("h8") + (1,), d1 + (2,), c("f8") + (1,), d2 + (2,)]))
print("base+f8+dW     :", engine_forbid(seq + [c("f8") + (1,), d1 + (2,)]))
