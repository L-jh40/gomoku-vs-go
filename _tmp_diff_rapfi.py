"""Differential test: project engine checkforbidden vs real Rapfi yxshowforbid."""
import os, random, re, subprocess, sys

RAPFI = r"C:\Users\lin\Desktop\gomoku-vs-go\tools\rapfi\yixin-gui\engine.exe"
PROJ = "cpp/build/engine.exe"
SIZE = 15

class Rapfi:
    def __init__(self):
        self.p = subprocess.Popen([RAPFI], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True, bufsize=1,
                                  cwd=os.path.dirname(RAPFI))
        self.send("INFO rule 2")
        self.send("START %d" % SIZE)
    def send(self, s):
        self.p.stdin.write(s + "\n"); self.p.stdin.flush()
    def read_until_forbid(self):
        while True:
            line = self.p.stdout.readline()
            if line == "":
                raise RuntimeError("rapfi closed")
            s = line.strip()
            if s.upper().startswith("FORBID"):
                return s
    def forbid(self, blacks, whites):
        self.send("YXBOARD")
        # all blacks first, then whites: the engine auto-inserts passes so the
        # final ply count is even -> black to move.
        for (x, y) in blacks:
            self.send("%d,%d,1" % (x, y))
        for (x, y) in whites:
            self.send("%d,%d,2" % (x, y))
        self.send("DONE")
        self.send("YXSHOWFORBID")
        line = self.read_until_forbid()
        body = line.split(" ", 1)[1].strip()
        digits = re.sub(r"[^0-9]", "", body)
        return {(int(digits[i:i+2]), int(digits[i+2:i+4])) for i in range(0, len(digits)-3, 4)}
    def close(self):
        try:
            self.send("END"); self.p.wait(timeout=5)
        except Exception:
            self.p.kill()

class Proj:
    def __init__(self):
        self.p = subprocess.Popen([PROJ], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True, bufsize=1)
    def send(self, s):
        self.p.stdin.write(s + "\n"); self.p.stdin.flush()
    def forbid(self, blacks, whites):
        self.send("size %d" % SIZE); self.send("clear")
        for (x, y) in blacks: self.send("set %d %d b" % (x, y))
        for (x, y) in whites: self.send("set %d %d w" % (x, y))
        self.send("checkforbidden")
        out = set()
        while True:
            line = self.p.stdout.readline().strip()
            if line == "end": break
            a, b = line.split()
            out.add((int(a), int(b)))
        return out
    def close(self):
        try:
            self.send("quit"); self.p.wait(timeout=5)
        except Exception:
            self.p.kill()

def gen(rng):
    n = rng.randint(3, 26)
    cells = set()
    while len(cells) < n:
        # bias to a central box so shapes actually touch
        x = rng.randint(3, 11); y = rng.randint(3, 11)
        cells.add((x, y))
    cells = list(cells)
    rng.shuffle(cells)
    blacks = [c for c in cells if rng.random() < 0.5]
    whites = [c for c in cells if c not in blacks]
    if not blacks:
        blacks, whites = [whites[0]], whites[1:]
    return blacks, whites

def main():
    rng = random.Random(int(sys.argv[1]) if len(sys.argv) > 1 else 12345)
    N = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    rap, proj = Rapfi(), Proj()
    mism = []
    tried = 0
    try:
        for i in range(N):
            blacks, whites = gen(rng)
            tried += 1
            a = rap.forbid(blacks, whites)
            b = proj.forbid(blacks, whites)
            if a != b:
                mism.append((blacks, whites, sorted(a), sorted(b)))
    finally:
        rap.close(); proj.close()
    print("positions=%d  mismatches=%d" % (tried, len(mism)))
    for (bl, wh, a, b) in mism[:8]:
        print("  rapfi=%s engine=%s" % (a, b))
        print("    blacks=%s" % sorted(bl))
        print("    whites=%s" % sorted(wh))
    return 1 if mism else 0

if __name__ == "__main__":
    sys.exit(main())
