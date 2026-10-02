// forbidden.cpp - 黑棋禁手判定：Rapfi checkForbiddenPoint 的忠实移植。
//
// 与 Rapfi board.cpp:423 checkForbiddenPoint 逐步对应：
//   1. O(1) 预筛：pattern4[BLACK](pos) != FORBID → 非禁手。
//      （pattern4 与逐方向线型来自 Board 的增量棋型缓存，落子/悔棋时刷新。）
//   2. 任一方向 OL → 长连禁手；B4/F4 累计 ≥2 方向 → 四四禁手。
//      落子后恰好成五（F5）合法且获胜——phase-1 组合表已把 F5 排在 FORBID 之前。
//   3. 三三：临时落子（真实 make_move，保证棋型缓存一致，判定后 undo），
//      对每个 F3/F3S 方向向两侧各最多 4 格（MaxFindDist）找延伸点，遇到第一个
//      空点即判定。延伸点满足以下任一即计入一个“真三”：
//        a) pattern4[BLACK] == B_FLEX4（可延伸成活四）；
//        b) pattern(BLACK, dir) == F5（直接成五）；
//        c) pattern4[BLACK] == FORBID 且 pattern(BLACK, dir) == F4 且
//           !checkForbiddenPoint(posi)（“假禁手”的活四级点，递归一层验证）。
//      真三数 ≥ 2 → 禁手。
//
// 对 Rapfi 的唯一扩展：阻挡（OPPO）的判定——白子 / 障碍 / 棋盘外 / 无气空点
// 在 Board::build_pattern_window 中映射为同一状态，代码层面完全一致。
#include "forbidden.h"

#include "pattern_table.h"

namespace gvg {

namespace {

const int FDX[4] = {1, 0, 1, 1};
const int FDY[4] = {0, 1, 1, -1};

constexpr int MaxFindDist    = 4;
// Rapfi 的递归没有深度上限（每次递归都在棋盘上多落一子，天然有界）；
// 这里保留一个纯防御性的上限，实际对局中不可能触及。
constexpr int MaxProbeDepth  = 64;

bool check_forbidden_impl(Board& b, int x, int y, int depth);  // 互递归前置声明

// 第三步主体：假定 p[0..3] 为落子点四方向线型（落子前缓存），临时落子后
// 统计“真三”方向数。scoped 用 make_move/undo_move 保证棋型缓存一致。
int count_true_threes(Board& b, int x, int y, const uint8_t p[4], int depth) {
    if (!b.make_move(x, y, BLACK)) return 0;  // 防御：自杀/占用不应发生

    int threes = 0;
    for (int d = 0; d < 4 && threes < 2; ++d) {
        const uint8_t q = p[d];
        if (q != F3 && q != F3S) continue;

        for (int sgn = -1; sgn <= 1 && threes < 2; sgn += 2) {
            int cx = x, cy = y;
            for (int i = 0; i < MaxFindDist; ++i) {
                cx += sgn * FDX[d];
                cy += sgn * FDY[d];
                if (!b.in_bounds(cx, cy)) break;      // 棋盘外 = 阻挡
                const int cidx = Board::index(cx, cy);
                const uint8_t v = b.at(cx, cy);
                if (v == EMPTY) {
                    // 遇到第一个空点即判定（与 Rapfi 一致）。
                    const uint8_t p4c = b.cached_pattern4_black(cidx);
                    const uint8_t pc  = b.cached_pattern(0, cidx, d);
                    bool ok = (p4c == B_FLEX4) || (pc == F5) ||
                              (p4c == FORBID && pc == F4 &&
                               !check_forbidden_impl(b, cx, cy, depth + 1));
                    if (ok) ++threes;
                    break;
                } else if (v != BLACK) {
                    break;  // 白 / 障碍 / 无气空点阻挡（统一状态）
                }
            }
        }
    }

    b.undo_move();
    return threes;
}

// 三步判定主体。depth 只作防御性递归上限。
bool check_forbidden_impl(Board& b, int x, int y, int depth) {
    if (!b.in_bounds(x, y) || !b.is_empty(x, y)) return false;
    if (depth >= MaxProbeDepth) return false;

    const int idx = Board::index(x, y);

    // ---- 第一步：O(1) 预筛（Rapfi: pattern4[BLACK] != FORBID → false）。----
    if (b.cached_pattern4_black(idx) != FORBID) return false;

    // ---- 第二步：长连 / 四四（44 计数只算 B4/F4，与 Rapfi 一致）。----
    int fours = 0;
    for (int d = 0; d < 4; ++d) {
        const uint8_t q = b.cached_pattern(0, idx, d);
        if (q == OL) return true;              // 长连必为真禁手
        if (q == B4 || q == F4) {
            if (++fours >= 2) return true;     // 四四必为真禁手
        }
    }

    // ---- 第三步：三三（带“假禁手延伸点”递归验证）。----
    if (depth + 1 >= MaxProbeDepth) return false;
    uint8_t p[4];
    for (int d = 0; d < 4; ++d) p[d] = b.cached_pattern(0, idx, d);
    return count_true_threes(b, x, y, p, depth) >= 2;
}

}  // namespace

bool check_forbidden(Board& board, int x, int y) {
    return check_forbidden_impl(board, x, y, 0);
}

PointPattern classify_point(const Board& board, int x, int y, int color,
                            int dx, int dy) {
    if (!board.in_bounds(x, y)) return PP_NONE;
    const int d = Board::dir_index(dx, dy);
    if (d < 0) return PP_NONE;  // 非四主方向：调用方不应使用
    const uint8_t p = board.cached_pattern(color, Board::index(x, y), d);
    switch (p) {
        case F5: return PP_FIVE;
        case OL: return PP_OL;
        case F4: return PP_FLEX4;
        case B4: return PP_B4;
        case F3: case F3S: return PP_FLEX3;
        case B3: return PP_B3;
        case F2: case F2A: case F2B: return PP_FLEX2;
        case B2: case B1: return PP_B2;
        default: return PP_NONE;  // DEAD / F1
    }
}

ForbiddenProbe probe_forbidden(Board& board, int x, int y) {
    ForbiddenProbe r{};
    for (int d = 0; d < 4; ++d) r.dir[d] = DEAD;
    r.p4 = P4_NONE;
    r.fours = 0;
    r.threes = 0;
    r.forbidden = false;
    if (!board.in_bounds(x, y) || !board.is_empty(x, y)) return r;

    const int idx = Board::index(x, y);
    uint8_t p[4];
    for (int d = 0; d < 4; ++d) {
        p[d] = board.cached_pattern(0, idx, d);
        r.dir[d] = p[d];
    }
    r.p4 = board.cached_pattern4_black(idx);

    if (r.p4 != FORBID) return r;  // O(1) 预筛：非禁手

    int fours = 0;
    for (int d = 0; d < 4; ++d) {
        const uint8_t q = p[d];
        if (q == OL) { r.forbidden = true; return r; }
        if (q == B4 || q == F4) ++fours;
    }
    r.fours = fours;
    if (fours >= 2) { r.forbidden = true; return r; }

    r.threes = count_true_threes(board, x, y, p, 0);
    r.forbidden = r.threes >= 2;
    return r;
}

}  // namespace gvg
