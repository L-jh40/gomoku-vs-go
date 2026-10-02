import subprocess
from board import HybridBoard, BLACK, WHITE, EMPTY, OBSTACLE
import board_tools as bt

def run(board, cmds):
    p = subprocess.Popen(["cpp/build/engine.exe"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
    def send(c):
        p.stdin.write(c + "\n"); p.stdin.flush()
    def rd():
        return p.stdout.readline().rstrip("\r\n")
    send("size %d" % board.size); send("clear")
    for x in range(board.size):
        for y in range(board.size):
            v = int(board.grid[x, y])
            if v == BLACK: send("set %d %d b" % (x, y))
            elif v == WHITE: send("set %d %d w" % (x, y))
            elif v == OBSTACLE: send("set %d %d o" % (x, y))
    out = []
    for c in cmds:
        send(c)
        if c == "dump":
            for _ in range(board.size):
                out.append(rd())
        elif c == "checkforbidden":
            while True:
                line = rd()
                if line == "end": break
                out.append(line)
        else:
            out.append(rd())
    send("quit")
    p.wait()
    return out

codes = "h9g10g9f7g8g6g7k8i8o15h7n15d10o14e7n14e6o13"
b, _ = bt.board_from_code(codes, size=15, first=bt.BLACK, gomoku=True)
res = run(b, ["dump", "checkforbidden"])
for i in range(15):
    print(res[i])
print("engine forbidden:", res[15:])
print("python forbid (from above):", sorted([(4,8),(5,7),(5,8),(7,9),(7,7)]))
# print the board as the project sees it
for x in range(15):
    print("".join({0:".",1:"X",2:"O",3:"#"}[int(b.grid[x,y])] for y in range(15)))
