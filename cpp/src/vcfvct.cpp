// vcfvct.cpp - VCF/VCT 威胁空间搜索 + W/L 标注实现（第 4 步）。
//
// 结构（自上而下）：
//   2.1 attack_class                单点威胁级别（把空点当黑子，复用 classify_point）
//   2.2 scan_four_windows           全盘 4 黑 + 1 空的五连窗 → 完成点
//   2.3 scan_capture_points         1 气黑块的唯一气点 → 白提子点
//   2.4 white_defense_for_fours     四的精确防御集 = 完成点 ∪ 提子点
//   2.5 white_defense_for_threes    三的防御超集 = 四集 ∪ 过点 5 窗空点 ∪ 提子点
//   2.6 PathCollector / SearchStats
//   2.7/2.8/2.9 vcf_dfs / vct_dfs / enum_black_wins（统一黑方攻击枚举）
//   2.10 analyse                    逐候选标注；2.11 vcf_exists / vct_exists
//
// 硬性约束：
//  * 全程只 make_move/undo_move，不拷贝棋盘；任何返回路径（含限流提前返回）
//    都成对 undo，退出时 hash 逐位还原（NDEBUG 关闭时用 assert 复核）。
//  * 输出确定：候选与白方应手都按 (威胁等级, order_score, x, y) 全序排序，
//    不含任何随机量。
//  * 健全性根基：白方对“四”的防御是精确集合（白下集合外黑下一步即成五）；
//    对“三”用超集（宁可多试白应手，不可漏掉真实防御）。
#include "vcfvct.h"

#include <algorithm>
#include <cassert>
#include <chrono>
#include <cstring>
#include <limits>

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

constexpr int ATTACK_RADIUS    = 4;  // 攻击候选：已有黑子切比雪夫距离 <= 4
constexpr int THREE_MIN_BLACK  = 2;  // 三防御超集：窗内黑子数下限
constexpr int DEFAULT_MAX_PATHS = 200;
constexpr long long DEFAULT_NODES = 300000;

using Pt    = std::pair<int, int>;
using Clock = std::chrono::steady_clock;

double now_sec() {
    return std::chrono::duration<double>(Clock::now().time_since_epoch()).count();
}

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

// ===========================================================================
// 2.2 全盘四窗扫描
// ===========================================================================
// 枚举 4 方向 × 全部盘内 5 连窗：窗内恰 4 黑 + 1 空 + 0 白/障碍 → 完成点。
// 含白或障碍的窗直接跳过（该窗已不可能成五）。
void scan_four_windows(const Board& b, std::vector<Pt>* block_points) {
    const int n = b.size();
    uint8_t seen[MAX_CELLS];
    std::memset(seen, 0, sizeof(seen));
    uint8_t line[MAX_BOARD];

    for (int d = 0; d < 4; ++d) {
        const int dx = DX4[d], dy = DY4[d];
        for (int sx = 0; sx < n; ++sx) {
            for (int sy = 0; sy < n; ++sy) {
                // 只从“线的起点”扫描：前一个格越界即起点。
                if (b.in_bounds(sx - dx, sy - dy)) continue;
                int len = 0;
                for (int cx = sx, cy = sy; b.in_bounds(cx, cy);
                     cx += dx, cy += dy)
                    line[len++] = b.at(cx, cy);
                for (int i = 0; i + 5 <= len; ++i) {
                    int nb = 0, nblk = 0, e = -1;
                    for (int k = 0; k < 5; ++k) {
                        const uint8_t v = line[i + k];
                        if (v == BLACK) ++nb;
                        else if (v == EMPTY) e = i + k;
                        else ++nblk;
                    }
                    if (nb == 4 && nblk == 0 && e >= 0) {
                        const int ex = sx + e * dx, ey = sy + e * dy;
                        const int idx = Board::index(ex, ey);
                        if (!seen[idx]) {
                            seen[idx] = 1;
                            block_points->push_back(Pt(ex, ey));
                        }
                    }
                }
            }
        }
    }
}

// ===========================================================================
// 2.3 提子点扫描
// ===========================================================================
// 局部 flood fill（读 b.at()，本文件内 visited 防重，不改 board.h）：
// 气数 == 1 的黑块，其唯一气点白下即提子。
void scan_capture_points(const Board& b, std::vector<Pt>* capture_points) {
    const int n = b.size();
    uint8_t visited[MAX_CELLS];
    std::memset(visited, 0, sizeof(visited));
    int stack[MAX_CELLS];
    int libs[MAX_CELLS];

    for (int x = 0; x < n; ++x) {
        for (int y = 0; y < n; ++y) {
            if (b.at(x, y) != BLACK) continue;
            const int start = Board::index(x, y);
            if (visited[start]) continue;
            int top = 0, nlib = 0;
            stack[top++] = start;
            visited[start] = 1;
            while (top > 0) {
                const int cur = stack[--top];
                const int cx = cur / MAX_BOARD, cy = cur % MAX_BOARD;
                for (int k = 0; k < 4; ++k) {
                    const int nx = cx + NX4[k], ny = cy + NY4[k];
                    if (!b.in_bounds(nx, ny)) continue;
                    const uint8_t v = b.at(nx, ny);
                    if (v == EMPTY) {
                        const int ni = Board::index(nx, ny);
                        bool dup = false;
                        for (int q = 0; q < nlib; ++q)
                            if (libs[q] == ni) { dup = true; break; }
                        if (!dup) libs[nlib++] = ni;
                    } else if (v == BLACK) {
                        const int ni = Board::index(nx, ny);
                        if (!visited[ni]) {
                            visited[ni] = 1;
                            stack[top++] = ni;
                        }
                    }
                }
            }
            if (nlib == 1) {
                capture_points->push_back(
                    Pt(libs[0] / MAX_BOARD, libs[0] % MAX_BOARD));
            }
        }
    }
}

// ===========================================================================
// 2.4 四的精确防御集
// ===========================================================================
std::vector<Pt> white_defense_for_fours(const Board& b) {
    std::vector<Pt> out;
    out.reserve(16);
    scan_four_windows(b, &out);
    scan_capture_points(b, &out);
    std::sort(out.begin(), out.end());
    out.erase(std::unique(out.begin(), out.end()), out.end());
    return out;
}

// ===========================================================================
// 2.5 三的防御超集
// ===========================================================================
// 黑刚在 (px,py) 下出活三级威胁：白方防御超集 =
//   四的精确防御集 ∪ 经过 (px,py) 且“无白无障碍、黑子数 >= 2”的窗的全部空点
//   ∪ 提子点。
std::vector<Pt> white_defense_for_threes(const Board& b, int px, int py) {
    std::vector<Pt> out = white_defense_for_fours(b);
    const int n = b.size();

    for (int d = 0; d < 4; ++d) {
        const int dx = DX4[d], dy = DY4[d];
        for (int k = 0; k < 5; ++k) {
            const int sx = px - k * dx, sy = py - k * dy;
            // 窗口必须整体落在盘内。
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
                if (b.is_empty(cx, cy)) out.push_back(Pt(cx, cy));
            }
        }
    }

    std::sort(out.begin(), out.end());
    out.erase(std::unique(out.begin(), out.end()), out.end());
    return out;
}

// ===========================================================================
// 2.6 路径收集器 / 搜索统计
// ===========================================================================
struct PathCollector {
    std::vector<WinPath> paths;
    size_t max_paths = DEFAULT_MAX_PATHS;
    long long max_nodes = DEFAULT_NODES;
    bool full = false;
    void collect(const WinPath& p) {
        if (full) return;
        paths.push_back(p);              // 深拷贝入 paths
        if (paths.size() >= max_paths) full = true;
    }
};

struct SearchStats {
    long long nodes = 0;
    long long node_limit = DEFAULT_NODES;
    double deadline = 0.0;               // steady_clock 秒；<=0 表示无时限
    bool timeout = false;
};

// 每层入口调用：nodes++ 并检查节点/时间上限。超限 → timeout=true。
bool budget_exceeded(SearchStats* st) {
    ++st->nodes;
    if (st->nodes > st->node_limit) {
        st->timeout = true;
        return true;
    }
    if (st->deadline > 0.0 && now_sec() > st->deadline) {
        st->timeout = true;
        return true;
    }
    return false;
}

// ===========================================================================
// 攻击候选生成（2.7 步骤 2 / 2.8 步骤 1-3）
// ===========================================================================
struct AttackCand {
    int x, y, rank, score;
};

// 黑方攻击候选：已有黑子切比雪夫距离 <= ATTACK_RADIUS 的空点，按威胁级别筛选：
//   allow_three=false (VCF)：FIVE / OPEN_FOUR / RUSH_FOUR
//   allow_three=true  (VCT)：再加 OPEN_THREE
// 必做剪枝：四（不含成五）且 steps_left < 2 剪掉；三且 steps_left < 3 剪掉。
void gen_attack_candidates(Board& b, int steps_left, bool allow_three,
                           std::vector<AttackCand>* out) {
    const int n = b.size();
    uint8_t seen[MAX_CELLS];
    std::memset(seen, 0, sizeof(seen));

    for (int x = 0; x < n; ++x) {
        for (int y = 0; y < n; ++y) {
            if (b.at(x, y) != BLACK) continue;
            const int x0 = std::max(0, x - ATTACK_RADIUS);
            const int x1 = std::min(n - 1, x + ATTACK_RADIUS);
            const int y0 = std::max(0, y - ATTACK_RADIUS);
            const int y1 = std::min(n - 1, y + ATTACK_RADIUS);
            for (int nx = x0; nx <= x1; ++nx) {
                for (int ny = y0; ny <= y1; ++ny) {
                    const int idx = Board::index(nx, ny);
                    if (seen[idx]) continue;
                    seen[idx] = 1;
                    if (!b.is_empty(nx, ny)) continue;
                    const int rank = attack_rank_at(b, nx, ny);
                    if (rank <= static_cast<int>(AtkType::NONE)) continue;
                    if (rank == static_cast<int>(AtkType::OPEN_THREE)) {
                        if (!allow_three) continue;
                        if (steps_left < 3) continue;
                    } else if (rank < static_cast<int>(AtkType::FIVE)) {
                        // 四类（活四/冲四）：至少还要一手才能成五。
                        if (steps_left < 2) continue;
                    }
                    AttackCand c;
                    c.x = nx;
                    c.y = ny;
                    c.rank = rank;
                    c.score = order_score(b, nx, ny, BLACK);
                    out->push_back(c);
                }
            }
        }
    }

    std::sort(out->begin(), out->end(), [](const AttackCand& a, const AttackCand& b2) {
        if (a.rank != b2.rank) return a.rank > b2.rank;      // OPEN_FOUR 在前
        if (a.score != b2.score) return a.score > b2.score;  // 同类按 order_score 降序
        if (a.x != b2.x) return a.x < b2.x;
        return a.y < b2.y;
    });
}

// 白方应手排序：order_score(b,w,WHITE) 降序，同分按坐标（保证确定性）。
void order_white_defenses(const Board& b, std::vector<Pt>* pts) {
    std::vector<std::pair<int, Pt>> tmp;
    tmp.reserve(pts->size());
    for (const Pt& p : *pts)
        tmp.push_back(std::make_pair(order_score(b, p.first, p.second, WHITE), p));
    std::sort(tmp.begin(), tmp.end(),
              [](const std::pair<int, Pt>& a, const std::pair<int, Pt>& b2) {
                  if (a.first != b2.first) return a.first > b2.first;
                  return a.second < b2.second;
              });
    for (size_t i = 0; i < tmp.size(); ++i) (*pts)[i] = tmp[i].second;
}

// ===========================================================================
// 2.7 / 2.8 / 2.9 黑方攻击枚举（VCF/VCT 共用内核）
// ===========================================================================
// 前置：b.turn()==BLACK，steps_left >= 1 为剩余黑攻击手数。
// 返回值：true 表示“应立即逐层返回”（收集满 或 触发限流），调用方负责 undo。
bool black_attacks(Board& b, int steps_left, WinPath* cur, PathCollector* pc,
                   SearchStats* st, bool allow_three) {
    if (budget_exceeded(st)) return true;
    if (steps_left <= 0) return false;
    if (pc->full) return false;

    std::vector<AttackCand> cands;
    cands.reserve(32);
    gen_attack_candidates(b, steps_left, allow_three, &cands);

    for (size_t ci = 0; ci < cands.size(); ++ci) {
        const AttackCand& c = cands[ci];
        if (!b.make_move(c.x, c.y, BLACK)) continue;   // 无气自杀等非法点跳过

        if (b.last_move_was_five()) {
            cur->black_moves.push_back(Pt(c.x, c.y));
            cur->defense_sets.push_back(std::vector<Pt>());   // 成五：白无应手
            pc->collect(*cur);
            cur->black_moves.pop_back();
            cur->defense_sets.pop_back();
            b.undo_move();
            if (pc->full || st->timeout) return true;
            continue;
        }

        // 防御集按黑方这一手的成分选择（2.8.2）：
        //   四成分（含成五）→ 四的精确防御集；纯活三 → 三的防御超集。
        std::vector<Pt> wdefs =
            (c.rank >= static_cast<int>(AtkType::RUSH_FOUR))
                ? white_defense_for_fours(b)
                : white_defense_for_threes(b, c.x, c.y);
        cur->black_moves.push_back(Pt(c.x, c.y));
        cur->defense_sets.push_back(wdefs);

        bool stop = false;
        if (wdefs.empty()) {
            pc->collect(*cur);
        } else {
            order_white_defenses(b, &wdefs);
            for (size_t wi = 0; wi < wdefs.size(); ++wi) {
                if (!b.make_move(wdefs[wi].first, wdefs[wi].second, WHITE))
                    continue;
                const bool r =
                    black_attacks(b, steps_left - 1, cur, pc, st, allow_three);
                b.undo_move();
                if (r) { stop = true; break; }
            }
        }
        cur->black_moves.pop_back();
        cur->defense_sets.pop_back();
        b.undo_move();

        if (stop || pc->full || st->timeout) return true;
    }
    return pc->full;
}

// 2.7 纯 VCF：候选只含四与成五。
bool vcf_dfs(Board& b, int steps_left, WinPath* cur, PathCollector* pc,
             SearchStats* st) {
    return black_attacks(b, steps_left, cur, pc, st, /*allow_three=*/false);
}

// 2.8 VCT：候选含四、三与成五。
bool vct_dfs(Board& b, int steps_left, WinPath* cur, PathCollector* pc,
             SearchStats* st) {
    return black_attacks(b, steps_left, cur, pc, st, /*allow_three=*/true);
}

// 2.9 统一枚举器。
//   b.turn()==BLACK：等价 vct_dfs 逻辑（含剪枝与防御集选择）。
//   b.turn()==WHITE：黑刚下威胁 c=cur->black_moves.back()，白先应 —— 按 c 是否
//   含四成分选防御集，白应手不消耗 steps_left。
bool enum_black_wins(Board& b, WinPath* cur, int steps_left, PathCollector* pc,
                     SearchStats* st) {
    if (b.turn() == BLACK) {
        return black_attacks(b, steps_left, cur, pc, st, /*allow_three=*/true);
    }

    if (budget_exceeded(st)) return true;
    if (pc->full) return false;
    if (cur->black_moves.empty()) return false;   // 防御性：不应发生

    const Pt c = cur->black_moves.back();
    const int rank = attack_rank_at(b, c.first, c.second);
    const bool four_component = rank >= static_cast<int>(AtkType::RUSH_FOUR);
    std::vector<Pt> wdefs = four_component
                                ? white_defense_for_fours(b)
                                : white_defense_for_threes(b, c.first, c.second);

    if (cur->defense_sets.size() < cur->black_moves.size())
        cur->defense_sets.push_back(std::vector<Pt>());
    cur->defense_sets.back() = wdefs;

    if (wdefs.empty()) {
        // 白方无应手 = 黑方威胁无法防守 → 收集一条路径。
        // 仅当黑方上一手确实是威胁（四/三/成五）时该结论才成立；普通落子没有
        // 威胁可言，此时“防御集为空”只是启发式集合为空，不能算必胜。
        if (rank >= static_cast<int>(AtkType::OPEN_THREE)) pc->collect(*cur);
        return false;
    }

    order_white_defenses(b, &wdefs);
    for (size_t wi = 0; wi < wdefs.size(); ++wi) {
        if (!b.make_move(wdefs[wi].first, wdefs[wi].second, WHITE)) continue;
        const bool r = enum_black_wins(b, cur, steps_left, pc, st);
        b.undo_move();
        if (r) return true;
    }
    return false;
}

// 候选 c 是否落在路径 P 的 U(P) = ∪_i (black_moves[i] ∪ defense_sets[i]) 内。
bool in_path_union(const WinPath& p, int x, int y) {
    for (size_t i = 0; i < p.black_moves.size(); ++i) {
        if (p.black_moves[i].first == x && p.black_moves[i].second == y)
            return true;
        if (i < p.defense_sets.size()) {
            const std::vector<Pt>& d = p.defense_sets[i];
            for (size_t k = 0; k < d.size(); ++k)
                if (d[k].first == x && d[k].second == y) return true;
        }
    }
    return false;
}

}  // namespace

// ===========================================================================
// 2.10 主入口
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

    SearchStats st;
    st.node_limit = node_limit;
    st.deadline = (time_limit_sec > 0.0) ? now_sec() + time_limit_sec : 0.0;

    const std::vector<Move> cands = gen_moves(b, color);
    res.labels.reserve(cands.size());
    const int root_steps = (color == BLACK) ? (max_steps - 1) : max_steps;

    for (size_t i = 0; i < cands.size(); ++i) {
        CandidateLabel lab;
        lab.x = cands[i].x;
        lab.y = cands[i].y;
        lab.tag = 0;
        lab.steps = 0;

        if (!st.timeout) {
            if (b.make_move(lab.x, lab.y, color)) {   // 失败/非法点保持无标注
                bool decided = false;
                if (color == BLACK && b.last_move_was_five()) {
                    lab.tag = 'W';
                    lab.steps = 1;
                    decided = true;
                } else if (b.white_wins_now(winmode)) {
                    decided = true;   // 此手之后白方已达成胜利条件
                }
                if (!decided) {
                    // 从 c 之后局面枚举黑必胜路径；黑候选时 c 计入 black_moves[0]。
                    WinPath cur;
                    if (color == BLACK) {
                        cur.black_moves.push_back(Pt(lab.x, lab.y));
                        cur.defense_sets.push_back(std::vector<Pt>());
                    }
                    PathCollector pc;
                    pc.max_nodes = node_limit;
                    enum_black_wins(b, &cur, root_steps, &pc, &st);
                    res.paths_found += static_cast<int>(pc.paths.size());

                    if (!pc.paths.empty()) {
                        int m_min = std::numeric_limits<int>::max();
                        for (size_t k = 0; k < pc.paths.size(); ++k)
                            m_min = std::min(m_min, pc.paths[k].plies());

                        if (color == BLACK) {
                            lab.tag = 'W';                 // c=第 1 步
                            lab.steps = 2 * m_min - 1;     // 黑第 m 手成五在步 2m-1
                        } else {
                            int best = std::numeric_limits<int>::max();
                            for (size_t k = 0; k < pc.paths.size(); ++k) {
                                if (!in_path_union(pc.paths[k], lab.x, lab.y))
                                    best = std::min(best, pc.paths[k].plies());
                            }
                            if (best < std::numeric_limits<int>::max()) {
                                lab.tag = 'L';             // 白第 1 步
                                lab.steps = 2 * best;      // 黑第 m 手成五在步 2m
                            }
                            // best==INF：c 在所有路径的 U 交集内 → 可能防住，不标。
                        }
                    }
                }
                b.undo_move();
            }
        }
        res.labels.push_back(lab);
    }

    res.nodes = st.nodes;
    res.timeout = st.timeout;
#ifndef NDEBUG
    assert(b.hash() == h0);
#endif
    return res;
}

// ===========================================================================
// 2.11 调试/测试包装
// ===========================================================================
bool vcf_exists(Board& b, int max_steps) {
    if (b.turn() != BLACK) return false;
#ifndef NDEBUG
    const uint64_t h0 = b.hash();
#endif
    WinPath cur;
    PathCollector pc;
    pc.max_paths = 1;
    SearchStats st;
    st.node_limit = pc.max_nodes;
    vcf_dfs(b, max_steps, &cur, &pc, &st);
#ifndef NDEBUG
    assert(b.hash() == h0);
#endif
    return !pc.paths.empty();
}

bool vct_exists(Board& b, int max_steps) {
    if (b.turn() != BLACK) return false;
#ifndef NDEBUG
    const uint64_t h0 = b.hash();
#endif
    WinPath cur;
    PathCollector pc;
    pc.max_paths = 1;
    SearchStats st;
    st.node_limit = pc.max_nodes;
    vct_dfs(b, max_steps, &cur, &pc, &st);
#ifndef NDEBUG
    assert(b.hash() == h0);
#endif
    return !pc.paths.empty();
}

}  // namespace gvg
