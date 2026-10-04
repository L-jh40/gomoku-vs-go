# CODE_MAP - 代码地图与编辑指南

本文用于人工和 AI 快速定位代码：哪个文件、哪个区域、实现什么功能，以及修改某个功能时应该去改哪里。

---

## 1. 顶层入口

| 文件 | 作用 |
|------|------|
| `main.py` | 程序入口，支持 GUI 和 CLI |
| `gui.py` | tkinter 窗口界面、AI 搜索调度（工作进程）、计时、复盘、模式窗口、候选点显示 |
| `board.py` | 棋盘数据结构、规则相关的底层判断、候选点、评分、障碍物 |
| `cpp/src/pattern_table.h/.cpp` | Rapfi 棋型 DP 查表（黑/白两套规则，禁手与棋型缓存共用） |
| `cpp/src/forbidden.h/.cpp` | Rapfi checkForbiddenPoint 忠实移植（增量棋型缓存 O(1) 预筛 + 假禁手延伸点递归） |
| `rules.py` | 禁手判定与单方向威胁分类 |
| `ai_search.py` | AI 搜索核心：minimax、白棋防守、黑棋算法 A、复盘表 |
| `ai_black.py` | 黑棋 AI 对外接口 |
| `ai_white.py` | 白棋 AI 对外接口 |
| `ai_worker.py` | 常驻 AI 搜索工作进程（GUI 经多进程调度搜索，主窗口不卡） |
| `engine_client.py` | C++ 引擎子进程封装（GUI"C++引擎"模式走它，协议见 cpp/README.md） |
| `cpp/` | C++ 引擎（Rapfi 棋型缓存+禁手、元组评估、alpha-beta、证明级 VCF/VCT），见 cpp/README.md |
| `engine_client.py` | C++ 引擎子进程封装（GUI"C++引擎"模式走它，协议见 cpp/README.md） |
| `cpp/` | C++ 引擎（make/undo+Rapfi 禁手+元组评估+alpha-beta+VCF/VCT），见 cpp/README.md |
| `board_tools.py` | 坐标代码（`a15`/`p0`）与棋盘文本互转、导出/导入、分析 CLI（威胁、蓝叉、禁手地图、AI 着法） |
| `../tools/rapfi-plugin/rapfi_plugin.py`（在程序目录**之外**） | 唯一的 Rapfi 外置插件：**直接从 Rapfi/Yixin 窗口抓局面**（Ctrl+C）或读剪贴板 → **禁手默认问 Rapfi 引擎**（`INFO rule 2` + `YXBOARD` + `YXSHOWFORBID`，与窗口显示一致）→ 追加代码行 + 禁手行到 `导出/粘贴板.md`，预览点阵把禁手画成 X；不改主程序任何文件、不读写 Yixin 目录，双击 `tools\rapfi-plugin\rapfi_plugin.bat` 运行 |
| `tests_torus.py` | 环面/禁手/GUI/坐标读取 自动化测试（`python tests_torus.py`） |
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
| `is_black_legal_move` | 黑棋合法/禁手判断：**逐行移植 Rapfi `checkForbiddenPoint`**（五连优先→长连/一线双四→两真活三）；自吃点不可落子；按棋盘状态缓存。与 C++ `cpp/src/forbidden.cpp` 同一算法，`cpp/tests/diff_forbidden.py` 逐点差分必须 0 不一致 |
| `_rapfi_pattern` / `_rapfi_combine4` | Rapfi 线型 DP 与四方向组合（B4S/B3S、长连、一线双四 dirty fix），带记忆表 |
| `_rapfi_dir_pattern` / `_rapfi_pattern4` | 11 格窗口（环面回绕）下某点的单方向线型 / 组合线型 |
| `_rapfi_count_true_threes` | Rapfi 第三步：每个方向最多 1 个真三（首侧命中即跳过另一侧），延伸点支持“假禁手”递归验证 |
| `_rapfi_cell_flag` | 黑棋视角格子状态：白子/障碍/无气空点/棋盘外一律 OPPO（三者代码层面完全一致） |
| `_windows_containing` | 枚举含该落点的 5 格线窗 |
| `_four_sets` | 旧棋形集合版“四”统计（现仅 `foul_lines` 画线用；判定已走 Rapfi 移植） |
| `_three_sets` | 旧棋形集合版真活三统计（现仅 `foul_lines` 画线用） |
| `_simple_forbidden` | 旧单层“延伸点不可用”检验（现仅 `foul_lines` 画线用） |
| `_count_foul_shapes` | 旧四数/真活三数统计（画线与差分归因用） |
| `foul_lines` | 返回构成禁手的线（供 GUI 红字画线；落子点临时放置后恢复） |
| `get_blue_cross_positions` | 禁手/自吃蓝叉缓存；落子后只增量刷新 4 条线（`_refresh_blue_cross`） |
| `find_all_threats` | 兼容接口 |

修改红色位置类型时：
- 若只改单方向棋形，去 `PATTERNS` / `match_line_threat`；
- 若改综合类型，去 `classify_position_after_move`；
- 若改禁手，去 `is_black_legal_move`（＝Rapfi 移植，改算法要同时改
  `cpp/src/forbidden.cpp`，并跑 `cpp/tests/diff_forbidden.py` 与
  `cpp/tests/forbid_cases.py`）。

注意 Rapfi 语义：`checkForbiddenPoint` **每个方向最多计 1 个真三**（先看一侧，
命中就跳到下一个方向），所以“同一条线上两个活三”（如 `0110A0110`）在 Rapfi
下**不算**三三；`1110A0111` 这类同线两个四被 Rapfi 编码成长连（OL），本程序按
四四报出（更贴近规则书，禁手集合相同）。

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
- 顶部按钮：新对局、对局设置、悔棋、Pass、AI 立即落子、AI 设置（导出/导入按钮已搬进“对局设置”窗口，G / I 快捷键不变）
- 「AI 设置」窗口（按钮就在“AI 立即落子”下面）：Minimax 层数（0~4）、最短/最长搜索时间、威胁搜索步数 VC2/VCT/VCF（缺省 1 / 18 / 180，随 `candidates` 命令传给引擎）
- 「对局设置」窗口（原“选择模式”）：棋盘尺寸、先手、禁手开关、白棋获胜条件、环面、障碍、保存目录/坐标文件，外加导入/导出按钮
- 勾选框：黑棋 AI / 白棋 AI、C++引擎（勾选后 AI 落子与候选点 W/L 角标都走 cpp/build/engine.exe）、棋盘样式（交叉点/格子，即时生效）、玩家落子提示、显示手数、显示AI候选点、取消投子认负
- 黄色棋盘区顶部统计条：黑棋时间/AI/人类（靠棋盘左缘三行）、白吃黑 N子（垂直居中）、白棋时间/AI/人类（靠棋盘右缘三行）；微软雅黑UI字体 9路≈9pt → 15路起封顶20pt，与棋盘间隔一行。AI 行=自动AI搜索思考时间（蓝字口径）累计；人类行=人类落子用时（含右键AI辅助）；同方人类+AI≈该方总用时
- 蓝/绿小字：AI回合显示搜索进度/上一步AI用时；人类回合蓝字=本步正在用时、绿字=上一手人类用时
- C++引擎模式：候选点 W/L 角标（绿=W 必胜手数、红=L），由 `_maybe_refresh_engine_labels` 异步取回、`draw_board` 画在候选点方块右上角；步数带 `+`（如 `L8+`）表示只是下界（层 2 智能应对兜底，见 vcfvct 的 `CandidateLabel::at_least`）；禁手蓝叉改由 `_maybe_refresh_engine_forbidden` 取引擎 `checkforbidden`（Rapfi 语义），不再用 Python `rules.py` 判定
- 模式窗口：棋盘尺寸（9~19 奇数，新对局生效）、先手、禁手设置、白棋获胜条件、环面模式（新对局生效）、障碍
- 环面模式：上下/左右互通（气、连五、禁手、领地、距离全部回绕，AI 只搜索实际 n×n 棋盘）
- 环面提示（主面板复选框）：开启后四周显示镜面复制区，宽度可选 2 格（n+4）或 4 格（n+8），关闭则只显示 n×n；复制区背景统一用第一圈色、网格线统一 50% 白、假棋子=50%棋子色+50%棋盘底色，实际棋盘四周只有一条 #f2f2f2 粗镜框；鼠标在复制区时幽灵棋子只显示在实际对应格；点击复制格映射到实际格落子
- 棋盘尺寸自适应：读取窗口/屏幕大小，优先完整显示棋盘；棋盘放不下时按比例缩小格子（最多缩小 50%，最小 15px），随后再按剩余空间选顶部字号；若顶部放不下，时间/吃子自动改到棋盘旁边（右侧面板）显示
- 保存目录/坐标文件：默认目录是程序目录下的 `导出/` 文件夹（自动创建，导出文件不会散在程序目录里），在"选择模式"窗口里可改"保存目录"（浏览）与"坐标文件"名（默认 `粘贴板.md`，可"打开"），立即生效
- 导出棋盘(复制)（G 键）：复制完整棋盘文本到剪贴板、写 `导出/board_dump.txt`，并把**只含坐标**的一行追加到坐标文件（无落子记录时不追加）
- 导入坐标（I 键/按钮）：弹窗内粘贴坐标或整份导出文本，也可"从文件读取…"（默认读坐标文件最后一行），选先行后回放；不合规则的着法**不会落子**，先列出（坐标+禁手类型）让用户确认是否跳过继续，选"否"则完全放弃导入、棋盘不变
- 抓取/判定 Rapfi 局面用程序目录**之外**的 `../tools/rapfi-plugin/rapfi_plugin.py`（见第 8 节）；程序目录里不再保留抓取脚本的副本

### 功能函数

| 函数 | 作用 |
|------|------|
| `new_game` | 按模式设置开新局（含所选棋盘尺寸） |
| `open_mode_window` | 对局设置窗口（原“选择模式”；内含导入/导出按钮） |
| `open_ai_window` / `_threat_steps` | AI 设置窗口（minimax 层数 / 限时 / 威胁搜索步数 VC2·VCT·VCF）与取值 |
| `run_ai_move` | 向 AI 工作进程提交搜索任务（立即返回，不阻塞界面） |
| `_ensure_worker / _shutdown_worker / _poll_worker` | AI 工作进程的启动/关闭与结果队列轮询 |
| `_sync_worker_epoch / _abort_active_search / _stop_search` | 跨进程中断：纪元计数器同步、“AI 立即落子”中断、废弃搜索 |
| `_worker_progress / _handle_worker_done / _finish_finished_search` | 工作进程进度回传与搜索结果落子 |
| `_ensure_engine_client / _run_ai_move_engine` | C++ 引擎子进程客户端（懒创建）与 C++ 引擎搜索落子（勾选“C++引擎”时替代工作进程路径） |
| `_update_engine_progress / _maybe_refresh_engine_labels` | 引擎 info depth 进度刷新、候选点 W/L 标注异步刷新（`engine_labels` → `draw_board`） |
| `_maybe_refresh_engine_forbidden`（引擎模式禁手蓝叉，Rapfi 语义） | 异步取引擎 `checkforbidden` 的禁手/无气点（`engine_forbidden`，纪元 `engine_forbidden_job` 防串台）→ `draw_board` 画蓝叉；`engine_var` 关闭时保留 Python `rules.py` 旧路径 |
| `_on_engine_toggle / _on_candidates_toggle` | “C++引擎”“显示AI候选点”勾选框回调（切换时清空/重新取标注） |
| `_handle_replay_done` | 复盘模式下工作进程算出的黑棋应手 |
| `progress_callback` | AI 进度回传 |
| `apply` | AI 结果应用与落子 |
| `draw_board / draw_hints / _draw_hover / _draw_top_band` | 棋盘、悬停落点提示与顶部统计绘制 |
| `_grid_extent / _update_origin / _point_center` | 棋盘像素范围、居中原点、逻辑坐标→画布坐标（区分交叉点/格子样式） |
| `_on_size_check / _selected_board_size` | 棋盘尺寸复选框互斥与读取 |
| `_on_style_point / _on_style_cell` | 棋盘样式复选框互斥与即时切换 |
| `_apply_canvas_size` | 尺寸变化时重设画布/侧栏大小与窗口标题 |
| `_get_candidate_display_positions` | 候选点显示（C++引擎模式=引擎 candidates 输出；关闭时=Python 算法） |
| `_finish_turn_time / update_info` | 用时统计 |
| `play_replay_black` | 复盘黑棋应对 |
| `undo_move / human_pass / _pass_turn` | 悔棋、Pass（`_pass_turn` 把"已下子数"记入 `pass_records`，导出时还原 `p0` 位置；悔棋时 `_trim_pass_records` 清理） |
| `_default_save_dir / _save_dir / _codes_file_path / _choose_save_dir / _open_codes_file` | 保存目录与坐标文件路径（相对路径按程序目录解析、自动建目录），"浏览""打开"按钮 |
| `export_moves_line / export_board_text / export_board` | 仅坐标行；完整导出文本（头部+`moves:`+棋盘点阵）；G 键导出（剪贴板+dump+追加坐标行） |
| `open_import_dialog / _apply_imported_board` | 导入坐标弹窗（粘贴/读文件/选先行）与回放落子、重建 `pass_records`、同步环面/尺寸设置 |

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

---

## 8. 坐标代码与棋盘文本（导出/导入）

### 坐标代码
- 每步一个记号，从先行方开始按颜色交替；字母=列（从左到右 a..），数字=行（**从下往上**数，1..size），所以 15 路上正中央是 `h8`
- Pass 记作 `p0`；导出列表按真实手序插入，例如 `moves: a15 b15 p0 f10`
- 内部实现：`board_tools.coord_to_code / code_to_coord / moves_from_board / pass_records_from_codes`（`pass_records` 存每次 Pass 时的已落子数）

### 导出文本（`board_dump.txt`）

```text
# 头部：size / torus / first / 禁手开关 / obstacles=(x,y),... / no_liberty=(x,y),...
moves: a15 b15 p0 f10 ...
棋盘点阵，每行 size 个字符（示例）:
```

- 点阵：`1`=黑子，`2`=白子 / 障碍 / 无气（黑落子即自吃）位置，`0`=空点；障碍写在 `# obstacles=`、无气空点写在 `# no_liberty=` 头部，导入时据此还原（无气点仍是空点，不会被读成白子）
- 无气判定：`board.get_no_liberty_positions()` 扫描**全部**空点（不限于 relevant 点），四周被黑/障碍填满且整块无气才算；导出时约 0.6ms（15 路稠密盘），不在 AI 热路径上

### 禁手行格式（粘贴板.md）
- 每个局面两行：第一行坐标（空格分隔，Pass 写 `p0`），第二行 `forbid:h8,i7`（逗号分隔，无禁手写 `forbid:None`），两组之间空一行；`#basic`/`#multiple` 这类以 `#` 开头的行是分组标题，会被读取器跳过
- 读取接口：`codes_from_text`（最后一行的代码，自动跳过 `forbid:` 行）、`forbidden_from_text`（最后一条 `forbid:` 值）、`forbidden_list`（`"h8,i7"` → 列表）、`blocks_from_text`（整份文件 → [(代码行, forbid 值)]）

### 无空格坐标自动分块
- Rapfi / Yixin 复制出来的局面没有分隔符，`board_tools.split_codes(text, size)` 自己切块：字母 + 1~2 位数字贪心（`h8i9j10`→ h8/i9/j10，`a15b14`→ a15/b14，9 路时两位数超界自动退回一位），支持大写、`,;|/` 等分隔符、多余的 `1.h8` 手数（忽略）、`moves:`/`board=` 前缀、`p0/pass` Pass；无法成坐标的碎片（孤立字母、纯数字）直接丢弃
- `board_from_code` / `parse_dump` / GUI 的导入弹窗 / CLI 全部走这个分块器，所以有空格、无空格都能读

### 外置插件 tools/rapfi-plugin/rapfi_plugin.py（在程序目录之外，全仓库唯一的抓取插件）
- 抓局面：点【抓 Rapfi 窗口（Ctrl+C）】给标题含关键字的窗口（默认 `Yixin`）发 Ctrl+C（= Yixin 的 putposclipboard），从剪贴板读局面代码；也可【读取剪贴板】或手工粘贴。**抓到/读到局面后自动显示判定结果**（不用再点【解析预览】）
- 判禁手：默认问 Rapfi 引擎 `tools/rapfi/yixin-gui/engine.exe`：`INFO rule 2` + `START <size>` + `YXBOARD` + 每子一行 `x,y,颜色` + `DONE` + `YXSHOWFORBID`（**0 基坐标、不加不减**；先喂黑子再喂白子并补 pass 保证轮到黑棋，否则引擎只回 `FORBID .`）。用 `YXBOARD` 而不是 `BOARD`，避免引擎顺手搜索几十秒。引擎不可用时回退到本程序 `rules.py`（同一 Rapfi 算法移植），预览里写明**判定来源**，且绝不把已有禁手点抹成 `forbid:None`
- 预览点阵把禁手点画成 **X**（`1`=黑 `2`=白 `.`=空 `#`=障碍）
- 选项：棋盘尺寸、先行（黑/白）、「外部局面」（默认开：直接摆子，不做吃子/自吃判定）、「禁手行写成 forbid:」、「禁手问 Rapfi 引擎」、窗口关键字
- 命令行：`--text "h8i9j10"` / `--clipboard` / `--grab [--force]` / `--append [--out 文件]` / `--engine 路径` / `--no-engine` / `--window 关键字`；启动时自动向上查找含 `board_tools.py` 的主程序目录，也可用环境变量 `GOMOKU_VS_GO_DIR` 指定，引擎可用 `RAPFI_ENGINE` 指定
- 依赖：只用本程序自己的 `board_tools` / `rules` / `board`，**不修改** gui.py，也**不读写** Yixin / Rapfi 目录里的任何文件（只读系统剪贴板）
- 头部里的禁手开关会随导入一起生效（同步到"选择模式"里的三个禁手复选框）；只导入坐标（没有头部）时保持界面当前设置不变
- 回放时黑棋每步都过一遍禁手判定（`board_from_code(..., check_rules=True)`，120 手约 12ms）：禁手 / 自吃 / 已占的着法**不落子**，记进 `board.import_errors`（坐标, 类型）并跳过该手（颜色照常轮转），所以不会出现"无气处黑子一闪就消失"或"禁手位置被保存"；CLI 加 `--loose` 可跳过判定
- 坐标文件（默认 `粘贴板.md`）每次导出追加一行纯坐标，方便以后按行读取测试；`board_tools.codes_from_text` 会自动跳过头部与点阵行，取最后一行坐标

### CLI 用法

```bat
python board_tools.py board_dump.txt            :: 分析（威胁/蓝叉/禁手地图）
python board_tools.py board_dump.txt --ai black --depth 2
python board_tools.py --code "h8 h7 g7 p0" --size 15
python board_tools.py --code-file 粘贴板.md     :: 读坐标文件最后一行
```

