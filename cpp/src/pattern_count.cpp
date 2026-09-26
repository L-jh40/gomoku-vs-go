// pattern_count.cpp - 六类线型计数的查表实现。
#include "pattern_count.h"

#include <cstring>

namespace gvg {

namespace {

// ---- 与 Python rules.py PATTERNS 逐类一致的模式表 ----
struct PatDef {
    const char* s;
    int         len;
    int         cls;
};

const PatDef kPatterns[] = {
    // open_four
    {"011110", 6, 0},
    // rush_four
    {"211110", 6, 1}, {"11101", 5, 1}, {"11011", 5, 1},
    // open_three
    {"011100", 6, 2}, {"011010", 6, 2},
    // sleep_three
    {"211100", 6, 3}, {"211010", 6, 3}, {"210110", 6, 3},
    {"2011102", 7, 3}, {"10101", 5, 3}, {"11001", 5, 3},
    // open_two
    {"001100", 6, 4}, {"011000", 6, 4}, {"010100", 6, 4}, {"010010", 6, 4},
    // sleep_two
    {"211000", 6, 5}, {"210100", 6, 5}, {"210010", 6, 5},
    {"2011002", 7, 5}, {"2010102", 7, 5}, {"10001", 5, 5},
};
constexpr int kNumPatterns = sizeof(kPatterns) / sizeof(kPatterns[0]);

// 每个“起始位置窗口”允许的最大长度是 7。tbl7 的索引是 7 个三进制位
// （每格 2 bit，0/1/2，最高位是最左侧的格）；tbl6 / tbl5 同理。
// 表项是该位置上命中的类别位掩码（bit c = 类别 c 命中）。
uint8_t g_tbl5[1 << 10];
uint8_t g_tbl6[1 << 12];
uint8_t g_tbl7[1 << 14];

// 把 idx 解码成 len 个三进制位（t[0] 为窗口最左格）。
inline void decode(uint32_t idx, uint8_t* t, int len) {
    for (int j = len - 1; j >= 0; --j) {
        t[j] = static_cast<uint8_t>(idx & 3u);
        idx >>= 2;
    }
}

inline bool match_at(const uint8_t* t, const char* pat, int len, bool rev) {
    for (int j = 0; j < len; ++j) {
        const int want = rev ? (pat[len - 1 - j] - '0') : (pat[j] - '0');
        if (t[j] != want) return false;
    }
    return true;
}

uint8_t build_mask(const uint8_t* t, int win) {
    uint8_t m = 0;
    for (int p = 0; p < kNumPatterns; ++p) {
        if (kPatterns[p].len > win) continue;
        if (match_at(t, kPatterns[p].s, kPatterns[p].len, false) ||
            match_at(t, kPatterns[p].s, kPatterns[p].len, true)) {
            m |= static_cast<uint8_t>(1u << kPatterns[p].cls);
        }
    }
    return m;
}

struct TableInit {
    TableInit() {
        uint8_t t[7];
        std::memset(g_tbl5, 0, sizeof(g_tbl5));
        std::memset(g_tbl6, 0, sizeof(g_tbl6));
        std::memset(g_tbl7, 0, sizeof(g_tbl7));
        for (uint32_t i = 0; i < (1u << 10); ++i) {
            decode(i, t, 5);
            g_tbl5[i] = build_mask(t, 5);
        }
        for (uint32_t i = 0; i < (1u << 12); ++i) {
            decode(i, t, 6);
            g_tbl6[i] = build_mask(t, 6);
        }
        for (uint32_t i = 0; i < (1u << 14); ++i) {
            decode(i, t, 7);
            g_tbl7[i] = build_mask(t, 7);
        }
    }
};
const TableInit g_table_init;

inline void add_mask(uint8_t m, int out[NUM_EVAL_PATTERNS]) {
    if (m & 1u)  out[0] += 1;
    if (m & 2u)  out[1] += 1;
    if (m & 4u)  out[2] += 1;
    if (m & 8u)  out[3] += 1;
    if (m & 16u) out[4] += 1;
    if (m & 32u) out[5] += 1;
}

}  // namespace

void count_line_chars(const char* s, int len, int out[NUM_EVAL_PATTERNS]) {
    out[0] = out[1] = out[2] = out[3] = out[4] = out[5] = 0;
    if (len <= 0) return;
    if (len > 24) len = 24;  // 防御性截断；合法线长 <= 19

    // 两端各补 4 个 '2'（障碍 / 边界）。
    char buf[24 + 8];
    const int pad = 4;
    for (int i = 0; i < pad; ++i) buf[i] = '2';
    std::memcpy(buf + pad, s, static_cast<size_t>(len));
    for (int i = 0; i < pad; ++i) buf[pad + len + i] = '2';
    const int P = len + 2 * pad;

    int c5 = 0, c6 = 0, c7 = 0;
    for (int i = 0; i < P; ++i) {
        const int t = buf[i] - '0';
        c5 = ((c5 << 2) | t) & 0x3FF;
        c6 = ((c6 << 2) | t) & 0xFFF;
        c7 = ((c7 << 2) | t) & 0x3FFF;
        // i-6 是 7 格窗口的起始位置（>=0 保证窗口完整）。
        if (i >= 6) add_mask(g_tbl7[c7], out);
    }
    // 末尾两个“不足 7 格”的起始位置：长度 5 / 6 的模式仍可能在
    // P-6 / P-5 起始处匹配。
    if (P >= 6) add_mask(g_tbl6[c6], out);
    if (P >= 5) add_mask(g_tbl5[c5], out);
}

PatternCounts count_line(const std::string& line) {
    PatternCounts out{};
    count_line_chars(line.c_str(), static_cast<int>(line.size()), out.data());
    return out;
}

}  // namespace gvg
