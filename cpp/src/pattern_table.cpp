// pattern_table.cpp - Rapfi 棋型 DP 的查表实现（黑/白两套规则各一份记忆表）。
// DP 分支与 Rapfi pattern.cpp getPattern<R, Side> 逐行对应；组合表与
// getPattern4<Forbid> 逐行对应（44 计数只算 B4/F4，B4S 在 Rapfi 中不存在）。
#include "pattern_table.h"

#include <cstring>

namespace gvg {

namespace {

struct Memo {
    uint8_t v[PAT_TRI];  // 0 = 未计算；否则 Pat+1
};

Memo g_memo_black;  // renju 黑棋规则（长连 / 同线双四 dirty fix）
Memo g_memo_white;  // 白棋规则（无长连、无 dirty fix）

inline int encode(const uint8_t* f) {
    int c = 0;
    for (int i = 0; i < PAT_LEN; ++i) c = c * 3 + f[i];
    return c;
}

// Rapfi countLine：realLen = 过中心的连续己方子数（隔空递减增量）；
// fullLen = 两端到第一个对方子为止的跨度；[start,end] 为该跨度。
void count_line(const uint8_t* f, int& realLen, int& fullLen,
                int& start, int& end) {
    realLen = 1;
    fullLen = 1;
    int inc = 1;
    start = end = PAT_MID;
    for (int i = PAT_MID - 1; i >= 0; --i) {
        if (f[i] == F_SELF)
            realLen += inc;
        else if (f[i] == F_OPPO)
            break;
        else
            inc = 0;
        ++fullLen;
        start = i;
    }
    inc = 1;
    for (int i = PAT_MID + 1; i < PAT_LEN; ++i) {
        if (f[i] == F_SELF)
            realLen += inc;
        else if (f[i] == F_OPPO)
            break;
        else
            inc = 0;
        ++fullLen;
        end = i;
    }
}

// Rapfi shiftLine：把第 i 格重新居中，窗口外的格视为对方子。
void shift_line(const uint8_t* line, int i, uint8_t* out) {
    for (int j = 0; j < PAT_LEN; ++j) {
        const int idx = j + i - PAT_MID;
        out[j] = (idx >= 0 && idx < PAT_LEN) ? line[idx]
                                             : static_cast<uint8_t>(F_OPPO);
    }
}

uint8_t get_pattern_rec(bool black_rules, const uint8_t* line) {
    Memo& memo = black_rules ? g_memo_black : g_memo_white;
    const int code = encode(line);
    if (memo.v[code]) return static_cast<uint8_t>(memo.v[code] - 1);

    int realLen, fullLen, start, end;
    count_line(line, realLen, fullLen, start, end);

    uint8_t p = DEAD;
    if (black_rules && realLen >= 6) {
        p = OL;                               // 长连（仅黑棋规则）
    } else if (realLen >= 5) {
        p = F5;                               // 成五（白棋 6 连也按成五记）
    } else if (fullLen < 5) {
        p = DEAD;                             // 两端跨度不足五，永远成不了五
    } else {
        int patCnt[PATTERN_NB] = {0};
        int f5Idx[2]           = {0};
        uint8_t shifted[PAT_LEN];
        for (int i = start; i <= end; ++i) {
            if (line[i] != F_EMPT) continue;
            shift_line(line, i, shifted);
            shifted[PAT_MID] = F_SELF;
            const uint8_t sp = get_pattern_rec(black_rules, shifted);
            if (sp == F5 && patCnt[F5] < 2) f5Idx[patCnt[F5]] = i;
            ++patCnt[sp];
        }
        if (patCnt[F5] >= 2) {
            p = F4;
            // Rapfi 的 dirty fix：同一线上两个成五点相距 < 5（同线双四）
            // 在 renju 黑棋规则下按长连禁手处理。
            if (black_rules && f5Idx[1] - f5Idx[0] < 5) p = OL;
        } else if (patCnt[F5]) {
            p = B4;                           // 一个成五点：冲四
        } else if (patCnt[F4] >= 2) {
            p = F3S;
        } else if (patCnt[F4]) {
            p = F3;
        } else if (patCnt[B4]) {
            p = B3;
        } else if (patCnt[F3S] + patCnt[F3] >= 4) {
            p = F2B;
        } else if (patCnt[F3S] + patCnt[F3] >= 3) {
            p = F2A;
        } else if (patCnt[F3S] + patCnt[F3]) {
            p = F2;
        } else if (patCnt[B3]) {
            p = B2;
        } else if (patCnt[F2] + patCnt[F2A] + patCnt[F2B]) {
            p = F1;
        } else if (patCnt[B2]) {
            p = B1;
        }
    }

    memo.v[code] = static_cast<uint8_t>(p + 1);
    return p;
}

struct PatternTableInit {
    PatternTableInit() {
        std::memset(g_memo_black.v, 0, sizeof(g_memo_black.v));
        std::memset(g_memo_white.v, 0, sizeof(g_memo_white.v));
        uint8_t line[PAT_LEN];
        for (int c = 0; c < PAT_TRI; ++c) {
            int t = c;
            for (int i = PAT_LEN - 1; i >= 0; --i) {
                line[i] = static_cast<uint8_t>(t % 3);
                t /= 3;
            }
            get_pattern_rec(true, line);
            get_pattern_rec(false, line);
        }
    }
};
const PatternTableInit g_pattern_init;

}  // namespace

uint8_t line_pattern(bool black_rules, const uint8_t* line) {
    return get_pattern_rec(black_rules, line);
}

Pattern4 combine_pattern4(bool forbid, uint8_t p1, uint8_t p2, uint8_t p3,
                          uint8_t p4) {
    return combine_pattern4_flags(forbid, forbid, forbid, p1, p2, p3, p4);
}

// 三档禁手开关版（GUI 的“长连/四四/三三”复选框）：关掉的那一档不再标 FORBID。
// 关掉后同一个点的组合线型会退回到“它本来是什么”（例如三三退回 F_FLEX3_2X），
// 于是 check_forbidden 的第一步预筛就不再把该点当禁手点。
Pattern4 combine_pattern4_flags(bool forbid_overline, bool forbid_44,
                                bool forbid_33, uint8_t p1, uint8_t p2,
                                uint8_t p3, uint8_t p4) {
    int n[PATTERN_NB] = {0};
    ++n[p1];
    ++n[p2];
    ++n[p3];
    ++n[p4];

    if (n[F5] >= 1) return A_FIVE;  // 恰好成五优先

    if (forbid_overline && n[OL] >= 1) return FORBID;          // 长连
    if (forbid_44 && n[F4] + n[B4] >= 2) return FORBID;        // 四四
    if (forbid_33 && n[F3] + n[F3S] >= 2) return FORBID;       // 三三（预筛）

    if (n[B4] >= 2) return B_FLEX4;
    if (n[F4] >= 1) return B_FLEX4;
    if (n[B4] >= 1) {
        if (n[F3] >= 1 || n[F3S] >= 1) return C_BLOCK4_FLEX3;
        if (n[B3] >= 1) return D_BLOCK4_PLUS;
        if (n[F2] + n[F2A] + n[F2B] >= 1) return D_BLOCK4_PLUS;
        return E_BLOCK4;
    }
    if (n[F3] >= 1 || n[F3S] >= 1) {
        if (n[F3] + n[F3S] >= 2) return F_FLEX3_2X;
        if (n[B3] >= 1) return G_FLEX3_PLUS;
        if (n[F2] + n[F2A] + n[F2B] >= 1) return G_FLEX3_PLUS;
        return H_FLEX3;
    }
    if (n[B3] >= 1) {
        if (n[B3] >= 2) return I_BLOCK3_PLUS;
        if (n[F2] + n[F2A] + n[F2B] >= 1) return I_BLOCK3_PLUS;
    }
    if (n[F2] + n[F2A] + n[F2B] >= 2) return J_FLEX2_2X;
    if (n[B3] >= 1) return K_BLOCK3;
    if (n[F2] + n[F2A] + n[F2B] >= 1) return L_FLEX2;
    return P4_NONE;
}

}  // namespace gvg
