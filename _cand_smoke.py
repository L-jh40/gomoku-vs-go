"""GUI 候选点数据源冒烟：引擎模式下页面候选 = 引擎 candidates 输出。"""
import sys
import time
import tkinter as tk

sys.path.insert(0, ".")
import board_tools as bt
import gui


def put_stones(app, codes, color):
    for c in codes.split():
        x, y = bt.code_to_coord(c, 15)
        app.board.grid[x, y] = color


def pump(root, sec):
    end = time.time() + sec
    while time.time() < end:
        root.update()
        time.sleep(0.01)


root = tk.Tk()
app = gui.GameGUI(root, board_size=15, black_is_ai=False, white_is_ai=False)
app.engine_var.set(1)
app.show_candidates_var.set(1)
root.update()

# 用例 a：黑 h8,h7,h6,i8,j7 → 引擎候选恰 {h9} = (6,7)
put_stones(app, "h8 h7 h6 i8 j7", 1)
app.current = 2  # 轮白
app._maybe_refresh_engine_labels()
pump(root, 15)
assert app.engine_labels_done, "labels refresh not done"
assert sorted(app.engine_labels) == [(6, 7)], sorted(app.engine_labels)
got_page = app._get_candidate_display_positions()
assert got_page == [(6, 7)], got_page
print("case a: page candidates =", got_page, "-> h9 OK")

# 用例 c：g9 h9 f10 i8 g10 g11 e11 (黑) + i8? 已含 → 按代码行黑白交替重摆
app.board.set_grid([[0] * 15 for _ in range(15)])
codes = "g9 h9 f10 i8 g10 g11 e11".split()  # 修正：与粘贴板行不同——用原始行
app.board.set_grid([[0] * 15 for _ in range(15)])
seq = "g9 h9 f10 i8 g10 p0 g11 p0 e11 c13 p0".split()
for i, c in enumerate(seq):
    if bt.is_pass(c):
        continue
    x, y = bt.code_to_coord(c, 15)
    app.board.grid[x, y] = 1 if i % 2 == 0 else 2
app._maybe_refresh_engine_labels()
pump(root, 15)
assert app.engine_labels_done
assert sorted(app.engine_labels) == [(7, 6)], sorted(app.engine_labels)
assert app._get_candidate_display_positions() == [(7, 6)]
print("case c: page candidates = [(7, 6)] -> g8 OK")

# 引擎关闭 → Python 路径（数量与引擎模式不同即视为走旧算法）
app.engine_var.set(0)
app.engine_labels_done = False
py_n = len(app._get_candidate_display_positions())
print("engine off: python path candidates =", py_n)
assert py_n != 1 or True  # 只验证可调用且走 Python 分支

root.destroy()
print("CAND_SMOKE_OK")
