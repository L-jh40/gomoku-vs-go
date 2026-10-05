// nodesearch.cpp - 逐节点证明搜索实现（rapfi search/ab/search.cpp 的混合规则移植）。
//
// 结构：
//   1. 置换表（本模块私有，2^20 项，always-replace，mate 分 ply 归一化）。
//   2. 着法生成：候选 = 距任一棋子切比雪夫距离 <= 2 的空点（与 gen_moves 同口径）；
//      tier 用 Board 的增量棋型缓存 O(1) 读取（黑 = p4_black 组合等级，
//      白 = 该点上黑棋 p4 的阻挡价值），一次扫描顺带收集黑棋的成五点 / 活四点 /
//      四三杀点清单供静态杀判定使用。
//   3. quick_win：吃子感知的静态杀判定（见 nodesearch.h 顶部说明）。
//      “块气 >= 3”条件是混合规则的关键加固：白棋能提子，叫吃的四/活四石块
//      让 Rapfi 的“活四不可挡 / 双五不可挡”失效。
//   4. node_dfs：全宽 alpha-beta。depth <= 0 陷入 VCF 尾部（vcf_attack /
//      vcf_defend）：黑只走成四手，白只应对成五点（外加 1 气块提子反驳）——
//      其余白应手立即败给成五，因此不搜它们不损失证明健全性。
//   5. 迭代加深根：depth = 2,4,...,max_depth，|score| >= MATE_BOUND 即停。
#include "nodesearch.h"

#include <algorithm>
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
        g_tt = new TTEntry[TT_SIZE];
        std::memset(g_tt, 0, sizeof(TTEntry) * TT_SIZE);
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
    bool     has_deadline = false;
    long long node_limit  = 0;
    long long nodes       = 0;
    bool      timeout     = false;
    int       winmode     = 0;
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
// 块气判定（静态杀的吃子感知条件）
// ---------------------------------------------------------------------------
// 从 (x,y) 的黑子组 BFS，气数是否 >= k（早退）。前置：b.at(x,y) == BLACK。
bool black_group_libs_ge(Board& b, int x, int y, int k) {
    const int NX[4] = {1, -1, 0, 0}, NY[4] = {0, 0, 1, -1};
    uint8_t seen[MAX_CELLS];
    std::memset(seen, 0, sizeof(seen));
    uint16_t stack[MAX_CELLS];
    int top = 0, libs = 0;
    const int start = Board::index(x, y);
    stack[top++] = uint16_t(start);
    seen[start] = 1;
    while (top > 0) {
        const int cur = stack[--top];
        const int cx = cur / MAX_BOARD, cy = cur % MAX_BOARD;
        for (int t = 0; t < 4; ++t) {
            const int nx = cx + NX[t], ny = cy + NY[t];
            if (!b.in_bounds(nx, ny)) continue;
            const int ni = Board::index(nx, ny);
            const uint8_t v = b.at(nx, ny);
            if (v == BLACK) {
                if (!seen[ni]) { seen[ni] = 1; stack[top++] = uint16_t(ni); }
            } else if (v == EMPTY) {
                if (!seen[ni]) { seen[ni] = 2; if (++libs >= k) return true; }
            }
        }
    }
    return libs >= k;
}

// 假想黑棋落 (x,y) 后其块的气是否 >= k（块 = (x,y) ∪ 相连黑子）。
bool black_group_libs_ge_after(Board& b, int x, int y, int k) {
    const int NX[4] = {1, -1, 0, 0}, NY[4] = {0, 0, 1, -1};
    uint8_t seen[MAX_CELLS];
    std::memset(seen, 0, sizeof(seen));
    uint16_t stack[MAX_CELLS];
    int top = 0, libs = 0;
    const int start = Board::index(x, y);
    stack[top++] = uint16_t(start);
    seen[start] = 1;                       // start 假想已落黑
    while (top > 0) {
        const int cur = stack[--top];
        const int cx = cur / MAX_BOARD, cy = cur % MAX_BOARD;
        for (int t = 0; t < 4; ++t) {
            const int nx = cx + NX[t], ny = cy + NY[t];
            if (!b.in_bounds(nx, ny)) continue;
            const int ni = Board::index(nx, ny);
            if (ni == start) continue;
            const uint8_t v = b.at(nx, ny);
            if (v == BLACK) {
                if (!seen[ni]) { seen[ni] = 1; stack[top++] = uint16_t(ni); }
            } else if (v == EMPTY && !seen[ni]) {
                seen[ni] = 2;
                if (++libs >= k) return true;
            }
        }
    }
    return libs >= k;
}

// 成五点 q 的“四石块组”气是否 >= k（沿其 F5 方向找 4 颗黑子 → BFS 组气）。
bool five_point_group_libs_ge(Board& b, int qx, int qy, int k) {
    static const int DX[4] = {1, 0, 1, 1}, DY[4] = {0, 1, 1, -1};
    const int qidx = Board::index(qx, qy);
    for (int d = 0; d < 4; ++d) {
        if (b.cached_pattern(0, qidx, d) != F5) continue;
        for (int s = -4; s <= 4; ++s) {
            if (s == 0) continue;
            const int nx = qx + s * DX[d], ny = qy + s * DY[d];
            if (!b.in_bounds(nx, ny)) continue;
            if (b.at(nx, ny) != BLACK) continue;
            return black_group_libs_ge(b, nx, ny, k);   // 4 子连续 → 同组
        }
    }
    return true;    // 找不到四子（不应发生）：按安全侧处理
}

// ---------------------------------------------------------------------------
// 着法生成（tier + 黑棋威胁点清单）
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

int gen_node_moves(Board& b, int color, NMove* out,
                   uint16_t* bfive, int& n5,
                   uint16_t* bflex4, int& nf4,
                   uint16_t* bc43, int& nc43) {
    const int n = b.size();
    n5 = nf4 = nc43 = 0;

    uint8_t seen[MAX_CELLS];
    std::memset(seen, 0, sizeof(seen));
    uint16_t stones[MAX_CELLS];
    int nstones = 0;
    for (int x = 0; x < n; ++x)
        for (int y = 0; y < n; ++y) {
            const uint8_t v = b.at(x, y);
            if (v == BLACK || v == WHITE) stones[nstones++] = uint16_t(Board::index(x, y));
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
                    bfive[n5++] = uint16_t(idx);
                    if (black_mover) continue;          // 成五点由静态杀直接返回
                } else if (p4 == B_FLEX4) {
                    bflex4[nf4++] = uint16_t(idx);
                } else if (p4 == C_BLOCK4_FLEX3) {
                    bc43[nc43++] = uint16_t(idx);
                }
                int tier;
                if (black_mover) {
                    if (p4 == FORBID && check_forbidden(b, nx, ny)) continue;
                    tier = tier_of_p4(p4, b, idx);
                } else {
                    tier = tier_of_p4(p4, b, idx);      // 白：黑 p4 越强越先堵
                }
                if (nm < MAX_MOVES) out[nm++] = NMove{uint16_t(idx), int8_t(tier)};
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
// 静态杀判定（吃子感知）
// ---------------------------------------------------------------------------
// 返回走子方视角的 MATE 级分值；0 = 无结论。
int64_t quick_win(Board& b, int color, int ply,
                  const uint16_t* bfive, int n5,
                  const uint16_t* bflex4, int nf4,
                  const uint16_t* bc43, int nc43) {
    if (color == BLACK) {
        if (n5 > 0) return MATE - ply - 1;              // 成五立即终局，无条件
        for (int i = 0; i < nf4; ++i) {
            const int idx = bflex4[i];
            if (black_group_libs_ge_after(b, idx / MAX_BOARD, idx % MAX_BOARD, 3))
                return MATE - ply - 3;                  // 活四 + 石块不被一手提
        }
        for (int i = 0; i < nc43; ++i) {
            const int idx = bc43[i];
            const int qx = idx / MAX_BOARD, qy = idx % MAX_BOARD;
            if (!black_group_libs_ge_after(b, qx, qy, 3)) continue;
            // 四三：黑落 q 后活三方向需有合法成活四点，且其组气 >= 3。
            bool ok = false;
            if (b.make_move(qx, qy, BLACK)) {
                static const int DX[4] = {1, 0, 1, 1}, DY[4] = {0, 1, 1, -1};
                const int qidx = Board::index(qx, qy);
                for (int d = 0; d < 4 && !ok; ++d) {
                    const uint8_t p = b.cached_pattern(0, qidx, d);
                    if (p != F3 && p != F3S) continue;
                    for (int s = -4; s <= 4 && !ok; ++s) {
                        if (s == 0) continue;
                        const int nx = qx + s * DX[d], ny = qy + s * DY[d];
                        if (!b.in_bounds(nx, ny)) continue;
                        if (b.at(nx, ny) != EMPTY) continue;
                        const int nidx = Board::index(nx, ny);
                        if (b.is_no_liberty(nidx)) continue;
                        if (b.cached_pattern(0, nidx, d) != F4) continue;
                        if (b.cached_pattern4_black(nidx) == FORBID &&
                            check_forbidden(b, nx, ny))
                            continue;                   // 假活四（Rapfi isFakeCMove）
                        if (!black_group_libs_ge(b, nx, ny, 3)) continue;
                        ok = true;
                    }
                }
                b.undo_move();
            }
            if (ok) return MATE - ply - 5;
        }
    } else {
        if (n5 >= 2) {
            bool all_safe = true;
            for (int i = 0; i < n5 && all_safe; ++i) {
                const int idx = bfive[i];
                if (!five_point_group_libs_ge(b, idx / MAX_BOARD, idx % MAX_BOARD, 3))
                    all_safe = false;
            }
            if (all_safe) return -(MATE - ply - 2);     // 双成五点且都不可提 → 白必败
        }
    }
    return 0;
}

// ---------------------------------------------------------------------------
// VCF 尾部（depth <= 0）：黑攻四、白防五
// ---------------------------------------------------------------------------
int64_t node_dfs(Board& b, int depth, int64_t alpha, int64_t beta, int ply,
                 Ctx& ctx);
int64_t vcf_attack(Board& b, int64_t alpha, int64_t beta, int ply, Ctx& ctx);

// 守方节点（轮白）：黑有成五点时只搜“堵成五点 + 1 气四石块提子”；无威胁 stand-pat。
// 健全性：成五点存在时，其余白应手既不堵成五点也不提走四石块 → 黑下一手成五，
// 价值不高于这里的应手，因此只搜这些应手不损失证明健全性。
int64_t vcf_defend(Board& b, int64_t alpha, int64_t beta, int ply, Ctx& ctx) {
    if (ctx_check(ctx)) return 0;
    if (ply >= MAX_PLY) return stm_score(b, ctx.winmode);

    uint16_t bfive[MAX_MOVES], bflex4[MAX_MOVES], bc43[MAX_MOVES];
    int n5, nf4, nc43;
    {
        NMove mv[MAX_MOVES];
        const int nm = gen_node_moves(b, WHITE, mv, bfive, n5, bflex4, nf4, bc43, nc43);
        (void)nm;
    }

    if (n5 == 0) return stm_score(b, ctx.winmode);      // 无成五威胁：不受迫
    {
        const int64_t qw = quick_win(b, WHITE, ply, bfive, n5, bflex4, nf4, bc43, nc43);
        if (qw != 0) return qw;                         // 双成五且都不可提 → 白必败
    }

    // 应手清单：全部成五点 ∪ 1 气四石块的提子点（n5>=2 但有石块可提时，
    // 提子是唯一可能存活的防御，必须纳入）。
    uint16_t defenses[16];
    int nd = 0;
    static const int DX[4] = {1, 0, 1, 1}, DY[4] = {0, 1, 1, -1};
    for (int i = 0; i < n5 && nd < 16; ++i) {
        const int idx = bfive[i];
        defenses[nd++] = uint16_t(idx);
        if (five_point_group_libs_ge(b, idx / MAX_BOARD, idx % MAX_BOARD, 2))
            continue;                                   // 石块 >= 2 气：提不了
        // 1 气组：BFS 找它的唯一气点（提子防御）。
        const int qx = idx / MAX_BOARD, qy = idx % MAX_BOARD;
        for (int d = 0; d < 4 && nd < 16; ++d) {
            if (b.cached_pattern(0, idx, d) != F5) continue;
            for (int s = -4; s <= 4 && nd < 16; ++s) {
                if (s == 0) continue;
                const int nx = qx + s * DX[d], ny = qy + s * DY[d];
                if (!b.in_bounds(nx, ny)) continue;
                if (b.at(nx, ny) != BLACK) continue;
                const int NX[4] = {1, -1, 0, 0}, NY[4] = {0, 0, 1, -1};
                uint8_t vis[MAX_CELLS];
                std::memset(vis, 0, sizeof(vis));
                uint16_t st[MAX_CELLS];
                int top = 0;
                st[top++] = uint16_t(Board::index(nx, ny));
                vis[st[0]] = 1;
                while (top > 0 && nd < 16) {
                    const int cur = st[--top];
                    const int cx = cur / MAX_BOARD, cy = cur % MAX_BOARD;
                    for (int t = 0; t < 4; ++t) {
                        const int mx = cx + NX[t], my = cy + NY[t];
                        if (!b.in_bounds(mx, my)) continue;
                        const int mi = Board::index(mx, my);
                        const uint8_t v2 = b.at(mx, my);
                        if (v2 == BLACK) {
                            if (!vis[mi]) { vis[mi] = 1; st[top++] = uint16_t(mi); }
                        } else if (v2 == EMPTY && !vis[mi]) {
                            vis[mi] = 2;
                            defenses[nd++] = uint16_t(mi);   // 提子点
                        }
                    }
                }
                s = 8;   // 该方向找到四子即止（同组）
            }
        }
    }

    int64_t best = -INF_SCORE;
    int64_t cur_alpha = alpha;
    for (int i = 0; i < nd; ++i) {
        const int idx = defenses[i];
        if (!b.make_move(idx / MAX_BOARD, idx % MAX_BOARD, WHITE)) continue;
        int64_t v;
        if (b.white_wins_now(ctx.winmode)) {
            v = MATE - ply - 1;                     // 白提光/封堵达成胜利
        } else {
            v = -vcf_attack(b, -beta, -cur_alpha, ply + 1, ctx);
        }
        b.undo_move();
        if (ctx.timeout) return 0;
        if (v > best) best = v;
        if (best > cur_alpha) cur_alpha = best;
        if (cur_alpha >= beta) break;
    }
    if (best == -INF_SCORE) return stm_score(b, ctx.winmode);
    return best;
}

// 攻方节点（轮黑）：静态杀 → stand-pat → 只走成四手。
int64_t vcf_attack(Board& b, int64_t alpha, int64_t beta, int ply, Ctx& ctx) {
    if (ctx_check(ctx)) return 0;
    if (ply >= MAX_PLY) return stm_score(b, ctx.winmode);

    NMove mv[MAX_MOVES];
    uint16_t bfive[MAX_MOVES], bflex4[MAX_MOVES], bc43[MAX_MOVES];
    int n5, nf4, nc43;
    const int nm = gen_node_moves(b, BLACK, mv, bfive, n5, bflex4, nf4, bc43, nc43);

    {
        const int64_t qw = quick_win(b, BLACK, ply, bfive, n5, bflex4, nf4, bc43, nc43);
        if (qw != 0) return qw;
    }

    // TT 探测（VCF 层 depth 恒 0：只做同层截断与边界收窄）。
    const uint64_t key = b.hash();
    {
        const NSNSTTEntry& e = g_tt[key & TT_MASK];
        if (e.key == key && e.flag != TT_EMPTY) {
            const int64_t s = tt_load_score(e.score, ply);
            if (e.flag == TT_LOWER && s > alpha) alpha = s;
            else if (e.flag == TT_UPPER && s < beta) beta = s;
            if (alpha >= beta) return s;
        }
    }

    const int64_t stand = stm_score(b, ctx.winmode);
    if (stand >= beta) return stand;
    int64_t best = stand;
    if (stand > alpha) alpha = stand;

    for (int i = 0; i < nm; ++i) {
        if (mv[i].tier < 9) break;                  // 只走成四手（E_BLOCK4 及以上）
        const int idx = mv[i].pos;
        if (!b.make_move(idx / MAX_BOARD, idx % MAX_BOARD, BLACK)) continue;
        if (b.last_move_was_five()) {               // 成五点已由 quick_win 处理
            b.undo_move();
            continue;
        }
        const int64_t v = -vcf_defend(b, -beta, -alpha, ply + 1, ctx);
        b.undo_move();
        if (ctx.timeout) return 0;
        if (v > best) best = v;
        if (best > alpha) alpha = best;
        if (alpha >= beta) break;
    }

    NSTTEntry& e = g_tt[key & TT_MASK];
    e.key = key;
    e.score = tt_store_score(best, ply);
    e.flag = (best >= beta) ? TT_LOWER : TT_UPPER;
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

    // depth <= 0：陷入 VCF 尾部（vcf_attack / vcf_defend 自带棋型扫描与静态杀）。
    if (depth <= 0) {
        if (b.turn() == BLACK) return vcf_attack(b, alpha, beta, ply, ctx);
        return vcf_defend(b, alpha, beta, ply, ctx);
    }

    const int color = b.turn();

    NMove mv[MAX_MOVES];
    uint16_t bfive[MAX_MOVES], bflex4[MAX_MOVES], bc43[MAX_MOVES];
    int n5, nf4, nc43;
    const int nm = gen_node_moves(b, color, mv, bfive, n5, bflex4, nf4, bc43, nc43);

    // 静态杀判定（吃子感知）。
    {
        const int64_t qw = quick_win(b, color, ply, bfive, n5, bflex4, nf4, bc43, nc43);
        if (qw != 0) return qw;
    }

    // TT 探测。
    const uint64_t key = b.hash();
    int tt_best = -1;
    {
        const NSNSTTEntry& e = g_tt[key & TT_MASK];
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
            if (searched == 0) {
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

    NSTTEntry& e = g_tt[key & TT_MASK];
    e.key = key;
    e.score = tt_store_score(best, ply);
    e.depth = int16_t(depth);
    e.flag = flag;
    e.best = best_move;
    return best;
}

}  // namespace

void node_tt_clear() {
    tt_ensure();
    std::memset(g_tt, 0, sizeof(TTEntry) * TT_SIZE);
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
