// pattern_count.h - 评估用的六类线型计数。
//
// 直接取 Python rules.py 的 PATTERNS 语义（逐类复制），并对一条线字符串
// 按“位置 × 类别”统计出现次数。线字符串字符集：
//   '0' 空点，'1' 当前评估方的子，'2' 阻挡（对方子 / 障碍 / 棋盘边界）。
//
// 计数规则（与任务指令一致）：
//   * 线字符串两端各补 4 个 '2'；
//   * 对每个起始位置 i 与每个类别 c：若该类任一 pattern 或其反转在 i 处匹配，
//     则 c 计数 +1（同一位置同类只加一次，不同位置各自累加，允许重叠）。
#pragma once

#include <array>
#include <string>

namespace gvg {

// 类别下标（顺序固定）：0 open_four, 1 rush_four, 2 open_three,
//                        3 sleep_three, 4 open_two, 5 sleep_two
constexpr int NUM_EVAL_PATTERNS = 6;

using PatternCounts = std::array<int, NUM_EVAL_PATTERNS>;

// 便捷接口：对一条不含补边的线字符串计数（内部会补 '2'）。
PatternCounts count_line(const std::string& line);

// 热路径接口：直接对 C 字符串计数，避免 std::string 的堆分配。
// len 为线长（<= MAX_BOARD），out 为 6 个类别计数。
void count_line_chars(const char* s, int len, int out[NUM_EVAL_PATTERNS]);

}  // namespace gvg
