// nodesearch.h - 逐节点证明搜索（rapfi 式，第 9 步）。
//
// 迁移自 Rapfi search/ab/search.cpp 的架构：
//   * 全宽 negamax alpha-beta（PVS）+ 置换表 + 迭代加深；
//   * 每个节点入口做**吃子感知的静态杀判定**（Rapfi quickWinCheck 的混合规则版）：
//       - 轮黑且有成五点           → 必胜（1 步）；
//       - 轮黑且有活四点（落子后块气 >= 3）→ 必胜（3 步）；
//       - 轮黑且有四三杀点（同上气条件且活三有合法成活四点）→ 必胜（5 步）；
//       - 轮白且黑棋成五点 >= 2（各组气 >= 3，白棋无法一手提子反驳）
//                                  → 白必败（2 步）；
//     气条件是混合规则的必要加固：白棋可以提子，四/活四的石块处于叫吃时
//     “活四不可挡 / 双五不可挡”不成立（Rapfi 无提子，不需要该条件）。
//   * depth <= 0 陷入 VCF 尾部（Rapfi vcfsearch / vcfdefend）：攻方（黑）只走
//     成四手，守方（白）只应对成五点（外加提子反驳）——全部防御之外的白应手
//     立即败给成五，故只搜这些应手不损失证明健全性。
//   * 非终局叶子用 stm_score（既有增量评估）引导排序与 stand-pat。
//
// 证明语义：|score| >= MATE_BOUND 即证明级结论（全宽搜索 + 健全剪枝，mate 分值
// 只来自真实成五 / 上述静态规则，评估分严格小于 MATE_BOUND）。score 的编码沿用
// search.cpp：走子方胜 = MATE - ply（ply 越小越快），tt 存取做 ply 归一化。
#pragma once

#include <cstdint>

#include "board.h"
#include "search.h"   // MATE / MATE_BOUND / INF_SCORE

namespace gvg {

struct NodeSearchResult {
    int64_t score = 0;        // 根分值（b.turn() 视角）
    int completed_depth = 0;  // 最后完成的迭代深度
    uint64_t nodes = 0;
    bool timeout = false;
};

// 逐节点证明搜索：迭代加深 depth = 2,4,...,max_depth，|score| >= MATE_BOUND
// 即提前返回（score 携带精确步数）。max_sec<=0 无时限；node_limit<=0 无节点
// 上限。clear_tt=false 时复用上次调用的置换表（candidates 逐候选调用时共享，
// 不同候选的子局面键不同，无串扰）。
NodeSearchResult node_search(Board& b, int max_depth, int winmode,
                             double max_sec, long long node_limit,
                             bool clear_tt = true);

}  // namespace gvg
