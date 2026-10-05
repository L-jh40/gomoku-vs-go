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
//   3.  威胁候选点（阻挡点）：查表规则的增量棋型实现（第 7 步新增）
//        collect_line_cells / line_threat_rank / line_blockers / collect_threat_lines
//        threat_lines_through / double_threat_points / black_five_within_two
//        capture_points_from_mask / blocking_point_forbidden_note
//   4.  三层 VCT：layer_attacks / smart_responses / layer_responses / layer_dfs /
//        layer_run（vct_all_response / vct_smart_response）+ mixed_defense_intersection
//   5.  主入口：sound_lose_steps（健全步数）+ analyse（黑方逐候选标注；
//        白方 = 威胁候选点 + 最好一档 + minimax 收尾）
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
#include "pattern_table.h"
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
    int cls = 2;   // 三档预算分类：2=VCF(冲四/活四/五) 1=VCT(活三/做杀) 0=VC2(活二/眠三)
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
// allow_vc2：再把“只形成活二 / 眠三”的点也收进来（VC2 档，见第 4 节的三档预算）。
void gen_attack_candidates(Board& b, int steps_left, bool allow_three,
                           std::vector<AttackCand>* out,
                           bool allow_vc2 = false) {
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
            int cls = -1;
            if (rank >= static_cast<int>(AtkType::RUSH_FOUR)) {
                cls = 2;                                  // 冲四 / 活四 / 五 -> VCF
                if (rank < static_cast<int>(AtkType::FIVE) && steps_left < 2)
                    continue;                             // 四类：至少还要一手才能成五
                if (steps_left < 1) continue;
            } else if (rank == static_cast<int>(AtkType::OPEN_THREE)) {
                cls = 1;                                  // 活三 / 做杀 -> VCT
                if (!allow_three) continue;
                if (steps_left < 3) continue;
            } else if (allow_vc2) {
                // 只形成活二 / 眠三 -> VC2
                for (int d = 0; d < 4; ++d) {
                    const PointPattern p =
                        classify_point(b, nx, ny, BLACK, DX4[d], DY4[d]);
                    if (p == PP_FLEX2 || p == PP_B3) { cls = 0; break; }
                }
                if (cls < 0) continue;
                if (steps_left < 1) continue;
            } else {
                continue;
            }
            if (black_point_illegal(b, nx, ny)) continue;   // 禁手 / 无气自杀
            AttackCand c;
            c.x = nx;
            c.y = ny;
            c.rank = rank;
            c.cls = cls;
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

// ===========================================================================
// 3. 白棋威胁候选点（第 8 步重写：rapfi 式威胁分类 + 逐威胁防御集 + 交集框架）
// ===========================================================================
// 迁移自 Rapfi 的威胁判定（game/pattern.cpp 的 DEFENCE 防守掩码思想、
// game/movegen.cpp 的 findFourDefence / findB4F3Defence / findFlex4LineDefence）。
//
// 威胁点分类（增量棋型缓存 O(1)/点，方向线型 point_pattern_d 组合；p4 == FORBID
// 且 check_forbidden 为真的真禁手点黑棋不能落 → 不是威胁；假禁手点照常分类）：
//   * kind 0 成五点：某方向 PP_FIVE（盘上已有四）→ 防御 = 成五点本身 ∪ 吃子点
//     （四的完成点唯一，白占其余位置无效——用户规格 10111/011112 → 1 点）；
//   * kind 1 杀点：活四/双四成分参与的立即胜（PP_FLEX4 ∧ 其他方向三/四、双活四、
//     双冲四、三三[禁手关闭时]）→ 活四/双四成分不可挡，防御 = 杀点本身 ∪ 吃子点
//     ∪ 无气构造点（占位/降级探针都挡不住活四，一律无效——用例 a → {h9}）；
//   * kind 2 四三杀点：PP_B4 ∧ PP_FLEX3 → 防御 = 杀点本身 ∪ 活三线“线型降级”
//     探针 ∪ 冲四线的成五点 ∪ 吃子/无气构造（用例 #4 → {h9,h10,g10,k6}）；
//   * kind 3 纯活四点：单方向 PP_FLEX4（活三的成活四点）→ 防御 = 该线的试落阻挡
//     点 ∪ 吃子/无气构造（用例 #5 → {h9,h5}；用例 c 交集 → {g8}）。
//   纯冲四点（单方向 PP_B4）不是强迫威胁（冲四的成五点一手可挡）→ 不产生候选
//   （用例 b legal:everywhere）；纯活三点同理（它的成活四点才是威胁点）。
//
// 试落阻挡点 = 空点 p，白棋真实 make_move(p, WHITE)（含提子/无气翻转）后，线上
// 不再存在“黑棋可落的成五/活四制造点”——Rapfi DEFENCE 查表（fillDefenceLUT：
// 防守子试落后攻击方线型 < F3）在混合规则下的运行时等价。用户规格查表逐条复现：
// 10111/011112 → 1 点；0011102 → 3 点；0011100 → 紧邻 2 点。
//
// 无气构造点 = 黑棋落威胁点 q 后其块恰有 1/2 口气时的气点（1 气：q 自填即被提；
// 2 气：白占一气后 q 变 1 气、下一手提）——混合规则的“吃子阻挡”（用例 c 的 g8）。
//
// 候选集 = 所有威胁防御集的**交集**；交集为空回退**并集**（黑棋多重杀时白棋已不可
// 挡，并集给出最有抵抗价值的点）；盘面无强迫威胁 → 不受约束（全盘空点）。

// 收集一条线（从线上第一个盘内格开始）的全部盘内格 idx。
int collect_line_cells(const Board& b, int d, int sx, int sy, int* out) {
    const int dx = DX4[d], dy = DY4[d];
    int n = 0;
    for (int cx = sx, cy = sy; b.in_bounds(cx, cy); cx += dx, cy += dy) {
        if (n >= MAX_BOARD) break;
        out[n++] = cell_index(cx, cy);
    }
    return n;
}

// 空点 e 在方向 d 上的“黑棋落子后”线型（直接读增量棋型缓存）。
PointPattern point_pattern_d(const Board& b, int idx, int d) {
    return classify_point(b, cell_x(idx), cell_y(idx), BLACK, DX4[d], DY4[d]);
}

// ---- 3.1 威胁点分类 -------------------------------------------------------
struct ThreatPoint {
    int x = 0, y = 0;
    int kind = 0;          // 0=成五点 1=杀点(活四/双四成分) 2=四三杀点 3=纯活四点
    uint8_t f5_dirs = 0;   // PP_FIVE 方向位掩码
    uint8_t f4_dirs = 0;   // PP_FLEX4 方向位掩码
    uint8_t b4_dirs = 0;   // PP_B4 方向位掩码
    uint8_t f3_dirs = 0;   // PP_FLEX3 方向位掩码
};

// 全盘扫描黑棋“强迫威胁点”：白棋必须应对，否则黑棋下一手（或两三手内）成五。
// 纯冲四 / 纯活三 / 更弱的点一律不算（冲四可挡、活三由它的成活四点代表）。
std::vector<ThreatPoint> scan_black_threats(Board& b) {
    std::vector<ThreatPoint> out;
    const int n = b.size();
    for (int x = 0; x < n; ++x) {
        for (int y = 0; y < n; ++y) {
            if (!b.is_empty(x, y)) continue;
            const int idx = cell_index(x, y);
            if (b.is_no_liberty(idx)) continue;            // 无气空点 = 阻挡
            const int p4 = b.cached_pattern4_black(idx);
            if (p4 == P4_NONE) continue;                   // O(1) 预筛：无三以上成分
            if (p4 == FORBID && check_forbidden(b, x, y))
                continue;                                  // 真禁手：黑棋不能落
            ThreatPoint t;
            t.x = x;
            t.y = y;
            int nf4 = 0, nb4 = 0, nf3 = 0;
            for (int d = 0; d < 4; ++d) {
                switch (point_pattern_d(b, idx, d)) {
                case PP_FIVE:   t.f5_dirs |= 1 << d; break;
                case PP_FLEX4:  t.f4_dirs |= 1 << d; ++nf4; break;
                case PP_B4:     t.b4_dirs |= 1 << d; ++nb4; break;
                case PP_FLEX3:  t.f3_dirs |= 1 << d; ++nf3; break;
                default: break;
                }
            }
            if (t.f5_dirs) {
                t.kind = 0;                                // 成五点（盘上有四）
            } else if (nf4 >= 1 && (nf3 >= 1 || nb4 >= 1 || nf4 >= 2)) {
                t.kind = 1;                                // 活四成分杀（立即胜）
            } else if (nf4 >= 1) {
                t.kind = 3;                                // 纯活四点（活三端点）
            } else if (nb4 >= 2) {
                t.kind = 1;                                // 双冲四杀（两个成五点）
            } else if (nb4 >= 1 && nf3 >= 1) {
                t.kind = 2;                                // 四三杀（冲四∧活三）
            } else if (nf3 >= 2) {
                t.kind = 1;                                // 三三杀（禁手关闭时才到达）
            } else {
                continue;                                  // 纯冲四 / 纯活三 / 更弱
            }
            out.push_back(t);
        }
    }
    return out;
}

// ---- 3.2 试落阻挡点 -------------------------------------------------------
// 线上是否仍存在“黑棋可落”的成五/活四制造点（制造点本身是禁手/自杀的算假威胁）。
bool line_has_fire(const Board& b, const int* cells, int n, int d) {
    for (int i = 0; i < n; ++i) {
        const int c = cells[i];
        const int x = cell_x(c), y = cell_y(c);
        if (!b.is_empty(x, y)) continue;
        if (b.is_no_liberty(c)) continue;                  // 无气空点 = 阻挡
        const PointPattern p = point_pattern_d(b, c, d);
        if (p != PP_FIVE && p != PP_FLEX4) continue;
        if (black_point_illegal(b, x, y)) continue;        // 禁手/自杀制造点 = 假威胁
        return true;
    }
    return false;
}

// 线上全部“试落阻挡点”：白棋真实落 p（含提子）后线上无成五/活四制造点。
// 只探测线上黑子 ±5 窗口内的空点（窗口外的白子不影响任何线型）。
std::vector<Pt> line_defense_points(Board& b, int d, int tx, int ty) {
    std::vector<Pt> out;
    int cells[MAX_BOARD];
    int sx = tx, sy = ty;
    const int dx = DX4[d], dy = DY4[d];
    while (b.in_bounds(sx - dx, sy - dy)) { sx -= dx; sy -= dy; }
    const int len = collect_line_cells(b, d, sx, sy, cells);

    // 线上黑子的位置（±5 窗口预筛用）。
    uint8_t near_black[MAX_BOARD];
    for (int i = 0; i < len; ++i) {
        const int x = cell_x(cells[i]), y = cell_y(cells[i]);
        int dist = std::abs(x - tx);
        if (d >= 2) dist = std::min(std::abs(x - tx), std::abs(y - ty));
        near_black[i] = (b.at(x, y) == BLACK && dist <= 5) ? 1 : 0;
    }
    for (int i = 0; i < len; ++i) {
        const int c = cells[i];
        const int x = cell_x(c), y = cell_y(c);
        if (!b.is_empty(x, y)) continue;
        // 白子必须落在某线上黑子 ±5 窗口内才可能改变线型（提子例外：提走线上
        // 黑子所在块，其邻点可能在窗口外——一并用窗口并集近似，漏掉的情形由
        // 交集/并集框架的吃子点覆盖）。
        bool in_window = false;
        for (int k = std::max(0, i - 9); k <= std::min(len - 1, i + 9) && !in_window; ++k)
            if (near_black[k]) in_window = true;
        if (!in_window) continue;
        if (!b.make_move(x, y, WHITE)) continue;
        const bool fire = line_has_fire(b, cells, len, d);
        b.undo_move();
        if (!fire) out.push_back(Pt(x, y));
    }
    return out;
}

// ---- 3.3 无气构造点 -------------------------------------------------------
// 假设黑棋落 (x,y)（不落子）：其块 = (x,y) ∪ 正交相连黑子，气 = 块的空正交邻点。
void black_group_libs_after(Board& b, int x, int y, std::vector<int>* libs) {
    libs->clear();
    uint8_t seen[MAX_CELLS];
    std::memset(seen, 0, sizeof(seen));
    std::vector<int> stack;
    const int start = cell_index(x, y);
    stack.push_back(start);
    seen[start] = 1;
    for (size_t qi = 0; qi < stack.size(); ++qi) {
        const int cur = stack[qi];
        const int cx = cell_x(cur), cy = cell_y(cur);
        for (int k = 0; k < 4; ++k) {
            const int nx = cx + NX4[k], ny = cy + NY4[k];
            if (!b.in_bounds(nx, ny)) continue;
            const int ni = cell_index(nx, ny);
            const uint8_t v = b.at(nx, ny);
            if (v == BLACK) {
                if (!seen[ni]) { seen[ni] = 1; stack.push_back(ni); }
            } else if (v == EMPTY && ni != start && !seen[ni]) {
                seen[ni] = 1;                          // start 假想已落黑，不算气
                libs->push_back(ni);
            }
        }
    }
}

// 黑棋落威胁点 q 后块气 ≤ 2 时的气点（白棋“构造无气/吃子”防御点）：
//   1 气：q 自填即死，白棋一手提走；2 气：白占一气后 q 变 1 气、下一手提。
// 气 >= 3：构造无气不可行 → 空表。
std::vector<Pt> self_capture_defense(Board& b, int x, int y) {
    std::vector<Pt> out;
    std::vector<int> libs;
    black_group_libs_after(b, x, y, &libs);
    const size_t take = std::min<size_t>(libs.size(), 2);
    for (size_t i = 0; i < take; ++i)
        out.push_back(Pt(cell_x(libs[i]), cell_y(libs[i])));
    return out;
}

// ---- 3.4 威胁相关吃子点 ---------------------------------------------------
// 威胁涉及方向线上（威胁点 ±5 窗口内）的黑子 → 相关黑块的吃子点：
// 1 气块的气点（一手提）；2 气块的两气点（落子后黑棋 2 步内不能连五才有效）。
std::vector<Pt> threat_captures(Board& b, const ThreatPoint& t) {
    uint8_t dirs = t.f5_dirs | t.f4_dirs | t.b4_dirs | t.f3_dirs;
    if (t.kind == 0) dirs = t.f5_dirs;         // 成五点：只有成五方向线上的黑子相关
    else if (t.kind == 1 && t.f4_dirs) dirs = t.f4_dirs;   // 活四杀：活四方向相关
    uint8_t mask[MAX_CELLS];
    std::memset(mask, 0, sizeof(mask));
    int cells[MAX_BOARD];
    for (int d = 0; d < 4; ++d) {
        if (!(dirs & (1 << d))) continue;
        int sx = t.x, sy = t.y;
        const int dx = DX4[d], dy = DY4[d];
        while (b.in_bounds(sx - dx, sy - dy)) { sx -= dx; sy -= dy; }
        const int len = collect_line_cells(b, d, sx, sy, cells);
        for (int i = 0; i < len; ++i) {
            const int x = cell_x(cells[i]), y = cell_y(cells[i]);
            if (b.at(x, y) != BLACK) continue;
            int dist = std::abs(x - t.x);
            if (d >= 2) dist = std::min(std::abs(x - t.x), std::abs(y - t.y));
            if (dist > 5) continue;
            mask[cells[i]] = 1;
        }
    }
    return capture_points_from_mask(b, mask);
}

// ---- 3.5 逐威胁防御集 -----------------------------------------------------
// Defense(T) = {T} ∪ 试落阻挡 ∪ 吃子 ∪ 无气构造。全部点经 PointSet 去重排序。
std::vector<Pt> threat_defense(Board& b, const ThreatPoint& t) {
    PointSet def;
    def.add(b, cell_index(t.x, t.y));                    // 占据威胁点（通用防御）

    int cells[MAX_BOARD];
    if (t.kind == 3 || (t.kind == 1 && !t.f4_dirs && !t.b4_dirs)) {
        // 纯活四点 / 三三杀：线上试落阻挡 / 活三线线型降级探针。
        for (int d = 0; d < 4; ++d) {
            const bool f4dir = (t.kind == 3) && (t.f4_dirs & (1 << d));
            const bool f3dir = (t.kind == 1) && (t.f3_dirs & (1 << d));
            if (!f4dir && !f3dir) continue;
            int sx = t.x, sy = t.y;
            const int dx = DX4[d], dy = DY4[d];
            while (b.in_bounds(sx - dx, sy - dy)) { sx -= dx; sy -= dy; }
            const int len = collect_line_cells(b, d, sx, sy, cells);
            for (int i = 0; i < len; ++i) {
                const int c = cells[i];
                const int x = cell_x(c), y = cell_y(c);
                if (!b.is_empty(x, y)) continue;
                if (!b.make_move(x, y, WHITE)) continue;
                bool defends;
                if (f4dir) {
                    defends = !line_has_fire(b, cells, len, d);
                } else {
                    // 三三杀：任一活三方向降级（< 活三）即防住其中一个三。
                    defends = classify_point(b, t.x, t.y, BLACK, dx, dy) < PP_FLEX3;
                }
                b.undo_move();
                if (defends) def.add(b, c);
            }
        }
    } else if (t.kind == 2) {
        // 四三杀：活三线的线型降级探针 + 冲四线的成五点。
        for (int d = 0; d < 4; ++d) {
            if (!(t.f3_dirs & (1 << d))) continue;
            const int dx = DX4[d], dy = DY4[d];
            int sx = t.x, sy = t.y;
            while (b.in_bounds(sx - dx, sy - dy)) { sx -= dx; sy -= dy; }
            const int len = collect_line_cells(b, d, sx, sy, cells);
            for (int i = 0; i < len; ++i) {
                const int c = cells[i];
                const int x = cell_x(c), y = cell_y(c);
                if (!b.is_empty(x, y)) continue;
                if (!b.make_move(x, y, WHITE)) continue;
                const bool defends =
                    classify_point(b, t.x, t.y, BLACK, dx, dy) < PP_FLEX3;
                b.undo_move();
                if (defends) def.add(b, c);
            }
        }
        for (int d = 0; d < 4; ++d) {
            if (!(t.b4_dirs & (1 << d))) continue;
            // 黑棋真实落杀点，其冲四的成五点即白棋防御点（冲四完成点唯一）。
            if (!b.make_move(t.x, t.y, BLACK)) continue;
            const int dx = DX4[d], dy = DY4[d];
            int sx = t.x, sy = t.y;
            while (b.in_bounds(sx - dx, sy - dy)) { sx -= dx; sy -= dy; }
            const int len = collect_line_cells(b, d, sx, sy, cells);
            for (int i = 0; i < len; ++i) {
                const int c = cells[i];
                if (!b.is_empty(cell_x(c), cell_y(c))) continue;
                if (point_pattern_d(b, c, d) == PP_FIVE) def.add(b, c);
            }
            b.undo_move();
        }
    }
    // kind 0 / kind 1(活四成分)：无试落阻挡（成五点唯一 / 活四不可挡）。

    const std::vector<Pt> caps = threat_captures(b, t);
    for (size_t i = 0; i < caps.size(); ++i)
        def.add(b, cell_index(caps[i].first, caps[i].second));

    if (t.kind != 0) {                       // 成五点不吃子反驳（成五即胜）
        const std::vector<Pt> selfcap = self_capture_defense(b, t.x, t.y);
        for (size_t i = 0; i < selfcap.size(); ++i)
            def.add(b, cell_index(selfcap[i].first, selfcap[i].second));
    }

    std::vector<Pt> out;
    def.finalize(&out);
    return out;
}

#if 0  // ==== 封存（第 8 步）：旧“威胁线阻挡点”查表实现，由威胁点分类 + 试落阻挡取代 ====
// 线的威胁等级：存在空点一步成五 → FIVE；一步成活四 → OPEN_FOUR；一步成冲四 →
// RUSH_FOUR；否则 NONE（活二 / 眠三 一类不构成“一步成四/五”的强制威胁）。
AtkType line_threat_rank(const Board& b, const int* cells, int n, int d) {
    AtkType r = AtkType::NONE;
    for (int i = 0; i < n; ++i) {
        const int c = cells[i];
        if (!b.is_empty(cell_x(c), cell_y(c))) continue;
        // 无气空点黑棋不能落（等同白/障碍）→ 不是黑棋的成五/成四点。
        if (b.is_dead_empty(cell_x(c), cell_y(c))) continue;
        const PointPattern p = point_pattern_d(b, c, d);
        if (p == PP_FIVE) return AtkType::FIVE;
        if (p == PP_FLEX4) r = AtkType::OPEN_FOUR;
        else if (p == PP_B4 && r == AtkType::NONE) r = AtkType::RUSH_FOUR;
    }
    return r;
}

// 白棋刚落 p 之后：该线上是否仍有黑棋“一步成五 / 成活四”的点。
bool line_still_winning(const Board& b, const int* cells, int n, int d) {
    for (int i = 0; i < n; ++i) {
        const int c = cells[i];
        if (!b.is_empty(cell_x(c), cell_y(c))) continue;
        if (b.is_dead_empty(cell_x(c), cell_y(c))) continue;   // 无气空点 = 阻挡
        const PointPattern p = point_pattern_d(b, c, d);
        if (p == PP_FIVE || p == PP_FLEX4) return true;
    }
    return false;
}

// 该线的全部阻挡点（枚举线上空点，真实 make_move(WHITE) 后用棋型缓存复判）。
std::vector<Pt> line_blockers(Board& b, const int* cells, int n, int d) {
    // 查表规则（用户规格）：阻挡点 = 该线上"黑棋落子能成五或成四"的空点。
    //   10111 / 011112 → 1 点（成五完成点）；
    //   0011102        → 3 点（三个 0 都是成四点）；
    //   0011100        → 紧邻两个 0（0A111B0 的 A、B，各成活四）。
    // 全部经增量棋型缓存 point_pattern_d 判定（O(1) 查表），不再试落验证。
    std::vector<Pt> out;
    for (int i = 0; i < n; ++i) {
        const int c = cells[i];
        const int x = cell_x(c), y = cell_y(c);
        if (!b.is_empty(x, y)) continue;
        if (b.is_dead_empty(x, y)) continue;          // 无气空点 = 阻挡，黑不能落
        const PointPattern p = point_pattern_d(b, c, d);
        if (p == PP_FIVE || p == PP_FLEX4 || p == PP_B4)
            out.push_back(Pt(x, y));
    }
    return out;
}
#endif  // ==== 封存结束：旧威胁线阻挡点 ====

#if 0  // ==== 封存（第 8 步）：旧“全盘威胁线 / 双威胁必须阻挡点”，由威胁点分类取代 ====
// 全盘威胁线：4 方向 × 每条线，rank != NONE 的线连同其阻挡点与线上黑子。
std::vector<ThreatLine> collect_threat_lines(Board& b) {
    std::vector<ThreatLine> out;
    const int n = b.size();
    int cells[MAX_BOARD];
    for (int d = 0; d < 4; ++d) {
        const int dx = DX4[d], dy = DY4[d];
        for (int sx = 0; sx < n; ++sx) {
            for (int sy = 0; sy < n; ++sy) {
                if (b.in_bounds(sx - dx, sy - dy)) continue;   // 只从线的起点扫
                const int len = collect_line_cells(b, d, sx, sy, cells);
                const AtkType rank = line_threat_rank(b, cells, len, d);
                if (rank == AtkType::NONE) continue;
                ThreatLine tl;
                tl.dx = dx;
                tl.dy = dy;
                tl.rank = static_cast<int>(rank);
                tl.cells = len;
                for (int i = 0; i < len; ++i) {
                    const uint8_t v = b.at(cell_x(cells[i]), cell_y(cells[i]));
                    if (v == BLACK) tl.black.push_back(Pt(cell_x(cells[i]), cell_y(cells[i])));
                }
                tl.blockers = line_blockers(b, cells, len, d);
                out.push_back(tl);
            }
        }
    }
    return out;
}

// 经过 (px,py) 的 4 条线中，仍有强制威胁的线（含其阻挡点）。供白棋应对集使用。
std::vector<ThreatLine> threat_lines_through(Board& b, int px, int py) {
    std::vector<ThreatLine> out;
    int cells[MAX_BOARD];
    for (int d = 0; d < 4; ++d) {
        const int dx = DX4[d], dy = DY4[d];
        // 回退到该线起点
        int sx = px, sy = py;
        while (b.in_bounds(sx - dx, sy - dy)) { sx -= dx; sy -= dy; }
        const int len = collect_line_cells(b, d, sx, sy, cells);
        const AtkType rank = line_threat_rank(b, cells, len, d);
        if (rank == AtkType::NONE) continue;
        ThreatLine tl;
        tl.dx = dx;
        tl.dy = dy;
        tl.rank = static_cast<int>(rank);
        tl.cells = len;
        for (int i = 0; i < len; ++i) {
            const uint8_t v = b.at(cell_x(cells[i]), cell_y(cells[i]));
            if (v == BLACK) tl.black.push_back(Pt(cell_x(cells[i]), cell_y(cells[i])));
        }
        tl.blockers = line_blockers(b, cells, len, d);
        out.push_back(tl);
    }
    return out;
}

// 双威胁必须阻挡点：黑棋落这里“做杀”必胜，白棋必须先占。三类做杀：
//   * 四三：某方向成活四（PP_FLEX4）且另一方向成活三（PP_FLEX3）——任何规则下都算；
//   * 三三：两方向成活三（PP_FLEX3 x2）——只在**三三禁手关闭**时才算杀（开着的话
//     黑棋自己不能落，不是威胁）；
//   * 四四：两方向成四（PP_B4/PP_FLEX4 共两个）——只在**四四禁手关闭**时才算杀。
// （用户规格：“不开禁手时三三、四四也是”。开关直接读 Board 的禁手开关。）
std::vector<Pt> double_threat_points(Board& b) {
    std::vector<Pt> out;
    const bool forbid33 = b.forbid_33();
    const bool forbid44 = b.forbid_44();
    const int n = b.size();
    for (int x = 0; x < n; ++x) {
        for (int y = 0; y < n; ++y) {
            if (!b.is_empty(x, y)) continue;
            const int idx = cell_index(x, y);
            int flex4 = 0, flex3 = 0, fours = 0;
            for (int d = 0; d < 4; ++d) {
                const PointPattern p = point_pattern_d(b, idx, d);
                if (p == PP_FLEX4) { ++flex4; ++fours; }
                else if (p == PP_B4) { ++fours; }
                else if (p == PP_FLEX3) ++flex3;
            }
            const bool four_three = (flex4 >= 1 && flex3 >= 1);
            const bool three_three = (!forbid33 && flex3 >= 2);
            const bool four_four = (!forbid44 && fours >= 2);
            if (!(four_three || three_three || four_four)) continue;
            // 黑棋自己不能落的点（真禁手 / 无气自杀）不是杀点——规格：“先检查是否有
            // 三三禁手在阻挡点上（四四/长连没有多重禁手），然后检查这两个三是否依赖
            // 于禁手预备点位”，也就是用 check_forbidden 的真判定而不是组合表预筛。
            if (black_point_illegal(b, x, y)) continue;
            out.push_back(Pt(x, y));
        }
    }
    return out;
}
#endif  // ==== 封存结束：旧威胁线/双威胁 ====

// 黑棋是否可能在 2 手内连五（用于“2 手内吃子点”的有效性校验）：
// 盘上存在一步成五的点，或存在一步成活四的点（活四无法同时封堵两端）。
bool black_five_within_two(Board& b) {
    const int n = b.size();
    for (int x = 0; x < n; ++x) {
        for (int y = 0; y < n; ++y) {
            if (!b.is_empty(x, y)) continue;
            const int idx = cell_index(x, y);
            for (int d = 0; d < 4; ++d) {
                const PointPattern p = point_pattern_d(b, idx, d);
                if (p == PP_FIVE || p == PP_FLEX4) return true;
            }
        }
    }
    return false;
}

// 吃子点：mask 覆盖的黑棋块中，气 == 1 的唯一气点（白棋 1 手直接提）；
// 气 == 2 的两个气点（白棋落子后该块变 1 气，下一步可提；且落子后黑棋 2 步内
// 不能连五，否则该吃子点无效）。
std::vector<Pt> capture_points_from_mask(Board& b, const uint8_t* mask) {
    std::vector<Pt> out;
    GroupTable gt;
    build_groups(b, mask, &gt);
    for (int g = 0; g < gt.ngroups; ++g) {
        if (!gt.has_window[g]) continue;              // 与威胁无关的块不计
        const int nl = gt.lib_count[g];
        if (nl == 1) {
            const int lib = gt.libs[gt.lib_begin[g]];
            out.push_back(Pt(cell_x(lib), cell_y(lib)));
        } else if (nl == 2) {
            for (int q = gt.lib_begin[g]; q < gt.lib_begin[g] + nl; ++q) {
                const int lib = gt.libs[q];
                const int x = cell_x(lib), y = cell_y(lib);
                if (!b.is_empty(x, y)) continue;
                if (!b.make_move(x, y, WHITE)) continue;
                const bool dangerous = black_five_within_two(b);
                b.undo_move();
                if (!dangerous) out.push_back(Pt(x, y));
            }
        }
    }
    return out;
}

// 把若干线的黑子标记进 mask。
void mark_line_black(const Board& b, const std::vector<ThreatLine>& lines,
                     uint8_t* mask) {
    for (size_t i = 0; i < lines.size(); ++i)
        for (size_t k = 0; k < lines[i].black.size(); ++k) {
            const Pt& p = lines[i].black[k];
            mask[cell_index(p.first, p.second)] = 1;
        }
    (void)b;
}

#if 0  // ==== 封存（第 8 步）：旧“阻挡点禁手说明”诊断，威胁点分类下不再需要 ====
// 禁手消失（多重禁手）说明：阻挡点本身可能是黑棋禁手（白棋占之合法）。返回
//   0 = 该点不是黑棋禁手（或非空点）；
//   1 = 真禁手（长连 / 四四 / 三三，Rapfi check_forbidden 复判为准）；
//   2 = 假禁手（组合表预筛 FORBID 但精判非禁手：三的延伸点本身是禁手点，去掉它后
//       三无法延伸成活四/五）。白棋占该点后此禁手消失，黑棋其余禁手仍阻挡黑棋。
// 本报告不影响候选集：白棋落禁手点合法。
struct ForbiddenNote {
    int  kind = 0;        // 0 非禁手 / 1 真禁手 / 2 假禁手
    int  threes = 0;      // 真三数
    int  fours = 0;       // 四数
    bool overline = false;
};
ForbiddenNote blocking_point_forbidden_note(Board& b, int x, int y) {
    ForbiddenNote note;
    if (!b.in_bounds(x, y) || !b.is_empty(x, y)) return note;
    const uint8_t p4 = b.cached_pattern4_black(cell_index(x, y));
    if (p4 != FORBID) return note;                     // O(1) 预筛：非禁手
    const ForbiddenProbe probe = probe_forbidden(b, x, y);
    note.threes = probe.threes;
    note.fours = probe.fours;
    for (int d = 0; d < 4; ++d)
        if (probe.dir[d] == OL) note.overline = true;
    note.kind = check_forbidden(b, x, y) ? 1 : 2;
    return note;
}
#endif  // ==== 封存结束：阻挡点禁手说明 ====

#if 0  // ==== 封存（第 8 步）：三层 VCT（全应对/智能应对/混合判定）整体停用 ====
//       用户指令：人工证明显示中央 5 子局面几分钟可完成证明，逐节点证明搜索
//       可以直接跑，初筛不必要。候选点改由威胁点分类 + 防御集交集给出
//       （见第 3 节与 white_threat_candidates），逐点 W/L 标注停用。
// ===========================================================================
// 4. 第二部分：三层 VCT（全应对 / 智能应对 / 混合判定）
// ===========================================================================
// 全应对 VCT：黑棋只走“能形成活三 / 眠四”的棋；白棋在**全部阻挡点**应对（外加吃子
// 点）。可靠（威胁空间内完备的应对集 ⇒ 胜即真胜）但不完备（黑方手受限）。
// 智能应对 VCT：白棋只在威胁候选点内落子，并按 2.2 的选点规则挑一个应手。
struct LayerCtx {
    VctParams params;
    long long nodes = 0;
    long long node_limit = 300000;
    double    deadline = 0.0;
    bool      timeout = false;
    // 三档预算已消耗的手数（0=VC2 活二/眠三，1=VCT 活三/做杀，2=VCF 冲四）。
    // 用户规格：预算优先消耗最大的档；现实现的调度是“最多 1 步 VC2，之后每步至少
    // VCT，VCT 耗尽后每步至少 VCF”（节点数少）。
    int used[3] = {0, 0, 0};
};

// RAII：选了一手就把对应档的预算计上，任何返回路径（含提前 return）都会还回去。
struct ClassGuard {
    int* used;
    int  cls;
    ClassGuard(int* u, int c) : used(u), cls(c) { ++used[cls]; }
    ~ClassGuard() { --used[cls]; }
};

bool layer_budget_exceeded(LayerCtx* c) {
    ++c->nodes;
    if (c->node_limit > 0 && c->nodes > c->node_limit) { c->timeout = true; return true; }
    if (c->deadline > 0.0 && now_sec() > c->deadline) { c->timeout = true; return true; }
    return false;
}

// 黑方威胁手（按三档预算）：VC2 = 只形成活二/眠三（预算 vc，只能第一手），
// VCT = 活三/做杀（预算 vct），VCF = 冲四/活四/五（预算 vcf）。
// 调度：最多 1 步 VC2 → 之后每步至少 VCT → VCT 耗尽后每步至少 VCF。
void layer_attacks(Board& b, int steps_left, LayerCtx* ctx,
                   std::vector<AttackCand>* out) {
    const VctParams& p = ctx->params;
    const bool allow_vc  = (ctx->used[0] < p.vc) && ctx->used[1] == 0 &&
                           ctx->used[2] == 0;          // VC2 只能是第一手
    const bool allow_vct = (ctx->used[1] < p.vct);
    const bool allow_vcf = (ctx->used[2] < p.vcf);
    if (!allow_vct && !allow_vcf) return;              // 三/四两档都耗尽
    gen_attack_candidates(b, steps_left, /*allow_three=*/allow_vct, out,
                          /*allow_vc2=*/allow_vc);
    size_t w = 0;
    for (size_t i = 0; i < out->size(); ++i) {
        const int cls = (*out)[i].cls;
        const bool ok = (cls == 2) ? allow_vcf
                                     : (cls == 1 ? allow_vct : allow_vc);
        if (ok) (*out)[w++] = (*out)[i];
    }
    out->resize(w);
}

// 全盘黑棋“眠三 / 活二”点数（智能应对的比较规则用）。
void count_black_sleep3_open2(Board& b, int* sleep3, int* open2) {
    *sleep3 = 0;
    *open2 = 0;
    const int n = b.size();
    for (int x = 0; x < n; ++x) {
        for (int y = 0; y < n; ++y) {
            if (!b.is_empty(x, y)) continue;
            const int idx = cell_index(x, y);
            bool s3 = false, o2 = false;
            for (int d = 0; d < 4; ++d) {
                const PointPattern p = point_pattern_d(b, idx, d);
                if (p == PP_B3) s3 = true;
                else if (p == PP_FLEX2) o2 = true;
            }
            if (s3) ++*sleep3;
            else if (o2) ++*open2;
        }
    }
}

// 智能应对选点（2.2）：1) 能吃子且吃后原有威胁不残留眠三 → 吃子；
// 2) 否则比较各阻挡点，取“白棋落子后黑棋眠三最少、其次活二最少”的一个
//    （挡成死三优先；`010110` 走中间 / `01110` 挡成死三都被这条比较规则覆盖）。
std::vector<Pt> smart_responses(Board& b, const std::vector<Pt>& blockers,
                                const std::vector<Pt>& captures) {
    for (size_t i = 0; i < captures.size(); ++i) {
        const int x = captures[i].first, y = captures[i].second;
        if (!b.is_empty(x, y)) continue;
        if (!b.make_move(x, y, WHITE)) continue;
        int s3 = 0, o2 = 0;
        count_black_sleep3_open2(b, &s3, &o2);
        b.undo_move();
        if (s3 == 0) {
            std::vector<Pt> one;
            one.push_back(captures[i]);
            return one;                                  // 吃子且不残留眠三
        }
    }
    int best = -1, best_s3 = 0, best_o2 = 0;
    for (size_t i = 0; i < blockers.size(); ++i) {
        const int x = blockers[i].first, y = blockers[i].second;
        if (!b.is_empty(x, y)) continue;
        if (!b.make_move(x, y, WHITE)) continue;
        int s3 = 0, o2 = 0;
        count_black_sleep3_open2(b, &s3, &o2);
        b.undo_move();
        if (best < 0 || s3 < best_s3 || (s3 == best_s3 && o2 < best_o2)) {
            best = static_cast<int>(i);
            best_s3 = s3;
            best_o2 = o2;
        }
    }
    std::vector<Pt> one;
    if (best >= 0) one.push_back(blockers[static_cast<size_t>(best)]);
    return one;
}

// 白棋对“黑棋刚在 (bx,by) 落下一手威胁”的全部应对：该手各威胁线的阻挡点 ∪ 吃子点。
std::vector<Pt> layer_responses(Board& b, int bx, int by, bool smart,
                                LayerCtx* ctx) {
    const std::vector<ThreatLine> lines = threat_lines_through(b, bx, by);
    std::vector<Pt> blockers;
    uint8_t mask[MAX_CELLS];
    std::memset(mask, 0, sizeof(mask));
    mark_line_black(b, lines, mask);
    for (size_t i = 0; i < lines.size(); ++i)
        for (size_t k = 0; k < lines[i].blockers.size(); ++k) {
            const Pt& p = lines[i].blockers[k];
            blockers.push_back(p);
        }
    std::vector<Pt> captures = capture_points_from_mask(b, mask);
    if (smart) return smart_responses(b, blockers, captures);

    PointSet set;
    for (size_t i = 0; i < blockers.size(); ++i)
        set.add(b, cell_index(blockers[i].first, blockers[i].second));
    for (size_t i = 0; i < captures.size(); ++i)
        set.add(b, cell_index(captures[i].first, captures[i].second));
    std::vector<Pt> out;
    set.finalize(&out);
    (void)ctx;
    return out;
}

// 层 1/2 共用 DFS：黑方 OR 节点（威胁手） × 白方应手（全应对 / 智能应对）。
// 成功时把本轮的 DefenseSet 填到 sets 的最前面（sets = 该路线的逐轮应对集）。
bool layer_dfs(Board& b, int steps_left, bool smart, LayerCtx* ctx,
               std::vector<DefenseSet>* sets) {
    if (layer_budget_exceeded(ctx)) return false;
    if (steps_left <= 0) return false;

    std::vector<AttackCand> cands;
    cands.reserve(32);
    layer_attacks(b, steps_left, ctx, &cands);
    for (size_t ci = 0; ci < cands.size(); ++ci) {
        const AttackCand c = cands[ci];
        ClassGuard guard(ctx->used, c.cls);   // 消耗对应档预算（离开作用域自动还）
        if (!b.make_move(c.x, c.y, BLACK)) continue;
        if (b.last_move_was_five()) {
            b.undo_move();
            return true;                     // 成五：1 手证明成功
        }
        std::vector<Pt> defs = layer_responses(b, c.x, c.y, smart, ctx);
        if (!defs.empty()) {
            bool all_ok = true;
            for (size_t wi = 0; wi < defs.size(); ++wi) {
                if (!b.make_move(defs[wi].first, defs[wi].second, WHITE)) continue;
                const bool sub = layer_dfs(b, steps_left - 1, smart, ctx, sets);
                b.undo_move();
                if (ctx->timeout) { b.undo_move(); return false; }
                if (!sub) { all_ok = false; break; }
            }
            if (all_ok) {
                DefenseSet ds;
                ds.points = defs;
                ds.bx = c.x;
                ds.by = c.y;
                ds.rank = c.rank;
                if (sets) sets->insert(sets->begin(), ds);
                b.undo_move();
                return true;
            }
        }
        b.undo_move();
    }
    return false;
}

// 顶层：迭代加深（m = 黑方攻击手数），收集所有成功路线的首轮应对集。
VctOutcome layer_run(Board& b, const VctParams& params, double time_sec, bool smart) {
    VctOutcome out;
    LayerCtx ctx;
    ctx.params = params;
    ctx.deadline = (time_sec > 0.0) ? now_sec() + time_sec : 0.0;
    // 手数上限 = 三档预算之和（VC2 1 步 + VCT 额外若干 + VCF 额外若干）。
    const int max_m = std::max(1, params.vc + params.vct + params.vcf);
    for (int m = 1; m <= max_m; ++m) {
        std::vector<AttackCand> cands;
        cands.reserve(32);
        layer_attacks(b, m, &ctx, &cands);
        bool any = false;
        for (size_t ci = 0; ci < cands.size(); ++ci) {
            if (layer_budget_exceeded(&ctx)) break;
            const AttackCand c = cands[ci];
            ClassGuard guard(ctx.used, c.cls);   // 消耗对应档预算
            if (!b.make_move(c.x, c.y, BLACK)) continue;
            bool win = false;
            std::vector<DefenseSet> route_sets;
            if (b.last_move_was_five()) {
                win = true;
            } else {
                std::vector<Pt> defs = layer_responses(b, c.x, c.y, smart, &ctx);
                if (!defs.empty()) {
                    win = true;
                    for (size_t wi = 0; wi < defs.size(); ++wi) {
                        if (!b.make_move(defs[wi].first, defs[wi].second, WHITE))
                            continue;
                        std::vector<DefenseSet> child;
                        const bool sub = layer_dfs(b, m - 1, smart, &ctx, &child);
                        b.undo_move();
                        if (ctx.timeout) { win = false; break; }
                        if (!sub) { win = false; break; }
                        route_sets = child;
                    }
                    if (win) {
                        DefenseSet ds;
                        ds.points = defs;
                        ds.bx = c.x;
                        ds.by = c.y;
                        ds.rank = c.rank;
                        route_sets.insert(route_sets.begin(), ds);
                    }
                }
            }
            b.undo_move();
            if (!win) continue;
            any = true;
            if (!route_sets.empty()) {
                out.first_sets.push_back(route_sets.front());
                VctRoute route;
                route.black_moves.push_back(Pt(c.x, c.y));
                route.sets = route_sets;
                out.routes.push_back(route);
            }
        }
        if (any) {
            out.win = true;
            out.steps = m;
            break;
        }
        if (ctx.timeout) break;
    }
    out.timeout = ctx.timeout;
    return out;
}
#endif  // ==== 封存结束：三层 VCT ====

}  // namespace

// 混合判定（第二部分 2.3）的防御点交集：把各条成功路线的首轮应手集合取交集
// （“每种可靠 VCT 的防御点位集合”）。交集为空时返回空表，调用方按规格退回到
// “按最大步数标注 W/L”。
std::vector<Pt> mixed_defense_intersection(Board& b, const VctOutcome& all_resp) {
    PointSet set;
    bool first = true;
    std::vector<int> keep;
    for (size_t i = 0; i < all_resp.first_sets.size(); ++i) {
        const DefenseSet& ds = all_resp.first_sets[i];
        if (first) {
            for (size_t k = 0; k < ds.points.size(); ++k)
                set.add(b, cell_index(ds.points[k].first, ds.points[k].second));
            first = false;
        } else {
            keep.clear();
            for (size_t k = 0; k < ds.points.size(); ++k) {
                const int idx = cell_index(ds.points[k].first, ds.points[k].second);
                if (set.mark[idx]) keep.push_back(idx);
            }
            std::memset(set.mark, 0, sizeof(set.mark));
            set.idx.clear();
            for (size_t k = 0; k < keep.size(); ++k) set.add(b, keep[k]);
        }
    }
    std::vector<Pt> out;
    set.finalize(&out);
    return out;
}

// 三层 VCT 对外包装。
VctOutcome vct_all_response(Board& b, const VctParams& p, double time_sec) {
#ifndef NDEBUG
    const uint64_t h0 = b.hash();
#endif
    VctOutcome out = layer_run(b, p, time_sec, /*smart=*/false);
#ifndef NDEBUG
    assert(b.hash() == h0);
#endif
    return out;
}

VctOutcome vct_smart_response(Board& b, const VctParams& p, double time_sec) {
#ifndef NDEBUG
    const uint64_t h0 = b.hash();
#endif
    VctOutcome out = layer_run(b, p, time_sec, /*smart=*/true);
#ifndef NDEBUG
    assert(b.hash() == h0);
#endif
    return out;
}

// 盘上“真三三禁手点”（递归复判，不看组合表预筛）：白棋占某点后如果黑棋多出这种点，
// 说明黑棋被自己的禁手挡住，白棋这一手就是有效应手（禁手消失 / 多重禁手）。
// 判据：预筛 FORBID → 无长连/一线双四 → 非四四 → check_forbidden 为真 且真三数 >= 2。
void collect_real_33(Board& b, std::vector<int>* out) {
    out->clear();
    const int n = b.size();
    for (int x = 0; x < n; ++x) {
        for (int y = 0; y < n; ++y) {
            if (!b.is_empty(x, y)) continue;
            const int idx = cell_index(x, y);
            if (b.cached_pattern4_black(idx) != FORBID) continue;  // O(1) 预筛
            const ForbiddenProbe pr = probe_forbidden(b, x, y);
            bool overline = false;
            for (int d = 0; d < 4; ++d)
                if (pr.dir[d] == OL) overline = true;   // 长连 / Rapfi 一线双四
            if (overline || pr.fours >= 2) continue;    // 四四/长连没有“多重禁手”
            if (pr.forbidden && pr.threes >= 2) out->push_back(idx);
        }
    }
}

// 白棋真实落 (px,py) 后，黑棋是否多出 before 里没有的真三三禁手点。
bool creates_new_black_33(Board& b, int px, int py,
                          const std::vector<int>& before) {
    if (!b.is_empty(px, py)) return false;
    if (!b.make_move(px, py, WHITE)) return false;
    std::vector<int> after;
    collect_real_33(b, &after);
    b.undo_move();
    for (size_t i = 0; i < after.size(); ++i) {
        bool seen = false;
        for (size_t k = 0; k < before.size(); ++k)
            if (before[k] == after[i]) { seen = true; break; }
        if (!seen) return true;
    }
    return false;
}

// ===========================================================================
// 3.6 白棋威胁候选点（交集框架）
// ===========================================================================
WhiteCandidateReport white_threat_candidates(Board& b) {
    WhiteCandidateReport rep;
    rep.lines = collect_threat_lines(b);
    rep.threat_lines = static_cast<int>(rep.lines.size());
    // “强制威胁”= 盘上存在黑棋一手成活四（或成五）的线（用户规格的实心圆 / 三角形
    // 一档：五连、活四、四三）。只有纯冲四 / 眠三（大圆圈 / 小圆圈一档）时白棋不被
    // 强迫，候选集退化为“不受约束”（全盘空点，legal:everywhere）。
    bool forced = false;
    for (size_t i = 0; i < rep.lines.size(); ++i)
        if (rep.lines[i].rank >= static_cast<int>(AtkType::OPEN_FOUR)) forced = true;
    if (!forced) {
        rep.unconstrained = true;              // 无强制威胁 → 全盘空点都是候选点
        const int n = b.size();
        for (int x = 0; x < n; ++x)
            for (int y = 0; y < n; ++y)
                if (b.is_empty(x, y)) rep.candidates.push_back(Pt(x, y));
        return rep;
    }

    // 交集：逐线取阻挡点集合的交（“对所有威胁的候选集合取交集”）。
    std::vector<int> inter;
    for (size_t i = 0; i < rep.lines.size(); ++i) {
        std::vector<int> cur;
        for (size_t k = 0; k < rep.lines[i].blockers.size(); ++k) {
            const Pt& p = rep.lines[i].blockers[k];
            cur.push_back(cell_index(p.first, p.second));
        }
        std::sort(cur.begin(), cur.end());
        cur.erase(std::unique(cur.begin(), cur.end()), cur.end());
        if (i == 0) {
            inter = cur;
        } else {
            std::vector<int> next;
            for (size_t k = 0; k < inter.size(); ++k)
                if (std::binary_search(cur.begin(), cur.end(), inter[k]))
                    next.push_back(inter[k]);
            inter.swap(next);
        }
    }
    rep.intersect_size = static_cast<int>(inter.size());
    rep.intersect_empty = inter.empty();

    // 交集为空 → 按规格回退到“所有威胁候选集合的并集”。
    PointSet pool;
    if (!inter.empty()) {
        for (size_t k = 0; k < inter.size(); ++k) pool.add(b, inter[k]);
    } else {
        for (size_t i = 0; i < rep.lines.size(); ++i)
            for (size_t k = 0; k < rep.lines[i].blockers.size(); ++k)
                pool.add(b, cell_index(rep.lines[i].blockers[k].first,
                                       rep.lines[i].blockers[k].second));
    }

    uint8_t mask[MAX_CELLS];
    std::memset(mask, 0, sizeof(mask));
    mark_line_black(b, rep.lines, mask);
    rep.captures = capture_points_from_mask(b, mask);
    for (size_t k = 0; k < rep.captures.size(); ++k)
        pool.add(b, cell_index(rep.captures[k].first, rep.captures[k].second));

    // 双威胁（做杀）必须阻挡点：黑棋在这些点做四三（禁手关掉时三三/四四也算）即必胜，
    // 白棋**只能占其中之一**。所以只要 must_block 非空，就把候选池整体裁到它——其余
    // 候选（最典型的就是活三的另一端）会被黑棋四三取胜，绝不能留在候选集里。
    // 唯一例外：白占某点后黑棋**多出一个真三三禁手**（禁手消失 / 多重禁手 → 黑棋被挡），
    // 这种点也算有效应手，保留在候选池里。
    rep.must_block = double_threat_points(b);
    if (!rep.must_block.empty()) {
        std::vector<int> before;
        collect_real_33(b, &before);
        PointSet keep;
        for (size_t k = 0; k < rep.must_block.size(); ++k)
            keep.add(b, cell_index(rep.must_block[k].first,
                                   rep.must_block[k].second));
        std::vector<Pt> pool_pts;
        pool.finalize(&pool_pts);
        for (size_t k = 0; k < pool_pts.size(); ++k) {
            const int idx = cell_index(pool_pts[k].first, pool_pts[k].second);
            if (keep.mark[idx]) continue;                  // 本身就是杀点
            if (creates_new_black_33(b, pool_pts[k].first, pool_pts[k].second,
                                     before))
                keep.add(b, idx);
        }
        pool = keep;
    }

    pool.finalize(&rep.candidates);
    return rep;
}

// ===========================================================================
// 5. 主入口：逐候选标注
// ===========================================================================
// 白方候选的健全步数：迭代加深（与第 6 步一致），返回首个证明成功的黑方攻击手数 m。
int sound_lose_steps(Board& b, int max_steps, ProveCtx* ctx, ProveTT* tt) {
    for (int m = 1; m <= max_steps; ++m) {
        const bool win = prove_black_dfs(b, m, true, ctx, tt);
        if (ctx->timeout) return 0;
        if (win) return m;
    }
    return 0;
}

AnalysisResult analyse(Board& b, int color, int max_steps, int winmode,
                       double time_limit_sec, long long node_limit,
                       const VctParams& params) {
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

    if (color == WHITE) {
        // ---- 白棋威胁候选点：阻挡点交集（无交集回退并集），再取标注最好的一档 ----
        const WhiteCandidateReport rep = white_threat_candidates(b);
        std::vector<Pt> pool = rep.candidates;

        if (rep.unconstrained) {
            // 盘面无强迫威胁（没有“黑棋一手成活四/成五”的线）：候选集**不受约束**=
            // 全盘空点（legal:everywhere）。逐点仍做健全证明搜索以给出诚实的标注
            // （L<2m> = 黑方 m 手内被证明必胜；W0 = 该点未被证明会输），但不做
            // “取最好一档”的收窄——不受约束就是全部空点。
            std::vector<Pt> all = pool;
            std::vector<CandidateLabel> labs;
            labs.reserve(all.size());
            for (size_t i = 0; i < all.size(); ++i) {
                const int x = all[i].first, y = all[i].second;
                if (ctx.timeout) break;          // 预算用尽：剩余点不输出（未见分晓的点不标）
                if (!b.make_move(x, y, WHITE)) continue;
                const int m = sound_lose_steps(b, max_steps, &ctx, &tt);
                b.undo_move();
                if (ctx.timeout) break;          // 该点未判定：宁可不标
                CandidateLabel lab;
                lab.x = x;
                lab.y = y;
                lab.tag = (m > 0) ? 'L' : 'W';
                lab.steps = (m > 0) ? 2 * m : 0;
                labs.push_back(lab);
            }
            std::sort(labs.begin(), labs.end(),
                      [](const CandidateLabel& a, const CandidateLabel& c) {
                          if (a.x != c.x) return a.x < c.x;
                          return a.y < c.y;
                      });
            res.labels = labs;
            res.paths_found = static_cast<int>(labs.size());
            res.nodes = ctx.nodes;
            res.timeout = ctx.timeout;
#ifndef NDEBUG
            assert(b.hash() == h0);
#endif
            return res;
        }

        struct Row {
            int x, y, steps;
            int score;
            char tag;
            bool smart_only;
        };
        std::vector<Row> rows;
        rows.reserve(pool.size());
        for (size_t i = 0; i < pool.size(); ++i) {
            if (ctx.timeout) break;
            const int x = pool[i].first, y = pool[i].second;
            if (!b.make_move(x, y, WHITE)) continue;

            // 1) 健全 AND-OR 证明搜索（第 6 步，含吃子反驳）——权威步数。
            int m = sound_lose_steps(b, max_steps, &ctx, &tt);
            bool smart_only = false;
            if (m == 0 && !ctx.timeout) {
                // 层 1 全应对（可靠但不完备）与层 2 智能应对（完备但不可靠）的先后：
                //   有禁手：先智能应对（快），再全应对；
                //   无禁手：先全应对（阻挡点少、分支小、可靠），智能应对只做兜底。
                // 用户规格（本轮）：无禁手先全应对、然后智能应对、最后枚举所有应对
                // （枚举 = 上面的健全 AND-OR 证明搜索，它已经先跑）；有禁手先智能应对
                // 再枚举所有应对。智能层兜底时步数只是下界（at_least → W/L<k>+）。
                const bool any_forbid = b.forbid_overline() || b.forbid_44() ||
                                        b.forbid_33();
                const bool smart_first = any_forbid;
                auto slice = [&](double frac) {
                    const double now = now_sec();
                    const double remain =
                        (ctx.deadline > 0.0) ? (ctx.deadline - now) : 0.0;
                    return (ctx.deadline > 0.0)
                               ? std::max(0.05, remain * frac)
                               : 0.0;
                };
                VctOutcome first = smart_first
                                       ? vct_smart_response(b, params, slice(0.25))
                                       : vct_all_response(b, params, slice(0.25));
                if (first.win) {
                    m = first.steps;
                    smart_only = smart_first;      // 智能层 = 步数下界
                } else if (!first.timeout) {
                    VctOutcome second =
                        smart_first
                            ? vct_all_response(b, params, slice(0.25))
                            : vct_smart_response(b, params, slice(0.25));
                    if (second.win) {
                        m = second.steps;
                        smart_only = !smart_first; // 智能层兜底 = 步数下界
                    }
                }
            }
            const int score = order_score(b, x, y, WHITE);
            b.undo_move();
            if (ctx.timeout) break;      // 该点未判定：不输出（宁可不标，不可错标）

            Row r;
            r.x = x;
            r.y = y;
            r.score = score;
            r.tag = (m > 0) ? 'L' : 'W';
            r.steps = (m > 0) ? 2 * m : 0;
            r.smart_only = smart_only;   // 仅层 2 兜底 → 步数是下界（L<k>+）
            rows.push_back(r);
        }

        // 取“最好的一档”：安全（W）优先；否则 L 步数最大者（活得最久）。
        std::sort(rows.begin(), rows.end(), [](const Row& a, const Row& b2) {
            const bool aw = (a.tag == 'W'), bw = (b2.tag == 'W');
            if (aw != bw) return aw;                      // W 优先
            if (a.steps != b2.steps) return a.steps > b2.steps;
            if (a.score != b2.score) return a.score > b2.score;
            if (a.x != b2.x) return a.x < b2.x;
            return a.y < b2.y;
        });

        size_t keep = 0;
        if (!rows.empty()) {
            while (keep < rows.size() &&
                   rows[keep].tag == rows[0].tag &&
                   rows[keep].steps == rows[0].steps)
                ++keep;
        }
        // 收尾（第二部分 2.4）：仍有多个候选点 → minimax 窄深判断，只留最优。
        if (keep > 1 && !ctx.timeout) {
            const double now = now_sec();
            double remain = (ctx.deadline > 0.0) ? (ctx.deadline - now) : 0.0;
            if (ctx.deadline <= 0.0 || remain > 0.01) {
                int best_i = -1;
                int64_t best_v = 0;
                for (size_t i = 0; i < keep; ++i) {
                    if (!b.make_move(rows[i].x, rows[i].y, WHITE)) continue;
                    SearchCtx sc;
                    sc.winmode = winmode;
                    sc.has_deadline = true;
                    sc.deadline = Clock::now() +
                                  std::chrono::milliseconds(
                                      static_cast<long long>(
                                          std::max(0.005, remain * 0.05) * 1000.0));
                    int64_t v = 0;
                    try {
                        v = alphabeta(b, 2, -INF_SCORE, INF_SCORE, 0, sc);
                    } catch (const SearchAbort&) {
                        v = 0;
                    }
                    b.undo_move();
                    // v 是“轮到黑方”的视角分：白方取最小。
                    if (best_i < 0 || v < best_v) { best_i = static_cast<int>(i); best_v = v; }
                }
                if (best_i > 0) {
                    Row chosen = rows[static_cast<size_t>(best_i)];
                    rows[0] = chosen;
                    keep = 1;
                } else if (best_i == 0) {
                    keep = 1;
                }
            }
        }
        if (keep == 0) keep = std::min<size_t>(1, rows.size());

        std::sort(rows.begin(), rows.begin() + keep, [](const Row& a, const Row& b2) {
            if (a.x != b2.x) return a.x < b2.x;
            return a.y < b2.y;
        });
        res.labels.reserve(keep);
        for (size_t i = 0; i < keep; ++i) {
            CandidateLabel lab;
            lab.x = rows[i].x;
            lab.y = rows[i].y;
            lab.tag = rows[i].tag;
            lab.steps = rows[i].steps;
            lab.at_least = (rows[i].tag != 0) && rows[i].smart_only;
            res.labels.push_back(lab);
            ++res.paths_found;
        }
        res.nodes = ctx.nodes;
        res.timeout = ctx.timeout;
#ifndef NDEBUG
        assert(b.hash() == h0);
#endif
        return res;
    }

    // ---- 黑方：对 gen_moves(BLACK) 逐候选打 W/L（第 6 步语义不变） ----
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
