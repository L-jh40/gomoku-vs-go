// vcfvct.cpp - 证明级 VCF/VCT 威胁空间搜索（AND-OR）+ W/L 标注实现（第 6 步重写）。
//
// 与第 4 步（OR 式路径枚举）的全部差异（对照任务书“不符点清单”）：
//   1. W 不再是“存在一条路径即标 W”，而是 AND-OR 证明：黑方 OR 节点存在一手攻击，
//      使白方**全部**防御应手都仍失败；白方 AND 节点要求集合内每个应手后黑方仍胜。
//   2. 攻击候选必须 check_forbidden==false 且非无气自杀点，展开时再以 make_move
//      实际成功为准（双保险）。
//   3. 五连窗的完成点必须是“当前就合法”的点（非长连/三三/四四/自杀），否则该窗
//      不是真威胁，完成点也不进防御集。
//   4. L 标注不再用 U(P) 交集过滤（整套路径枚举/交集机制已废弃），改为对白方候选
//      直接做证明搜索：白下 c 后黑方在预算 m 内被证明必胜 ⇒ L = 2*m。
//   5. 步数 = 首个证明成功的预算（迭代加深 IDA），不再是启发式的“最短路径”。
//
// 结构（自上而下）：
//   2.0 常量 / 计时 / 邻域
//   2.1 attack_rank_at / attack_class    单点威胁级别（复用 classify_point）
//   2.2 scan_completion_points           合法完成点 + a 类窗内黑子标记
//   2.3 build_groups                     黑块表（气列表 / 气数 / 是否含 a 类窗黑子）
//   2.4 defense_four                     四威胁的健全防御集 = a ∪ b ∪ c ∪ d
//   2.5 defense_three                    三威胁的健全防御超集 = a ∪ b ∪ c ∪ d
//   2.6 gen_attack_candidates            攻击候选（禁手/自杀过滤 + 预算剪枝 + 排序）
//   2.7 prove_black_dfs                  黑方节点（OR：候选）× 白方防御集（AND）
//   2.8 prove_white_node                 根候选落下后白方的 AND 节点
//   2.9 analyse                          逐候选标注
//   2.10 prove_black / vcf_exists / vct_exists
//
// 硬性约束：
//  * 全程只 make_move/undo_move，不拷贝棋盘；任何返回路径（含限流提前返回）都成对
//    undo，退出时 hash 逐位还原（assert 复核；build.bat 未定义 NDEBUG，断言生效）。
//  * 输出确定：候选按 (威胁等级, order_score, x, y) 全序，防御集按
//    (order_score(b,w,WHITE), x, y) 全序，无随机量、无指针顺序依赖。
//
// ---------------------------------------------------------------------------
// 健全性论证（与 IMPLEMENTATION.md 同一份文字）
// ---------------------------------------------------------------------------
// [2.2.2 defense_four] 设黑刚下出四威胁，C = 合法完成点集合（a：5 连窗内恰 4 黑 +
//   1 空 + 0 白/障碍，且完成点 c 不是长连/四四/三三禁手、也不是无气自杀点）。对白方
//   应手 w ∉ defense_four：
//     (1) w 不占任何合法完成点（a 类闭包）⇒ 至少有一个 c 仍为空；
//     (2) w 不是任何 1 气黑块的提子点（b）⇒ w 不通过提子消除任何黑块，特别是不消除
//         构成四窗的黑块；
//     (3) w 不减少任何“≤2 气且含 a 类窗内黑子”的黑块的气（c）⇒ w 无法把这种块压成
//         1 气组；
//     (4) w 不减少“完成点 c 落子后所属黑块”的气、也不占 c 的空正交邻点（d）⇒ 黑下 c
//         后该块仍有气；
//   于是黑下 c：不自杀（4）；白子只会给黑棋形添加阻挡，阻挡不可能制造长连/三三/四四
//   （禁手成分只随己方棋子增加而增加，白子等同墙）⇒ c 不构成新的长连/三三/四四；
//   剩余唯一情形是 c 所在线 run == 5 ⇒ 黑恰五（恰五优先于长连判定）⇒ 黑胜。
//   逐条成立 ⇒ 集合外白应手必败，AND 只需遍历集合内应手。
// [2.3.2 defense_three] 设黑刚下出活三威胁，F = 该三的全部“四 maker”（b 类窗内空点
//   中 attack_class ∈ {OPEN_FOUR,RUSH_FOUR} 者）。对白方应手 w ∉ defense_three：
//     (1) 每个 f ∈ F 仍是空点（b 类闭包含 f 本身）且仍合法：d 类闭包（f 的 4 个正交
//         空邻点）封住了“白下 f 的邻点把 f 变成自杀点”这一唯一途径；白子不可能让
//         f 变长连/三三/四四（同 2.2.2 的阻挡论证）⇒ 黑下 f 必得四威胁；
//     (2) w 不影响 defense_four 的任何封闭项（a/b/c/d 同 2.2.2 逐条）⇒ 该四威胁的
//         防御集仍是 defense_four 的健全超集。
//   因此三威胁对集合外白应手的“三→四升级”必达，随后由 defense_four 的健全性接管。
//   ⇒ 集合外白应手必败，AND 只需遍历集合内应手。
// ---------------------------------------------------------------------------
#include "vcfvct.h"

#include <algorithm>
#include <cassert>
#include <chrono>
#include <cstring>
#include <unordered_map>

#include "eval.h"
#include "forbidden.h"
#include "search.h"

namespace gvg {

namespace {

// 四方向（与 forbidden.cpp / order_score 完全一致）。
constexpr int DX4[4] = {1, 0, 1, 1};
constexpr int DY4[4] = {0, 1, 1, -1};
// 正交 4 邻域（气与提子）。
constexpr int NX4[4] = {1, -1, 0, 0};
constexpr int NY4[4] = {0, 0, 1, -1};

constexpr int ATTACK_RADIUS   = 4;  // 攻击候选：已有黑子切比雪夫距离 <= 4
constexpr int THREE_MIN_BLACK = 2;  // 三防御超集：窗内黑子数下限
constexpr long long DEFAULT_NODES = 300000;

using Pt    = std::pair<int, int>;
using Clock = std::chrono::steady_clock;

double now_sec() {
    return std::chrono::duration<double>(Clock::now().time_since_epoch()).count();
}

inline int cell_index(int x, int y) { return Board::index(x, y); }
inline int cell_x(int idx) { return idx / MAX_BOARD; }
inline int cell_y(int idx) { return idx % MAX_BOARD; }

// ===========================================================================
// 2.1 单点威胁级别
// ===========================================================================
// 把 (x,y) 当作黑子（不落子）求其最强方向的线型等级。允许 (x,y) 上已有黑子
// （此时 classify_point 的中心恒为 SELF，结果即该黑子自身的线型）。
int attack_rank_at(const Board& b, int x, int y) {
    bool flex4 = false, b4 = false, flex3 = false;
    for (int d = 0; d < 4; ++d) {
        const PointPattern p = classify_point(b, x, y, BLACK, DX4[d], DY4[d]);
        if (p == PP_FIVE) return static_cast<int>(AtkType::FIVE);
        if (p == PP_FLEX4) flex4 = true;
        else if (p == PP_B4) b4 = true;
        else if (p == PP_FLEX3) flex3 = true;
    }
    // 合法黑棋不可能同时有两个方向的四（四四禁手），故“任一方向”语义安全。
    if (flex4) return static_cast<int>(AtkType::OPEN_FOUR);
    if (b4) return static_cast<int>(AtkType::RUSH_FOUR);
    if (flex3) return static_cast<int>(AtkType::OPEN_THREE);
    return static_cast<int>(AtkType::NONE);
}

AtkType attack_class(Board& b, int x, int y) {
    if (!b.is_empty(x, y)) return AtkType::NONE;
    return static_cast<AtkType>(attack_rank_at(b, x, y));
}

// 黑棋在该空点是否“不可落”：Rapfi 禁手（长连/四四/三三）或无气自杀。
// 与 gen_moves 的黑方过滤条件一致（check_forbidden 本身不含自杀判定）。
bool black_point_illegal(Board& b, int x, int y) {
    if (b.is_dead_empty(x, y)) return true;
    return check_forbidden(b, x, y);
}

// ===========================================================================
// 2.2 全盘四窗扫描：合法完成点 + a 类窗内黑子标记
// ===========================================================================
// 枚举 4 方向 × 全部盘内 5 连窗：窗内恰 4 黑 + 1 空 + 0 白/障碍 → 完成点候选；
// 完成点还需本身合法（非禁手、非自杀），否则该窗只是“假四”（长连完成点等），
// 既不是真威胁，也不产生防御点。同时对 a 类窗的 4 个黑子做标记（供 2.4c 用）。
void scan_completion_points(Board& b, uint8_t* window_black,
                            std::vector<int>* comps) {
    const int n = b.size();
    uint8_t seen[MAX_CELLS];
    std::memset(seen, 0, sizeof(seen));
    int line[MAX_BOARD];

    for (int d = 0; d < 4; ++d) {
        const int dx = DX4[d], dy = DY4[d];
        for (int sx = 0; sx < n; ++sx) {
            for (int sy = 0; sy < n; ++sy) {
                if (b.in_bounds(sx - dx, sy - dy)) continue;  // 只从线的起点扫
                int len = 0;
                for (int cx = sx, cy = sy; b.in_bounds(cx, cy);
                     cx += dx, cy += dy)
                    line[len++] = cell_index(cx, cy);
                for (int i = 0; i + 5 <= len; ++i) {
                    int nb = 0, e = -1;
                    bool blocked = false;
                    for (int k = 0; k < 5; ++k) {
                        const uint8_t v = b.at(cell_x(line[i + k]),
                                               cell_y(line[i + k]));
                        if (v == BLACK) ++nb;
                        else if (v == EMPTY) e = k;
                        else { blocked = true; break; }
                    }
                    if (blocked || nb != 4 || e < 0) continue;
                    const int cidx = line[i + e];
                    if (black_point_illegal(b, cell_x(cidx), cell_y(cidx)))
                        continue;   // 长连/33/44/自杀：不是真威胁
                    for (int k = 0; k < 5; ++k)
                        if (k != e) window_black[line[i + k]] = 1;
                    if (!seen[cidx]) {
                        seen[cidx] = 1;
                        comps->push_back(cidx);
                    }
                }
            }
        }
    }
}

// ===========================================================================
// 2.3 黑块表（气列表 / 气数 / 是否含 a 类窗内黑子）
// ===========================================================================
struct GroupTable {
    int  gid[MAX_CELLS];       // 棋格 -> 块号；非黑子为 -1
    int  lib_begin[MAX_CELLS]; // 块号 -> libs 起点
    int  lib_count[MAX_CELLS]; // 块号 -> 气数
    bool has_window[MAX_CELLS];// 块号 -> 是否含 a 类窗内黑子
    int  ngroups = 0;
    std::vector<int> libs;     // 扁平气列表（去重）
};

void build_groups(const Board& b, const uint8_t* window_black, GroupTable* t) {
    const int n = b.size();
    for (int i = 0; i < MAX_CELLS; ++i) t->gid[i] = -1;
    t->libs.clear();
    t->ngroups = 0;

    uint8_t seen[MAX_CELLS];
    std::memset(seen, 0, sizeof(seen));
    std::vector<int> stack;

    for (int x = 0; x < n; ++x) {
        for (int y = 0; y < n; ++y) {
            if (b.at(x, y) != BLACK) continue;
            const int start = cell_index(x, y);
            if (seen[start]) continue;

            const int g = t->ngroups++;
            t->lib_begin[g]  = static_cast<int>(t->libs.size());
            t->has_window[g] = false;
            stack.clear();
            stack.push_back(start);
            seen[start] = 1;
            t->gid[start] = g;

            for (size_t qi = 0; qi < stack.size(); ++qi) {
                const int cur = stack[qi];
                const int cx = cell_x(cur), cy = cell_y(cur);
                if (window_black && window_black[cur]) t->has_window[g] = true;
                for (int k = 0; k < 4; ++k) {
                    const int nx = cx + NX4[k], ny = cy + NY4[k];
                    if (!b.in_bounds(nx, ny)) continue;
                    const int ni = cell_index(nx, ny);
                    const uint8_t v = b.at(nx, ny);
                    if (v == BLACK) {
                        if (!seen[ni]) {
                            seen[ni] = 1;
                            t->gid[ni] = g;
                            stack.push_back(ni);
                        }
                    } else if (v == EMPTY) {
                        bool dup = false;
                        for (size_t q = t->lib_begin[g]; q < t->libs.size(); ++q)
                            if (t->libs[q] == ni) { dup = true; break; }
                        if (!dup) t->libs.push_back(ni);
                    }
                }
            }
            t->lib_count[g] = static_cast<int>(t->libs.size()) - t->lib_begin[g];
        }
    }
}

// 去重累积器（棋盘空点集合）。
struct PointSet {
    uint8_t mark[MAX_CELLS];
    std::vector<int> idx;
    PointSet() { std::memset(mark, 0, sizeof(mark)); }
    void add(const Board& b, int i) {
        if (i < 0 || i >= MAX_CELLS || mark[i]) return;
        const int x = cell_x(i), y = cell_y(i);
        if (!b.is_empty(x, y)) return;
        mark[i] = 1;
        idx.push_back(i);
    }
    void finalize(std::vector<Pt>* out) const {
        out->clear();
        out->reserve(idx.size());
        for (size_t i = 0; i < idx.size(); ++i)
            out->push_back(Pt(cell_x(idx[i]), cell_y(idx[i])));
        std::sort(out->begin(), out->end());
    }
};

// ===========================================================================
// 2.4 四威胁的健全防御集：a) 合法完成点 b) 1 气块提子点
//                          c) 吃子使能闭包 d) 自杀使能闭包
// ===========================================================================
std::vector<Pt> defense_four(Board& b) {
    uint8_t window_black[MAX_CELLS];
    std::memset(window_black, 0, sizeof(window_black));
    std::vector<int> comps;
    comps.reserve(8);
    scan_completion_points(b, window_black, &comps);

    PointSet set;
    for (size_t i = 0; i < comps.size(); ++i) set.add(b, comps[i]);   // (a)

    GroupTable gt;
    build_groups(b, window_black, &gt);
    for (int g = 0; g < gt.ngroups; ++g) {
        const int nl = gt.lib_count[g];
        // (b) 1 气黑块：白下其唯一气点即提子，可能消掉含窗内子的块。
        if (nl == 1) set.add(b, gt.libs[gt.lib_begin[g]]);
        // (c) 吃子使能闭包：≤2 气且含 a 类窗内黑子的块的全部气（白可先压成 1 气组）。
        if (nl <= 2 && gt.has_window[g])
            for (int q = gt.lib_begin[g]; q < gt.lib_begin[g] + nl; ++q)
                set.add(b, gt.libs[q]);
    }

    for (size_t i = 0; i < comps.size(); ++i) {
        const int c = comps[i];
        const int cx = cell_x(c), cy = cell_y(c);
        for (int k = 0; k < 4; ++k) {
            const int nx = cx + NX4[k], ny = cy + NY4[k];
            if (!b.in_bounds(nx, ny)) continue;
            const int ni = cell_index(nx, ny);
            if (b.at(nx, ny) == BLACK) {
                // (d) 自杀使能闭包：与完成点正交相邻的黑块的全部气。
                const int g = gt.gid[ni];
                if (g >= 0)
                    for (int q = gt.lib_begin[g]; q < gt.lib_begin[g] + gt.lib_count[g]; ++q)
                        set.add(b, gt.libs[q]);
            } else if (b.is_empty(nx, ny)) {
                // (d) 完成点自身的空正交邻点：白占之可减少 c 落子后所属块的气。
                set.add(b, ni);
            }
        }
    }

    std::vector<Pt> out;
    set.finalize(&out);
    return out;
}

// ===========================================================================
// 2.5 三威胁的健全防御超集：a) 四的防御集 b) 过点三窗空点
//                          c) 吃子使能闭包 d) 升级合法性闭包
// ===========================================================================
std::vector<Pt> defense_three(Board& b, int px, int py) {
    PointSet set;
    // (a) 四的防御集（白下这里可抢先破坏其它四威胁）全部并入。
    {
        std::vector<Pt> fours = defense_four(b);
        for (size_t i = 0; i < fours.size(); ++i)
            set.add(b, cell_index(fours[i].first, fours[i].second));
    }

    // (b) 经过 (px,py) 的盘内 5 窗中“0 白 0 障碍且黑子 >= 2”的窗的全部空点。
    uint8_t window_black[MAX_CELLS];
    std::memset(window_black, 0, sizeof(window_black));
    std::vector<int> makers;   // b 类窗内的空点（四 maker 候选）
    for (int d = 0; d < 4; ++d) {
        const int dx = DX4[d], dy = DY4[d];
        for (int k = 0; k < 5; ++k) {
            const int sx = px - k * dx, sy = py - k * dy;
            if (!b.in_bounds(sx, sy)) continue;
            if (!b.in_bounds(sx + 4 * dx, sy + 4 * dy)) continue;
            int nb = 0;
            bool blocked = false;
            for (int i = 0; i < 5; ++i) {
                const uint8_t v = b.at(sx + i * dx, sy + i * dy);
                if (v == BLACK) ++nb;
                else if (v != EMPTY) { blocked = true; break; }
            }
            if (blocked || nb < THREE_MIN_BLACK) continue;
            for (int i = 0; i < 5; ++i) {
                const int cx = sx + i * dx, cy = sy + i * dy;
                if (!b.is_empty(cx, cy)) continue;
                const int ci = cell_index(cx, cy);
                window_black[ci] = 1;
                set.add(b, ci);
            }
        }
    }

    // (c) 吃子使能闭包：≤2 气且含 b 类窗内黑子的块的全部气。
    GroupTable gt;
    build_groups(b, window_black, &gt);
    for (int g = 0; g < gt.ngroups; ++g) {
        const int nl = gt.lib_count[g];
        if (nl == 1) set.add(b, gt.libs[gt.lib_begin[g]]);   // 与四集同源的提子点
        if (nl <= 2 && gt.has_window[g])
            for (int q = gt.lib_begin[g]; q < gt.lib_begin[g] + nl; ++q)
                set.add(b, gt.libs[q]);
    }

    // (d) 升级合法性闭包：每个“四 maker”f 的 4 个正交空邻点。
    for (int cx = 0; cx < b.size(); ++cx) {
        for (int cy = 0; cy < b.size(); ++cy) {
            const int ci = cell_index(cx, cy);
            if (!window_black[ci]) continue;
            const AtkType cls = attack_class(b, cx, cy);
            if (cls != AtkType::OPEN_FOUR && cls != AtkType::RUSH_FOUR) continue;
            for (int k = 0; k < 4; ++k) {
                const int nx = cx + NX4[k], ny = cy + NY4[k];
                if (!b.in_bounds(nx, ny)) continue;
                if (b.is_empty(nx, ny)) set.add(b, cell_index(nx, ny));
            }
        }
    }

    std::vector<Pt> out;
    set.finalize(&out);
    return out;
}

// ===========================================================================
// 2.6 攻击候选生成
// ===========================================================================
struct AttackCand {
    int x, y, rank, score;
};

// 黑方攻击候选：已有黑子切比雪夫距离 <= ATTACK_RADIUS 的空点里
//   allow_three=false (VCF)：FIVE / OPEN_FOUR / RUSH_FOUR
//   allow_three=true  (VCT)：再加 OPEN_THREE
// 每个候选必须 check_forbidden==false 且非无气自杀点（禁手手一律不是攻击候选）。
// 预算剪枝：FIVE 需 steps_left>=1；四类需 >=2；活三需 >=3。
//
// 廉价预筛（不改变结果集）：任何五/四/三都要求该点在某个 5 连窗内与 >= 2 个黑子
// 同行同列同对角，故“切比雪夫距离 <= 4 的邻域内黑子数 < 2”的点必然
// attack_class == NONE，直接跳过。邻域黑子数用二维前缀和 O(1) 查询。
void gen_attack_candidates(Board& b, int steps_left, bool allow_three,
                           std::vector<AttackCand>* out) {
    const int n = b.size();
    const int S = MAX_BOARD + 1;
    int pre[(MAX_BOARD + 1) * (MAX_BOARD + 1)];
    std::memset(pre, 0, sizeof(pre));
    for (int x = 0; x < n; ++x) {
        int rowsum = 0;
        for (int y = 0; y < n; ++y) {
            if (b.at(x, y) == BLACK) ++rowsum;
            pre[(x + 1) * S + (y + 1)] = pre[x * S + (y + 1)] + rowsum;
        }
    }
    auto box_count = [&](int x0, int y0, int x1, int y1) {
        return pre[(x1 + 1) * S + (y1 + 1)] - pre[x0 * S + (y1 + 1)] -
               pre[(x1 + 1) * S + y0] + pre[x0 * S + y0];
    };

    for (int nx = 0; nx < n; ++nx) {
        for (int ny = 0; ny < n; ++ny) {
            if (!b.is_empty(nx, ny)) continue;
            const int x0 = std::max(0, nx - ATTACK_RADIUS);
            const int x1 = std::min(n - 1, nx + ATTACK_RADIUS);
            const int y0 = std::max(0, ny - ATTACK_RADIUS);
            const int y1 = std::min(n - 1, ny + ATTACK_RADIUS);
            if (box_count(x0, y0, x1, y1) < 2) continue;   // 不可能构成威胁
            const int rank = attack_rank_at(b, nx, ny);
            if (rank <= static_cast<int>(AtkType::NONE)) continue;
            if (rank == static_cast<int>(AtkType::OPEN_THREE)) {
                if (!allow_three) continue;
                if (steps_left < 3) continue;
            } else if (rank < static_cast<int>(AtkType::FIVE)) {
                if (steps_left < 2) continue;   // 四类：至少还要一手才能成五
            }
            if (black_point_illegal(b, nx, ny)) continue;   // 禁手 / 无气自杀
            AttackCand c;
            c.x = nx;
            c.y = ny;
            c.rank = rank;
            c.score = order_score(b, nx, ny, BLACK);
            out->push_back(c);
        }
    }

    std::sort(out->begin(), out->end(), [](const AttackCand& a, const AttackCand& b2) {
        if (a.rank != b2.rank) return a.rank > b2.rank;      // FIVE > 活四 > 冲四 > 活三
        if (a.score != b2.score) return a.score > b2.score;  // 同类按 order_score 降序
        if (a.x != b2.x) return a.x < b2.x;
        return a.y < b2.y;
    });
}

// 白方应手排序：order_score(b,w,WHITE) 降序，同分按坐标（保证确定性）。
void order_white_defenses(const Board& b, std::vector<Pt>* pts) {
    std::vector<std::pair<int, Pt>> tmp;
    tmp.reserve(pts->size());
    for (size_t i = 0; i < pts->size(); ++i)
        tmp.push_back(std::make_pair(
            order_score(b, (*pts)[i].first, (*pts)[i].second, WHITE), (*pts)[i]));
    std::sort(tmp.begin(), tmp.end(),
              [](const std::pair<int, Pt>& a, const std::pair<int, Pt>& b2) {
                  if (a.first != b2.first) return a.first > b2.first;
                  return a.second < b2.second;
              });
    for (size_t i = 0; i < tmp.size(); ++i) (*pts)[i] = tmp[i].second;
}

// ===========================================================================
// 2.7 / 2.8 证明搜索
// ===========================================================================
struct ProveCtx {
    long long nodes = 0;
    long long node_limit = DEFAULT_NODES;
    double    deadline = 0.0;      // steady_clock 秒；<=0 表示无时限
    bool      timeout = false;
};

// hash -> 已证明成功的**最小**黑攻击手数（证明距离）。只存“证明成功”的结果
// （UNKNOWN 与预算相关，不能存）。
//
// 方向说明（与任务书 2.3 步骤 2 的 `tt[hash] >= steps_left` 不同，是必须的健全性
// 修正）：“预算 k 内必胜”是**单调增**的（k 手内能赢 ⇒ 更多手也能赢），因此已证明
// 的 k 只能推出“任何 steps_left >= k 都成立”。若按 `stored >= steps_left` 命中，
// 等于用“6 手内必胜”去断言“4 手内必胜”——不成立。实测反例（第 6 步调试记录）：
// T4 局面候选 (5,8) 在带该错误方向的 TT 下会拿到 W9（预算 4）标签，而同一调用用
// 空 TT 重跑在 2998 个节点内即被白方反驳（win=false）；修成 <= 后两张表一致。
using ProveTT = std::unordered_map<uint64_t, int>;

// 节点入口的预算检查：超限即 timeout=true。
bool budget_exceeded(ProveCtx* ctx) {
    ++ctx->nodes;
    if (ctx->node_limit > 0 && ctx->nodes > ctx->node_limit) {
        ctx->timeout = true;
        return true;
    }
    if (ctx->deadline > 0.0 && now_sec() > ctx->deadline) {
        ctx->timeout = true;
        return true;
    }
    return false;
}

// 记录“该局面（黑先）在 budget 手内被证明必胜”，保留最小证明距离。
void tt_store(ProveTT* tt, uint64_t key, int budget) {
    ProveTT::iterator it = tt->find(key);
    if (it == tt->end())
        tt->emplace(key, budget);
    else if (budget < it->second)
        it->second = budget;
}

// 黑方节点（OR 节点）。前置 b.turn()==BLACK，steps_left = 剩余黑攻击手数。
// 返回 true 当且仅当“存在一手攻击 e，使白方防御集内每个应手后黑方仍被证明必胜”。
bool prove_black_dfs(Board& b, int steps_left, bool allow_three, ProveCtx* ctx,
                     ProveTT* tt) {
    if (budget_exceeded(ctx)) return false;
    if (steps_left <= 0) return false;

    const uint64_t key = b.hash();
    {
        ProveTT::const_iterator it = tt->find(key);
        // 已证明的距离 <= 当前预算 ⇒ 预算内同样必胜（单调增方向）。
        if (it != tt->end() && it->second <= steps_left) return true;
    }

    std::vector<AttackCand> cands;
    cands.reserve(32);
    gen_attack_candidates(b, steps_left, allow_three, &cands);

    for (size_t ci = 0; ci < cands.size(); ++ci) {
        const AttackCand& c = cands[ci];
        if (!b.make_move(c.x, c.y, BLACK)) continue;   // 禁手之外再验一次（自杀等）
        if (b.last_move_was_five()) {                  // 成五：1 手证明，直接成功
            b.undo_move();
            tt_store(tt, key, steps_left);
            return true;
        }

        // 防御集按黑方这一手的成分选择：含四成分 → 四的防御集；纯活三 → 三的超集。
        std::vector<Pt> wdefs =
            (c.rank >= static_cast<int>(AtkType::RUSH_FOUR))
                ? defense_four(b)
                : defense_three(b, c.x, c.y);

        // 防御集为空：只有当“白下集合外黑立即成五”成立时才算证明成功。防御集的 a 项
        // 已收录全盘所有**合法**完成点，因此集合为空等价于“全盘没有可立即成五的合法点”
        // （含假四：完成点长连/三三/四四/自杀），此时 2.2.2 的论证不成立 → 不算证明。
        // 任务书 2.3 步骤 4d 在这一分支直接返回成功，属该论证未覆盖的退化情形；
        // 实测 1500 个随机局面 / 678 个四类候选 + 7891 个三类候选从未出现空集合，
        // 故这里只做健全性加固（宁可漏标）：不影响任何实测到的分支。
        if (wdefs.empty()) {
            b.undo_move();
            continue;
        }

        order_white_defenses(b, &wdefs);
        bool all_ok = true;
        for (size_t wi = 0; wi < wdefs.size(); ++wi) {
            if (!b.make_move(wdefs[wi].first, wdefs[wi].second, WHITE)) continue;
            const bool sub =
                prove_black_dfs(b, steps_left - 1, allow_three, ctx, tt);
            b.undo_move();
            if (ctx->timeout) { b.undo_move(); return false; }
            if (!sub) { all_ok = false; break; }        // 存在白方反驳 → 该候选失败
        }
        b.undo_move();
        if (all_ok) {
            tt_store(tt, key, steps_left);
            return true;
        }
    }
    return false;
}

// 白方节点（AND 节点）。前置 b.turn()==WHITE，黑方刚在 (cx,cy) 落子。
// 返回 true 当且仅当“该手是真威胁，且防御集内每个应手后黑方都在 budget 手内必胜”。
bool prove_white_node(Board& b, int cx, int cy, int budget, ProveCtx* ctx,
                      ProveTT* tt) {
    if (budget_exceeded(ctx)) return false;
    const int rank = attack_rank_at(b, cx, cy);
    if (rank < static_cast<int>(AtkType::OPEN_THREE))
        return false;   // 非威胁手 → 非强制 → 不成证明

    std::vector<Pt> wdefs =
        (rank >= static_cast<int>(AtkType::RUSH_FOUR))
            ? defense_four(b)
            : defense_three(b, cx, cy);
    // 防御集为空 → 与 prove_black_dfs 同样的健全性处理：只有“集合外黑立即成五”被
    // 论证覆盖时才算证明成功；而防御集空 ⟺ 全盘无合法完成点，故不算证明（宁可漏标）。
    if (wdefs.empty()) return false;

    order_white_defenses(b, &wdefs);
    for (size_t wi = 0; wi < wdefs.size(); ++wi) {
        if (!b.make_move(wdefs[wi].first, wdefs[wi].second, WHITE)) continue;
        const bool sub = prove_black_dfs(b, budget, true, ctx, tt);
        b.undo_move();
        if (ctx->timeout) return false;
        if (!sub) return false;       // 存在白方反驳 → 未证明
    }
    return true;
}

}  // namespace

// ===========================================================================
// 2.9 主入口：逐候选标注
// ===========================================================================
AnalysisResult analyse(Board& b, int color, int max_steps, int winmode,
                       double time_limit_sec, long long node_limit) {
    AnalysisResult res;
    res.paths_found = 0;
    res.nodes = 0;
    res.timeout = false;
#ifndef NDEBUG
    const uint64_t h0 = b.hash();
#endif

    ProveCtx ctx;
    ctx.node_limit = node_limit;
    ctx.deadline = (time_limit_sec > 0.0) ? now_sec() + time_limit_sec : 0.0;
    ProveTT tt;

    const std::vector<Move> cands = gen_moves(b, color);
    res.labels.reserve(cands.size());
    for (size_t i = 0; i < cands.size(); ++i) {
        CandidateLabel lab;
        lab.x = cands[i].x;
        lab.y = cands[i].y;
        lab.tag = 0;
        lab.steps = 0;

        if (!ctx.timeout && b.make_move(lab.x, lab.y, color)) {
            bool decided = false;
            if (color == BLACK && b.last_move_was_five()) {
                lab.tag = 'W';          // 该手立即成五（1 手）
                lab.steps = 1;
                decided = true;
            } else if (b.white_wins_now(winmode)) {
                decided = true;         // 此手之后白方已达成胜利条件
            }
            if (!decided && color == BLACK) {
                // 迭代加深：m = 总黑攻击手数（含本手 c）。非威胁手有预算下界：
                // 活三至少还要两手（三→四→五），四类至少还要一手。
                const int cls = attack_rank_at(b, lab.x, lab.y);
                const int lo = (cls == static_cast<int>(AtkType::OPEN_THREE))
                                   ? 3
                                   : ((cls == static_cast<int>(AtkType::OPEN_FOUR) ||
                                       cls == static_cast<int>(AtkType::RUSH_FOUR))
                                          ? 2
                                          : 0);
                for (int m = std::max(2, lo); m <= max_steps; ++m) {
                    if (m < lo) continue;
                    const bool win = prove_white_node(b, lab.x, lab.y, m - 1, &ctx, &tt);
                    if (ctx.timeout) break;
                    if (win) {
                        lab.tag = 'W';
                        lab.steps = 2 * m - 1;   // 黑第 m 手成五落在总第 2m-1 手
                        break;
                    }
                }
            } else if (!decided && color == WHITE) {
                // 白候选 c 已落盘：黑方在 m 手内被证明必胜 ⇒ c 是必败手。
                for (int m = 1; m <= max_steps; ++m) {
                    const bool win = prove_black_dfs(b, m, true, &ctx, &tt);
                    if (ctx.timeout) break;
                    if (win) {
                        lab.tag = 'L';
                        lab.steps = 2 * m;       // 白第 1 手 + 黑第 m 手
                        break;
                    }
                }
            }
            b.undo_move();
        }
        if (lab.tag != 0) ++res.paths_found;
        res.labels.push_back(lab);
    }

    res.nodes = ctx.nodes;
    res.timeout = ctx.timeout;
#ifndef NDEBUG
    assert(b.hash() == h0);
#endif
    return res;
}

// ===========================================================================
// 2.10 包装：prove_black / vcf_exists / vct_exists
// ===========================================================================
ProveResult prove_black(Board& b, int max_steps, bool allow_three,
                        double time_sec, long long node_limit) {
    if (b.turn() != BLACK) return ProveResult::UNKNOWN;
#ifndef NDEBUG
    const uint64_t h0 = b.hash();
#endif
    ProveCtx ctx;
    ctx.node_limit = node_limit;
    ctx.deadline = (time_sec > 0.0) ? now_sec() + time_sec : 0.0;
    ProveTT tt;
    const bool win = prove_black_dfs(b, max_steps, allow_three, &ctx, &tt);
#ifndef NDEBUG
    assert(b.hash() == h0);
#endif
    if (ctx.timeout) return ProveResult::TIMEOUT;
    return win ? ProveResult::WIN : ProveResult::UNKNOWN;
}

bool vcf_exists(Board& b, int max_steps) {
    return prove_black(b, max_steps, /*allow_three=*/false, 30.0, DEFAULT_NODES) ==
           ProveResult::WIN;
}

bool vct_exists(Board& b, int max_steps) {
    return prove_black(b, max_steps, /*allow_three=*/true, 30.0, DEFAULT_NODES) ==
           ProveResult::WIN;
}

}  // namespace gvg
