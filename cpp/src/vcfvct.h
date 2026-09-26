// vcfvct.h - VCF/VCT 威胁空间搜索 + W*/L* 必胜/必败步数标注。
//
// 语义约定：
//  * 攻击方恒为黑棋（VCF/VCT 是黑方的威胁空间搜索）。对手恒为白棋。
//  * “四”的防御集合是精确集合：挡全部完成点 ∪ 提掉 1 气黑块的点；
//    “三”的防御集合是超集（健全性优先：宁可多试白应手，不可漏真实防御）。
//  * steps 是“到达黑方成五那一步的总手数”：黑候选 W = 2*m-1（m 为黑攻击手数），
//    白候选 L = 2*m（白第 1 手 + 黑第 m 手成五）。
//  * 搜索全程 make_move/undo_move，不拷贝棋盘，返回后 hash 逐位还原。
#pragma once

#include <cstdint>
#include <utility>
#include <vector>

#include "board.h"

namespace gvg {

enum class AtkType : uint8_t { NONE, OPEN_THREE, RUSH_FOUR, OPEN_FOUR, FIVE };

struct WinPath {
    std::vector<std::pair<int,int>> black_moves; // 攻击方(黑)依次落的点
    std::vector<std::vector<std::pair<int,int>>> defense_sets; // defense_sets[i] = black_moves[i] 落下后白方的全部防御点集合（阻挡∪吃子）
    int plies() const { return (int)black_moves.size(); } // 黑攻击手数 m
};

struct CandidateLabel {
    int x, y;
    char tag;   // 'W' / 'L' / 0(无标注)
    int steps;  // W: 2*m-1（黑候选）/ L: 2*m（白候选）；tag==0 时无意义
};

struct AnalysisResult {
    std::vector<CandidateLabel> labels;
    int paths_found;      // 枚举到的必胜路径条数（对当前行棋方而言）
    long long nodes;      // 搜索节点数（统计用）
    bool timeout;         // 是否因时间/节点上限截断
};

// 主入口：对"轮到 color 行棋"的当前局面，给 gen_moves(color) 的每个候选打标注。
AnalysisResult analyse(Board& b, int color, int max_steps, int winmode,
                       double time_limit_sec, long long node_limit);

// 供调试/测试：只判断黑方在 max_steps 攻击手数内是否存在 VCF 必胜（纯 VCF，不含三）。
bool vcf_exists(Board& b, int max_steps);
// 黑方 VCT（含四与三）必胜判断。
bool vct_exists(Board& b, int max_steps);

}  // namespace gvg
