// forbidden.cpp - 黑棋禁手判定的 Rapfi 移植实现。
//
// 三步流程（对应 Rapfi board.cpp: checkForbiddenPoint）：
//   1. 廉价预筛：取出落子点在 4 个方向上的线型。若没有任何
//      四(B4/B4S/F4)/三(F3/F3S)/长连(OL)成分，直接判非禁手。
//   2. 长连 / 四四：任一方向 OL -> 禁手；B4/B4S/F4 累计 >= 2 个方向 -> 禁手。
//      落子后恰好成五(F5) 则直接合法（即使同时构成四四/三三）。
//   3. 三三：临时落子（scoped，判定后还原），对每个 F3/F3S 方向向两侧各最多
//      找 4 格(MaxFindDist)。若存在空点能把该三延伸成 B_FLEX4 或 F5，并且该
//      延伸点本身不是真禁手（checkForbiddenPoint 只递归一层），则该方向计入
//      一个真三；真三数 >= 2 -> 禁手。
//
// 线型分类用查表：11 格窗口(中心 + 每侧 5 格；Rapfi renju 规则为检测长连需要
// 看到距离 5 的子)编码为三进制，用与 Rapfi pattern.cpp 相同的动态规划在静态
// 初始化时生成一次 (Pattern 表)，运行期只做 O(1) 查表。
//
// 阻挡(OPPO)的定义在本混合规则下被扩展为：白子 ∪ 障碍 ∪ 棋盘外 ∪ 无气点。
#include "forbidden.h"

#include <cstring>

namespace gvg {

namespace {

// ---------------- 线型 / 组合线型枚举（数值顺序沿用 Rapfi，越大越强） ----------------
enum Pat : uint8_t {
    DEAD = 0, OL, B1, F1, B2, F2, F2A, F2B, B3, B3S, F3, F3S, B4, B4S, F4, F5,
    PATTERN_NB
};

enum Pattern4 : uint8_t {
    P4_NONE = 0, FORBID, L_FLEX2, K_BLOCK3, J_FLEX2_2X, I_BLOCK3_PLUS, H_FLEX3,
    G_FLEX3_PLUS, F_FLEX3_2X, E_BLOCK4, D_BLOCK4_PLUS, C_BLOCK4_FLEX3, B_FLEX4,
    A_FIVE, PATTERN4_NB
};

// 窗口内相对黑棋的格状态。数值同时用作三进制编码，必须与 Rapfi 一致。
enum Flag : uint8_t { SELF = 0, OPPO = 1, EMPT = 2 };

constexpr int H       = 5;             // 中心每侧格数（renju 需 5 才能看到长连）
constexpr int LEN     = 2 * H + 1;     // 11 格窗口
constexpr int MID     = H;
constexpr int TRI     = 177147;        // 3^11

uint8_t g_memo[TRI];                   // 0 = 未计算；否则 Pattern+1

inline int encode(const uint8_t* f) {
    int c = 0;
    for (int i = 0; i < LEN; ++i) c = c * 3 + f[i];
    return c;
}

// Rapfi pattern.cpp countLine：realLen = 过中心的连续己方子数；
// fullLen = 两端到第一个对方子为止的跨度；[start,end] 为该跨度。
void count_line(const uint8_t* f, int& realLen, int& fullLen, int& start, int& end) {
    realLen = 1; fullLen = 1;
    int inc = 1;
    start = end = MID;
    for (int i = MID - 1; i >= 0; --i) {
        if (f[i] == SELF) realLen += inc;
        else if (f[i] == OPPO) break;
        else inc = 0;
        ++fullLen;
        start = i;
    }
    inc = 1;
    for (int i = MID + 1; i < LEN; ++i) {
        if (f[i] == SELF) realLen += inc;
        else if (f[i] == OPPO) break;
        else inc = 0;
        ++fullLen;
        end = i;
    }
}

// Rapfi shiftLine：把第 i 格重新居中，窗口外的格视为对方子。
void shift_line(const uint8_t* line, int i, uint8_t* out) {
    for (int j = 0; j < LEN; ++j) {
        const int idx = j + i - MID;
        out[j] = (idx >= 0 && idx < LEN) ? line[idx] : static_cast<uint8_t>(OPPO);
    }
}

// 动态规划分类：不断在空点落己方子，递归到 OL/F5/DEAD 等平凡态，再回溯取最强。
uint8_t get_pattern_rec(const uint8_t* line) {
    const int code = encode(line);
    if (g_memo[code]) return static_cast<uint8_t>(g_memo[code] - 1);

    int realLen, fullLen, start, end;
    count_line(line, realLen, fullLen, start, end);

    uint8_t p = DEAD;
    if (realLen >= 6) p = OL;               // 长连
    else if (realLen >= 5) p = F5;          // 成五
    else if (fullLen < 5) p = DEAD;         // 两端跨度不足五，永远成不了五
    else {
        int patCnt[PATTERN_NB] = {0};
        int f5Idx[2]           = {0};
        uint8_t shifted[LEN];
        for (int i = start; i <= end; ++i) {
            if (line[i] != EMPT) continue;
            shift_line(line, i, shifted);
            shifted[MID] = SELF;
            const uint8_t sp = get_pattern_rec(shifted);
            if (sp == F5 && patCnt[F5] < 2) f5Idx[patCnt[F5]] = i;
            ++patCnt[sp];
        }
        if (patCnt[F5] >= 2) {
            p = F4;
            // Rapfi 的“脏修复”：同一条线上两个四(两个成五点相距 <5)视作长连禁手，
            // 这样同线双四也能被长连分支拒绝。
            if (f5Idx[1] - f5Idx[0] < 5) p = OL;
        } else if (patCnt[F5] == 1) {
            // 冲四：对方必挡，挡住后若还有成四手段则记为 B4S(连冲四)，否则 B4。
            uint8_t blocked[LEN];
            std::memcpy(blocked, line, LEN);
            blocked[f5Idx[0]] = OPPO;
            p = (get_pattern_rec(blocked) >= B3) ? B4S : B4;
        } else if (patCnt[F4] >= 2) p = F3S;
        else if (patCnt[F4]) p = F3;
        else if (patCnt[B4S]) p = B3S;
        else if (patCnt[B4]) p = B3;
        else if (patCnt[F3S] + patCnt[F3] >= 4) p = F2B;
        else if (patCnt[F3S] + patCnt[F3] >= 3) p = F2A;
        else if (patCnt[F3S] + patCnt[F3]) p = F2;
        else if (patCnt[B3] + patCnt[B3S]) p = B2;
        else if (patCnt[F2] + patCnt[F2A] + patCnt[F2B]) p = F1;
        else if (patCnt[B2]) p = B1;
    }

    g_memo[code] = static_cast<uint8_t>(p + 1);
    return p;
}

// 静态初始化：枚举全部 3^11 窗口并填满 DP 记忆表（只做一次）。
struct PatternTableInit {
    PatternTableInit() {
        std::memset(g_memo, 0, sizeof(g_memo));
        uint8_t line[LEN];
        for (int c = 0; c < TRI; ++c) {
            int t = c;
            for (int i = LEN - 1; i >= 0; --i) { line[i] = static_cast<uint8_t>(t % 3); t /= 3; }
            get_pattern_rec(line);
        }
    }
};
const PatternTableInit g_pattern_init;

// ---------------- 四方向组合：Rapfi getPattern4<Forbid=true> ----------------
uint8_t combine_pattern4(uint8_t p1, uint8_t p2, uint8_t p3, uint8_t p4) {
    int n[PATTERN_NB] = {0};
    ++n[p1]; ++n[p2]; ++n[p3]; ++n[p4];
    n[B4] += n[B4S];   // 阶段一把连冲四归入冲四
    n[B3] += n[B3S];

    if (n[F5] >= 1) return A_FIVE;                  // 恰好成五优先
    if (n[OL] >= 1) return FORBID;                  // 长连
    if (n[F4] + n[B4] >= 2) return FORBID;          // 四四
    if (n[F3] + n[F3S] >= 2) return FORBID;         // 三三（预筛标记）
    if (n[B4] >= 2) return B_FLEX4;
    if (n[F4] >= 1) return B_FLEX4;
    if (n[B4] >= 1) {
        if (n[F3] >= 1 || n[F3S] >= 1) return C_BLOCK4_FLEX3;
        if (n[B3] >= 1) return D_BLOCK4_PLUS;
        if (n[F2] + n[F2A] + n[F2B] >= 1) return D_BLOCK4_PLUS;
        return E_BLOCK4;
    }
    if (n[F3] >= 1 || n[F3S] >= 1) {
        if (n[F3] + n[F3S] >= 2) return F_FLEX3_2X;
        if (n[B3] >= 1) return G_FLEX3_PLUS;
        if (n[F2] + n[F2A] + n[F2B] >= 1) return G_FLEX3_PLUS;
        return H_FLEX3;
    }
    if (n[B3] >= 1) {
        if (n[B3] >= 2) return I_BLOCK3_PLUS;
        if (n[F2] + n[F2A] + n[F2B] >= 1) return I_BLOCK3_PLUS;
    }
    if (n[F2] + n[F2A] + n[F2B] >= 2) return J_FLEX2_2X;
    if (n[B3] >= 1) return K_BLOCK3;
    if (n[F2] + n[F2A] + n[F2B] >= 1) return L_FLEX2;
    return P4_NONE;
}

// Rapfi 的四方向顺序（横 / 竖 / 主对角 / 副对角），与本项目 Python 版一致。
const int DX4[4] = {1, 0, 1, 1};
const int DY4[4] = {0, 1, 1, -1};

// 从黑棋视角把一格编码成 Flag。障碍 / 白子 / 棋盘外 / 无气空点 都算阻挡(OPPO)。
inline uint8_t cell_flag(const Board& b, int x, int y) {
    if (!b.in_bounds(x, y)) return OPPO;
    const uint8_t v = b.at(x, y);
    if (v == BLACK) return SELF;
    if (v == WHITE || v == OBSTACLE) return OPPO;
    return b.is_dead_empty(x, y) ? static_cast<uint8_t>(OPPO) : static_cast<uint8_t>(EMPT);
}

// 构造以 (x,y) 为中心、方向 (dx,dy) 的 11 格窗口（中心恒为 SELF）。
void build_flags(const Board& b, int x, int y, int dx, int dy, uint8_t* f) {
    for (int i = -H; i <= H; ++i) {
        if (i == 0) { f[MID] = SELF; continue; }
        f[i + MID] = cell_flag(b, x + i * dx, y + i * dy);
    }
}

inline uint8_t dir_pattern(const Board& b, int x, int y, int dx, int dy) {
    uint8_t f[LEN];
    build_flags(b, x, y, dx, dy, f);
    return get_pattern_rec(f);
}

inline uint8_t pattern4_at(const Board& b, int x, int y) {
    uint8_t p[4];
    for (int d = 0; d < 4; ++d) p[d] = dir_pattern(b, x, y, DX4[d], DY4[d]);
    return combine_pattern4(p[0], p[1], p[2], p[3]);
}

inline bool is_forbidden_component(uint8_t p) {
    return p == OL || p == B4 || p == B4S || p == F4 || p == F3 || p == F3S;
}

constexpr int MAX_EXT_DEPTH = 1;  // 三三延伸点的递归只做一层
constexpr int MaxFindDist   = 4;

bool check_forbidden_impl(Board& b, int x, int y, int depth);  // 前置声明（互相递归）

// 第三步主体：假定 p[] 为落子点四方向线型，临时落子后统计“真三”方向数。
int count_true_threes(Board& b, int x, int y, const uint8_t p[4], int depth) {
    b.set_cell_raw(x, y, BLACK);               // scoped：结束前还原
    int threes = 0;
    for (int d = 0; d < 4 && threes < 2; ++d) {
        const uint8_t q = p[d];
        if (q != F3 && q != F3S) continue;

        bool found = false;
        for (int sgn = -1; sgn <= 1 && !found; sgn += 2) {
            int cx = x, cy = y;
            for (int i = 0; i < MaxFindDist; ++i) {
                cx += sgn * DX4[d];
                cy += sgn * DY4[d];
                if (!b.in_bounds(cx, cy)) break;
                const uint8_t v = b.at(cx, cy);
                if (v == EMPTY) {
                    // (a) 该空点必须真能把三延伸成活四(B_FLEX4) 或成五(F5)。
                    const uint8_t p4c = pattern4_at(b, cx, cy);
                    const uint8_t pc  = dir_pattern(b, cx, cy, DX4[d], DY4[d]);
                    bool ok = (p4c == B_FLEX4) || (pc == F5);
                    // 无气点黑棋根本无法落子，等同边缘，不能作为延伸点。
                    if (ok && b.is_dead_empty(cx, cy)) ok = false;
                    // (b) 延伸点本身不能是真禁手（只递归一层）。
                    if (ok && depth < MAX_EXT_DEPTH)
                        ok = !check_forbidden_impl(b, cx, cy, depth + 1);
                    if (ok) found = true;
                    break;  // 遇到第一个空点即判定，不继续向外找
                } else if (v != BLACK) {
                    break;  // 被白/障碍/墙挡住
                }
            }
        }
        if (found) ++threes;
    }
    b.set_cell_raw(x, y, EMPTY);
    return threes;
}

// 三步判定主体。depth 用于限制三三延伸点的递归层数。
bool check_forbidden_impl(Board& b, int x, int y, int depth) {
    if (!b.in_bounds(x, y) || !b.is_empty(x, y)) return false;

    // ---- 第一步：便宜预筛。取落子点四方向线型，不含四/三/长连成分直接放行。 ----
    uint8_t p[4];
    for (int d = 0; d < 4; ++d) p[d] = dir_pattern(b, x, y, DX4[d], DY4[d]);
    bool candidate = false;
    for (int d = 0; d < 4; ++d)
        if (is_forbidden_component(p[d])) { candidate = true; break; }
    if (!candidate) return false;

    // ---- 第二步：长连 / 四四。先查长连；成五直接合法。 ----
    for (int d = 0; d < 4; ++d)
        if (p[d] == OL) return true;
    for (int d = 0; d < 4; ++d)
        if (p[d] == F5) return false;          // 恰好成五，合法且获胜
    int fours = 0;
    for (int d = 0; d < 4; ++d) {
        const uint8_t q = p[d];
        if (q == B4 || q == B4S || q == F4) ++fours;
    }
    if (fours >= 2) return true;

    // ---- 第三步：三三。 ----
    return count_true_threes(b, x, y, p, depth) >= 2;
}

}  // namespace

bool check_forbidden(Board& board, int x, int y) {
    return check_forbidden_impl(board, x, y, 0);
}

ForbiddenProbe probe_forbidden(Board& board, int x, int y) {
    ForbiddenProbe r{};
    for (int d = 0; d < 4; ++d) r.dir[d] = DEAD;
    r.p4 = P4_NONE;
    r.fours = 0;
    r.threes = 0;
    r.forbidden = false;
    if (!board.in_bounds(x, y) || !board.is_empty(x, y)) return r;

    uint8_t p[4];
    for (int d = 0; d < 4; ++d) {
        p[d] = dir_pattern(board, x, y, DX4[d], DY4[d]);
        r.dir[d] = p[d];
    }
    r.p4 = combine_pattern4(p[0], p[1], p[2], p[3]);
    for (int d = 0; d < 4; ++d) {
        const uint8_t q = p[d];
        if (q == B4 || q == B4S || q == F4) ++r.fours;
    }
    bool candidate = false;
    for (int d = 0; d < 4; ++d)
        if (is_forbidden_component(p[d])) { candidate = true; break; }
    if (candidate) {
        bool ol = false, five = false;
        for (int d = 0; d < 4; ++d) { ol |= (p[d] == OL); five |= (p[d] == F5); }
        if (ol) r.forbidden = true;
        else if (!five) {
            if (r.fours >= 2) r.forbidden = true;
            else {
                r.threes = count_true_threes(board, x, y, p, 0);
                r.forbidden = r.threes >= 2;
            }
        }
    }
    return r;
}

}  // namespace gvg
