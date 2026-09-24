// board.h - 五子棋(黑) vs 围棋(白)混合规则棋盘。
//
// 坐标约定与 Python 引擎保持一致：x = 行(0 起，自上而下)，y = 列(0 起，自左而右)。
// 格子取值：0=空, 1=黑, 2=白, 3=障碍(墙)。
//
// 本类只负责“棋盘状态 + 落子/悔棋”，不含任何搜索/评估。设计要点：
//  * 固定上限 19x19 的 uint8 数组，make_move/undo_move 不做整盘拷贝。
//  * 历史栈预分配，热路径无堆分配（所有临时数组都是栈上的定长数组）。
//  * liberties 只扫描受落子影响的相邻棋块，不做整盘 flood fill。
//  * Zobrist 哈希包含：棋子(黑/白)、障碍布局、轮到谁走；make/undo O(1) 增量更新。
#pragma once

#include <cstdint>
#include <cstddef>

namespace gvg {

constexpr int MAX_BOARD = 19;
constexpr int MAX_CELLS = MAX_BOARD * MAX_BOARD;

// 格子取值（与 Python board.py 完全一致）。
enum Cell : uint8_t {
    EMPTY    = 0,
    BLACK    = 1,
    WHITE    = 2,
    OBSTACLE = 3,
};

class Board {
public:
    explicit Board(int size = 15);

    // 重置为 size x size 空盘（size 会被规整到 9..19 的奇数），turn = 黑。
    void reset(int size);
    // 保留尺寸，清空全部格子与历史。
    void clear();

    int size() const { return size_; }
    bool in_bounds(int x, int y) const {
        return static_cast<unsigned>(x) < static_cast<unsigned>(size_) &&
               static_cast<unsigned>(y) < static_cast<unsigned>(size_);
    }
    static int index(int x, int y) { return x * MAX_BOARD + y; }

    // 越界按“墙”处理（返回 OBSTACLE），方便禁手判定把棋盘外等同障碍。
    uint8_t at(int x, int y) const {
        return in_bounds(x, y) ? cells_[index(x, y)] : static_cast<uint8_t>(OBSTACLE);
    }
    bool is_empty(int x, int y) const {
        return in_bounds(x, y) && cells_[index(x, y)] == EMPTY;
    }

    // 直接摆放一个格子（摆局面 / 布置障碍），不做提子、不切换回合并增量更新哈希。
    void set_cell(int x, int y, uint8_t value);
    // 供禁手判定使用的“临时落子”：只改数组、不动哈希/历史，调用方负责还原。
    void set_cell_raw(int x, int y, uint8_t value) {
        if (in_bounds(x, y)) cells_[index(x, y)] = value;
    }

    // 执行一步。黑棋：拒绝自杀(无气)、永不提白；白棋：提走所有无气的黑棋块。
    // 返回是否成功。成功时会切换回合并压入历史。
    bool make_move(int x, int y, int color);
    // 悔一步，完整还原被提子与回合。返回是否成功。
    bool undo_move();

    int turn() const { return turn_; }
    int move_count() const { return move_count_; }
    uint64_t hash() const { return hash_; }

    // 空点：若黑棋落在此处会立刻无气（自杀）。障碍/白子/棋盘外/已成子处返回 false。
    bool is_dead_empty(int x, int y) const;
    // (x,y) 所在的棋块是否有至少一口气（用于黑棋自杀检测）。非黑子返回 false。
    bool black_group_has_liberty(int x, int y) const;

private:
    struct HistoryEntry {
        uint16_t pos;        // index(x, y)
        uint8_t  color;      // 落子方
        uint16_t cap_begin;  // captured_pool_ 中本步被提子的起点
        uint16_t cap_count;  // 被提子数
    };

    uint8_t  cells_[MAX_CELLS];
    int      size_        = 15;
    int      turn_        = BLACK;
    int      move_count_  = 0;
    uint64_t hash_        = 0;
    HistoryEntry history_[MAX_CELLS + 1];
    uint16_t captured_pool_[MAX_CELLS];  // 沿当前历史链被提走的所有黑子
    int      captured_top_ = 0;
};

}  // namespace gvg
