// search.cpp - alpha-beta 搜索实现。
#include "search.h"

#include <algorithm>
#include <cassert>
#include <cstring>

#include "eval.h"
#include "forbidden.h"

namespace gvg {

namespace {

// ---- 置换表：固定 2^20 项，索引 = key & (2^20 - 1)，always-replace ----
constexpr size_t TT_BITS = 20;
constexpr size_t TT_SIZE = size_t(1) << TT_BITS;
constexpr size_t TT_MASK = TT_SIZE - 1;

constexpr int8_t TT_EMPTY = 0;
constexpr int8_t TT_EXACT = 1;
constexpr int8_t TT_LOWER = 2;
constexpr int8_t TT_UPPER = 3;

constexpr uint16_t TT_NO_MOVE = 0xFFFF;

TTEntry* g_tt = nullptr;

void tt_ensure() {
    if (g_tt == nullptr) {
        g_tt = new TTEntry[TT_SIZE];
        std::memset(g_tt, 0, sizeof(TTEntry) * TT_SIZE);
    }
}

inline uint16_t pack_pos(int x, int y) {
    return static_cast<uint16_t>(Board::index(x, y));
}

// 存入 TT 前把 MATE 级别分值归一化为“相对本节点”的值；取出时反向还原。
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

// 根搜索单层结果。
struct RootOutcome {
    int64_t score = -INF_SCORE;
    int x = -1;
    int y = -1;
};

// 根节点着法重排：prev 最佳第一，TT 最佳第二，其余保持 gen_moves 的顺序。
void reorder_root(std::vector<Move>& moves, int prev_x, int prev_y,
                  int tt_best) {
    auto move_to = [&](size_t dst, int px, int py) {
        for (size_t i = dst; i < moves.size(); ++i) {
            if (moves[i].x == px && moves[i].y == py) {
                std::swap(moves[dst], moves[i]);
                return true;
            }
        }
        return false;
    };
    if (prev_x >= 0) move_to(0, prev_x, prev_y);
    if (tt_best >= 0) {
        const int bx = tt_best / MAX_BOARD, by = tt_best % MAX_BOARD;
        if (moves.empty() || moves[0].x != bx || moves[0].y != by)
            move_to(moves.size() >= 2 ? 1 : 0, bx, by);
    }
}

RootOutcome root_search_depth(Board& b, int depth, SearchCtx& ctx, int prev_x,
                              int prev_y) {
    const int color = b.turn();
    std::vector<Move> moves = gen_moves(b, color);
    RootOutcome out;
    if (moves.empty()) return out;
    out.x = moves[0].x;
    out.y = moves[0].y;

    // 根节点只用 TT 的 best move 排序，不看 depth。
    int tt_best = -1;
    const uint64_t key = b.hash();
    {
        const TTEntry& e = g_tt[key & TT_MASK];
        if (e.key == key && e.flag != TT_EMPTY && e.best != TT_NO_MOVE)
            tt_best = e.best;
    }
    reorder_root(moves, prev_x, prev_y, tt_best);

    int64_t alpha = -INF_SCORE;
    const int64_t beta = INF_SCORE;
    int64_t best = -INF_SCORE;
    for (const Move& m : moves) {
        if (!b.make_move(m.x, m.y, color)) continue;
        int64_t score;
        try {
            if (b.last_move_was_five()) {
                score = MATE - 1;                 // 黑方立即成五
            } else if (b.white_wins_now(ctx.winmode)) {
                // 白方（=刚走子的一方）达成胜利条件。
                score = (color == WHITE) ? (MATE - 1) : (-MATE);
            } else {
                score = -alphabeta(b, depth - 1, -beta, -alpha, 1, ctx);
            }
        } catch (...) {
            b.undo_move();
            throw;
        }
        b.undo_move();

        if (score > best) {
            best = score;
            out.x = m.x;
            out.y = m.y;
        }
        if (score > alpha) alpha = score;
    }
    out.score = best;

    // 根节点结果写回 TT（EXACT）：下一轮迭代加深可据此优先排着。
    if (out.x >= 0) {
        TTEntry& e = g_tt[key & TT_MASK];
        e.key = key;
        e.depth = static_cast<int16_t>(depth);
        e.flag = TT_EXACT;
        e.score = tt_store_score(best, 0);
        e.best = pack_pos(out.x, out.y);
    }
    return out;
}

}  // namespace

void tt_clear() {
    tt_ensure();
    std::memset(g_tt, 0, sizeof(TTEntry) * TT_SIZE);
}

// ===========================================================================
// 着法排序启发（不落子、不改棋盘）
// ===========================================================================
int order_score(const Board& board, int x, int y, int color, int* own_level) {
    if (!board.is_empty(x, y)) {
        if (own_level) *own_level = PP_NONE;
        return 0;
    }
    static const int DX[4] = {1, 0, 1, 1};
    static const int DY[4] = {0, 1, 1, -1};

    const int opp = (color == BLACK) ? WHITE : BLACK;

    // 己方四方向线型等级。
    int own[4];
    int own_best = PP_NONE;
    for (int d = 0; d < 4; ++d) {
        const PointPattern p =
            classify_point(board, x, y, color, DX[d], DY[d]);
        own[d] = static_cast<int>(p);
        if (own[d] > own_best) own_best = own[d];
    }
    if (own_level) *own_level = own_best;

    // (a) 落此点立即成恰五。
    if (own_best == PP_FIVE) return 1000000000;

    // 对方四方向线型等级（按需计算，最多 4 次分类）。
    int opp_best = -1;
    auto opp_max = [&]() -> int {
        if (opp_best < 0) {
            opp_best = PP_NONE;
            for (int d = 0; d < 4; ++d) {
                const PointPattern p =
                    classify_point(board, x, y, opp, DX[d], DY[d]);
                if (static_cast<int>(p) > opp_best)
                    opp_best = static_cast<int>(p);
            }
        }
        return opp_best;
    };

    // (b) 白棋堵黑的成五点；黑棋补活被叫吃（唯一气）的块。
    if (color == WHITE) {
        if (opp_max() == PP_FIVE) return 500000000;
    } else {
        if (board.white_would_capture(x, y)) return 500000000;
    }

    // (c) 己方成活四，或堵住对方的活四点。
    if (own_best == PP_FLEX4) return 100000000;
    if (opp_max() == PP_FLEX4) return 100000000;

    // (d) 己方成冲四或活三。
    for (int d = 0; d < 4; ++d) {
        if (own[d] == PP_B4 || own[d] == PP_FLEX3) return 10000000;
    }

    // (e) 四方向等级分值求和（黑/白对称）。
    static const int VAL[9] = {
        0,    // PP_NONE
        8,    // PP_B2
        40,   // PP_FLEX2
        80,   // PP_B3
        400,  // PP_FLEX3
        800,  // PP_B4
        0,    // PP_FLEX4（上面已返回）
        0,    // PP_FIVE（上面已返回）
        0,    // PP_OL（长连，黑棋禁手/白棋无意义）
    };
    int sum = 0;
    for (int d = 0; d < 4; ++d) sum += VAL[own[d]];
    return sum;
}

// ===========================================================================
// 着法生成
// ===========================================================================
std::vector<Move> gen_moves(const Board& board, int color) {
    const int n = board.size();
    std::vector<Move> out;
    out.reserve(96);   // 避免热路径上的多次扩容

    uint8_t seen[MAX_CELLS];
    std::memset(seen, 0, sizeof(seen));

    bool any_piece = false;
    for (int x = 0; x < n; ++x) {
        for (int y = 0; y < n; ++y) {
            const uint8_t v = board.at(x, y);
            if (v != BLACK && v != WHITE) continue;   // 障碍不产生候选
            any_piece = true;
            const int x0 = (x - 2 < 0) ? 0 : x - 2;
            const int x1 = (x + 2 > n - 1) ? n - 1 : x + 2;
            const int y0 = (y - 2 < 0) ? 0 : y - 2;
            const int y1 = (y + 2 > n - 1) ? n - 1 : y + 2;
            for (int nx = x0; nx <= x1; ++nx) {
                for (int ny = y0; ny <= y1; ++ny) {
                    const int idx = Board::index(nx, ny);
                    if (seen[idx]) continue;
                    seen[idx] = 1;
                    if (board.is_empty(nx, ny)) {
                        const Move m{nx, ny, 0};
                        out.push_back(m);
                    }
                }
            }
        }
    }

    if (!any_piece) {
        const int c = n / 2;
        if (board.is_empty(c, c)) {
            const Move m{c, c, 0};
            out.push_back(m);
        }
        return out;
    }

    // 每个候选先算 order_score；对黑棋，只有 own_level >= PP_B3（即该方向
    // 出现眠三/活三/冲四/活四/长连等禁手成分）才需要调用昂贵的
    // check_forbidden。该预筛是充分必要的：check_forbidden 的第一步预筛
    // 正是“四方向线型中必须含 OL/B4/B4S/F4/F3/F3S”。过滤在原数组上原地完成。
    Board& mb = const_cast<Board&>(board);
    size_t w = 0;
    for (size_t i = 0; i < out.size(); ++i) {
        Move m = out[i];
        int own_level = gvg::PP_NONE;
        m.score = order_score(board, m.x, m.y, color, &own_level);
        if (color == BLACK) {
            if (board.is_dead_empty(m.x, m.y)) continue;
            if (own_level >= gvg::PP_B3 && check_forbidden(mb, m.x, m.y))
                continue;
        }
        out[w++] = m;
    }
    out.resize(w);

    std::sort(out.begin(), out.end(), [](const Move& a, const Move& b) {
        if (a.score != b.score) return a.score > b.score;
        if (a.x != b.x) return a.x < b.x;
        return a.y < b.y;
    });
    return out;
}

// ===========================================================================
// negamax 核心
// ===========================================================================
int64_t alphabeta(Board& b, int depth, int64_t alpha, int64_t beta, int ply,
                  SearchCtx& ctx) {
    if (ctx.has_deadline &&
        std::chrono::steady_clock::now() >= ctx.deadline)
        throw SearchAbort();
    ++ctx.nodes;

#ifndef NDEBUG
    // 调试断言：进出节点 hash 必须完全一致（含异常展开路径）。
    struct HashGuard {
        const Board& board;
        uint64_t h;
        ~HashGuard() { assert(board.hash() == h); }
    } hash_guard{b, b.hash()};
#endif

    // 落子即胜由调用方（父节点 make_move 之后）判定，这里只做叶子评估。
    if (depth <= 0) return stm_score(b, ctx.winmode);

    const uint64_t key = b.hash();
    int tt_best = -1;
    {
        const TTEntry& e = g_tt[key & TT_MASK];
        if (e.key == key && e.flag != TT_EMPTY) {
            const int64_t s = tt_load_score(e.score, ply);
            if (e.depth >= depth) {
                if (e.flag == TT_EXACT) return s;
                if (e.flag == TT_LOWER) {
                    if (s > alpha) alpha = s;
                } else if (e.flag == TT_UPPER) {
                    if (s < beta) beta = s;
                }
                if (alpha >= beta) return s;
            }
            if (e.best != TT_NO_MOVE) tt_best = e.best;
        }
    }

    const int color = b.turn();
    std::vector<Move> moves = gen_moves(b, color);

    if (moves.empty()) {
        // 黑方无着 = 白胜（被吃光 / 全盘无合法点）；白方无着 = pass，黑继续。
        if (color == BLACK) return -MATE + ply;
        return stm_score(b, ctx.winmode);
    }

    if (tt_best >= 0) {
        for (size_t i = 0; i < moves.size(); ++i) {
            if (pack_pos(moves[i].x, moves[i].y) == tt_best) {
                std::swap(moves[0], moves[i]);
                break;
            }
        }
    }

    int64_t best = -INF_SCORE;
    int best_move = -1;
    int8_t flag = TT_UPPER;   // 先假设 fail-low
    for (const Move& m : moves) {
        if (!b.make_move(m.x, m.y, color)) continue;
        int64_t score;
        try {
            if (b.last_move_was_five()) {
                // 黑方刚成恰五：对走子方（黑）是胜利。
                score = MATE - ply - 1;
            } else if (b.white_wins_now(ctx.winmode)) {
                // 白方达成胜利条件。走子方是白则白胜，否则（理论不可达）黑负。
                score = (color == WHITE) ? (MATE - ply - 1) : (-MATE + ply);
            } else {
                score = -alphabeta(b, depth - 1, -beta, -alpha, ply + 1, ctx);
            }
        } catch (...) {
            b.undo_move();   // 异常路径也必须成对 undo
            throw;
        }
        b.undo_move();

        if (score > best) {
            best = score;
            best_move = pack_pos(m.x, m.y);
        }
        if (score > alpha) {
            alpha = score;
            flag = TT_EXACT;
        }
        if (alpha >= beta) {
            flag = TT_LOWER;
            break;
        }
    }

    if (best_move < 0) {
        // 所有候选 make_move 都失败（理论上不会发生）。
        return (color == BLACK) ? (-MATE + ply) : stm_score(b, ctx.winmode);
    }

    // 递归可能覆盖同一个槽位，写入前重新取一次。
    TTEntry& e = g_tt[key & TT_MASK];
    e.key = key;
    e.depth = static_cast<int16_t>(depth);
    e.flag = flag;
    e.score = tt_store_score(best, ply);
    e.best = static_cast<uint16_t>(best_move);
    return best;
}

// ===========================================================================
// 迭代加深根搜索
// ===========================================================================
SearchResult search_root(Board& b, int max_depth, double min_sec, double max_sec,
                         int winmode) {
    tt_ensure();
    // 每次根搜索都从空表开始：保证“同局面 + 同参数 → 同输出”（跨调用也确定）。
    // 迭代加深内部的 TT 复用不受影响。
    tt_clear();
    SearchResult res;
    const auto start = std::chrono::steady_clock::now();

    SearchCtx ctx;
    ctx.winmode = winmode;
    if (max_sec > 0.0) {
        ctx.has_deadline = true;
        ctx.deadline =
            start + std::chrono::duration_cast<std::chrono::steady_clock::duration>(
                        std::chrono::duration<double>(max_sec));
    }

    auto finish = [&]() {
        res.nodes = ctx.nodes;
        res.elapsed_sec =
            std::chrono::duration<double>(std::chrono::steady_clock::now() -
                                          start)
                .count();
        return res;
    };

    // ---- depth 0：只用着法排序给出候选（不搜索） ----
    {
        const int color = b.turn();
        std::vector<Move> moves = gen_moves(b, color);
        res.completed_depth = 0;
        res.score = stm_score(b, winmode);
        if (!moves.empty()) {
            res.move_x = moves[0].x;
            res.move_y = moves[0].y;
        }
        res.depth_scores.push_back(res.score);
        res.depth_move_x.push_back(res.move_x);
        res.depth_move_y.push_back(res.move_y);
    }
    if (max_depth <= 0 || res.move_x < 0) return finish();

    for (int d = 2; d <= max_depth && d <= 8; d += 2) {
        if (ctx.has_deadline && std::chrono::steady_clock::now() >= ctx.deadline)
            break;
        RootOutcome ro;
        bool aborted = false;
        try {
            ro = root_search_depth(b, d, ctx, res.move_x, res.move_y);
        } catch (const SearchAbort&) {
            aborted = true;
        }
        if (aborted) break;   // 保留上一完整深度的结果
        if (ro.x < 0) break;
        res.score = ro.score;
        res.move_x = ro.x;
        res.move_y = ro.y;
        res.completed_depth = d;
        res.depth_scores.push_back(ro.score);
        res.depth_move_x.push_back(ro.x);
        res.depth_move_y.push_back(ro.y);
        if (d >= 8) break;
        const double elapsed =
            std::chrono::duration<double>(std::chrono::steady_clock::now() -
                                          start)
                .count();
        if (res.completed_depth >= max_depth && elapsed >= min_sec) break;
    }
    return finish();
}

}  // namespace gvg
