// board.cpp - Board 实现（棋盘、提子、悔棋、Zobrist、增量评估计数器）。
#include "board.h"

#include "pattern_count.h"

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

// 正交方向（提子 / 气 / 自杀检测）。
const int DX4[4] = {-1, 1, 0, 0};
const int DY4[4] = {0, 0, -1, 1};

// 评估用的四条线方向，与 Python DIRECTIONS 一致：(1,0),(0,1),(1,1),(1,-1)。
const int EDX[4] = {1, 0, 1, 1};
const int EDY[4] = {0, 1, 1, -1};

}  // namespace

// ===========================================================================
// 几何辅助
// ===========================================================================

void Board::dir_vec(int d, int& dx, int& dy) {
    dx = EDX[d];
    dy = EDY[d];
}

int Board::line_id(int d, int x, int y) const {
    switch (d) {
        case 0: return y;                                   // 竖线 (1,0)
        case 1: return x;                                   // 横线 (0,1)
        case 2: return x - y + (MAX_BOARD - 1);             // 主对角 (1,1)
        default: return x + y;                              // 副对角 (1,-1)
    }
}

void Board::line_through(int d, int x, int y, int& sx, int& sy, int& len,
                         int& k) const {
    const int dx = EDX[d], dy = EDY[d];
    int bx = x, by = y, back = 0;
    while (in_bounds(bx - dx, by - dy)) { bx -= dx; by -= dy; ++back; }
    int n = 0, cx = bx, cy = by;
    while (in_bounds(cx, cy)) { ++n; cx += dx; cy += dy; }
    sx = bx; sy = by; len = n; k = back;
}

bool Board::window_blocked(int x0, int y0, int dx, int dy) const {
    for (int i = 0; i < 5; ++i) {
        const uint8_t v = cells_[index(x0 + i * dx, y0 + i * dy)];
        if (v == WHITE || v == OBSTACLE) return true;
    }
    return false;
}

void Board::count_line_both(int d, int sx, int sy, int len, int* outB,
                            int* outW) const {
    char bufB[MAX_BOARD];
    char bufW[MAX_BOARD];
    const int dx = EDX[d], dy = EDY[d];
    int cx = sx, cy = sy;
    for (int i = 0; i < len; ++i) {
        const uint8_t v = cells_[index(cx, cy)];
        bufB[i] = (v == BLACK) ? '1' : (v == EMPTY) ? '0' : '2';
        bufW[i] = (v == WHITE) ? '1' : (v == EMPTY) ? '0' : '2';
        cx += dx; cy += dy;
    }
    count_line_chars(bufB, len, outB);
    count_line_chars(bufW, len, outW);
}

// ===========================================================================
// 评估计数器的全盘重算（摆局面 / 悔棋缓存重建，非热路径）
// ===========================================================================

void Board::compute_wins_total() {
    std::memset(wins_total_, 0, sizeof(wins_total_));
    for (int d = 0; d < 4; ++d) {
        const int dx = EDX[d], dy = EDY[d];
        for (int x = 0; x < size_; ++x) {
            for (int y = 0; y < size_; ++y) {
                if (in_bounds(x - dx, y - dy)) continue;  // 不是线的起点
                int len = 0, cx = x, cy = y;
                while (in_bounds(cx, cy)) { ++len; cx += dx; cy += dy; }
                for (int s = 0; s + 5 <= len; ++s) {
                    for (int i = 0; i < 5; ++i) {
                        ++wins_total_[index(x + (s + i) * dx, y + (s + i) * dy)];
                    }
                }
            }
        }
    }
}

void Board::rebuild_cell_caches() {
    std::memset(wins_blocked_, 0, sizeof(wins_blocked_));
    std::memset(win_blocked_, 0, sizeof(win_blocked_));
    std::memset(self_cap_, 0, sizeof(self_cap_));
    std::memset(dead_, 0, sizeof(dead_));

    for (int d = 0; d < 4; ++d) {
        const int dx = EDX[d], dy = EDY[d];
        for (int x = 0; x < size_; ++x) {
            for (int y = 0; y < size_; ++y) {
                if (in_bounds(x - dx, y - dy)) continue;
                int len = 0, cx = x, cy = y;
                while (in_bounds(cx, cy)) { ++len; cx += dx; cy += dy; }
                const int id = line_id(d, x, y);
                for (int s = 0; s + 5 <= len; ++s) {
                    if (window_blocked(x + s * dx, y + s * dy, dx, dy)) {
                        win_blocked_[d][id][s] = 1;
                        for (int i = 0; i < 5; ++i) {
                            ++wins_blocked_[index(x + (s + i) * dx, y + (s + i) * dy)];
                        }
                    }
                }
            }
        }
    }

    for (int x = 0; x < size_; ++x) {
        for (int y = 0; y < size_; ++y) {
            const int idx = index(x, y);
            if (cells_[idx] == EMPTY && is_dead_empty(x, y)) self_cap_[idx] = 1;
        }
    }
    for (int x = 0; x < size_; ++x) {
        for (int y = 0; y < size_; ++y) {
            const int idx = index(x, y);
            dead_[idx] = dead_cell(idx) ? 1 : 0;
        }
    }
}

int Board::risk_full() const {
    uint16_t all[MAX_CELLS];
    int n = 0;
    for (int x = 0; x < size_; ++x)
        for (int y = 0; y < size_; ++y) all[n++] = static_cast<uint16_t>(index(x, y));
    return risk_of_cells(all, n);
}

void Board::recompute_all_counters() {
    compute_wins_total();

    std::memset(black_cnt_, 0, sizeof(black_cnt_));
    std::memset(white_cnt_, 0, sizeof(white_cnt_));
    std::memset(line_cnt_, 0, sizeof(line_cnt_));

    int outB[NUM_EVAL_CLASSES], outW[NUM_EVAL_CLASSES];
    for (int d = 0; d < 4; ++d) {
        const int dx = EDX[d], dy = EDY[d];
        for (int x = 0; x < size_; ++x) {
            for (int y = 0; y < size_; ++y) {
                if (in_bounds(x - dx, y - dy)) continue;
                int len = 0, cx = x, cy = y;
                while (in_bounds(cx, cy)) { ++len; cx += dx; cy += dy; }
                count_line_both(d, x, y, len, outB, outW);
                const int id = line_id(d, x, y);
                for (int c = 0; c < NUM_EVAL_CLASSES; ++c) {
                    line_cnt_[d][id][0][c] = static_cast<int16_t>(outB[c]);
                    line_cnt_[d][id][1][c] = static_cast<int16_t>(outW[c]);
                    black_cnt_[c] += outB[c];
                    white_cnt_[c] += outW[c];
                }
            }
        }
    }

    rebuild_cell_caches();

    territory_ = 0;
    for (int x = 0; x < size_; ++x)
        for (int y = 0; y < size_; ++y) territory_ += dead_[index(x, y)];

    risk_ = risk_full();
}

// ===========================================================================
// 死格 / 风险辅助
// ===========================================================================

bool Board::relevant_black(int idx) const {
    const int x = idx / MAX_BOARD, y = idx % MAX_BOARD;
    for (int d = 0; d < 4; ++d) {
        const int dx = EDX[d], dy = EDY[d];
        for (int k = -4; k <= 4; ++k) {
            if (k == 0) continue;
            const int nx = x + k * dx, ny = y + k * dy;
            if (in_bounds(nx, ny) && cells_[index(nx, ny)] == BLACK) return true;
        }
    }
    return false;
}

int Board::dead_cell(int idx) const {
    const uint8_t v = cells_[idx];
    if (v == WHITE || v == OBSTACLE) return 0;
    const bool alive = wins_total_[idx] != wins_blocked_[idx];
    if (v == BLACK) return alive ? 0 : 1;
    // EMPTY：无白子自由五连窗，或“无气空点且受黑棋影响（后者与 Python
    // get_dead_positions 的 relevant_empty_positions 修正一致）”。
    if (!alive) return 1;
    if (self_cap_[idx] && relevant_black(idx)) return 1;
    return 0;
}

int Board::risk_of_cells(const uint16_t* cells, int n) const {
    ++comp_gen_;
    if (comp_gen_ == 0) { std::memset(comp_stamp_, 0, sizeof(comp_stamp_)); comp_gen_ = 1; }
    int total = 0;
    int stack[MAX_CELLS];
    for (int i = 0; i < n; ++i) {
        const int s = cells[i];
        if (cells_[s] != BLACK || comp_stamp_[s] == comp_gen_) continue;
        int top = 0;
        stack[top++] = s;
        comp_stamp_[s] = comp_gen_;
        ++lib_gen_;
        if (lib_gen_ == 0) { std::memset(lib_stamp_, 0, sizeof(lib_stamp_)); lib_gen_ = 1; }
        int libs = 0;
        for (int q = 0; q < top; ++q) {
            const int cur = stack[q];
            const int cx = cur / MAX_BOARD, cy = cur % MAX_BOARD;
            for (int k = 0; k < 4; ++k) {
                const int nx = cx + DX4[k], ny = cy + DY4[k];
                if (!in_bounds(nx, ny)) continue;
                const int ni = index(nx, ny);
                const uint8_t v = cells_[ni];
                if (v == EMPTY) {
                    if (lib_stamp_[ni] != lib_gen_) { lib_stamp_[ni] = lib_gen_; ++libs; }
                } else if (v == BLACK && comp_stamp_[ni] != comp_gen_) {
                    comp_stamp_[ni] = comp_gen_;
                    stack[top++] = ni;
                }
            }
        }
        if (libs == 1) total += 4;
        else if (libs == 2) total += 1;
    }
    return total;
}

int Board::predict_captures(int x, int y, uint16_t* out) const {
    uint8_t seen[MAX_CELLS];
    std::memset(seen, 0, sizeof(seen));
    int stack[MAX_CELLS];
    int n = 0;
    const int pidx = index(x, y);
    for (int k = 0; k < 4; ++k) {
        const int nx = x + DX4[k], ny = y + DY4[k];
        if (!in_bounds(nx, ny)) continue;
        const int ni = index(nx, ny);
        if (cells_[ni] != BLACK || seen[ni]) continue;
        int top = 0;
        stack[top++] = ni;
        seen[ni] = 1;
        bool other_lib = false;
        for (int q = 0; q < top; ++q) {
            const int cur = stack[q];
            const int cx = cur / MAX_BOARD, cy = cur % MAX_BOARD;
            for (int kk = 0; kk < 4; ++kk) {
                const int ax = cx + DX4[kk], ay = cy + DY4[kk];
                if (!in_bounds(ax, ay)) continue;
                const int ai = index(ax, ay);
                const uint8_t av = cells_[ai];
                if (av == EMPTY) {
                    if (ai != pidx) other_lib = true;
                } else if (av == BLACK && !seen[ai]) {
                    seen[ai] = 1;
                    stack[top++] = ai;
                }
            }
        }
        if (!other_lib) {
            for (int i = 0; i < top; ++i) out[n++] = static_cast<uint16_t>(stack[i]);
        }
    }
    return n;
}

void Board::touch_begin() {
    ++touch_gen_;
    if (touch_gen_ == 0) { std::memset(touch_stamp_, 0, sizeof(touch_stamp_)); touch_gen_ = 1; }
}

void Board::touch_push(uint16_t* list, int& n, int idx) {
    if (touch_stamp_[idx] != touch_gen_) {
        touch_stamp_[idx] = touch_gen_;
        list[n++] = static_cast<uint16_t>(idx);
    }
}

// ===========================================================================
// 增量更新：落子后调用，差量维护全部评估计数器
// ===========================================================================

void Board::eval_update_after_move(int pos, int color, HistoryEntry& h,
                                   const uint16_t* captured, int ncap,
                                   const uint16_t* riskCells, int rn,
                                   int risk_before) {
    const int x = pos / MAX_BOARD, y = pos % MAX_BOARD;
    (void)color;

    // (0) 保存旧全局值，供 undo O(1) 还原。
    for (int c = 0; c < NUM_EVAL_CLASSES; ++c) {
        h.old_black[c] = black_cnt_[c];
        h.old_white[c] = white_cnt_[c];
    }
    h.old_territory = territory_;
    h.old_risk      = risk_;

    // (1) 经过落子点的 4 条线：只重算这 4 条并把差量加进全局计数器。
    for (int d = 0; d < 4; ++d) {
        int sx, sy, len, k;
        line_through(d, x, y, sx, sy, len, k);
        const int id = line_id(d, sx, sy);
        int newB[NUM_EVAL_CLASSES], newW[NUM_EVAL_CLASSES];
        count_line_both(d, sx, sy, len, newB, newW);
        for (int c = 0; c < NUM_EVAL_CLASSES; ++c) {
            h.old_line[d][0][c] = line_cnt_[d][id][0][c];
            h.old_line[d][1][c] = line_cnt_[d][id][1][c];
            black_cnt_[c] += newB[c] - line_cnt_[d][id][0][c];
            white_cnt_[c] += newW[c] - line_cnt_[d][id][1][c];
            line_cnt_[d][id][0][c] = static_cast<int16_t>(newB[c]);
            line_cnt_[d][id][1][c] = static_cast<int16_t>(newW[c]);
        }
    }

    // (2) 领地：受影响的窗口 blocked 标志差量 + 受影响格的死格重算。
    touch_begin();
    uint16_t tlist[MAX_CELLS];
    int tn = 0;

    // 2a. 经过落子点的所有盘内五连窗；blocked 标志翻转时更新窗内 5 格。
    for (int d = 0; d < 4; ++d) {
        int sx, sy, len, k;
        line_through(d, x, y, sx, sy, len, k);
        if (len < 5) continue;
        const int id = line_id(d, sx, sy);
        int s0 = k - 4; if (s0 < 0) s0 = 0;
        int s1 = k;     if (s1 > len - 5) s1 = len - 5;
        for (int s = s0; s <= s1; ++s) {
            const int x0 = sx + s * EDX[d], y0 = sy + s * EDY[d];
            const bool nb = window_blocked(x0, y0, EDX[d], EDY[d]);
            if (nb != (win_blocked_[d][id][s] != 0)) {
                win_blocked_[d][id][s] = nb ? 1 : 0;
                for (int i = 0; i < 5; ++i) {
                    const int ci = index(x0 + i * EDX[d], y0 + i * EDY[d]);
                    if (nb) ++wins_blocked_[ci]; else --wins_blocked_[ci];
                }
            }
            for (int i = 0; i < 5; ++i) {
                touch_push(tlist, tn, index(x0 + i * EDX[d], y0 + i * EDY[d]));
            }
        }
    }

    // 2b. 落子点及其正交邻域。
    touch_push(tlist, tn, pos);
    for (int k = 0; k < 4; ++k) {
        const int nx = x + DX4[k], ny = y + DY4[k];
        if (in_bounds(nx, ny)) touch_push(tlist, tn, index(nx, ny));
    }

    // 2c. 提子及其邻域 / 线邻域（relevant 可能变化）。
    for (int i = 0; i < ncap; ++i) {
        const int c = captured[i];
        touch_push(tlist, tn, c);
        const int cx = c / MAX_BOARD, cy = c % MAX_BOARD;
        for (int k = 0; k < 4; ++k) {
            const int nx = cx + DX4[k], ny = cy + DY4[k];
            if (in_bounds(nx, ny)) touch_push(tlist, tn, index(nx, ny));
        }
        for (int d = 0; d < 4; ++d) {
            for (int k = -4; k <= 4; ++k) {
                if (k == 0) continue;
                const int nx = cx + k * EDX[d], ny = cy + k * EDY[d];
                if (in_bounds(nx, ny)) touch_push(tlist, tn, index(nx, ny));
            }
        }
    }

    // 2d. 落子点的线邻域（relevant 可能变化）。
    for (int d = 0; d < 4; ++d) {
        for (int k = -4; k <= 4; ++k) {
            if (k == 0) continue;
            const int nx = x + k * EDX[d], ny = y + k * EDY[d];
            if (in_bounds(nx, ny)) touch_push(tlist, tn, index(nx, ny));
        }
    }

    // 2e. 受落子/提子影响的棋块：把它们的空邻点也纳入（气数变化会影响
    //     这些空点的无气自杀状态，进而影响死格）。
    ++comp_gen_;
    if (comp_gen_ == 0) { std::memset(comp_stamp_, 0, sizeof(comp_stamp_)); comp_gen_ = 1; }
    {
        int stack[MAX_CELLS];
        for (int i = 0; i < rn; ++i) {
            const int s = riskCells[i];
            if (cells_[s] != BLACK || comp_stamp_[s] == comp_gen_) continue;
            int top = 0;
            stack[top++] = s;
            comp_stamp_[s] = comp_gen_;
            for (int q = 0; q < top; ++q) {
                const int cur = stack[q];
                const int cx = cur / MAX_BOARD, cy = cur % MAX_BOARD;
                for (int k = 0; k < 4; ++k) {
                    const int nx = cx + DX4[k], ny = cy + DY4[k];
                    if (!in_bounds(nx, ny)) continue;
                    const int ni = index(nx, ny);
                    if (cells_[ni] == EMPTY) {
                        touch_push(tlist, tn, ni);
                    } else if (cells_[ni] == BLACK && comp_stamp_[ni] != comp_gen_) {
                        comp_stamp_[ni] = comp_gen_;
                        stack[top++] = ni;
                    }
                }
            }
        }
    }

    // (3) 无气空点标志：只对候选集合重算。
    for (int i = 0; i < tn; ++i) {
        const int ci = tlist[i];
        if (cells_[ci] == EMPTY)
            self_cap_[ci] = is_dead_empty(ci / MAX_BOARD, ci % MAX_BOARD) ? 1 : 0;
        else
            self_cap_[ci] = 0;
    }

    // (4) 死格标志差量 -> territory_。
    for (int i = 0; i < tn; ++i) {
        const int ci = tlist[i];
        const int nd = dead_cell(ci);
        territory_ += nd - static_cast<int>(dead_[ci]);
        dead_[ci] = static_cast<uint8_t>(nd);
    }

    // (5) 风险：受影响棋块的贡献差量（同一坐标区域上取落子前后）。
    const int risk_after = risk_of_cells(riskCells, rn);
    risk_ += risk_after - risk_before;
}

// ===========================================================================
// 生命周期
// ===========================================================================

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
    recompute_all_counters();
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
    recompute_all_counters();
}

// ===========================================================================
// 落子 / 悔棋
// ===========================================================================

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

    // ---- 评估预计算：预判提子并取“受影响棋块”的坐标区域 ----
    uint16_t predCap[MAX_CELLS];
    int predN = 0;
    if (color == WHITE) predN = predict_captures(x, y, predCap);

    uint16_t riskCells[5 * MAX_CELLS + 8];
    int rn = 0;
    riskCells[rn++] = static_cast<uint16_t>(idx);
    for (int k = 0; k < 4; ++k) {
        const int nx = x + DX4[k], ny = y + DY4[k];
        if (in_bounds(nx, ny)) riskCells[rn++] = static_cast<uint16_t>(index(nx, ny));
    }
    for (int i = 0; i < predN; ++i) {
        const int c = predCap[i];
        riskCells[rn++] = static_cast<uint16_t>(c);
        const int cx = c / MAX_BOARD, cy = c % MAX_BOARD;
        for (int k = 0; k < 4; ++k) {
            const int nx = cx + DX4[k], ny = cy + DY4[k];
            if (in_bounds(nx, ny)) riskCells[rn++] = static_cast<uint16_t>(index(nx, ny));
        }
    }
    const int risk_before = risk_of_cells(riskCells, rn);

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

    // ---- 增量维护评估计数器 ----
    HistoryEntry& h = history_[move_count_ - 1];
    eval_update_after_move(idx, color, h, captured_pool_ + h.cap_begin,
                           h.cap_count, riskCells, rn, risk_before);

    turn_ = (color == BLACK) ? WHITE : BLACK;
    hash_ ^= zob().turn;  // turn 键参与哈希
    return true;
}

bool Board::undo_move() {
    if (move_count_ <= 0) return false;
    const HistoryEntry& h = history_[--move_count_];

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

    // ---- 评估计数器还原 ----
    // 全局线型计数与每条线缓存从历史 O(1) 取回。
    for (int c = 0; c < NUM_EVAL_CLASSES; ++c) {
        black_cnt_[c] = h.old_black[c];
        white_cnt_[c] = h.old_white[c];
    }
    const int x = h.pos / MAX_BOARD, y = h.pos % MAX_BOARD;
    for (int d = 0; d < 4; ++d) {
        int sx, sy, len, k;
        line_through(d, x, y, sx, sy, len, k);
        const int id = line_id(d, sx, sy);
        for (int c = 0; c < NUM_EVAL_CLASSES; ++c) {
            line_cnt_[d][id][0][c] = h.old_line[d][0][c];
            line_cnt_[d][id][1][c] = h.old_line[d][1][c];
        }
    }
    territory_ = h.old_territory;
    risk_      = h.old_risk;
    // 逐格缓存（窗口 blocked / 无气 / 死格）按其定义精确重建。
    rebuild_cell_caches();
    return true;
}

}  // namespace gvg
