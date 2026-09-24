// forbidden.h - 黑棋禁手判定（移植自 Rapfi 的 checkForbiddenPoint）。
//
// check_forbidden(board, x, y) 假设 (x,y) 为空点，返回该点是否为黑棋的
// 长连 / 四四 / 三三禁手。注意：本函数只做 Rapfi 语义下的“禁手”判定；
// “无气点自杀”属于混合规则的非法律，由调用方结合 Board::is_dead_empty 处理。
#pragma once

#include "board.h"

namespace gvg {

bool check_forbidden(Board& board, int x, int y);

}  // namespace gvg
