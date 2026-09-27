// vcfvct.h - 证明级 VCF/VCT 威胁空间搜索（AND-OR）+ W*/L* 必胜/必败步数标注。
//
// 语义约定（第 6 步重写：从“OR 式路径枚举”改为“证明级 AND-OR 搜索”）：
//  * 攻击方恒为黑棋（VCF/VCT 是黑方的威胁空间搜索）。对手恒为白棋。
//  * 只有能被一棵 AND-OR 证明树支撑的结论才会被标注：
//      - 黑方节点（OR）：存在一手攻击，使白方**全部**防御都应手失败；
//      - 白方节点（AND）：对防御集合内**每一个**应手，黑方都仍能强制成五。
//    证明不出（预算耗尽 / 触限流）→ 不标注。宁可漏标，不可错标。
//  * 四的防御集合是“白下集合外黑立即成五”的健全超集；三的防御集合是
//    “白下集合外黑必能完成三→四升级”的健全超集。组成与逐条论证见 vcfvct.cpp
//    顶部注释与 IMPLEMENTATION.md。
//  * steps 是“到达黑方成五那一步的总手数”：黑候选 W = 2*m-1（m 为黑攻击手数），
//    白候选 L = 2*m（白第 1 手 + 黑第 m 手成五）。m 通过迭代加深取“首个证明成功
//    的预算”，而不是启发式最短路径。
//  * 搜索全程 make_move/undo_move，不拷贝棋盘，返回后 hash 逐位还原。
#pragma once

#include <cstdint>
#include <utility>
#include <vector>

#include "board.h"

namespace gvg {

enum class AtkType : uint8_t { NONE, OPEN_THREE, RUSH_FOUR, OPEN_FOUR, FIVE };

// 证明搜索结果。
//   WIN     - 已构造出健全的 AND-OR 证明树（黑方在预算内强制成五）。
//   UNKNOWN - 证明不出（候选耗尽 / 非威胁手 / 预算不足），不得据此标注。
//   TIMEOUT - 触及时间或节点上限，结论未知。
enum class ProveResult : uint8_t { WIN, UNKNOWN, TIMEOUT };

// 仅作调试用途（第 6 步的证明搜索不再填充该结构）。
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
    int paths_found;      // 已证明成功的候选数（旧版语义为“枚举到的路径条数”）
    long long nodes;      // 搜索节点数（统计用）
    bool timeout;         // 是否因时间/节点上限截断
};

// 主入口：对“轮到 color 行棋”的当前局面，给 gen_moves(color) 的每个候选打标注。
AnalysisResult analyse(Board& b, int color, int max_steps, int winmode,
                       double time_limit_sec, long long node_limit);

// 黑方证明搜索（第 6 步新增）：前置 b.turn()==BLACK。只有“在 max_steps 个黑
// 攻击手数内对白方全部防御都成立”才返回 WIN。allow_three=false 为纯 VCF，
// true 为含三的 VCT。time_sec<=0 表示无时限，node_limit<=0 表示无节点上限。
ProveResult prove_black(Board& b, int max_steps, bool allow_three,
                        double time_sec, long long node_limit);

// 供调试/测试：黑方是否存在预算内的 VCF / VCT 必胜（= prove_black == WIN）。
bool vcf_exists(Board& b, int max_steps);
bool vct_exists(Board& b, int max_steps);

}  // namespace gvg
