// forbidden.cpp - 黑棋禁手判定：Rapfi checkForbiddenPoint 的忠实移植。
//
// 与 Rapfi board.cpp:423 checkForbiddenPoint 逐步对应：
//   1. O(1) 预筛：pattern4[BLACK](pos) != FORBID → 非禁手。
//      （pattern4 与逐方向线型来自 Board 的增量棋型缓存，落子/悔棋时刷新。）
//   2. 任一方向 OL → 长连禁手；B4/F4 累计 ≥2 方向 → 四四禁手。
//      落子后恰好成五（F5）合法且获胜——phase-1 组合表已把 F5 排在 FORBID 之前。
//   3. 三三：临时落子（真实 make_move，保证棋型缓存一致，判定后 undo），
//      对每个 F3/F3S 方向先向负方向、再向正方向找延伸点（穿过连续黑子后的
//      第一个空点，最多 4 格 MaxFindDist），遇到第一个空点即判定。**每个方向
//      最多贡献 1 个“真三”**：负方向判定成功就直接跳到下一个方向、不再看
//      正方向；负方向失败（空点不合格 / 被阻挡 / 4 格内全是黑子）才看正方向
//      —— 这是 Rapfi 源码里 goto next_direction 的语义。延伸点满足以下任一
//      即计入一个“真三”：
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

// 把 (x,y) 当成黑子时，穿过它的连续黑子数（不落子，纯读盘）。
// 用来区分两种 OL：真长连（run >= 6）与 Rapfi 把“一线双四”编码成的 OL
// （run <= 5，见 pattern_table.cpp 的 dirty fix）——前者只受“长连禁手”开关管，
// 后者本质是四四、计入 fours。
int run_through(const Board& b, int x, int y, int dx, int dy) {
    int n = 1;
    for (int s = -1; s <= 1; s += 2) {
        for (int i = 1; i < b.size(); ++i) {
            const int nx = x + s * i * dx, ny = y + s * i * dy;
            if (!b.in_bounds(nx, ny) || b.at(nx, ny) != BLACK) break;
            ++n;
        }
    }
    return n;
}

// 第三步主体：假定 p[0..3] 为落子点四方向线型（落子前缓存），临时落子后
// 统计“真三”方向数。scoped 用 make_move/undo_move 保证棋型缓存一致。
int count_true_threes(Board& b, int x, int y, const uint8_t p[4], int depth) {
    if (!b.make_move(x, y, BLACK)) return 0;  // 防御：自杀/占用不应发生

    int threes = 0;
    for (int d = 0; d < 4 && threes < 2; ++d) {
        const uint8_t q = p[d];
        if (q != F3 && q != F3S) continue;

        // Rapfi 的扫描次序：先向负方向找穿过连续黑子后的第一个空点；该点
        // 判定成功就计 1 个真三并直接跳到下一个方向（不再看正方向），失败
        // 才继续向正方向找。因此**每个方向最多计 1 个真三**。
        bool counted = false;
        for (int pass = 0; pass < 2 && !counted; ++pass) {
            const int sgn = (pass == 0) ? -1 : 1;
            int cx = x, cy = y;
            for (int i = 0; i < MaxFindDist; ++i) {
                cx += sgn * FDX[d];
                cy += sgn * FDY[d];
                if (!b.in_bounds(cx, cy)) break;      // 棋盘外 = 阻挡
                const int cidx = Board::index(cx, cy);
                const uint8_t v = b.at(cx, cy);
                if (v == EMPTY) {
                    // 无气空点在本项目里等同白子（算法层同一形式：白/障碍/无气/棋盘外
                    // 都是同一个阻挡态），所以它不是延伸点——直接当阻挡，不算这一个三。
                    if (b.is_no_liberty(cidx)) break;
                    // 遇到第一个空点即判定（与 Rapfi 一致）。
                    const uint8_t p4c = b.cached_pattern4_black(cidx);
                    const uint8_t pc  = b.cached_pattern(0, cidx, d);
                    bool ok = (p4c == B_FLEX4) || (pc == F5) ||
                              (p4c == FORBID && pc == F4 &&
                               !check_forbidden_impl(b, cx, cy, depth + 1));
                    if (ok) {
                        ++threes;
                        counted = true;
                    }
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
    // 三档禁手开关（GUI 复选框）：关掉的那一档不再是禁手；关掉“长连”时，真长连
    // 方向既不判禁手也不计入四四（与 rules.py 的 _forbid_overline 语义一致）。
    const bool forbid_ol = b.forbid_overline();
    const bool forbid44  = b.forbid_44();
    const bool forbid33  = b.forbid_33();
    int fours = 0;
    for (int d = 0; d < 4; ++d) {
        const uint8_t q = b.cached_pattern(0, idx, d);
        if (q == OL) {
            if (run_through(b, x, y, FDX[d], FDY[d]) >= 6) {
                if (forbid_ol) return true;        // 真长连必为真禁手
            } else {
                fours += 2;                        // Rapfi 的“一线双四”
                if (forbid44 && fours >= 2) return true;
            }
        } else if (q == B4 || q == F4) {
            if (forbid44 && ++fours >= 2) return true;   // 四四必为真禁手
        }
    }

    // ---- 第三步：三三（带“假禁手延伸点”递归验证）。----
    if (!forbid33) return false;                 // 三三禁手关闭：不再往下判
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
    // 注意 cached_pattern 的 color 约定是 0=黑/1=白，而调用方传的是 Cell
    // 枚举值（BLACK=1/WHITE=2），需要换算。
    const int ci = (color == BLACK) ? 0 : 1;
    const uint8_t p = board.cached_pattern(ci, Board::index(x, y), d);
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

    // 与 check_forbidden_impl 同口径（含禁手开关与“一线双四/真长连”区分）。
    const bool forbid_ol = board.forbid_overline();
    const bool forbid44  = board.forbid_44();
    const bool forbid33  = board.forbid_33();
    int fours = 0;
    for (int d = 0; d < 4; ++d) {
        const uint8_t q = p[d];
        if (q == OL) {
            if (run_through(board, x, y, FDX[d], FDY[d]) >= 6) {
                if (forbid_ol) { r.forbidden = true; return r; }
            } else {
                fours += 2;
            }
        } else if (q == B4 || q == F4) {
            ++fours;
        }
    }
    r.fours = fours;
    if (forbid44 && fours >= 2) { r.forbidden = true; return r; }
    if (!forbid33) return r;

    r.threes = count_true_threes(board, x, y, p, 0);
    r.forbidden = r.threes >= 2;
    return r;
}

}  // namespace gvg
