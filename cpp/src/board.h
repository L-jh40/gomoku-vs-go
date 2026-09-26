// board.h - 五子棋(黑) vs 围棋(白)混合规则棋盘。
//
// 坐标约定与 Python 引擎保持一致：x = 行(0 起，自上而下)，y = 列(0 起，自左而右)。
// 格子取值：0=空, 1=黑, 2=白, 3=障碍(墙)。
//
// 本类负责“棋盘状态 + 落子/悔棋 + 增量评估计数器”，不含任何搜索。设计要点：
//  * 固定上限 19x19 的 uint8 数组，make_move/undo_move 不做整盘拷贝。
//  * 历史栈预分配，热路径无堆分配（所有临时数组都是栈上的定长数组）。
//  * liberties 只扫描受落子影响的相邻棋块，不做整盘 flood fill。
//  * Zobrist 哈希包含：棋子(黑/白)、障碍布局、轮到谁走；make/undo O(1) 增量更新。
//  * 评估计数器（线型六类计数 / 领地 / 风险）随 make_move 增量维护，
//    undo_move 精确还原（全局计数从 HistoryEntry O(1) 取回，逐格缓存重建）。
#pragma once

#include <cstdint>
#include <cstddef>

namespace gvg {

constexpr int MAX_BOARD  = 19;
constexpr int MAX_CELLS  = MAX_BOARD * MAX_BOARD;
// 每个方向的线 id 空间：行/列 size 条，(1,1)/(1,-1) 各 2*size-1 条。
constexpr int MAX_LINES  = 2 * MAX_BOARD;
// 六类线型计数：open_four/rush_four/open_three/sleep_three/open_two/sleep_two。
constexpr int NUM_EVAL_CLASSES = 6;
// 一条线在某个起点命中多个模式时按“位置 × 类别”只计一次，用位掩码表达。
constexpr int MAX_LINE_POS = MAX_BOARD;

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
    // 摆完后全盘重算所有评估计数器（非热路径）。
    void set_cell(int x, int y, uint8_t value);
    // 供禁手判定使用的“临时落子”：只改数组、不动哈希/历史/计数器，
    // 调用方负责还原（禁止在临时改动期间读取评估计数器）。
    void set_cell_raw(int x, int y, uint8_t value) {
        if (in_bounds(x, y)) cells_[index(x, y)] = value;
    }

    // 执行一步。黑棋：拒绝自杀(无气)、永不提白；白棋：提走所有无气的黑棋块。
    // 返回是否成功。成功时会切换回合并压入历史，同时增量更新评估计数器。
    bool make_move(int x, int y, int color);
    // 悔一步，完整还原被提子与回合，并把评估计数器精确还原。返回是否成功。
    bool undo_move();

    int turn() const { return turn_; }
    int move_count() const { return move_count_; }
    uint64_t hash() const { return hash_; }

    // 空点：若黑棋落在此处会立刻无气（自杀）。障碍/白子/棋盘外/已成子处返回 false。
    bool is_dead_empty(int x, int y) const;
    // (x,y) 所在的棋块是否有至少一口气（用于黑棋自杀检测）。非黑子返回 false。
    bool black_group_has_liberty(int x, int y) const;

    // ---- 评估计数器只读接口 ----
    // 六类线型计数（黑/白分开），下标 0..5 依次为
    // open_four/rush_four/open_three/sleep_three/open_two/sleep_two。
    const int32_t* black_counts() const { return black_cnt_; }
    const int32_t* white_counts() const { return white_cnt_; }
    // 黑棋风险：Σ over 黑棋块 [气数==1]*4 + [气数==2]*1。
    int32_t risk() const { return risk_; }
    // 领地/死格计数（黑棋视角的“白方领地”）：死格 = 无白子自由五连窗的
    // 空/黑格 ∪ 无气空点（与 Python get_dead_positions 一致）。
    int32_t territory() const { return territory_; }
    // 全盘重算所有评估计数器（reset/clear/set_cell 调用）。
    void recompute_all_counters();

private:
    struct HistoryEntry {
        uint16_t pos;        // index(x, y)
        uint8_t  color;      // 落子方
        uint16_t cap_begin;  // captured_pool_ 中本步被提子的起点
        uint16_t cap_count;  // 被提子数
        int32_t  old_black[NUM_EVAL_CLASSES];  // 本步前的黑线型全局计数
        int32_t  old_white[NUM_EVAL_CLASSES];  // 本步前的白线型全局计数
        int16_t  old_line[4][2][NUM_EVAL_CLASSES];  // 本步前四方向线的缓存计数
        int32_t  old_territory;
        int32_t  old_risk;
    };

    // ---- 线 / 窗口几何 ----
    static void dir_vec(int d, int& dx, int& dy);
    int  line_id(int d, int x, int y) const;
    void line_through(int d, int x, int y, int& sx, int& sy, int& len, int& k) const;
    bool window_blocked(int x0, int y0, int dx, int dy) const;

    // ---- 增量维护辅助 ----
    void compute_wins_total();
    void rebuild_cell_caches();
    void count_line_both(int d, int sx, int sy, int len, int* outB, int* outW) const;
    void eval_update_after_move(int pos, int color, HistoryEntry& h,
                                const uint16_t* captured, int ncap,
                                const uint16_t* riskCells, int rn,
                                int risk_before);
    int  risk_of_cells(const uint16_t* cells, int n) const;
    int  risk_full() const;
    // 预判白棋落子 (x,y) 会提走哪些黑子（不改动棋盘）。
    int  predict_captures(int x, int y, uint16_t* out) const;

    int  dead_cell(int idx) const;
    bool relevant_black(int idx) const;

    // 去重用的 touch 标记。
    void touch_begin();
    void touch_push(uint16_t* list, int& n, int idx);

    uint8_t  cells_[MAX_CELLS];
    int      size_        = 15;
    int      turn_        = BLACK;
    int      move_count_  = 0;
    uint64_t hash_        = 0;
    HistoryEntry history_[MAX_CELLS + 1];
    uint16_t captured_pool_[MAX_CELLS];  // 沿当前历史链被提走的所有黑子
    int      captured_top_ = 0;

    // ---- 评估计数器 ----
    // 每条线（4 方向 × line_id）缓存的黑/白六类计数，用于差量重算。
    int16_t  line_cnt_[4][MAX_LINES][2][NUM_EVAL_CLASSES];
    int32_t  black_cnt_[NUM_EVAL_CLASSES];
    int32_t  white_cnt_[NUM_EVAL_CLASSES];
    // 每格经过的盘内五连窗总数 / 含白子或障碍的窗数。
    uint8_t  wins_total_[MAX_CELLS];
    uint8_t  wins_blocked_[MAX_CELLS];
    // 每个窗口的 blocked 标志（含白子或障碍）。
    uint8_t  win_blocked_[4][MAX_LINES][MAX_LINE_POS];
    // 每格的无气自杀标志（仅对空点有意义）。
    uint8_t  self_cap_[MAX_CELLS];
    // 每格的死格标志（territory_ == Σ dead_）。
    uint8_t  dead_[MAX_CELLS];
    int32_t  territory_ = 0;
    int32_t  risk_      = 0;

    // 组件 / 气 去重时间戳（避免每次 BFS 都 memset）。
    mutable uint32_t comp_stamp_[MAX_CELLS];
    mutable uint32_t comp_gen_ = 0;
    mutable uint32_t lib_stamp_[MAX_CELLS];
    mutable uint32_t lib_gen_ = 0;
    uint32_t touch_stamp_[MAX_CELLS];
    uint32_t touch_gen_ = 0;
};

}  // namespace gvg
