import sys, time, tkinter as tk
sys.path.insert(0, ".")
import board_tools as bt

import engine_client as _ec
_orig_cand = _ec.EngineClient.candidates
def _logged(self, *a, **k):
    import time as _t
    _t0 = _t.time()
    try:
        r = _orig_cand(self, *a, **k)
        print("[cand] %.2fs -> %d labels" % (_t.time() - _t0, len(r) if r else 0), flush=True)
        return r
    except _ec.EngineError as e:
        print("[cand] %.2fs -> EngineError: %s" % (_t.time() - _t0, e), flush=True)
        raise
_ec.EngineClient.candidates = _logged

import gui

root = tk.Tk()
app = gui.GameGUI(root, board_size=15, black_is_ai=False, white_is_ai=False)
app.engine_var.set(1)
app.show_candidates_var.set(1)
root.update()
for c in "h8 h7 h6 i8 j7".split():
    x, y = bt.code_to_coord(c, 15)
    ok, _ = app.board.play_black(x, y)
    assert ok
app.current = 2
app._maybe_refresh_engine_labels()
end = time.time() + 15
while time.time() < end:
    root.update()
    time.sleep(0.01)
    if app.engine_labels_done:
        break
assert app.engine_labels_done
assert sorted(app.engine_labels) == [(6, 7)], sorted(app.engine_labels)
assert app._get_candidate_display_positions() == [(6, 7)]
print("case a page source: [(6, 7)] = h9 OK")
app.engine_var.set(0)
app.engine_labels_done = False
n = len(app._get_candidate_display_positions())
print("engine off: python path count =", n)
root.destroy()
print("CAND_SMOKE_OK")
