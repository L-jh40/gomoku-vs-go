# CODE_MAP - 代码地图与编辑指南

本文用于人工和 AI 快速定位代码：哪个文件、哪个区域、实现什么功能，以及修改某个功能时应该去改哪里。

---

## 1. 顶层入口

| 文件 | 作用 |
|------|------|
| `main.py` | 程序入口，支持 GUI 和 CLI |
| `gui.py` | tkinter 窗口界面、AI 搜索调度（工作进程）、计时、复盘、模式窗口、候选点显示 |
| `board.py` | 棋盘数据结构、规则相关的底层判断、候选点、评分、障碍物 |
| `rules.py` | 禁手判定与单方向威胁分类 |
| `ai_search.py` | AI 搜索核心：minimax、白棋防守、黑棋算法 A、复盘表 |
| `ai_black.py` | 黑棋 AI 对外接口 |
| `ai_white.py` | 白棋 AI 对外接口 |
| `ai_worker.py` | 常驻 AI 搜索工作进程（GUI 经多进程调度搜索，主窗口不卡） |
| `board_tools.py` | 棋盘文本导出/解析与分析 CLI（威胁、蓝叉、禁手地图、AI 着法） |
| `tests_torus.py` | 环面/禁手/GUI 自动化测试（`python tests_torus.py`） |
| `tests_text.py` | text.md 局面的自动化测试 |
| `AI_ALGORITHM.md` | 算法逻辑说明 |
| `README.md` | 使用说明 |
| `CODE_MAP.md` | 本文档 |

---

## 2. board.py - 棋盘与底层逻辑

### 主要常量
- `EMPTY / BLACK / WHITE / OBSTACLE`
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
| `HybridBoard.__init__ / copy` | 棋盘初始化、缓存复制（含 torus 标记） |
| `wrap / step_from` | 坐标归一化与"沿方向走 k 步"（环面时自动回绕） |
| `get_group / get_black_groups` | Go 气与连通块（气随环面回绕） |
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
| `is_black_legal_move` | 黑棋合法/禁手判断：五连优先→长连→两四（四四）→两真活三（三三）→白棋吃子可消除的不算禁手；按棋盘状态缓存 |
| `_windows_containing` | 枚举含该落点的 5 格线窗 |
| `_four_sets` | 四的集合（4 子 + 1 空成五），去重：活四计 1，一线两侧两个冲四计 2（四四） |
| `_three_sets` | 真活三集合：按 6 格窗匹配活三棋形（直 011100 / 跳 011010，眠三 10101 不算）；延伸点须紧邻该三、可落（非自吃/真禁手）且能形成四；一线两侧两个活三计 2（三三） |
| `_count_foul_shapes` | 统计四数与真活三数 |
| `_black_one_liberty_liberties` | 白棋一步可提的黑棋块（用于吃子阻挡判定） |
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
- 勾选框：黑棋 AI / 白棋 AI、棋盘样式（交叉点/格子，即时生效）、玩家落子提示、显示手数、显示AI候选点、取消投子认负
- 搜索设置：Minimax 层数（0~4）、最短搜索时间、最长搜索时间
- 黄色棋盘区顶部统计条：黑棋时间/AI/人类（靠棋盘左缘三行）、白吃黑 N子（垂直居中）、白棋时间/AI/人类（靠棋盘右缘三行）；微软雅黑UI字体 9路≈9pt → 15路起封顶20pt，与棋盘间隔一行。AI 行=自动AI搜索思考时间（蓝字口径）累计；人类行=人类落子用时（含右键AI辅助）；同方人类+AI≈该方总用时
- 蓝/绿小字：AI回合显示搜索进度/上一步AI用时；人类回合蓝字=本步正在用时、绿字=上一手人类用时
- 模式窗口：棋盘尺寸（9~19 奇数，新对局生效）、先手、禁手设置、白棋获胜条件、环面模式（新对局生效）、障碍
- 环面模式：上下/左右互通（气、连五、禁手、领地、距离全部回绕，AI 只搜索实际 n×n 棋盘）
- 环面提示（主面板复选框）：开启后四周显示镜面复制区，宽度可选 2 格（n+4）或 4 格（n+8），关闭则只显示 n×n；复制区背景统一用第一圈色、网格线统一 50% 白、假棋子=50%棋子色+50%棋盘底色，实际棋盘四周只有一条 #f2f2f2 粗镜框；鼠标在复制区时幽灵棋子只显示在实际对应格；点击复制格映射到实际格落子
- 棋盘尺寸自适应：读取窗口/屏幕大小，优先完整显示棋盘；棋盘放不下时按比例缩小格子（最多缩小 50%，最小 15px），随后再按剩余空间选顶部字号；若顶部放不下，时间/吃子自动改到棋盘旁边（右侧面板）显示

### 功能函数

| 函数 | 作用 |
|------|------|
| `new_game` | 按模式设置开新局（含所选棋盘尺寸） |
| `open_mode_window` | 选择模式窗口 |
| `run_ai_move` | 向 AI 工作进程提交搜索任务（立即返回，不阻塞界面） |
| `_ensure_worker / _shutdown_worker / _poll_worker` | AI 工作进程的启动/关闭与结果队列轮询 |
| `_sync_worker_epoch / _abort_active_search / _stop_search` | 跨进程中断：纪元计数器同步、“AI 立即落子”中断、废弃搜索 |
| `_worker_progress / _handle_worker_done / _finish_finished_search` | 工作进程进度回传与搜索结果落子 |
| `_handle_replay_done` | 复盘模式下工作进程算出的黑棋应手 |
| `progress_callback` | AI 进度回传 |
| `apply` | AI 结果应用与落子 |
| `draw_board / draw_hints / _draw_hover / _draw_top_band` | 棋盘、悬停落点提示与顶部统计绘制 |
| `_grid_extent / _update_origin / _point_center` | 棋盘像素范围、居中原点、逻辑坐标→画布坐标（区分交叉点/格子样式） |
| `_on_size_check / _selected_board_size` | 棋盘尺寸复选框互斥与读取 |
| `_on_style_point / _on_style_cell` | 棋盘样式复选框互斥与即时切换 |
| `_apply_canvas_size` | 尺寸变化时重设画布/侧栏大小与窗口标题 |
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

### 修改棋盘尺寸 / 样式 / 居中
- `gui.py` → `BOARD_SIZES` / `STAR_POINTS`（支持尺寸与各尺寸星位）
- `gui.py` → `_grid_extent` / `_update_origin` / `_point_center`（绘制原点与坐标换算）
- `gui.py` → `open_mode_window`（尺寸、样式复选框）
- `gui.py` → `new_game`（尺寸在新对局时生效）

### 修改候选点绿色显示
- `gui.py` → `_draw_candidate_squares`
- `gui.py` → `_get_candidate_display_positions`

---

## 7. 数据流简介

```text
GUI 点击/自动触发
    ↓
run_ai_move()  ──job_queue──▶  ai_worker 工作进程（搜索不占 GUI 进程的 GIL）
    ↓                                ↓
（界面保持流畅，_poll_worker 轮询）   result_queue（progress / done 消息）
    ↓
gui._handle_worker_done → 落子 / 弹窗 / 复盘应手
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
