// eval.cpp - pack_score 实现。
#include "eval.h"

#include <algorithm>

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

}  // namespace gvg
