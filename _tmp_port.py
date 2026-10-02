"""Prototype: exact Rapfi checkForbiddenPoint in Python + benchmark."""
import time, sys, os
sys.path.insert(0, os.getcwd())
from board import HybridBoard, BLACK, WHITE, EMPTY, OBSTACLE, DIRECTIONS
import board_tools as bt

_SELF, _OPPO, _EMPT = 0, 1, 2
_MID, _LEN = 5, 11
DEAD, OL, B1, F1, B2, F2, F2A, F2B, B3, B3S, F3, F3S, B4, B4S, F4, F5 = range(16)
(P4_NONE, FORBID, L_FLEX2, K_BLOCK3, J_FLEX2_2X, I_BLOCK3_PLUS, H_FLEX3,
 G_FLEX3_PLUS, F_FLEX3_2X, E_BLOCK4, D_BLOCK4_PLUS, C_BLOCK4_FLEX3,
 B_FLEX4, A_FIVE) = range(14)

_MEMO = {}

def _count_line(line):
    real_len, full_len, inc = 1, 1, 1
    start = end = _MID
    for i in range(_MID - 1, -1, -1):
        v = line[i]
        if v == _SELF: real_len += inc
        elif v == _OPPO: break
        else: inc = 0
        full_len += 1; start = i
    inc = 1
    for i in range(_MID + 1, _LEN):
        v = line[i]
        if v == _SELF: real_len += inc
        elif v == _OPPO: break
        else: inc = 0
        full_len += 1; end = i
    return real_len, full_len, start, end

def _shift(line, i):
    return tuple(line[j + i - _MID] if 0 <= j + i - _MID < _LEN else _OPPO
                 for j in range(_LEN))

def pattern_of(line):
    got = _MEMO.get(line)
    if got is not None: return got
    real_len, full_len, start, end = _count_line(line)
    if real_len >= 6: p = OL
    elif real_len >= 5: p = F5
    elif full_len < 5: p = DEAD
    else:
        cnt = [0] * 16
        f5_idx = [0, 0]
        for i in range(start, end + 1):
            if line[i] != _EMPT: continue
            sl = list(_shift(line, i)); sl[_MID] = _SELF
            sp = pattern_of(tuple(sl))
            if sp == F5 and cnt[F5] < 2: f5_idx[cnt[F5]] = i
            cnt[sp] += 1
        if cnt[F5] >= 2:
            p = F4
            if f5_idx[1] - f5_idx[0] < 5: p = OL
        elif cnt[F5] == 1:
            blocked = list(line); blocked[f5_idx[0]] = _OPPO
            p = B4S if pattern_of(tuple(blocked)) >= B3 else B4
        elif cnt[F4] >= 2: p = F3S
        elif cnt[F4]: p = F3
        elif cnt[B4S]: p = B3S
        elif cnt[B4]: p = B3
        elif cnt[F3S] + cnt[F3] >= 4: p = F2B
        elif cnt[F3S] + cnt[F3] >= 3: p = F2A
        elif cnt[F3S] + cnt[F3]: p = F2
        elif cnt[B3] + cnt[B3S]: p = B2
        elif cnt[F2] + cnt[F2A] + cnt[F2B]: p = F1
        elif cnt[B2]: p = B1
        else: p = DEAD
    _MEMO[line] = p
    return p

def combine4_forbid(p1, p2, p3, p4):
    n = [0] * 16
    for p in (p1, p2, p3, p4): n[p] += 1
    n[B4] += n[B4S]; n[B3] += n[B3S]
    if n[F5] >= 1: return A_FIVE
    if n[OL] >= 1: return FORBID
    if n[F4] + n[B4] >= 2: return FORBID
    if n[F3] + n[F3S] >= 2: return FORBID
    if n[B4] >= 2: return B_FLEX4
    if n[F4] >= 1: return B_FLEX4
    return P4_NONE

class Ctx:
    __slots__ = ("board", "grid", "size", "noli", "dirpat")
    def __init__(self, board):
        self.board = board
        self.grid = board.grid
        self.size = board.size
        self.noli = board.get_no_liberty_positions()
        self.dirpat = {}

def _flag(ctx, x, y):
    if not (0 <= x < ctx.size and 0 <= y < ctx.size): return _OPPO
    v = int(ctx.grid[x, y])
    if v == BLACK: return _SELF
    if v in (WHITE, OBSTACLE): return _OPPO
    return _OPPO if (x, y) in ctx.noli else _EMPT

def dir_pattern(ctx, x, y, dx, dy):
    key = (x, y, dx, dy)
    got = ctx.dirpat.get(key)
    if got is not None: return got
    line = [_EMPT] * _LEN
    line[_MID] = _SELF
    for i in range(-5, 6):
        if i == 0: continue
        line[i + _MID] = _flag(ctx, x + i * dx, y + i * dy)
    p = pattern_of(tuple(line))
    ctx.dirpat[key] = p
    return p

def pattern4(ctx, x, y):
    return combine4_forbid(*[dir_pattern(ctx, x, y, dx, dy) for dx, dy in DIRECTIONS])

def check_forbidden(ctx, x, y, depth=0):
    if not ctx.board.is_empty(x, y): return False
    if depth >= 64: return False
    if pattern4(ctx, x, y) != FORBID: return False
    win_four = 0
    for dx, dy in DIRECTIONS:
        p = dir_pattern(ctx, x, y, dx, dy)
        if p == OL: return True
        if p in (B4, B4S, F4):
            win_four += 1
            if win_four >= 2: return True
    ctx.grid[x, y] = BLACK
    ctx.dirpat.clear()
    try:
        win_three = 0
        for dx, dy in DIRECTIONS:
            p = dir_pattern(ctx, x, y, dx, dy)
            if p not in (F3, F3S): continue
            counted = False
            for sgn in (-1, 1):
                if counted: break
                cx, cy = x, y
                for _ in range(4):
                    cx += sgn * dx; cy += sgn * dy
                    if not (0 <= cx < ctx.size and 0 <= cy < ctx.size): break
                    v = int(ctx.grid[cx, cy])
                    if v == EMPTY:
                        p4 = pattern4(ctx, cx, cy)
                        pc = dir_pattern(ctx, cx, cy, dx, dy)
                        if (p4 == B_FLEX4) or (pc == F5) or (
                                p4 == FORBID and pc == F4 and
                                not check_forbidden(ctx, cx, cy, depth + 1)):
                            counted = True
                        break
                    if v != BLACK: break
            if counted: win_three += 1
        return win_three >= 2
    finally:
        ctx.grid[x, y] = EMPTY
        ctx.dirpat.clear()

def scan(board):
    ctx = Ctx(board)
    out = []
    for x in range(board.size):
        for y in range(board.size):
            if board.is_empty(x, y) and check_forbidden(ctx, x, y):
                out.append(bt.coord_to_code(x, y, board.size))
    return sorted(out), len(_MEMO)

if __name__ == "__main__":
    import rules
    cases = [
        ("user position", "h9g10g9f7g8g6g7k8i8o15h7n15d10o14e7n14e6o13"),
        ("case12", "h9 i9 i8 j7 i7 f11 i6 f6 h6 p0 f10 p0 f9 p0 f8 p0 f7"),
        ("block7", "i10 p0 i9 p0 j9 p0 j8 p0 g8 p0 g7 p0 h7 p0 h6"),
        ("block9", "h10o15g10a15g9a1i9o1j9o14j8n14f8n15f7m15g7m14i7o13i6n13h6m13"),
    ]
    for name, codes in cases:
        b, _ = bt.board_from_code(codes, size=15, first=bt.BLACK, gomoku=True)
        t0 = time.perf_counter(); got, memo = scan(b); dt = time.perf_counter() - t0
        t1 = time.perf_counter()
        old = sorted(c for c, _ in bt.forbidden_codes(b))
        dt2 = time.perf_counter() - t1
        print("%-14s port=%-42s %.3fs | rules=%-42s %.3fs  memo=%d" % (
            name, got, dt, old, dt2, memo))
