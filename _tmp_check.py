# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r"C:\Users\lin\Desktop\gomoku-vs-go\gomoku-vs-go2")
import numpy as np
import board_tools as bt
from board import HybridBoard, BLACK, WHITE, EMPTY, OBSTACLE

# consistent pass scenario: after 2 stones it is black's turn, black passes
b = HybridBoard(15)
seq = [(BLACK,0,0),(WHITE,0,1),(WHITE,5,5),(BLACK,6,6),(BLACK,7,7),(WHITE,7,8)]
for c,x,y in seq:
    if c == BLACK:
        ok,cap = b.play_black(x,y,check_rules=False)
    else:
        ok,cap = b.play_white(x,y)
    assert ok, (x,y)
passes = [2]
codes = bt.moves_from_board(b, passes)
print("moves:", codes)
txt = bt.board_to_text(b, pass_records=passes)
open("_tmp_dump.txt","w",encoding="utf-8").write(txt)
b2, named = bt.load_board("_tmp_dump.txt")
print("same grid:", np.array_equal(b.grid, b2.grid), "same captured:", b.captured_count == b2.captured_count, "turn:", b.turn, b2.turn)
print("errors:", b2.import_errors)

# trailing pass
b3 = HybridBoard(15)
b3.play_black(7,7,check_rules=False); b3.play_white(7,8)
print("trailing pass moves:", bt.moves_from_board(b3, [2]))

# capture round trip
b4 = HybridBoard(15)
for c,x,y in [(BLACK,0,0),(WHITE,0,1),(BLACK,5,5),(WHITE,1,0),(BLACK,9,9)]:
    (b4.play_black(x,y,check_rules=False) if c==BLACK else b4.play_white(x,y))
t4 = bt.board_to_text(b4)
open("_tmp_dump2.txt","w",encoding="utf-8").write(t4)
b5,_ = bt.load_board("_tmp_dump2.txt")
print("capture round trip grid:", np.array_equal(b4.grid,b5.grid), "captured:", b4.captured_count==b5.captured_count, b5.captured_count)

# torus header round trip
b6 = HybridBoard(15); b6.torus = True; b6.play_black(0,0,check_rules=False)
open("_tmp_dump3.txt","w",encoding="utf-8").write(bt.board_to_text(b6))
b7,_ = bt.load_board("_tmp_dump3.txt")
print("torus reload:", b7.torus, np.array_equal(b6.grid,b7.grid))

# obstacle header round trip (obstacles are not moves)
b8 = HybridBoard(15); b8.play_black(7,7,check_rules=False)
b8.grid[3,3] = OBSTACLE; b8._invalidate_caches()
t8 = bt.board_to_text(b8)
print([l for l in t8.split(chr(10)) if l.startswith("#")])
open("_tmp_dump4.txt","w",encoding="utf-8").write(t8)
b9,_ = bt.load_board("_tmp_dump4.txt")
print("obstacle reload:", b9.grid[3,3]==OBSTACLE, np.array_equal(b8.grid,b9.grid))
print("ALL_OK")
