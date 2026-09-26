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

}  // namespace gvg
