// eval.cpp - pack_score / stm_score 实现。
#include "eval.h"

#include <algorithm>

#include "search.h"

namespace gvg {

int64_t pack_score(const Board& board) {
    const int32_t* bc = board.black_counts();

    const uint64_t F1 = static_cast<uint64_t>(std::min<int32_t>(bc[0], 255));
    const uint64_t F2 = static_cast<uint64_t>(std::min<int32_t>(bc[1], 255));
    const uint64_t F3 = static_cast<uint64_t>(std::min<int32_t>(bc[2], 255));
    const uint64_t F4 =
        static_cast<uint64_t>(std::min<int32_t>(bc[3] + bc[4], 255));
    const uint64_t F5 = static_cast<uint64_t>(std::min<int32_t>(bc[5], 255));
    const uint64_t F6 =
        static_cast<uint64_t>(255 - std::min<int32_t>(board.risk(), 255));
    const uint64_t F7 =
        static_cast<uint64_t>(255 - std::min<int32_t>(board.territory(), 255));
    const uint64_t F8 = 0;

    const uint64_t packed = (F1 << 56) | (F2 << 48) | (F3 << 40) | (F4 << 32) |
                            (F5 << 24) | (F6 << 16) | (F7 << 8) | F8;
    return static_cast<int64_t>(packed);
}

namespace {

// 把 pack_score 的“黑棋视角 7 字段元组”压进窄带，同时严格保持字典序：
//   F1(open_four)      8bit -> 4bit，饱和 15
//   F2(rush_four)      8bit -> 4bit，饱和 15
//   F3(open_three)     8bit -> 5bit，饱和 31
//   F4(sleep3+open2)   8bit -> 5bit，饱和 31
//   F5(sleep_two)      8bit -> 5bit，饱和 31
//   F6=255-risk        8bit -> 5bit，以 risk 饱和 31 后反转
//   F7=255-territory   8bit -> 6bit，以 territory 饱和 63 后反转
// 结果落在 [0, 2^34)，再平移 -2^33 居中。为什么必须压缩：pack_score 本身
// 可以到 2^56 量级，直接减 EVAL_CENTER 后是 ±2^62 量级，而 MATE = 2^40，
// 终局分会被普通评估完全淹没（白方甚至会为了更大的普通分值而不取胜），
// 置换表的 MATE ply 归一化（|score| > MATE_BOUND）也会误判。压缩后
// |普通评估| <= 2^33 << MATE_BOUND，终局分严格支配。
inline int64_t compress_eval_tuple(int64_t packed) {
    const uint64_t p = static_cast<uint64_t>(packed);
    const auto cap = [](int64_t v, int64_t hi) { return v > hi ? hi : v; };
    const int64_t f1 = cap(static_cast<int64_t>((p >> 56) & 0xFF), 15);
    const int64_t f2 = cap(static_cast<int64_t>((p >> 48) & 0xFF), 15);
    const int64_t f3 = cap(static_cast<int64_t>((p >> 40) & 0xFF), 31);
    const int64_t f4 = cap(static_cast<int64_t>((p >> 32) & 0xFF), 31);
    const int64_t f5 = cap(static_cast<int64_t>((p >> 24) & 0xFF), 31);
    // F6 = 255 - min(risk,255) → risk = 255 - F6；越大越好，反转成 31-risk。
    const int64_t risk =
        cap(255 - static_cast<int64_t>((p >> 16) & 0xFF), 31);
    const int64_t terr =
        cap(255 - static_cast<int64_t>((p >> 8) & 0xFF), 63);
    const int64_t v = (f1 << 30) | (f2 << 26) | (f3 << 21) | (f4 << 16) |
                      (f5 << 11) | ((31 - risk) << 6) | (63 - terr);
    return v - (1LL << 33);
}

}  // namespace

int64_t stm_score(const Board& board, int winmode) {
    // 终局优先。这里按“轮到谁走”的视角给分（negamax 语义）：
    // 黑恰五时轮到白走 → 白方视角为 -MATE；白达成胜利条件时轮到黑走 → -MATE。
    if (board.last_move_was_five())
        return (board.turn() == BLACK) ? MATE : -MATE;
    if (board.white_wins_now(winmode))
        return (board.turn() == WHITE) ? MATE : -MATE;

    // 指令 5 的平移（black_packed - EVAL_CENTER）本身不改变字典序，只是把
    // “黑越大越好”的点数搬进 int64 的负数区间；这里再把它压缩进 MATE 支配的
    // 窄带（保持 7 字段字典序，见 compress_eval_tuple 的说明）。
    const int64_t black_packed = pack_score(board);
    const int64_t value = compress_eval_tuple(black_packed);
    return (board.turn() == BLACK) ? value : -value;
}

}  // namespace gvg
