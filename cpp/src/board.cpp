// board.cpp - Board 实现（棋盘、提子、悔棋、Zobrist）。
#include "board.h"

#include <cstring>

namespace gvg {

namespace {

// ---- Zobrist 随机数表（静态初始化一次，无第三方依赖） ----
struct SplitMix64 {
    uint64_t s;
    explicit SplitMix64(uint64_t seed) : s(seed) {}
    uint64_t next() {
        uint64_t z = (s += 0x9E3779B97F4A7C15ULL);
        z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
        z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
        return z ^ (z >> 31);
    }
};

struct Zobrist {
    uint64_t piece[4][MAX_CELLS];  // 下标即格子值(黑/白/障碍)；0 号空位不使用
    uint64_t turn;                 // 轮到白走时异或此键
    Zobrist() {
        SplitMix64 rng(0xD1B54A32D192ED03ULL);
        for (int c = 0; c < 4; ++c)
            for (int i = 0; i < MAX_CELLS; ++i) piece[c][i] = rng.next();
        turn = rng.next();
    }
};

const Zobrist& zob() {
    static const Zobrist table;  // 线程安全且只构造一次
    return table;
}

const int DX4[4] = {-1, 1, 0, 0};
const int DY4[4] = {0, 0, -1, 1};

}  // namespace

Board::Board(int size) {
    reset(size);
}

void Board::reset(int size) {
    if (size < 9) size = 9;
    if (size > MAX_BOARD) size = MAX_BOARD;
    if ((size & 1) == 0) ++size;              // 规整到奇数
    if (size > MAX_BOARD) size = MAX_BOARD - 1;
    size_        = size;
    turn_        = BLACK;
    move_count_  = 0;
    captured_top_ = 0;
    hash_        = 0;                          // 空盘 + 黑先 => 哈希 0
    std::memset(cells_, 0, sizeof(cells_));
}

void Board::clear() {
    reset(size_);
}

void Board::set_cell(int x, int y, uint8_t value) {
    if (!in_bounds(x, y)) return;
    const int idx = index(x, y);
    const uint8_t old = cells_[idx];
    if (old == value) return;
    if (old != EMPTY) hash_ ^= zob().piece[old][idx];
    cells_[idx] = value;
    if (value != EMPTY) hash_ ^= zob().piece[value][idx];
}

bool Board::black_group_has_liberty(int x, int y) const {
    const int start = index(x, y);
    if (cells_[start] != BLACK) return false;

    uint8_t seen[MAX_CELLS];
    std::memset(seen, 0, sizeof(seen));
    int stack[MAX_CELLS];
    int top = 0;
    stack[top++] = start;
    seen[start]  = 1;

    while (top > 0) {
        const int cur = stack[--top];
        const int cx = cur / MAX_BOARD;
        const int cy = cur % MAX_BOARD;
        for (int k = 0; k < 4; ++k) {
            const int nx = cx + DX4[k];
            const int ny = cy + DY4[k];
            if (!in_bounds(nx, ny)) continue;
            const int ni = index(nx, ny);
            const uint8_t v = cells_[ni];
            if (v == EMPTY) return true;              // 找到一口气
            if (v == BLACK && !seen[ni]) {
                seen[ni] = 1;
                stack[top++] = ni;
            }
        }
    }
    return false;  // 整块无气
}

bool Board::is_dead_empty(int x, int y) const {
    if (!in_bounds(x, y)) return false;
    const int idx = index(x, y);
    if (cells_[idx] != EMPTY) return false;

    // 只要有一个正交邻点是空点，落黑后就有气，立即判活。
    // 若所有邻点都被占据，则把相邻黑块合并后看是否还有气（候选点自身不算气）。
    uint8_t seen[MAX_CELLS];
    std::memset(seen, 0, sizeof(seen));
    int stack[MAX_CELLS];

    for (int k = 0; k < 4; ++k) {
        const int nx = x + DX4[k];
        const int ny = y + DY4[k];
        if (!in_bounds(nx, ny)) continue;
        const int ni = index(nx, ny);
        const uint8_t v = cells_[ni];
        if (v == EMPTY) return false;
        if (v == BLACK && !seen[ni]) {
            int top = 0;
            stack[top++] = ni;
            seen[ni]     = 1;
            bool hasLib  = false;
            while (top > 0) {
                const int cur = stack[--top];
                const int cx = cur / MAX_BOARD;
                const int cy = cur % MAX_BOARD;
                for (int kk = 0; kk < 4; ++kk) {
                    const int ax = cx + DX4[kk];
                    const int ay = cy + DY4[kk];
                    if (!in_bounds(ax, ay)) continue;
                    const int ai = index(ax, ay);
                    const uint8_t av = cells_[ai];
                    if (av == EMPTY) {
                        if (ai != idx) { hasLib = true; }  // 候选点不算气
                    } else if (av == BLACK && !seen[ai]) {
                        seen[ai] = 1;
                        stack[top++] = ai;
                    }
                }
            }
            if (hasLib) return false;
        }
    }
    return true;  // 落黑即无气
}

bool Board::make_move(int x, int y, int color) {
    if (!in_bounds(x, y)) return false;
    if (color != BLACK && color != WHITE) return false;
    const int idx = index(x, y);
    if (cells_[idx] != EMPTY) return false;
    if (move_count_ >= MAX_CELLS) return false;

    if (color == BLACK) {
        cells_[idx] = BLACK;
        hash_ ^= zob().piece[BLACK][idx];
        if (!black_group_has_liberty(x, y)) {
            // 黑棋自杀：等同非法，撤销落子。
            cells_[idx] = EMPTY;
            hash_ ^= zob().piece[BLACK][idx];
            return false;
        }
        // 黑棋永不提白子。
        history_[move_count_++] =
            HistoryEntry{static_cast<uint16_t>(idx), static_cast<uint8_t>(BLACK),
                         static_cast<uint16_t>(captured_top_), 0};
    } else {
        cells_[idx] = WHITE;
        hash_ ^= zob().piece[WHITE][idx];

        // 白棋落子只会影响与之相邻的黑块，只对这些块做气检测。
        int ncap = 0;
        uint16_t* cap = captured_pool_ + captured_top_;
        uint8_t seen[MAX_CELLS];
        std::memset(seen, 0, sizeof(seen));
        int stack[MAX_CELLS];
        int grp[MAX_CELLS];

        for (int k = 0; k < 4; ++k) {
            const int nx = x + DX4[k];
            const int ny = y + DY4[k];
            if (!in_bounds(nx, ny)) continue;
            const int ni = index(nx, ny);
            if (cells_[ni] != BLACK || seen[ni]) continue;

            int top = 0, gcount = 0;
            bool hasLib = false;
            stack[top++] = ni;
            seen[ni]     = 1;
            while (top > 0) {
                const int cur = stack[--top];
                grp[gcount++] = cur;
                const int cx = cur / MAX_BOARD;
                const int cy = cur % MAX_BOARD;
                for (int kk = 0; kk < 4; ++kk) {
                    const int ax = cx + DX4[kk];
                    const int ay = cy + DY4[kk];
                    if (!in_bounds(ax, ay)) continue;
                    const int ai = index(ax, ay);
                    const uint8_t av = cells_[ai];
                    if (av == EMPTY) hasLib = true;
                    else if (av == BLACK && !seen[ai]) {
                        seen[ai] = 1;
                        stack[top++] = ai;
                    }
                }
            }
            if (!hasLib) {
                // 无气黑块整块提走。不同棋块互不相邻，因此清除顺序不影响结果。
                for (int g = 0; g < gcount; ++g) {
                    const int s = grp[g];
                    cells_[s] = EMPTY;
                    hash_ ^= zob().piece[BLACK][s];
                    cap[ncap++] = static_cast<uint16_t>(s);
                }
            }
        }
        history_[move_count_++] =
            HistoryEntry{static_cast<uint16_t>(idx), static_cast<uint8_t>(WHITE),
                         static_cast<uint16_t>(captured_top_),
                         static_cast<uint16_t>(ncap)};
        captured_top_ += ncap;
    }

    turn_ = (color == BLACK) ? WHITE : BLACK;
    hash_ ^= zob().turn;  // turn 键参与哈希
    return true;
}

bool Board::undo_move() {
    if (move_count_ <= 0) return false;
    const HistoryEntry h = history_[--move_count_];

    // 复原被提走的黑子。
    for (int i = 0; i < h.cap_count; ++i) {
        const int s = captured_pool_[h.cap_begin + i];
        cells_[s] = BLACK;
        hash_ ^= zob().piece[BLACK][s];
    }
    captured_top_ = h.cap_begin;

    // 移除本步落子并还原回合。
    cells_[h.pos] = EMPTY;
    hash_ ^= zob().piece[h.color][h.pos];
    turn_ = h.color;
    hash_ ^= zob().turn;
    return true;
}

}  // namespace gvg
