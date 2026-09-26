// eval.h - 评估元组的字典序打包（int64）。
//
// 打包后整数直接比较 = 字段从高到低的字典序比较，alpha-beta 可直接使用。
// 字段（每字段 8 bit，全部非负）：
//   F1 = min(黑 open_four, 255)
//   F2 = min(黑 rush_four, 255)
//   F3 = min(黑 open_three, 255)
//   F4 = min(黑 sleep_three + 黑 open_two, 255)
//   F5 = min(黑 sleep_two, 255)
//   F6 = 255 - min(risk, 255)
//   F7 = 255 - min(territory, 255)
//   F8 = 0
#pragma once

#include <cstdint>

#include "board.h"

namespace gvg {

int64_t pack_score(const Board& board);

// 搜索用的“轮到谁走”视角分数（negamax）。
//   black_packed = pack_score(board)
//   return (black_packed - EVAL_CENTER) * (turn==BLACK ? +1 : -1)
// EVAL_CENTER 是 1LL<<62 的平移量：pack_score 越大对黑越有利，平移后相减
// 取负即可让“白方视角”的字典序正确翻转（详见 search.h 说明）。
//
// 终局优先（正常情况下节点入口已排除终局，这里是安全网）：
//   黑已恰五 → +MATE；白已达成胜利条件 → -MATE。
// winmode 与 Board::white_wins_now 一致（0=line_block, 1=occupy）。
int64_t stm_score(const Board& board, int winmode = 0);

}  // namespace gvg
