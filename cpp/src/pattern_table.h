// pattern_table.h - Rapfi 棋型 DP 查表（board 的增量 pattern 缓存与禁手判定共用）。
//
// 移植自 Rapfi pattern.cpp 的 getPattern<R, Side> / getPattern4<Forbid>：
//   * 线型 DP：不断在空点落己方子递归，直到平凡态（OL / F5 / DEAD），回溯取最强。
//   * renju 黑棋规则：realLen >= 6 为长连；同线双四（两个成五点相距 < 5）dirty fix
//     归为长连。白棋规则没有这两条（白棋无禁手概念）。
//   * 黑 / 白两套记忆表在静态初始化时各填一遍，运行期 O(1) 查表。
// 与 Rapfi 的唯一区别（本项目规格）：阻挡格（OPPO）由 Board 的统一判定给出——
// 白子 / 障碍 / 棋盘外 / 无气空点在代码层面完全一致。
#pragma once

#include <cstdint>

namespace gvg {

// 线型枚举（数值顺序沿用 Rapfi：越大越强）。注意 Rapfi 没有 B4S/B3S——
// "冲四挡住后仍是三"在 Rapfi 里就是 B4，与普通冲四在 44 计数中同等对待。
enum Pat : uint8_t {
    DEAD = 0, OL, B1, F1, B2, F2, F2A, F2B, B3, F3, F3S, B4, F4, F5,
    PATTERN_NB
};

// 四方向组合线型（Rapfi getPattern4<Forbid=true> 的输出域）。
enum Pattern4 : uint8_t {
    P4_NONE = 0, FORBID, L_FLEX2, K_BLOCK3, J_FLEX2_2X, I_BLOCK3_PLUS,
    H_FLEX3, G_FLEX3_PLUS, F_FLEX3_2X, E_BLOCK4, D_BLOCK4_PLUS,
    C_BLOCK4_FLEX3, B_FLEX4, A_FIVE, PATTERN4_NB
};

// 窗口内相对当前行棋方的格状态。数值同时用作三进制编码权重。
enum PatFlag : uint8_t { F_SELF = 0, F_OPPO = 1, F_EMPT = 2 };

constexpr int PAT_H   = 5;             // 中心每侧格数（renju 需 5 才能看到长连）
constexpr int PAT_LEN = 2 * PAT_H + 1; // 11 格窗口
constexpr int PAT_MID = PAT_H;
constexpr int PAT_TRI = 177147;        // 3^11

// line：PAT_LEN 个 PatFlag（中心恒为 F_SELF）。black_rules 选择黑/白规则表。
uint8_t line_pattern(bool black_rules, const uint8_t* line);

// 四方向线型组合。forbid=true 时按 renju 黑棋语义把长连/四四/三三标记为 FORBID。
Pattern4 combine_pattern4(bool forbid, uint8_t p1, uint8_t p2, uint8_t p3,
                          uint8_t p4);

// 同上，但三档禁手分别开关（GUI 的“长连 / 四四 / 三三”复选框；关掉的那一档
// 不再标 FORBID，于是该点不再是禁手点）。combine_pattern4(f,...) 等价于三档全开。
Pattern4 combine_pattern4_flags(bool forbid_overline, bool forbid_44,
                                bool forbid_33, uint8_t p1, uint8_t p2,
                                uint8_t p3, uint8_t p4);

}  // namespace gvg
