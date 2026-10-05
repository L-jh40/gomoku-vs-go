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

// 棋盘坐标 (x, y)：x = 行(0 起，自上而下)，y = 列(0 起，自左而右)。
using Pt = std::pair<int, int>;

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
    // true = 步数只是下界（“至少 steps 步”）：来自层 2 智能应对（完备但不可靠）的
    // 兜底步数，输出成 W<steps>+ / L<steps>+；后续枚举全部应对可以把步数算准。
    bool at_least = false;
};

struct AnalysisResult {
    std::vector<CandidateLabel> labels;
    int paths_found;      // 已证明成功的候选数（旧版语义为“枚举到的路径条数”）
    long long nodes;      // 搜索节点数（统计用）
    bool timeout;         // 是否因时间/节点上限截断
};

// ===========================================================================
// 白棋威胁候选点（第 8 步重写：rapfi 式威胁分类 + 逐威胁防御集 + 交集框架）
// ===========================================================================
// 迁移自 Rapfi 的威胁判定（game/pattern.cpp DEFENCE 防守掩码、game/movegen.cpp
// findFourDefence / findB4F3Defence / findFlex4LineDefence）。黑棋“强迫威胁点”
// 按方向线型组合分类：
//   * 成五点（某方向 F5，盘上已有四）：防御 = 成五点本身 ∪ 吃子点；
//   * 杀点（活四/双四成分参与的立即胜：F4∧三/四、双活四、双冲四、三三[禁手关]）：
//     防御 = 杀点本身 ∪ 吃子点 ∪ 无气构造点；
//   * 四三杀点（B4∧F3）：防御 = 杀点 ∪ 活三线降级探针 ∪ 冲四线成五点 ∪ 吃子/无气；
//   * 纯活四点（单方向 F4，活三的成活四点）：防御 = 该线试落阻挡点 ∪ 吃子/无气。
// 纯冲四点（单方向 B4）与纯活三点不是强迫威胁（冲四成五点一手可挡；活三由它的
// 成活四点代表）→ 不产生候选。试落阻挡点 = 白棋落 p（真实 make_move，含提子）后
// 线上不再有“黑棋可落的成五/活四制造点”（Rapfi DEFENCE 表的运行时等价）。
// 候选集 = 所有威胁防御集的交集；交集为空回退并集；无威胁 → 全盘空点（everywhere）。

// 三层 VCT 的步数参数（analyse 的缺省参数；candidates 命令的 steps 覆盖 vct 层）。
// 注意：第 8 步起白方候选不再做逐点 W/L 标注，该参数仅保留协议兼容。
struct VctParams {
    int vc  = 1;    // VC ：黑落子至少形成活二 / 眠三，最多 1 步（浅层筛查）
    int vct = 18;   // VCT：黑落子至少形成活三 / 做杀（四三；无禁手时三三、四四）
    int vcf = 180;  // VCF：黑落子形成冲四
};

// 一条“含黑棋强制威胁”的线：线上存在黑棋一步成五 / 成四的点。
// （第 8 步起 rep.lines 改为逐威胁报告：rank = 威胁种类，black = {威胁点}，
//   blockers = 该威胁的防御集。）
struct ThreatLine {
    int dx = 0, dy = 0;        // 线方向（DX4/DY4 之一）
    int rank = 0;              // 该线黑棋最强威胁等级（AtkType 值）
    int cells = 0;             // 线上格数（盘内）
    std::vector<Pt> black;     // 线上黑子（idx 形式）
    std::vector<Pt> blockers;  // 阻挡点（白棋有效应对点，idx 形式）
};

// “本轮全部应对点”集合：Rapfi 式必胜搜索里可平移、可判定无效防御的存储单元。
// 本轮 = 黑棋刚落下的那一手威胁手（bx,by）；points = 白棋对它的全部应对
// （阻挡点 ∪ 吃子点）。（第 8 步起随三层 VCT 封存，仅保留类型定义。）
struct DefenseSet {
    std::vector<Pt> points;    // 本轮白棋的全部应对点
    int bx = -1, by = -1;      // 产生该应对集的黑棋威胁手
    int rank = 0;              // 该手的威胁等级（AtkType 值）
};

// 一条被证明成功的 VCT 路线（黑攻击手序列 + 逐轮应对集）。
struct VctRoute {
    std::vector<Pt> black_moves;
    std::vector<DefenseSet> sets;
};

// 三层 VCT 的结果。（第 8 步起随三层 VCT 封存，仅保留类型定义。）
struct VctOutcome {
    bool win = false;                    // 黑方在预算内被证明必胜
    int  steps = 0;                      // 成功时的黑方攻击手数 m
    bool timeout = false;                // 是否因时间上限截断
    std::vector<DefenseSet> first_sets;  // 所有成功路线的**首轮**应对集（取交集 = 候选点）
    std::vector<VctRoute> routes;        // 成功路线（供后续 Rapfi 式必胜搜索）
};

// 层 1 全应对 VCT / 层 2 智能应对 VCT——第 8 步起**已封存**（vcfvct.cpp 内 #if 0），
// 仅有声明无定义；任何调用都会链接失败。保留声明以记录历史接口。
VctOutcome vct_all_response(Board& b, const VctParams& p, double time_sec);
VctOutcome vct_smart_response(Board& b, const VctParams& p, double time_sec);

// 混合判定的防御点交集——同上，已封存。
std::vector<Pt> mixed_defense_intersection(Board& b, const VctOutcome& all_resp);

// 白棋威胁候选点的完整报告（candidates w 的输出依据）。
struct WhiteCandidateReport {
    bool unconstrained = false;   // 盘面无黑棋强迫威胁 → 全盘空点都是候选点（legal:everywhere）
    int  threat_lines   = 0;      // 威胁点数（字段名沿用：威胁点分类后不再按“线”计数）
    int  intersect_size = 0;      // 交集规模（无交集时为 0）
    bool intersect_empty = false; // 交集为空 → 回退并集（黑棋多重杀，白棋已不可挡）
    std::vector<Pt> must_block;   // 杀点类威胁点（成五点/杀点：白棋“只能占据”的点）
    std::vector<Pt> captures;     // 威胁相关吃子点并集
    std::vector<Pt> candidates;   // 最终候选点（交集 / 并集回退，已排序去重）
    std::vector<ThreatLine> lines;// 逐威胁报告（rank=种类, black={威胁点}, blockers=防御集）
};
WhiteCandidateReport white_threat_candidates(Board& b);

// 主入口：对“轮到 color 行棋”的当前局面给候选打标注。
//   color == BLACK：对 gen_moves(BLACK) 的每个候选打 W/L（第 6 步 AND-OR 证明语义，
//     不变）。
//   color == WHITE：候选集 = 白棋威胁候选点（第 8 步：威胁防御集交集，无交集回退
//     并集；无强迫威胁时输出全部空点 legal:everywhere）。候选点一律 tag=0 无标注
//     （输出三列 cand x y）；逐点 W/L 证明标注已停用封存，由后续的 rapfi 式
//     逐节点搜索承担。
AnalysisResult analyse(Board& b, int color, int max_steps, int winmode,
                       double time_limit_sec, long long node_limit,
                       const VctParams& params = VctParams());

// 黑方证明搜索（第 6 步新增）：前置 b.turn()==BLACK。只有“在 max_steps 个黑
// 攻击手数内对白方全部防御都成立”才返回 WIN。allow_three=false 为纯 VCF，
// true 为含三的 VCT。time_sec<=0 表示无时限，node_limit<=0 表示无节点上限。
ProveResult prove_black(Board& b, int max_steps, bool allow_three,
                        double time_sec, long long node_limit);

// 供调试/测试：黑方是否存在预算内的 VCF / VCT 必胜（= prove_black == WIN）。
bool vcf_exists(Board& b, int max_steps);
bool vct_exists(Board& b, int max_steps);

}  // namespace gvg
