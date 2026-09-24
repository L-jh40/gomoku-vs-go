// forbidden.h - 黑棋禁手判定（移植自 Rapfi 的 checkForbiddenPoint）。
//
// check_forbidden(board, x, y) 假设 (x,y) 为空点，返回该点是否为黑棋的
// 长连 / 四四 / 三三禁手。注意：本函数只做 Rapfi 语义下的“禁手”判定；
// “无气点自杀”属于混合规则的非法律，由调用方结合 Board::is_dead_empty 处理。
#pragma once

#include "board.h"

namespace gvg {

bool check_forbidden(Board& board, int x, int y);

// 诊断用：暴露某空点的四方向线型 / 组合线型 / 四数 / 真三数。
// dir[i] 为方向 i 的 Pat 枚举值（0=DEAD ... 15=F5），p4 为 Pattern4 枚举值。
struct ForbiddenProbe {
    int  dir[4];
    int  p4;
    int  fours;
    int  threes;
    bool forbidden;
};
ForbiddenProbe probe_forbidden(Board& board, int x, int y);

}  // namespace gvg
