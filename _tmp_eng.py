# -*- coding: utf-8 -*-
import os, subprocess
APP = r"C:\Users\lin\Desktop\gomoku-vs-go\gomoku-vs-go2"
ENGINE = os.path.join(APP, "cpp", "build", "engine.exe")

def run(cmds, label):
    out = subprocess.run([ENGINE], input=chr(10).join(cmds) + chr(10),
                         capture_output=True, text=True, timeout=60)
    print("=== %s ===" % label)
    print("rc=%s" % out.returncode)
    print(out.stdout.strip()[:800])
    if out.stderr.strip():
        print("STDERR:", out.stderr.strip()[:300])
    print()

# case 1: black h9? no: h8=(7,7) b, i7? code i7 -> (8,8) white? compute properly
sys_path = APP
import sys
sys.path.insert(0, APP)
import board_tools as bt
from board import BLACK, WHITE
block, board, info, fouls = bt.position_block("h8 p0 i7 p0 g7 p0 g8", size=15, gomoku=True)
print(bt.render(board))
print("python fouls:", [c for c, _t in fouls])
sets = []
for x in range(board.size):
    for y in range(board.size):
        v = int(board.grid[x, y])
        if v == BLACK:
            sets.append("set %d %d b" % (x, y))
        elif v == WHITE:
            sets.append("set %d %d w" % (x, y))
run(["size 15"] + sets + ["checkforbidden", "quit"], "set + checkforbidden")
run(["size 15", "play b 7 7", "play w 7 8", "play b 7 6", "checkforbidden", "quit"], "play x3 + checkforbidden")
run(["size 15", "help", "quit"], "help")
