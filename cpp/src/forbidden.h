// forbidden.h - 黑棋禁手判定（Rapfi checkForbiddenPoint 的忠实移植）。
//
// check_forbidden(board, x, y) 假设 (x,y) 为空点，返回该点是否为黑棋的
// 长连 / 四四 / 三三禁手。判定完全走 Board 的增量棋型缓存（O(1) 预筛），
// 三三的“假禁手延伸点”用真实 make_move/undo_move 递归验证。
// 注意：“无气点自杀”属于混合规则的非法律，不是 renju 禁手；无气空点在
// 棋型层由 Board 统一映射为阻挡（与白子/障碍代码层面完全一致）。
#pragma once

#include "board.h"

namespace gvg {

bool check_forbidden(Board& board, int x, int y);

// 单方向点线型等级（由弱到强，可直接用 > 比较取最强方向）。
// 命名对应 Rapfi 的线型枚举经合并后的等级：
//   PP_B2     = B2/B1（眠二）
//   PP_FLEX2  = F2/F2A/F2B（活二）
//   PP_B3     = B3（眠三）
//   PP_FLEX3  = F3/F3S（活三）
//   PP_B4     = B4（冲四）
//   PP_FLEX4  = F4（活四）
//   PP_FIVE   = F5（恰好成五）
//   PP_OL     = OL（长连；对黑棋是禁手，排在最后仅表示“必须走禁手判定”）
// DEAD / F1 归入 PP_NONE。own_best >= PP_B3 是“该点可能构成禁手成分”的
// 必要（非充分）条件，gen_moves 用它配合 O(1) 的棋型缓存预筛。
enum PointPattern : uint8_t {
    PP_NONE = 0,
    PP_B2,
    PP_FLEX2,
    PP_B3,
    PP_FLEX3,
    PP_B4,
    PP_FLEX4,
    PP_FIVE,
    PP_OL,
};

// 把 (x,y) 当作 color 的子、沿方向 (dx,dy) 分类其线型等级（不落子、不改棋盘）。
// color==BLACK 时“无气空点”视作阻挡（与禁手判定一致）；color==WHITE 时空点
// 一律视作可落子。order_score 与禁手判定共用该函数。
PointPattern classify_point(const Board& board, int x, int y, int color,
                            int dx, int dy);

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
