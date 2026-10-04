"""_daoqi_smoke.py - headless smoke test for the daoqi (KataGo) client.

Builds a torus HybridBoard, plays moves including a capture that wraps
around the edge, and checks that katago_client returns a legal best move
plus winrate / scoreLead for every query.

Run:  python _daoqi_smoke.py
"""
import time

from board import BLACK, WHITE, HybridBoard
import katago_client as kc


def main():
    assert kc.available(), "daoqi_katago/ files missing"
    # GTP coordinate conversion spot checks (col letters skip I).
    assert kc.gtp_to_xy("A1", 9) == (0, 8)
    assert kc.gtp_to_xy("J4", 19) == (8, 15)
    assert kc.gtp_to_xy("T19", 19) == (18, 0)
    assert kc.gtp_to_xy("pass", 9) is None
    assert kc.xy_to_gtp(15, 0, 16) == "Q16"
    assert kc.gtp_to_xy("Q16", 16) == (15, 0)
    for x in range(19):
        for y in range(19):
            assert kc.gtp_to_xy(kc.xy_to_gtp(x, y, 19), 19) == (x, y)
    print("gtp_to_xy / xy_to_gtp OK")

    client = kc.KataGoClient()
    t0 = time.time()
    board = HybridBoard(9)
    board.torus = True
    board.turn = WHITE

    r = client.analyze(board, WHITE, max_visits=48, komi=5.5)
    print(f"[{time.time()-t0:.1f}s] empty 9x9 torus, white to move: "
          f"backend={r['backend']} wr(B)={r['winrate']:.3f} "
          f"sl(B)={r['scoreLead']:+.2f} visits={r['visits']} "
          f"best={r['move']} ({r['seconds']:.1f}s)")
    assert r["verdict"] == "move" and r["move"] is not None
    x, y = r["move"]
    assert board.is_empty(x, y)
    ok, _ = board.play_white(x, y)
    assert ok, "KataGo move rejected by board"

    # Torus capture: a black stone on the top row dies when its wrapped
    # liberty is taken from the bottom row (on a torus a "corner" stone
    # still has four neighbours: (1,0), (8,0)≡(-1,0), (0,1), (0,8)≡(0,-1)).
    b = HybridBoard(9)
    b.torus = True
    b.turn = WHITE
    ok, _ = b.play_black(0, 0, check_rules=False)
    assert ok
    for wx, wy in ((1, 0), (0, 1), (8, 0), (0, 8)):
        ok, _ = b.play_white(wx, wy)
        assert ok
    assert b.grid[0, 0] == 0, "stone should be captured via wrapped liberty"
    print("torus capture OK: black (0,0) removed by white at (0,8)")

    r2 = client.analyze(b, BLACK, max_visits=48, komi=5.5)
    print(f"after capture, black to move: wr(B)={r2['winrate']:.3f} "
          f"sl(B)={r2['scoreLead']:+.2f} visits={r2['visits']} "
          f"cands={[(c[0], c[1]) for c in r2['candidates'][:3]]}")
    assert r2["verdict"] == "move"
    for cx, cy, *_ in r2["candidates"]:
        assert b.is_empty(cx, cy), f"candidate ({cx},{cy}) not empty"

    # A real gomoku-vs-go middlegame position: black four in a row (open
    # three + rush four mix) on a 9x9 torus, white to move.
    c = HybridBoard(9)
    c.torus = True
    c.turn = WHITE
    for bx in (2, 3, 4):
        c.play_black(bx, 4, check_rules=False)
    c.play_white(2, 3)
    c.play_black(5, 4, check_rules=False)   # black four 2..5 on row 4
    c.play_white(6, 4)                       # block one end
    r3 = client.analyze(c, WHITE, max_visits=64, komi=5.5)
    print(f"middlegame white to move: wr(B)={r3['winrate']:.3f} "
          f"sl(B)={r3['scoreLead']:+.2f} best={r3['move']} "
          f"n_cands={len(r3['candidates'])}")
    assert r3["verdict"] == "move"
    mx, my = r3["move"]
    assert c.is_empty(mx, my)
    ok, captured = c.play_white(mx, my)
    assert ok

    client.quit()
    print("daoqi smoke OK")


if __name__ == "__main__":
    main()
