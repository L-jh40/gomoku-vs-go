# CODE_MAP - 代码地图与编辑指南

本文用于人工和 AI 快速定位代码：哪个文件、哪个区域、实现什么功能，以及修改某个功能时应该去改哪里。

---

## 1. 顶层入口

| 文件 | 作用 |
|------|------|
| `main.py` | 程序入口，支持 GUI 和 CLI |
| `gui.py` | tkinter 窗口界面、AI 线程、计时、复盘、模式窗口、候选点显示 |
| `board.py` | 棋盘数据结构、规则相关的底层判断、候选点、评分 |
| `rules.py` | 禁手判定与单方向威胁分类 |
| `ai_search.py` | AI 搜索核心：minimax、白棋防守、黑棋算法 A、复盘表 |
| `ai_black.py` | 黑棋 AI 对外接口 |
| `ai_white.py` | 白棋 AI 对外接口 |
| `tests_text.py` | text.md 局面的自动化测试 |
| `AI_ALGORITHM.md` | 算法逻辑说明 |
| `README.md` | 使用说明 |
| `CODE_MAP.md` | 本文档 |

---

## 2. board.py - 棋盘与底层逻辑

### 主要常量
- `EMPTY / BLACK / WHITE`
- `DIRECTIONS`
- `THREAT_MARKER`
- `THREAT_SCORE`
- `HOLLOW_TRIANGLE_SCORE`
- `FORCED_THREAT_TYPES`
- `RED_LEVEL_GROUPS`
- `THREAT_N`
- `RED_LEVEL_RANK`

### 主要区域

| 函数/区域 | 实现内容 |
|-----------|----------|
| `HybridBoard.__init__ / copy` | 棋盘初始化、缓存复制 |
| `get_group / get_black_groups` | Go 气与连通块 |
| `play_black / play_white` | 落子、提子、禁手检查 |
| `check_black_five / check_black_overline` | 五连/长连 |
| `get_dead_positions` | 白棋领地计算 |
| `get_blue_cross_positions` | 禁手/无气蓝叉位置 |
| `get_black_candidate_moves / get_white_candidate_moves` | 原始搜索范围 |
| `get_black_priority_candidates / get_white_priority_candidates` | 无强制威胁时的优先级候选 |
| `get_white_defense_candidates` | 有强制威胁时的白棋防守候选 |
| `compute_threats` | 全局红色威胁分类 |
| `get_hollow_triangles` | 空心三角形判定 |
| `get_red_scores / get_threat_score` | 评分 |
| `compute_group_capture_loss / compute_group_score` | 黑棋块分数 |
| `evaluate_black_position` | 黑棋视角静态评估 |
| `farthest_open_positions` | 无红点时的距离选择 |
| `get_black_group_infos` | 黑棋块缓存信息 |

---

## 3. rules.py - 禁手与单线威胁

| 函数 | 作用 |
|------|------|
| `line_code` | 将一条线编码为 9 格字符串 |
| `match_line_threat` | 匹配活四/冲四/活三/眠三等 |
| `classify_direction_after_move` | 单方向威胁判定 |
| `classify_position_after_move` | 落子后的综合威胁类型 |
| `is_black_legal_move` | 黑棋合法/禁手判断 |
| `find_all_threats` | 兼容接口 |

修改红色位置类型时：
- 若只改单方向棋形，去 `PATTERNS` / `match_line_threat`；
- 若改综合类型，去 `classify_position_after_move`；
- 若改禁手，去 `is_black_legal_move`。

---

## 4. ai_search.py - AI 搜索核心

### 核心函数

| 函数 | 作用 |
|------|------|
| `_white_defense` | 白棋强制防守搜索 |
| `white_safe_move_set` | 白棋安全候选集合 |
| `_black_algorithm_a_candidates` | 黑棋算法 A 候选 |
| `black_algorithm_a` | 黑棋有三角形时的算法 A |
| `_moves_for_player` | minimax 中按规则生成候选 |
| `_alphabeta` | minimax + alpha-beta |
| `_best_root_move_at_depth` | 单层根节点搜索 |
| `_iterative_minimax` | 多层迭代加深 |
| `best_black_move_info / best_white_move_info` | 公共 AI 入口逻辑 |
| `_record_replay_move / _board_signature` | 复盘表生成与查表 |

修改搜索行为时主要去这里。

---

## 5. GUI - gui.py

### UI 区域
- 顶部按钮：新对局、选择模式、悔棋、Pass、AI 立即落子
- 勾选框：黑棋 AI / 白棋 AI、玩家落子提示、显示手数、显示候选点、取消投子认负
- 搜索设置：Minimax 层数、最短搜索时间、最长搜索时间
- 模式窗口：先手、禁手设置、预留接口
- 统计栏：黑白 AI/人类用时、吃子

### 功能函数

| 函数 | 作用 |
|------|------|
| `new_game` | 按模式设置开新局 |
| `open_mode_window` | 选择模式窗口 |
| `run_ai_move` | 启动 AI 搜索线程 |
| `progress_callback` | AI 进度回传 |
| `apply` | AI 结果应用与落子 |
| `draw_board / draw_hints` | 棋盘与提示绘制 |
| `_get_candidate_display_positions` | 候选点显示 |
| `_finish_turn_time / update_info` | 用时统计 |
| `play_replay_black` | 复盘黑棋应对 |
| `undo_move / human_pass` | 悔棋、Pass |

---

## 6. AI 与编辑常用入口速查

### 修改“实心圆/三角形/大圆圈等分值”
- `board.py` → `THREAT_SCORE`
- `board.py` → `HOLLOW_TRIANGLE_SCORE`
- 如果要改变空心三角形是否计入威胁，去 `compute_threats` 和 `get_hollow_triangles`

### 修改“白棋遇到强制威胁时的候选点”
- `board.py` → `get_white_defense_candidates`

### 修改“无强制威胁时的候选点”
- `board.py` → `get_black_priority_candidates`
- `board.py` → `get_white_priority_candidates`

### 修改“白棋强制防守搜索”
- `ai_search.py` → `_white_defense`

### 修改“黑棋三角形算法 A”
- `ai_search.py` → `black_algorithm_a`

### 修改 minimax 层数/时间
- `ai_search.py` → `_iterative_minimax`
- `gui.py` → `run_ai_move`
- `gui.py` → `max_search_time_var` / `min_search_time_var`

### 修改复盘表
- `ai_search.py` → `_record_replay_move`
- `ai_search.py` → `_board_signature`
- `gui.py` → `_choose_table_move`

### 修改距离算法
- `board.py` → `farthest_open_positions`

### 修改候选点绿色显示
- `gui.py` → `_draw_candidate_squares`
- `gui.py` → `_get_candidate_display_positions`

---

## 7. 数据流简介

```text
GUI 点击/自动触发
    ↓
run_ai_move()
    ↓
ai_black.best_black_move / ai_white.best_white_move
    ↓
ai_search.best_black_move_info / best_white_move_info
    ↓
compute_threats()
候选点生成
    ↓
白棋强制防守 / 黑棋算法 A / minimax
    ↓
返回落子
    ↓
GUI play_black/play_white
    ↓
draw_board / update_info
```

修改一个功能前，先根据本文档找到对应函数，再判断是否会影响其他层。
