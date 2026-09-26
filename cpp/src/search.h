// search.h - alpha-beta 搜索（negamax + 置换表 + 着法排序 + 迭代加深）。
//
// 设计要点：
//  * 评估是“黑棋视角的字典序元组”pack_score（int64）。为了在 negamax 里对白方
//    取负仍保持字典序，把元组搬进 int64 的负数区间（平移 EVAL_CENTER），并压缩
//    到 |值| <= 2^33 的窄带（详见 eval.cpp::compress_eval_tuple / stm_score）。
//  * 终局（黑恰五 / 白全封堵 / 白吃光 / 占满）用 MATE 级别的绝对值，严格支配
//    任何普通评估：|普通评估| <= 2^33 < MATE_BOUND = MATE - 4096 = 2^40 - 4096。
//    因此置换表里 |score| > MATE_BOUND 就一定是 MATE 级别的分值，可以安全地
//    做 ply 归一化。
//  * 搜索全程只 make_move/undo_move，绝不拷贝棋盘；任何返回路径（含超时异常）
//    都保证 hash 与进入时完全一致。
#pragma once

#include <chrono>
#include <cstdint>
#include <exception>
#include <vector>

#include "board.h"

namespace gvg {

// 评估平移量与胜负分。
constexpr int64_t EVAL_CENTER = 1LL << 62;
constexpr int64_t MATE        = 1LL << 40;
constexpr int64_t MATE_BOUND  = MATE - 4096;
// 搜索用的“无穷大”，必须严格大于任何 MATE 级别分值。
constexpr int64_t INF_SCORE   = MATE * 4;

// 着法：score 为 order_score 启发分（越大越先搜）。
struct Move {
    int x;
    int y;
    int score;
};

// 搜索上下文：时间预算、胜负模式、节点计数。
struct SearchCtx {
    std::chrono::steady_clock::time_point deadline{};
    bool     has_deadline = false;
    int      winmode      = 0;
    uint64_t nodes        = 0;
};

// 超时中断：由 alphabeta 在节点入口抛出，search_root 捕获后返回上一完整深度。
class SearchAbort : public std::exception {
public:
    const char* what() const noexcept override { return "search deadline exceeded"; }
};

// 置换表项（指令 9）：flag 0=空 1=EXACT 2=LOWER 3=UPPER。
struct TTEntry {
    uint64_t key;
    int16_t  depth;
    int8_t   flag;
    int64_t  score;
    uint16_t best;
};

// 候选着法：与任一棋子切比雪夫距离 <= 2 的空点（棋盘空 → 中心点）。
// 黑方剔除禁手/无气自杀点；返回前按 score 降序（同分按坐标）排序。
std::vector<Move> gen_moves(const Board& board, int color);

// 着法排序启发分（纯启发，不落子、不改棋盘）。
// own_level（可选输出）= 己方四方向中最强的点线型等级（PointPattern）。
// gen_moves 用它做“该点是否可能构成禁手成分”的廉价预筛。
int order_score(const Board& board, int x, int y, int color,
                int* own_level = nullptr);

// negamax 核心。depth 为剩余深度，ply 为距根的步数。
// 抛 SearchAbort 表示超时；抛出前所有 make_move 都已 undo。
int64_t alphabeta(Board& board, int depth, int64_t alpha, int64_t beta,
                  int ply, SearchCtx& ctx);

struct SearchResult {
    int64_t score = 0;
    int move_x = -1;
    int move_y = -1;
    int completed_depth = -1;
    std::vector<int64_t> depth_scores;
    std::vector<int> depth_move_x;
    std::vector<int> depth_move_y;
    uint64_t nodes = 0;
    double elapsed_sec = 0.0;
};

// 迭代加深根搜索：depth = 0,2,4,6,8（到 max_depth 为止；max_depth==0 只做 depth0）。
// max_sec<=0 表示无时限。返回的 move_x<0 表示当前方无着（白 pass / 黑 resign）。
SearchResult search_root(Board& board, int max_depth, double min_sec,
                         double max_sec, int winmode);

// 清空置换表（main.cpp 在 size 命令时调用）。
void tt_clear();

}  // namespace gvg
