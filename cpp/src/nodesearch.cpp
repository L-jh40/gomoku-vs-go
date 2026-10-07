// nodesearch.cpp - 逐节点证明搜索实现（rapfi search/ab/search.cpp 的混合规则移植）。
//
// 结构：
//   1. 置换表（本模块私有，2^20 项，always-replace，mate 分 ply 归一化）。
//   2. 着法生成：候选 = 距任一棋子切比雪夫距离 <= 2 的空点（与 gen_moves 同口径）；
//      tier 用 Board 的增量棋型缓存 O(1) 读取（黑 = p4_black 组合等级，
//      白 = 该点上黑棋 p4 的阻挡价值）；一次扫描顺带收集黑棋成五点清单。
//   3. 静态杀判定只保留一条**无条件健全**规则：轮黑且有成五点 → MATE（成五立即
//      终局，提子/禁手都无法干预）。其余“活四/四三/双五不可挡”类 Rapfi 静态规则
//      在本游戏**不健全**（白棋可以提子破解：斜向四子的石块分属不同正交组，叫吃
//      的那颗被提走四即消失），一律改由 VCF 尾部搜索健全地解决。
//   4. node_dfs：全宽 alpha-beta（PVS）。depth <= 0 陷入 VCF 尾部（vcf_attack /
//      vcf_defend）：攻方（黑）只走成四手；守方（白）只应对成五点 ∪ 成五点四子
//      中 1 气正交组的提子点（逐石子组检查，斜向四子各石子的组都要查）——其余
//      白应手立即败给成五，不搜它们不损失证明健全性。
//   5. 非终局叶子用 stm_score（既有增量评估）做 stand-pat；评估分 |值| < MATE_BOUND
//      严格小于证明分，因此 MATE 级结论只可能来自真实成五，证明不被评估污染。
#include "nodesearch.h"

#include <algorithm>
#include <cstdio>
#include <cstdio>
#include <cstdlib>
#include <cassert>
#include <chrono>
#include <cstring>

#include "eval.h"
#include "forbidden.h"
#include "pattern_table.h"

namespace gvg {

namespace {

// ---------------------------------------------------------------------------
// 置换表
// ---------------------------------------------------------------------------
constexpr size_t TT_BITS = 20;
constexpr size_t TT_SIZE = size_t(1) << TT_BITS;
constexpr size_t TT_MASK = TT_SIZE - 1;

constexpr int8_t TT_EMPTY = 0;
constexpr int8_t TT_EXACT = 1;
constexpr int8_t TT_LOWER = 2;
constexpr int8_t TT_UPPER = 3;
constexpr uint16_t TT_NO_MOVE = 0xFFFF;

struct NSTTEntry {
    uint64_t key;
    int64_t  score;
    uint16_t best;
    int16_t  depth;
    int8_t   flag;
    uint8_t  pad_[3];
};
static_assert(sizeof(NSTTEntry) == 24, "unexpected NSTTEntry layout");

NSTTEntry* g_tt = nullptr;

void tt_ensure() {
    if (g_tt == nullptr) {
        g_tt = new NSTTEntry[TT_SIZE];
        std::memset(g_tt, 0, sizeof(NSTTEntry) * TT_SIZE);
    }
}

inline int64_t tt_store_score(int64_t score, int ply) {
    if (score > MATE_BOUND) return score + ply;
    if (score < -MATE_BOUND) return score - ply;
    return score;
}
inline int64_t tt_load_score(int64_t score, int ply) {
    if (score > MATE_BOUND) return score - ply;
    if (score < -MATE_BOUND) return score + ply;
    return score;
}

// ---------------------------------------------------------------------------
// 搜索上下文与着法
// ---------------------------------------------------------------------------
constexpr int MAX_PLY   = 60;
constexpr int MAX_MOVES = 256;

struct Ctx {
    std::chrono::steady_clock::time_point deadline{};
    bool      has_deadline = false;
    long long node_limit   = 0;
    long long nodes        = 0;
    bool      timeout      = false;
    int       winmode      = 0;
};

struct NMove {
    uint16_t pos;
    int8_t   tier;
};

inline bool ctx_check(Ctx& ctx) {
    ++ctx.nodes;
    if (ctx.node_limit > 0 && ctx.nodes > ctx.node_limit) {
        ctx.timeout = true;
        return true;
    }
    if (ctx.has_deadline &&
        std::chrono::steady_clock::now() >= ctx.deadline) {
        ctx.timeout = true;
        return true;
    }
    return false;
}

// ---------------------------------------------------------------------------
// 正交组气检查（吃子防御判定的基础件）
// ---------------------------------------------------------------------------
const int NNX[4] = {1, -1, 0, 0}, NNY[4] = {0, 0, 1, -1};

// 从种子黑子 BFS 其正交组，统计气数（early-exit >= k），返回组气是否 >= k。
// visited 复用：组员标记 1、气点标记 2，跨多次调用共享（多组检查去重）。
bool group_libs_ge_from(Board& b, int x, int y, int k,
                        uint8_t* visited, uint16_t* cap_lib) {
    uint16_t stack[MAX_CELLS];
    int top = 0, libs = 0;
    const int start = Board::index(x, y);
    stack[top++] = uint16_t(start);
    visited[start] = 1;
    while (top > 0) {
        const int cur = stack[--top];
        const int cx = cur / MAX_BOARD, cy = cur % MAX_BOARD;
        for (int t = 0; t < 4; ++t) {
            const int nx = cx + NNX[t], ny = cy + NNY[t];
            if (!b.in_bounds(nx, ny)) continue;
            const int ni = Board::index(nx, ny);
            const uint8_t v = b.at(nx, ny);
            if (v == BLACK) {
                if (!visited[ni]) { visited[ni] = 1; stack[top++] = uint16_t(ni); }
            } else if (v == EMPTY && !visited[ni]) {
                visited[ni] = 2;
                if (cap_lib != nullptr && libs == 0) *cap_lib = uint16_t(ni);
                if (++libs >= k) return true;
            }
        }
    }
    return libs >= k;
}

// 成五点 q 的四子窗口：收集其 F5 方向 ±4 内的黑子 idx（四子的正交组可能互不
// 相连——斜向四子正是如此——必须逐石子检查所在组）。
int collect_five_window_stones(Board& b, int qx, int qy,
                               uint16_t* stones, int cap) {
    static const int DX[4] = {1, 0, 1, 1}, DY[4] = {0, 1, 1, -1};
    const int qidx = Board::index(qx, qy);
    int ns = 0;
    for (int d = 0; d < 4; ++d) {
        if (b.cached_pattern(0, qidx, d) != F5) continue;
        for (int s = -4; s <= 4 && ns < cap; ++s) {
            if (s == 0) continue;
            const int nx = qx + s * DX[d], ny = qy + s * DY[d];
            if (!b.in_bounds(nx, ny)) continue;
            if (b.at(nx, ny) != BLACK) continue;
            stones[ns++] = uint16_t(Board::index(nx, ny));
        }
    }
    return ns;
}

// ---------------------------------------------------------------------------
// 着法生成（tier + 黑棋成五点清单）
// ---------------------------------------------------------------------------
// tier（越大越先搜）：13=成五点(白必堵) 12=活四点 11=四三/双四 10/9=冲四类
// 8..6=活三类 5..2=活二/眠三 1=FORBID(假禁手) 0=无。
int tier_of_p4(int p4, const Board& b, int idx) {
    if (p4 == FORBID) {
        // 假禁手（check_forbidden 精判合法）按方向线型定级。
        int t = 1;
        for (int d = 0; d < 4; ++d) {
            const uint8_t p = b.cached_pattern(0, idx, d);
            if (p == F4 || p == B4) return 11;
            if (p == F3 || p == F3S) t = std::max(t, 8);
            else if (p == B3) t = std::max(t, 5);
        }
        return t;
    }
    return p4;
}

int gen_node_moves(Board& b, int color, NMove* out, uint16_t* bfive, int& n5) {
    const int n = b.size();
    n5 = 0;

    uint8_t seen[MAX_CELLS];
    std::memset(seen, 0, sizeof(seen));
    uint16_t stones[MAX_CELLS];
    int nstones = 0;
    for (int x = 0; x < n; ++x)
        for (int y = 0; y < n; ++y) {
            const uint8_t v = b.at(x, y);
            if (v == BLACK || v == WHITE)
                stones[nstones++] = uint16_t(Board::index(x, y));
        }

    int nm = 0;
    const bool black_mover = (color == BLACK);
    for (int si = 0; si < nstones; ++si) {
        const int sx = stones[si] / MAX_BOARD, sy = stones[si] % MAX_BOARD;
        const int x0 = std::max(0, sx - 2), x1 = std::min(n - 1, sx + 2);
        const int y0 = std::max(0, sy - 2), y1 = std::min(n - 1, sy + 2);
        for (int nx = x0; nx <= x1; ++nx)
            for (int ny = y0; ny <= y1; ++ny) {
                const int idx = Board::index(nx, ny);
                if (seen[idx]) continue;
                seen[idx] = 1;
                if (b.at(nx, ny) != EMPTY) continue;
                if (black_mover && b.is_no_liberty(idx)) continue;  // 黑自杀
                const int p4 = b.cached_pattern4_black(idx);
                if (p4 == A_FIVE) {
                    if (n5 < MAX_MOVES) bfive[n5++] = uint16_t(idx);
                    if (black_mover) continue;      // 成五点由静态杀直接返回
                }
                if (black_mover && p4 == FORBID && check_forbidden(b, nx, ny))
                    continue;                       // 真禁手
                if (nm < MAX_MOVES)
                    out[nm++] = NMove{uint16_t(idx), int8_t(tier_of_p4(p4, b, idx))};
            }
    }
    if (nstones == 0) {
        const int c = n / 2;
        if (b.is_empty(c, c) && nm < MAX_MOVES)
            out[nm++] = NMove{uint16_t(Board::index(c, c)), 0};
        return nm;
    }
    std::sort(out, out + nm, [](const NMove& a, const NMove& c) {
        if (a.tier != c.tier) return a.tier > c.tier;
        return a.pos < c.pos;
    });
    return nm;
}

// ---------------------------------------------------------------------------
// 静态杀判定：唯一保留“轮黑有成五点 → MATE”（无条件健全：成五立即终局）。
// ---------------------------------------------------------------------------
inline int64_t quick_win(int color, int ply, int n5) {
    if (color == BLACK && n5 > 0) {
        if (ply >= 2 && getenv("NODESEARCH_DUMP5"))
            fprintf(stderr, "==== five-point mate ply=%d n5=%d ====\n", ply, n5);
        return MATE - ply - 1;
    }
    return 0;
}

// ---------------------------------------------------------------------------
// VCF 尾部（depth <= 0）：黑攻四、白防五。
// 尾部是**无窗口的纯 AND-OR 精确搜索**：defend 不做 alpha-beta 截断、穷举完整
// 防御清单；attack 的 mate 值只来自 quick_win（真实成五）经完整防御穷举传播。
// 这样 mate 结论不依赖边界传播，健全性与主搜索的 PVS 窗口完全解耦。
// 防御清单（对每个黑棋成五点 q，白棋全部不败着法）：
//   a) 占据 q（堵成五点）；
//   b) 提子：q 的四子窗口中某颗黑子所在正交组恰 1 气 → 该气点（提走四子破四）；
//   c) 无气杀：假想黑落 q 后其块恰 1 气 → 该气点（白占之 q 变自杀点，黑不能落）。
// 其余白应手既不堵五也不破四也不杀五点 → 黑下一手成五，不必搜索。
// ---------------------------------------------------------------------------
int64_t node_dfs(Board& b, int depth, int64_t alpha, int64_t beta, int ply,
                 Ctx& ctx);
int64_t vcf_attack(Board& b, int ply, Ctx& ctx);

// 假想黑棋落 (x,y) 后其块的气；返回气数（<= 2 早退），single_lib 给出第 1 气。
int black_group_libs_after(Board& b, int x, int y, int cap, uint16_t* single_lib) {
    uint8_t visited[MAX_CELLS];
    std::memset(visited, 0, sizeof(visited));
    uint16_t stack[MAX_CELLS];
    int top = 0, libs = 0;
    const int start = Board::index(x, y);
    stack[top++] = uint16_t(start);
    visited[start] = 1;                        // start 假想已落黑
    if (single_lib) *single_lib = 0;
    while (top > 0 && libs < cap) {
        const int cur = stack[--top];
        const int cx = cur / MAX_BOARD, cy = cur % MAX_BOARD;
        for (int t = 0; t < 4 && libs < cap; ++t) {
            const int nx = cx + NNX[t], ny = cy + NNY[t];
            if (!b.in_bounds(nx, ny)) continue;
            const int ni = Board::index(nx, ny);
            if (ni == start) continue;
            const uint8_t v = b.at(nx, ny);
            if (v == BLACK) {
                if (!visited[ni]) { visited[ni] = 1; stack[top++] = uint16_t(ni); }
            } else if (v == EMPTY && !visited[ni]) {
                visited[ni] = 2;
                if (libs == 0 && single_lib) *single_lib = uint16_t(ni);
                ++libs;
            }
        }
    }
    return libs;
}

int64_t vcf_defend(Board& b, int ply, Ctx& ctx) {
    if (ctx_check(ctx)) return 0;
    if (ply >= MAX_PLY) return stm_score(b, ctx.winmode);

    uint16_t bfive[MAX_MOVES];
    int n5;
    {
        NMove mv[MAX_MOVES];
        const int nm = gen_node_moves(b, WHITE, mv, bfive, n5);
        (void)nm;
    }

    if (n5 == 0) return stm_score(b, ctx.winmode);      // 无成五威胁：不受迫

    // 完整防御清单（去重）。
    uint16_t defenses[32];
    int nd = 0;
    uint8_t dmark[MAX_CELLS];
    std::memset(dmark, 0, sizeof(dmark));
    auto add_defense = [&](uint16_t idx) {
        if (nd < 32 && !dmark[idx]) { dmark[idx] = 1; defenses[nd++] = idx; }
    };
    for (int i = 0; i < n5; ++i) {
        const int idx = bfive[i];
        add_defense(uint16_t(idx));                     // a) 堵成五点
        // b) 四子窗口中 1 气正交组的提子点。
        uint16_t stones[16];
        const int ns = collect_five_window_stones(b, idx / MAX_BOARD,
                                                  idx % MAX_BOARD, stones, 16);
        uint8_t visited[MAX_CELLS];
        std::memset(visited, 0, sizeof(visited));
        for (int k = 0; k < ns; ++k) {
            if (visited[stones[k]]) continue;
            uint16_t cap_lib = 0;
            if (!group_libs_ge_from(b, stones[k] / MAX_BOARD,
                                    stones[k] % MAX_BOARD, 2, visited, &cap_lib)) {
                if (cap_lib != 0) {
                    if (getenv("NODESEARCH_TRACE") && ply <= 8) {
                        fprintf(stderr, "  cap-lib for q=(%d,%d) stone=(%d,%d): (%d,%d)\n",
                                idx / MAX_BOARD, idx % MAX_BOARD,
                                stones[k] / MAX_BOARD, stones[k] % MAX_BOARD,
                                cap_lib / MAX_BOARD, cap_lib % MAX_BOARD);
                        for (int x = 0; x < b.size(); ++x) {
                            for (int y = 0; y < b.size(); ++y) {
                                const uint8_t v = b.at(x, y);
                                fprintf(stderr, "%c", v == BLACK ? 'X' : v == WHITE ? 'O' : '.');
                            }
                            fprintf(stderr, "\n");
                        }
                    }
                    add_defense(cap_lib);               // 1 气组 → 提子点
                }
            }
        }
        // c) 黑落 q 后块恰 1 气 → 该气点（无气杀）。
        uint16_t kill_lib = 0;
        if (black_group_libs_after(b, idx / MAX_BOARD, idx % MAX_BOARD, 2,
                                   &kill_lib) < 2 && kill_lib != 0) {
            if (getenv("NODESEARCH_TRACE") && ply <= 8)
                fprintf(stderr, "  kill-lib for q=(%d,%d): (%d,%d)\n",
                        idx / MAX_BOARD, idx % MAX_BOARD,
                        kill_lib / MAX_BOARD, kill_lib % MAX_BOARD);
            add_defense(kill_lib);
        }
    }

    if (getenv("NODESEARCH_TRACE") && ply <= 8) {
        fprintf(stderr, "defend ply=%d n5=%d nd=%d defenses:", ply, n5, nd);
        for (int i = 0; i < nd; ++i)
            fprintf(stderr, " (%d,%d)", defenses[i] / MAX_BOARD, defenses[i] % MAX_BOARD);
        fprintf(stderr, "\n");
    }
    int64_t best = -INF_SCORE;
    for (int i = 0; i < nd; ++i) {
        const int idx = defenses[i];
        if (!b.make_move(idx / MAX_BOARD, idx % MAX_BOARD, WHITE)) continue;
        int64_t v;
        if (b.white_wins_now(ctx.winmode)) {
            v = MATE - ply - 1;                         // 白提光/封堵达成胜利
        } else {
            v = -vcf_attack(b, ply + 1, ctx);
        }
        b.undo_move();
        if (ctx.timeout) return 0;
        if (getenv("NODESEARCH_TRACE") && ply <= 8)
            fprintf(stderr, "  defend ply=%d def=(%d,%d) v=%lld\n", ply,
                    idx / MAX_BOARD, idx % MAX_BOARD, (long long)v);
        if (v > best) best = v;
    }
    if (best == -INF_SCORE) return stm_score(b, ctx.winmode);
    return best;
}

// 攻方节点（轮黑）：静态杀 → stand-pat → 全部成四手取最大（无截断，精确）。
int64_t vcf_attack(Board& b, int ply, Ctx& ctx) {
    if (ctx_check(ctx)) return 0;
    if (ply >= MAX_PLY) return stm_score(b, ctx.winmode);

    NMove mv[MAX_MOVES];
    uint16_t bfive[MAX_MOVES];
    int n5;
    const int nm = gen_node_moves(b, BLACK, mv, bfive, n5);

    if (getenv("NODESEARCH_TRACE") && ply <= 4) {
        fprintf(stderr, "tail-attack ply=%d n5=%d four-moves:", ply, n5);
        for (int i = 0; i < nm && mv[i].tier >= 9; ++i)
            fprintf(stderr, " (%d,%d,t%d)", mv[i].pos / MAX_BOARD, mv[i].pos % MAX_BOARD, mv[i].tier);
        fprintf(stderr, "
");
    }

    {
        const int64_t qw = quick_win(BLACK, ply, n5);
        if (qw != 0) {
            if (ply >= 2 && getenv("NODESEARCH_DUMP5")) {
                fprintf(stderr, "==== tail five-point mate ply=%d n5=%d ====\n", ply, n5);
                for (int x = 0; x < b.size(); ++x) {
                    for (int y = 0; y < b.size(); ++y) {
                        const uint8_t v = b.at(x, y);
                        fprintf(stderr, "%c", v == BLACK ? 'X' : v == WHITE ? 'O' : '.');
                    }
                    fprintf(stderr, "\n");
                }
            }
            return qw;
        }
    }

    // TT 探测（尾部值是局面的确定函数，EXACT 直接返回）。
    const uint64_t key = b.hash();
    {
        const NSTTEntry& e = g_tt[key & TT_MASK];
        if (e.key == key && e.flag == TT_EXACT)
            return tt_load_score(e.score, ply);
    }

    const int64_t stand = stm_score(b, ctx.winmode);
    int64_t best = stand;

    for (int i = 0; i < nm; ++i) {
        if (mv[i].tier < 9) break;                  // 只走成四手（E_BLOCK4 及以上）
        const int idx = mv[i].pos;
        if (!b.make_move(idx / MAX_BOARD, idx % MAX_BOARD, BLACK)) continue;
        int64_t v;
        if (b.last_move_was_five()) {               // 成五点已由静态杀处理
            v = MATE - ply - 1;
        } else {
            v = -vcf_defend(b, ply + 1, ctx);
        }
        b.undo_move();
        if (ctx.timeout) return 0;
        if (v > best) best = v;
    }

    NSTTEntry& e = g_tt[key & TT_MASK];
    e.key = key;
    e.score = tt_store_score(best, ply);
    e.flag = TT_EXACT;
    e.depth = 0;
    e.best = TT_NO_MOVE;
    return best;
}

// ---------------------------------------------------------------------------
// 主搜索（全宽 alpha-beta）
// ---------------------------------------------------------------------------
int64_t node_dfs(Board& b, int depth, int64_t alpha, int64_t beta, int ply,
                 Ctx& ctx) {
    if (ctx_check(ctx)) return 0;

#ifndef NDEBUG
    struct HashGuard {
        const Board& board;
        uint64_t h;
        ~HashGuard() { assert(board.hash() == h); }
    } hash_guard{b, b.hash()};
#endif

    if (ply >= MAX_PLY) return stm_score(b, ctx.winmode);

    // depth <= 0：陷入 VCF 尾部。
    if (depth <= 0) {
        if (getenv("NODESEARCH_NO_VCF")) return stm_score(b, ctx.winmode);
        if (b.turn() == BLACK) return vcf_attack(b, ply, ctx);
        return vcf_defend(b, ply, ctx);
    }

    const int color = b.turn();

    NMove mv[MAX_MOVES];
    uint16_t bfive[MAX_MOVES];
    int n5;
    const int nm = gen_node_moves(b, color, mv, bfive, n5);

    {
        const int64_t qw = quick_win(color, ply, n5);
        if (qw != 0) return qw;
    }

    // TT 探测。
    const uint64_t key = b.hash();
    int tt_best = -1;
    if (getenv("NODESEARCH_NO_TT") == nullptr) {
        const NSTTEntry& e = g_tt[key & TT_MASK];
        if (e.key == key && e.flag != TT_EMPTY) {
            const int64_t s = tt_load_score(e.score, ply);
            if (e.depth >= depth) {
                if (e.flag == TT_EXACT) return s;
                if (e.flag == TT_LOWER && s > alpha) alpha = s;
                else if (e.flag == TT_UPPER && s < beta) beta = s;
                if (alpha >= beta) return s;
            }
            if (e.best != TT_NO_MOVE) tt_best = e.best;
        }
    }

    if (nm == 0) {
        // 黑无着 = 白胜（被吃光 / 全盘无合法点）；白无着 = pass，黑继续。
        if (color == BLACK) return -MATE + ply;
        return stm_score(b, ctx.winmode);
    }

    // TT best 提前。
    if (tt_best >= 0) {
        for (int i = 0; i < nm; ++i)
            if (mv[i].pos == tt_best) {
                std::swap(mv[0], mv[i]);
                break;
            }
    }

    int64_t best = -INF_SCORE;
    uint16_t best_move = TT_NO_MOVE;
    int8_t flag = TT_UPPER;
    int searched = 0;
    for (int i = 0; i < nm; ++i) {
        const int idx = mv[i].pos;
        if (!b.make_move(idx / MAX_BOARD, idx % MAX_BOARD, color)) continue;
        int64_t score;
        if (b.last_move_was_five()) {
            score = MATE - ply - 1;
        } else if (b.white_wins_now(ctx.winmode)) {
            score = (color == WHITE) ? (MATE - ply - 1) : (-MATE + ply);
        } else {
            if (searched == 0 || getenv("NODESEARCH_NO_PVS")) {
                score = -node_dfs(b, depth - 1, -beta, -alpha, ply + 1, ctx);
            } else {
                // PVS：零窗口试探，失败高再以全窗口重搜。
                score = -node_dfs(b, depth - 1, -alpha - 1, -alpha, ply + 1, ctx);
                if (score > alpha && score < beta)
                    score = -node_dfs(b, depth - 1, -beta, -alpha, ply + 1, ctx);
            }
        }
        b.undo_move();
        if (ctx.timeout) return 0;
        ++searched;
        if (ply <= 6)
            fprintf(stderr, "dfs ply=%d depth=%d color=%d move=(%d,%d) score=%lld\n",
                    ply, depth, color, idx / MAX_BOARD, idx % MAX_BOARD,
                    (long long)score);

        if (score > best) {
            best = score;
            best_move = uint16_t(idx);
        }
        if (best > alpha) {
            alpha = best;
            flag = TT_EXACT;
        }
        if (alpha >= beta) {
            flag = TT_LOWER;
            break;
        }
    }

    if (best_move == TT_NO_MOVE) {
        return (color == BLACK) ? (-MATE + ply) : stm_score(b, ctx.winmode);
    }

    if (getenv("NODESEARCH_NO_TT") == nullptr) {
        NSTTEntry& e = g_tt[key & TT_MASK];
        e.key = key;
        e.score = tt_store_score(best, ply);
        e.depth = int16_t(depth);
        e.flag = flag;
        e.best = best_move;
    }
    return best;
}

}  // namespace

void node_tt_clear() {
    tt_ensure();
    std::memset(g_tt, 0, sizeof(NSTTEntry) * TT_SIZE);
}

NodeSearchResult node_search(Board& b, int max_depth, int winmode,
                             double max_sec, long long node_limit,
                             bool clear_tt) {
    tt_ensure();
    if (clear_tt) node_tt_clear();

    NodeSearchResult res;
    const auto start = std::chrono::steady_clock::now();
    Ctx ctx;
    ctx.winmode = winmode;
    ctx.node_limit = node_limit;
    if (max_sec > 0.0) {
        ctx.has_deadline = true;
        ctx.deadline = start +
            std::chrono::duration_cast<std::chrono::steady_clock::duration>(
                std::chrono::duration<double>(max_sec));
    }

    for (int d = 2; d <= max_depth; d += 2) {
        const int64_t s = node_dfs(b, d, -INF_SCORE, INF_SCORE, 0, ctx);
        if (ctx.timeout) break;                     // 保留上一完整深度的结果
        res.score = s;
        res.completed_depth = d;
        if (s >= MATE_BOUND || s <= -MATE_BOUND) break;   // 已有证明级结论
    }
    res.nodes = ctx.nodes;
    res.timeout = ctx.timeout;
    return res;
}

}  // namespace gvg
