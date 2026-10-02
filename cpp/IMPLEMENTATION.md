# C++ 混合规则引擎（棋盘 + 黑棋禁手 + 增量评估 + alpha-beta 搜索）

## 总览与快速上手

**一句话定位**：五子棋(黑) vs 围棋(白)混合规则 C++ 引擎 —— make/undo 增量引擎 +
Rapfi 禁手移植 + 字典序元组评估 + alpha-beta 搜索 + 证明级(AND-OR) VCF/VCT + W/L 标注。

### 构建与运行

```bat
cmd /c cpp\build.bat          :: 编译 cpp\src\*.cpp -> cpp\build\engine.exe
cpp\build\engine.exe          :: 启动引擎，从 stdin 逐行读命令、stdout 逐行输出并 flush
```

`build.bat` 调用本机 MSVC 的 `vcvars64.bat`，以
`cl /nologo /utf-8 /EHsc /O2 /std:c++17 /MT` 编译 `src\*.cpp`。
引擎是纯 stdin/stdout 协议进程，既可人工交互，也可由测试脚本逐行驱动。

### 命令表（与 `src/main.cpp` 逐条核对）

| 命令 | 参数 | 功能 | 输出格式 |
| --- | --- | --- | --- |
| `size` | `<n>`（9..19 奇数） | 重置 n×n 空盘，同时清空置换表 | 无输出 |
| `set` | `<x> <y> <b\|w\|o>` | 直接摆子（`o`=障碍），不提子、不换回合 | 无输出 |
| `clear` | 无 | 清空棋盘 | 无输出 |
| `checkforbidden` | 无 | 列出所有黑棋非法点（Rapfi 禁手 ∪ 无气自杀） | 每行 `x y`，末尾 `end` |
| `play` | `<b\|w> <x> <y>` | 正式落子（白提黑、黑自杀拒绝，`make_move` 负责换回合） | `ok` / `illegal` |
| `move` | `<x> <y> <b\|w>` | 同 `play`（旧接口，参数顺序不同） | `ok` / `err` |
| `undo` | 无 | 悔一步 | `ok` / `err`（空历史 `err`） |
| `hash` | 无 | 当前局面 Zobrist 哈希 | 16 位小写十六进制 |
| `dump` | 无 | 棋盘转储 | `size` 行，每行 `size` 个格子值 `0..3` |
| `pat` | `<x> <y>` | 禁手诊断 | 四方向线型、`p4 fours threes forbidden` |
| `eval` | 无 | 打包评估（只评估不搜索） | `eval <packed> F1=.. F2=.. F3=.. F4=.. F5=.. risk=.. terr=..` |
| `counters` | 无 | 黑白六类线型计数 / 风险 / 领地 | `cnt b=<6 个逗号分隔> w=<6 个逗号分隔> risk=<n> terr=<n>` |
| `bencheval` | `<n>` | 随机走 n 步 `make_move` + `pack_score`（每 200 步 undo 一次） | `bencheval <n> <毫秒> <evals/sec>` |
| `winmode` | `<0\|1>` | 胜负模式（0=line_block 默认，1=occupy） | 无输出 |
| `genmove` | `<b\|w> [max_depth] [min_sec] [max_sec] [winmode]` | 迭代加深搜索，不落子、不改棋盘 | 每完成一个偶深度一行 `info depth <d> move <x> <y> score <packed>`；末行 `move <x> <y>`，白方无着 `pass`、黑方无着 `resign` |
| `searchstat` | 无 | 上一次 `genmove` 的统计 | `searchstat nodes <n> depth <d> ms <毫秒>` |
| `candidates` | `<b\|w> [steps=11] [max_sec=10] [winmode=0]` | 对 `gen_moves(color)` 的每个候选做 VCF/VCT W/L 标注 | 每行 `cand <x> <y> <W\|L><steps>`，截断时一行 `timeout`，末尾 `end`；检测到哈希被改动时只输出 `error hash` |
| `prove` | `<steps> [max_sec=10]` | 黑方证明搜索（含三的 VCT，不落子、不改棋盘） | `win` / `no` / `timeout`；非黑方回合输出 `error turn` |
| `quit` | 无 | 退出进程 | 无 |

> `undo` 的既有实现输出 `ok` / `err`（空历史 `err`），与早期任务文字里的
> `ok` / `nohistory` 不同；`diff_forbidden.py` 明确断言空历史返回 `err`，
> 故保持不变。测试脚本把 `err` 视为“无更多历史”。

### 测试清单（`cpp\tests\*.py`，均在仓库根目录运行）

| 文件 | 一句话说明 | 运行 |
| --- | --- | --- |
| `tests/engine_protocol.py` | 命令行协议回归：十手落子全 `ok`、非法落子、11 次 undo 回到初始 `hash`、`genmove`/`candidates` 无副作用、`size` 切换与 `quit` 干净退出（43 条断言）。 | `py cpp\tests\engine_protocol.py` |
| `tests/diff_forbidden.py` | 黑棋禁手判定与 Python `HybridBoard + rules.is_black_legal_move` 的差分测试，对 Rapfi 语义差异逐条归因，附 make/undo 压力测试。 | `py cpp\tests\diff_forbidden.py` |
| `tests/diff_eval.py` | 增量评估计数器差分（种子 20240917）：随机自对弈逐步比对 `counters`/`eval`/packed，逐步 undo 可逆、查询命令无副作用。 | `py cpp\tests\diff_eval.py` |
| `tests/search_sanity.py` | alpha-beta 搜索健全性（种子 20240917）：自对弈合法性、搜索无副作用、确定性、必胜立即执行、救叫吃、depth6 nps 报告。 | `py cpp\tests\search_sanity.py` |
| `tests/tactics.py` | 证明级 VCF/VCT 战术用例（T1..T10，241 条断言，含 A1/A2/A3 标注健全性交叉验证）。 | `py cpp\tests\tactics.py` |

### 三条已知限制

1. **证明级下标注显著变少、且深证明很贵**：第 6 步把 W/L 改成 AND-OR 证明搜索后，
   只有能对白方**全部**防御都证明必胜的候选才会被标注（旧版“枚举到一条路径即标 W”
   已废弃）。T4 双三局面的候选要 6 手（11 步）才证明得出，`candidates b 11 10`
   会被 `max_sec` 自限截断并输出 `timeout`（实测 10.5 s）。这是“宁可漏标，不可错标”
   的预期代价，不是 bug。
2. **超时截断漏标注**：`nodes > 300000` 或超过 `max_sec` 时 `AnalysisResult::timeout = true`，
   正在搜索的候选与之后所有候选都保持无标注（宁可漏标，不可错标），并追加一行 `timeout`。
3. **GUI 未接入**：引擎只提供 stdin/stdout 命令行协议，尚未接入任何图形界面。

> 本节是总览与快速上手；技术细节若与下文“分步实现记录”冲突，**以下文为准**。

本目录用 C++17 从零实现「五子棋(黑) vs 围棋(白)」混合规则引擎：可 make/undo 的
棋盘、移植自 Rapfi 的黑棋禁手判定、随 make/undo 增量维护的评估计数器、在此之上的
alpha-beta 搜索（negamax + 置换表 + 着法排序 + 迭代加深），以及证明级（AND-OR）
VCF/VCT 威胁搜索与 W/L 步数标注。不含 GUI。

## 目录与职责

| 文件 | 职责 |
| --- | --- |
| `src/board.h` / `src/board.cpp` | `Board` 类：19×19 上限的 `uint8` 棋盘、历史栈、白提黑、黑自杀拒绝、Zobrist 哈希、障碍摆放，随 `make/undo` 增量维护的评估计数器（线型六类 / 领地 / 风险），以及搜索用的 O(1) 计数器（黑/白/障碍子数、开放五连窗格数）与终局判定。 |
| `src/pattern_count.h` / `src/pattern_count.cpp` | 六类线型计数：按 Python `rules.PATTERNS` 逐类复制，对一条线字符串按“位置 × 类别”计数（查表实现）。 |
| `src/eval.h` / `src/eval.cpp` | `pack_score(board)`：把六类计数 / 风险 / 领地打包成字典序可比较的 `int64`；`stm_score(board, winmode)`：negamax 用的“轮到谁走”视角分数。 |
| `src/forbidden.h` / `src/forbidden.cpp` | `check_forbidden(board,x,y)`：黑棋长连 / 四四 / 三三禁手判定；线型分类查表；`classify_point(...)` 供着法排序复用；`probe_forbidden` 诊断接口。 |
| `src/search.h` / `src/search.cpp` | 搜索：常量、`gen_moves`、`order_score`、置换表、`alphabeta`（negamax）、`search_root`（迭代加深）。 |
| `src/main.cpp` | 命令行循环（逐行读、逐行 flush），协议见下。 |
| `build.bat` | 调用指定路径的 `vcvars64.bat`，用 `cl /std:c++17 /O2 /MT` 编译 `src\*.cpp` 到 `build\engine.exe`。 |
| `tests/diff_forbidden.py` | 与 Python `board.HybridBoard` + `rules.is_black_legal_move` 的差分测试，以及 make/undo 压力测试。 |
| `tests/diff_eval.py` | 增量评估计数器的差分测试（种子 20240917）：随机自对弈逐步比对 counters/eval/packed，逐步 undo 可逆，查询命令无副作用。 |
| `tests/search_sanity.py` | 搜索健全性测试（种子 20240917）：自对弈合法性、搜索无副作用、确定性、必胜立即执行、救叫吃、depth6 nps 报告。 |
| `tests/verify_rapfi.py` | 交叉验证：用独立重实现的 Rapfi 判定与引擎 `checkforbidden` 逐点比较。 |

## 构建与运行

```bat
cmd /c cpp\build.bat
py cpp\tests\search_sanity.py
py cpp\tests\diff_forbidden.py
py cpp\tests\diff_eval.py
```

`bencheval 20000`（15×15，随机走子 make_move+pack_score，每 200 步 undo 一次，
盘满时清盘继续以保证跑满 20000 次）本机实测：

```
bencheval 20000 56 353978      :: 约 315k~354k evals/sec（要求 >= 200000）
```

## Board 设计

* 格子值：`0=空, 1=黑, 2=白, 3=障碍`；坐标 `x=行, y=列`，与 Python 版一致。
  `at(x,y)` 越界返回 `OBSTACLE`，使「棋盘外」与「墙」在所有判定里等价。
* 固定数组 `cells_[19*19]`；`make_move` / `undo_move` 不做整盘拷贝。
* `make_move`：
  * 黑：落子后只检查该点所在黑块的气；若无气立即撤销并返回 `false`（自杀非法）。
    黑棋永不提白子。
  * 白：只对与落子点正交相邻的黑块做 BFS 气检测，无气整块提走（不同棋块互不相邻，
    清除顺序无关）。
* `undo_move`：从历史栈完整还原被提子（`captured_pool_`）与回合；哈希用异或对称还原。
* 热路径无堆分配：BFS 的 `seen/stack/group` 都是栈上定长数组，历史栈与提子池预分配。
* Zobrist：`piece[4][361]`（黑 / 白 / 障碍）+ `turn`。`make/undo` 每步异或落子、
  被提子与 `turn` 键，O(1) 增量更新；`set_cell` 增量更新障碍 / 摆子。`hash` 命令输出 16 进制。
* `is_dead_empty(x,y)`：空点，若落黑后（合并相邻黑块、排除自身）仍无气则为 true。
  只需 O(1) 快速路径（有任意空邻点即活），全被占据时才 BFS 相邻黑块。

## 禁手三步实现（`forbidden.cpp`）

线型分类：11 格窗口（中心 + 每侧 5 格）编码成三进制，用与 Rapfi `pattern.cpp`
相同的动态规划在静态初始化时生成一次查表（`3^11 = 177147` 项）。
> 说明：任务文字写的是“9 格窗口”，但要在混合规则下正确识别长连（中心位于六连一端时
> 第 6 子距离为 5），必须看到每侧 5 格；Rapfi 的 renju 规则同样使用 `HalfLineLen = 5`。
> 因此这里采用 11 格窗口。

落子点方向的格编码（黑棋视角）：

* 黑子 → `SELF`；白子 / 障碍 / 棋盘外 → `OPPO`；
* 空点 → 若 `is_dead_empty` 则 `OPPO`（无气点等同边缘 / 阻挡），否则 `EMPT`。

判定流程：

1. **廉价预筛**：取落子点 4 个方向的线型。若四个线型都不含
   `OL / B4 / B4S / F4 / F3 / F3S` 成分，直接非禁手。
2. **长连 / 四四**：任一方向 `OL` → 禁手；否则任一方向 `F5` → 合法且获胜
   （恰好成五优先于四四 / 三三）；否则 `B4/B4S/F4` 的方向数 `>= 2` → 四四禁手。
3. **三三**（scoped 临时落子，结束前还原）：对每个 `F3/F3S` 方向，沿两侧各最多走
   `MaxFindDist = 4` 格（穿过连续黑子，遇到第一个非黑子）。若某个空点满足
   * (a) 能使该方向延伸成 `B_FLEX4`（活四）或 `F5`（成五），且
   * (b) 该点本身不是真禁手（`!check_forbidden`，只递归一层），且
   * 该点不是无气自杀点，

   则该方向计入一个真三；真三方向数 `>= 2` → 三三禁手。
   条件 (a)(b) 正是 Rapfi 相对朴素棋形匹配更严格、能修掉假活三的两条关键。

`checkforbidden` 命令输出的是「黑棋不能落」的全部点：Rapfi 禁手 **或** 无气自杀
（`is_dead_empty`），与 Python `is_black_legal_move`（返回 `self_capture` 等）对齐；
而 `check_forbidden()` 函数本身只做 Rapfi 禁手三步。

## 命令行协议（`main.cpp`）

```
size <n>             9..19 奇数，重置空盘（同时清空置换表）
set <x> <y> <b|w|o>  摆子（o=障碍），不提子、不换回合
clear                清空棋盘
checkforbidden       输出所有黑棋非法点(禁手+自杀)，每行 "x y"，末尾 end
quit                 退出
move <x> <y> <b|w>   正式落子(白提黑、黑自杀拒绝)，输出 ok / err
undo                 悔一步，输出 ok / err（空历史返回 err，与既有测试一致）
hash                 输出 16 位十六进制 Zobrist
dump                 输出 size 行、每行 size 个格子值(0..3)
pat <x> <y>          诊断：输出四方向线型、组合线型、四数、真三数、是否禁手
eval                 输出一行：eval <packed> F1=.. F2=.. F3=.. F4=.. F5=.. risk=.. terr=..
counters             输出一行：cnt b=<6 个逗号分隔> w=<6 个逗号分隔> risk=<n> terr=<n>
bencheval <n>        随机走 n 步；每步 make_move+pack_score，每 200 步 undo 一次；
                     输出：bencheval <n> <毫秒> <每秒 eval 次数>
play <b|w> <x> <y>   正式落子(bool 返回值语义同 move)，输出 ok / illegal
winmode <0|1>        设置胜负模式（0=line_block 默认，1=occupy）
genmove <b|w> [max_depth] [min_sec] [max_sec] [winmode]
                     迭代加深搜索（默认 max_depth=4, min_sec=0, max_sec=10,
                     winmode=当前全局值）。每完成一个偶深度输出一行
                     info depth <d> move <x> <y> score <packed>；
                     最后输出 move <x> <y>（当前方无着：白 pass / 黑 resign）。
                     搜索不落子、不改棋盘。
searchstat           输出上次 genmove 的 nodes / depth / 毫秒（nps 报告用）
```

> `undo` 在任务指令里写作输出 `ok`/`nohistory`，但既有回归测试
> `diff_forbidden.py` 明确断言空历史 undo 返回 `err`；为不改动既有断言，
> 这里保留 `ok`/`err`。

## 搜索（`search.h` / `search.cpp`）

### negamax 与元组比较的结合

评估元组是**黑棋视角**的 `pack_score(board)`（int64，高位字段优先，整数比较
即字典序）。要让 negamax 在轮到白方时“取负仍保持字典序”，关键是：

```
stm_score(board) = f(pack_score(board)) * (turn == BLACK ? +1 : -1)
```

* `f` 是一个**严格单调**（保序）变换：先按指令 5 平移
  `packed - EVAL_CENTER`（`EVAL_CENTER = 1<<62`），把“黑越大越好”的点数搬进
  int64 的负数区间；再做一次保序压缩。
* **为什么要压缩**：`pack_score` 可达 2^56 量级，直接减 `EVAL_CENTER` 后是
  ±2^62 量级，而 `MATE = 2^40`。若不压缩，终局分会被普通评估完全淹没——白方
  甚至会为了普通评估里更大的分值而**拒绝取胜**，`MATE` 级别的 ply 归一化
  （`|score| > MATE_BOUND`）也会把所有普通分值误判成终局分。
  因此 `compress_eval_tuple` 把 7 个 8 bit 字段压成
  `F1:4 F2:4 F3:5 F4:5 F5:5 F6:5 F7:6` bits（按字段高位优先拼接，风险/领地
  用 `min(risk,31)` / `min(territory,63)` 反转），严格保序，值域 `|v| <= 2^33`。
  于是 `|普通评估| <= 2^33 < MATE_BOUND = 2^40-4096 < MATE`，终局分严格支配
  普通评估，TT 的 MATE ply 归一化也只在真正的终局分上生效。
* 终局分按“轮到谁走”的视角给出：黑恰五时轮到白走 → 白方视角 `-MATE`；
  白达成胜利条件时轮到黑走 → `-MATE`。搜索节点内的终局分统一写成
  `MATE - ply - 1`（走子方获胜）或 `-MATE + ply`（走子方落败），越小 ply 的
  胜利越大、失败越小。

### 着法生成与排序分层（`gen_moves` / `order_score`）

候选 = 与任一黑/白子切比雪夫距离 ≤ 2 的空点（障碍不产生候选；空盘返回天元）。
黑方剔除 `is_dead_empty`（无气自杀）与 `check_forbidden`（长连/四四/三三）的点；
白方所有空点合法。`order_score` 纯启发、不落子，分五层：

| 层 | 条件 | 分值 |
| --- | --- | --- |
| a | 落此点立即成**恰五** | 1 000 000 000 |
| b | 白：堵黑成五点；黑：补活唯一气被叫吃的块 | 500 000 000 |
| c | 己方成活四，或堵对方活四点 | 100 000 000 |
| d | 己方成冲四或活三 | 10 000 000 |
| e | 四方向等级分求和：`B4=800, FLEX3=400, B3=80, FLEX2=40, B2=8` | — |

方向等级由 `classify_point(board,x,y,color,dx,dy)` 给出（Rapfi 线型 DP，与禁手
判定共用；`F5→PP_FIVE, F4→PP_FLEX4, B4/B4S→PP_B4, F3/F3S→PP_FLEX3,
B3/B3S→PP_B3, F2*→PP_FLEX2, B2/B1→PP_B2, OL→PP_OL`）。`gen_moves` 返回前按
score 降序、同分按 `(x,y)` 升序排序，保证确定性。

性能优化（结果与朴素实现等价）：
* `order_score` 顺带输出“己方最强方向等级”；黑方只有 `own_level >= PP_B3`
  才需要调用昂贵的 `check_forbidden`（其第一步预筛正是“存在
  OL/B4/B4S/F4/F3/F3S 方向”）。
* `white_would_capture` 在 BFS 发现“该黑块还有别的气”时立即退出。

### 置换表

```cpp
struct TTEntry { uint64_t key; int16_t depth; int8_t flag; int64_t score; uint16_t best; };
```

固定 `2^20` 项（`new` 一次，引擎生命周期复用），索引 `key & (2^20-1)`，
always-replace；`flag` 0=空 / 1=EXACT / 2=LOWER / 3=UPPER；`best` 为
`index(x,y)`，`0xFFFF` 表示无。查询时 key 完全匹配且 `depth` 足够才按 flag
返回/收窄窗口，`depth` 不足只用 `best` 排序。MATE 级别分值存入前 `score+ply`、
取出时还原（LOWER/UPPER/EXACT 都做），避免不同 ply 的同一局面取到错位的
“几步杀”。`tt_clear()` 在 `size` 命令时调用；`search_root` 每次开始也清空一次，
保证“同局面 + 同参数 → 同输出”（迭代加深内部的复用不受影响）。

### 终局检测计数器

`Board` 增量维护（`HistoryEntry` 存旧值，`undo` O(1) 还原）：
`black_count_`、`white_count_`、`obstacle_count_`、`alive_windows_`
（`wins_total_ > wins_blocked_` 的格数 = 仍有开放五连窗的格数）。据此：

* `last_move_was_five()`：最后一手是黑且 `black_run_length == 5`；
* `white_wins_now(winmode)`：吃光黑子（`black_count_==0 && white_count_>0`）；
  `winmode==0` 再判断全线封堵 `alive_windows_==0`；`winmode==1`（occupy）判断
  `white_count_ == size²`。

`alive_windows_` 与 `territory_` 独立维护：前者只跟踪“是否还有白子未被挡的
五连窗”，后者还包含“无气自杀空点”等修正。

### 节点与迭代加深

* 每个节点入口检查 deadline，超时抛 `SearchAbort`；所有 `make_move` 都用
  try/catch 保证抛出前成对 `undo_move`（并在 `#ifndef NDEBUG` 下用 RAII
  断言进出节点 Zobrist 完全相等）。
* `depth<=0` 返回 `stm_score`；无合法着法时黑方返回 `-MATE+ply`（白胜），
  白方返回 `stm_score`（白 pass、黑继续）。
* 子着法：`make_move` 后依次判断“黑方刚成恰五”“白方达成胜利条件”，否则
  `-alphabeta(depth-1, -beta, -alpha, ply+1)`；随后 `undo_move`，按
  alpha/beta 提升情况写 TT（EXACT/LOWER/UPPER）。
* `search_root` 迭代加深 `depth = 0,2,4,6,8`（到 `max_depth` 为止，
  `max_depth==0` 只做 depth0）；depth0 只用排序给出候选。每层重排根着法：
  上一轮最佳第一、TT best 第二、其余按 `order_score`；根节点不看 TT 的 depth
  截止。捕获 `SearchAbort` 时返回上一完整深度的结果。`max_sec<=0` 表示无限。
* `SearchResult` 额外携带每个完成深度的最佳着法与分值，供 `main.cpp` 打印
  `info depth ...`。

### 实测（本机，`/O2`）

固定 10 手中局（`search_sanity.py` 的 `SEQ_MID`，非战术局面，评分非 MATE）：

```
[nps] fixed midgame depth6: completed_depth=6 elapsed=16.85s nodes=558547 nps=33155
```

即 **depth6 在 max_sec 30 内完成（约 17s，33k nodes/s）**，远超“完成深度 6”
的验收要求；`search_sanity.py` 会在未完成 depth6 时直接 FAIL。
作为参照，另一固定局面（`SEQ12` 的 12 手更松散中局，同样非战术局面）：
`nodes=605194 elapsed=21.4s`，depth6 也在 30s 内完成。

## 评估元组（增量维护，只评估不搜索）

### 字段与打包（`eval.h` / `eval.cpp`）

从高到低每字段 8 bit（全部非负），`packed` 直接整数比较即字典序比较：

| 字段 | 含义 |
| --- | --- |
| `F1` | `min(黑 open_four 计数, 255)` |
| `F2` | `min(黑 rush_four 计数, 255)` |
| `F3` | `min(黑 open_three 计数, 255)` |
| `F4` | `min(黑 sleep_three + 黑 open_two 计数, 255)` |
| `F5` | `min(黑 sleep_two 计数, 255)` |
| `F6` | `255 - min(risk, 255)` |
| `F7` | `255 - min(territory, 255)` |
| `F8` | `0` |

```text
packed = (F1<<56)|(F2<<48)|(F3<<40)|(F4<<32)|(F5<<24)|(F6<<16)|(F7<<8)|F8
```

`packed` 恒为正（`F8=0`，且各字段 <=255），两局面直接比较 `int64` 即得
“大圆圈(冲四/活三) → 小圆圈(眠三/活二) → 红点(眠二) → 领地/吃子风险”的字典序。
`Board` 内部保存未截断的 `risk_` / `territory_`，只在打包与 `eval` 输出时
`min(...,255)`。

### 六类线型计数（`pattern_count.*`）

模式表逐类复制 Python `rules.PATTERNS`（`open_four/rush_four/open_three/
sleep_three/open_two/sleep_two`）。计数规则：线字符串两端各补 4 个 `'2'`；
对每个起始位置与每个类别，若该类任一 pattern 或其反转在该位置匹配，则该类
在该位置计 1（同位置同类只加一次，不同位置各自累加，允许重叠）。

实现用查表：把窗口编码成三进制（`'0'/'1'/'2'`，每格 2 bit），预生成
`tbl5/tbl6/tbl7`（该位置命中的类别位掩码），每个起始位置一次查表。

### 行/列/两对角线的增量维护

* `line_cnt_[4][line_id][2色][6类]` 缓存每条线的黑白计数；
  `black_cnt_ / white_cnt_[6]` 是全局计数。
* `make_move` 只重算受影响的线：落子点所在 4 条线 **以及每个被提子所在 4 条线**
  （提子会移除不经过落子点的线上的黑子，必须一并重算），把差量加进全局计数。
* `HistoryEntry` 保存本步之前的 12 个全局计数（黑白各 6）。`undo_move` 直接
  O(1) 取回；逐条线的缓存与逐格缓存在还原局面后按定义精确重建。

### 领地（`territory_`）

* 维护每格 `wins_total_[i]`（经过该格的盘内五连窗总数）与
  `wins_blocked_[i]`（含白子或障碍的窗数），以及每个窗口的 blocked 标志
  `win_blocked_[dir][line][start]`。
* `make_move` 只对经过落子点的窗口（≤20 个）重算 blocked 标志；标志翻转时
  更新窗内 5 格的 `wins_blocked_`。
* 死格定义与 Python `get_dead_positions()` 一致：
  * 空/黑格且 `wins_total_ == wins_blocked_`（无白子自由五连窗；含
    `wins_total_ == 0` 的边角格）；
  * 或者空点且“落黑即无气（`is_dead_empty`）”且位于某黑子 4 步线邻域内
    （对应 Python `relevant_empty_positions` 的修正；没有这条会多算被白子包死、
    且附近无黑子的空点）。
* `territory_` 只对可能变化的候选集合做死格标志差量：经过落子点的窗口格、
  落子点邻域、提子及其邻域、提子/落子点的线邻域、以及受影响黑棋块的空邻点。
* `HistoryEntry` 保存本步之前的 `territory_`；`undo_move` 直接恢复，并按定义
  重建逐格缓存。

### 风险（`risk_`）

`risk_ = Σ over 黑棋块( [气数==1]*4 + [气数==2]*1 )`。`make_move` 在落子前取
“受影响棋块”坐标区域 `{落子点} ∪ N4(落子点) ∪ 被提子 ∪ N4(被提子)`，落子前后
在同一区域上重算这些棋块的气数与贡献，差量更新 `risk_`（这样能覆盖“提子给
远处相邻黑块加气”的情形）。`HistoryEntry` 保存本步之前的 `risk_`，undo 恢复。

### 与 Python `evaluate_black_position` 的对应与差异

* 共同点：领地都用 `get_dead_positions()` 同义的“无白子自由五连窗 / 无气空点”
  口径；风险对应 `get_black_groups()` 的气数惩罚（1 气 4 分、2 气 1 分）。
* 差异：
  1. Python 的 `evaluate_black_position` 是“棋块分 + 红点分 − 领地罚”的浮点值；
     本引擎按任务要求把这些信息重新组织为“六类线型计数 + 风险 + 领地”的
     8-bit 字段并打包成 `int64`，供 alpha-beta 直接做字典序比较。
  2. Python `rules.match_line_threat` 每条线只取最优的**一个**威胁；本引擎按
     “位置 × 类别”统计**出现次数**（同一方向可同时命中多类、多位置），因此
     `F1..F5` 是计数值而非“有没有”。
  3. 六类计数只统计**黑棋**视角的线码（黑=`'1'`，白/障碍/边界=`'2'`，空=`'0'`）；
     白棋计数同样维护（`counters` 命令输出），但不进打包字段。


## 与 Python 版规则的已知差异清单

差分测试（77 个局面、11075 个空点；其中前 71 个局面与验收失败的版本逐位一致）中，
除下列两类外逐点一致；测试对每个不一致显式复核并归因
（`cpp/tests/diff_forbidden.py` 内独立用 Python 重实现了 Rapfi 的线型 DP）。

1. **三不能延伸成活四 / 成五（Rapfi 更严，归因 `rapfi_dir_not_open_three` /
   `no_live_extension`）**
   Python 用 6 格窗口模板 `011100` / `011010` 匹配活三，而 Rapfi 用整条线的动态规划
   分类。某些方向 Python 认为是活三，Rapfi 却判定为 `B3`（冲三）等更弱的线型，即该
   方向无法延伸成活四 / 成五，因而不计为真三。最典型的是一子在同一条线上形成两个
   可延伸的三：Python 按“棋形集合”计为 2 个三（判三三禁手），Rapfi 每个方向只计一次
   且该线型为 `B3`，故判合法。
2. **延伸点 / 补五点本身是禁手（归因 `ext_point_forbidden` /
   `four_completion_forbidden`）**
   * 三：Rapfi 要求三的延伸点本身不是禁手 / 不是自杀点，否则该方向不计入三三。
   * 四：Rapfi 的四按方向由线型给出；若该四唯一的补五点本身是长连 / 自杀等禁手点，
     Python 的 `_four_sets` 会因补点不能构成“恰好五”而不计该四，Rapfi 仍计为四，
     极端时 Rapfi 会多判出四四。

其它实现层面的约定（非判定差异）：

* **无气点视为阻挡**：本混合规则下黑棋不能落在无气点，故在线型编码中把无气空点当作
  障碍（等同边缘）。Python 的 `line_code` 不把无气点当阻挡，但其四 / 三的延伸检查会
  单独排除自杀点，因此两者在测试局面上仍然一致（本项为规则要求）。
* **长连优先于成五**：若一子同时在某方向成五、另一方向成六，按任务规则（及 Python
  `black_run_length` 取最大连）判长连禁手；Rapfi 原始 `getPattern4` 让 `F5` 优先，
  这里按任务说明改为先判 `OL`。
* **禁手只约束黑棋**：禁手点仍是空点，白棋可以落在其上；`check_forbidden` 只对空点有效。

## 差分验收发现的差异与归因（固定种子 20240917）

本节对应验收失败那一轮暴露的 3 个问题，给出根因、典型棋形（用线码表示）与结论。

线码约定：**11 格窗口**，中心 = 落子点，沿该方向从左到右；`1` = 黑，`0` = 空，
`2` = 阻挡（白 / 障碍 / 出界 / 无气点）。例如 `00010110100` 表示中心以外第
`-3, -1, 0, +1, +3` 格是黑子。

### A. make/undo 阶段“引擎 stdout 意外关闭 / 疑似段崩溃” → 脚本 bug，引擎无辜

旧版 `make_undo_test` 用下面一行读 `dump`：

```python
grid = [[int(eng.readline()[y]) for y in range(size)] for _ in range(size)]
```

`eng.readline()` 位于**内层**推导式中，因此每一行都会调用 `size` 次
（15×15 局面下每个 `dump` 要读 **225** 行），而引擎对 `dump` 只输出 `size` 行。
第 16 次 `readline()` 永远等不到数据，进程停在第一次 `dump`（`applied == 7`）阻塞；
当引擎进程随后被会话/超时清理时，阻塞的读变成 EOF，即
`engine closed its stdout unexpectedly`。用 `faulthandler` 可以确认阻塞点正是该行。

修复方式：逐行读一次再取字符（`row = eng.readline(); [int(row[y]) ...]`），
并让 stdout 由后台线程持续抽干、`stderr=subprocess.DEVNULL`、读取带 30s 超时。

**引擎本身没有崩溃**：`board.cpp` 的被提子复原（`cap_begin/cap_count`）、历史栈
下溢保护、`main.cpp` 的空历史 `undo`、`hash`、以及 `history_` / `captured_pool_`
的配对都检查过，没有越界。新增的 make/undo 压力测试（200 步对局 ×3 轮、
300 步随机 make/undo 游走、逐步哈希可逆、空历史 `undo` 返回 `err`、
增量哈希 == `clear + set` 重建哈希）全部通过，因此 `cpp/src` 无需改动。

### B. 23 个 `py=three_three, cpp=合法` → C++（Rapfi）正确，Python 把眠三当活三

归因器在 Python 里独立重实现 Rapfi 的线型 DP，逐个方向复算。典型棋形：

| 局面/点 | 方向线码 | Rapfi | Python | 归因类别 |
| --- | --- | --- | --- | --- |
| 13×13 (0,5) | `00010110100` | `B3` | 同方向两个 `011010` 三 | `rapfi_dir_not_open_three(B3)` |
| 15×15 (6,0) | `00101101000` | `B3` | 两个三 | `rapfi_dir_not_open_three(B3)` |
| 19×19 (8,18) | `00101101001` | `B3` | 两个三 | `rapfi_dir_not_open_three(B3)` |
| 19×19 (9,12) | `00010110100` | `B3` | 两个三 | `rapfi_dir_not_open_three(B3)` |
| 19×19 (5,5) | `00010101100` | `B3` | 两个三 | `rapfi_dir_not_open_three(B3)` |
| 19×19 (6,6) | `20001101012` | `B3S` | 两个三 | `rapfi_dir_not_open_three(B3S)` |
| 13×13 (4,7) | `20010110100` | `B3` | 两个三 | `rapfi_dir_not_open_three(B3)` |
| 13×13 (5,9) | `00101101020` | `B3` | 两个三 | `rapfi_dir_not_open_three(B3)` |
| 15×15 (8,2) | `20101110000` | `B4S` | 一个三 + 一个四 | `rapfi_dir_not_open_three(B4S)` |
| 15×15 (13,12) | `00101102222` | `F3`，但唯一延伸点 (11,12) 本身四四 | 两个三 | `ext_point_forbidden` |

以 `00010110100` 为例（黑子在第 3、5、6、8 列，中心在第 5 列）：

```
0 0 0 1 0 1 1 0 1 0 0
```

Python 的 6 格窗口匹配器在局部同时命中两个 `011010`（黑子集合 `{3,5,6}` 与
`{5,6,8}` 在同一方向上重叠），于是各计一个活三 → 假双三。但把任一集合补成
“活四”时，补点会与外侧第 8 列（或第 3 列）的黑子连成 **6 连长连**，只能成冲四，
所以它们其实是**眠三**。Rapfi 用整条 11 格线做 DP，正确给出 `B3`，不计真三，
因此不构成三三——C++ 没有漏判。

`(13,12)` 属于第二类严格条件：线码 `00101102222` 的 Rapfi 线型是 `F3`，但唯一能
把它延伸成活四的点 `(11,12)` 同时形成 “活四 + 冲四”（四四禁手点），不能作为合法
延伸；另一方向 `00011100222` 是真活三，于是总共只有 **1** 个真三，不构成三三。

### C. 4 个 `cpp_stricter`（9×9，点 (8,7)）→ C++（Rapfi）正确

(8,7) 落子后 Rapfi 看到两个方向是四：

* `dir1 (0,1)`：黑子在列 4,5,6,8，补列 3 成五 → `B4`（Python 也认可这个四）；
* `dir2 (1,1)`：线码 `01011122222` → `B4`。该四的补五点是 `(5,4)`，但 `(5,4)`
  同时把同一行补成 `XXXXXX`（**长连**），即补点非法。

Python 的 `_four_sets` 要求补点能形成**合法**的恰好五，因此不把 `dir2` 算四；
Rapfi 的线型 DP 只看单线，把它算四。两个四 → 四四禁手，归因
`four_completion_forbidden`。注意 `(5,4)` 不是自杀点（落子后有气，只是长连禁手），
所以不属于 `self_capture`。

### D. 归因汇总与交叉验证

固定种子 20240917 的验收输出：

```
局面数: 77 (含无气点局面: 8)  比较空点数: 11075  一致: 11048 (禁手/非法 45)
  [需归因]     cpp_stricter     4
  [需归因]     three_three      23
  归因[ext_point_forbidden] = 1
  归因[four_completion_forbidden] = 4
  归因[rapfi_dir_not_open_three] = 22
  已归因 = 27
  无法归因不一致 = 0
[make/undo] plan=200 applied=200 dumps=24 bad_replies=0 ... ok=True
PASS
```

其中 27 条与验收失败那一轮的 27 条一一对应；`self_capture/overline/five/occupied`
类不一致为 0。

此外，用与 `check_forbidden_impl` 逐行等价的 Python 重实现（含一层递归、
`MaxFindDist = 4`、无气点视为阻挡），在全部 77 个局面的 **11075** 个空点上与引擎
`checkforbidden`（`is_dead_empty ∪ check_forbidden`）逐点比较：

```bat
py cpp\tests\verify_rapfi.py
:: points=11075  engine_vs_rapfi_disagreements=0
```

即引擎与 Rapfi 语义完全一致，没有漏判或误判。

## 评估差分验收（固定种子 20240917，`cpp/tests/diff_eval.py`）

测试内独立重算 Python 参考值（六类计数按指令 2-4；`risk` 用
`get_black_groups()`；`territory` 用 `get_dead_positions()`；`packed` 按打包
规则），随机自对弈 4 局（15×15 / 13×13 / 9×9 / 9×9+4 障碍），每步引擎落子后
发 `counters` 与 `eval` 逐项断言，局末逐步 undo 到底并断言 `hash` 回到初始值，
另做查询命令无副作用断言。最终输出：

```
[15x15] size=15 obstacles=0 moves=48 checks=98
[13x13] size=13 obstacles=0 moves=48 checks=196
[9x9] size=9 obstacles=0 moves=48 checks=294
[9x9+obs] size=9 obstacles=4 moves=41 checks=378
================================================================
自对弈步数=185  计数器断言=378  失败=0
PASS
```

另外用同一测试框架做过更重的模糊测试（12 局、9×9..19×19、含障碍、最多 200 步，
共 1531 步 / 3084 次断言）全部一致。过程中发现并修复了一个真实增量缺陷：
**白棋提子会移除不经过落子点的线上的黑子**，早期只重算了落子点所在 4 条线，
导致线型计数偏小；修复后 `make_move` 会重算“落子点 + 所有被提子”所在的全部线。


## 证明级 VCF/VCT 与 W/L 标注（第 6 步重写，`cpp/src/vcfvct.*`、`candidates` / `prove` 命令）

> 第 7 步把**白方**（`candidates w`）的输出语义整体升级为“威胁候选点”，见文末
> “威胁候选点与三层 VCT”一节。本节描述的 AND-OR 证明搜索、黑方候选标注
> （`candidates b`）与 `prove` 命令的语义不变；`candidates w` 只在这一节的基础上
> 换成“先算阻挡点交集、再取标注最好的一档”。

第 4 步的实现是“OR 式路径枚举”（枚举到一条黑方成五的路径就出标注）。第 6 步整体
重写为**证明级 AND-OR 搜索**：只有能被一棵证明树支撑的结论才会标注，证明不出就
不标注（宁可漏标，不可错标）。核心改动见文末“与第 4 步的差异清单”。

### 证明级语义（AND-OR）

* 接口：`ProveResult { WIN, UNKNOWN, TIMEOUT }` 与
  `prove_black(Board&, int max_steps, bool allow_three, double time_sec, long long node_limit)`。
* **黑方节点（OR）** `prove_black_dfs(b, steps_left, allow_three, ctx, tt)`：
  前置 `b.turn()==BLACK`。返回 true 当且仅当存在一手攻击 `e`，使白方防御集内
  **每个**应手之后黑方仍被证明必胜（递归）；成五直接构成 1 手证明。防御集**为空**
  是退化情形，见下文“空防御集的健全性处理”（不算证明）。
* **白方节点（AND）** `prove_white_node(b, cx, cy, budget, ctx, tt)`：
  前置 `b.turn()==WHITE`，黑方刚在 `(cx,cy)` 落子。`(cx,cy)` 不是威胁
  （`attack_rank_at < OPEN_THREE`）→ 非强制手，证明失败；否则按成分取防御集
  （含四成分 → `defense_four`，纯活三 → `defense_three`），集合内**每个**应手后
  都要 `prove_black_dfs(b, budget, …)` 成立才算证明成功。
* **预算只数黑攻击手数**：黑落一手 −1，白应手不消耗。`analyse` 对黑候选做迭代加深
  `m = max(2, lo) … max_steps`（`lo` 为“非威胁手不可能进证明”的预算下界：活三 3、
  四类 2、其余 0），首个证明成功的预算即结论：`W = 2m-1`；白候选 `m = 1…max_steps`，
  白下一手后黑方在 `m` 手内被证明必胜 ⇒ `L = 2m`。**步数 = 首个证明成功的预算**
  （IDA），不再是“已枚举路径中最短者”的启发式取值。
* 全程只 `make_move`/`undo_move`，不拷贝棋盘；所有排序为全序（候选按
  `(威胁等级, order_score, x, y)`，防御集按 `(order_score(b,w,WHITE), x, y)`），
  输出确定。

### 攻击候选生成 `gen_attack_candidates`

* 空点范围：与任一已有黑子切比雪夫距离 ≤ 4（用二维前缀和 O(1) 预筛“邻域黑子 < 2”
  的必然非威胁点）。
* `attack_class(e)` ∈ `{FIVE, OPEN_FOUR, RUSH_FOUR}`（`allow_three=true` 再加
  `OPEN_THREE`）。
* **必须 `check_forbidden(b,e)==false` 且非无气自杀点**（`black_point_illegal`；
  `check_forbidden` 本身只判禁手，自杀由 `is_dead_empty` 补），展开时再以
  `make_move` 实际成功为准（双保险）。
* 预算剪枝：`FIVE` 需 `steps_left ≥ 1`，四类需 `≥ 2`，活三需 `≥ 3`。
* 排序：`FIVE > OPEN_FOUR > RUSH_FOUR > OPEN_THREE`，同类按 `order_score` 降序。

### 四威胁的健全防御集 `defense_four`（a ∪ b ∪ c ∪ d，去重）

* **a) 合法完成点**：扫全盘 4 方向 5 连窗，窗内恰 4 黑 + 1 空 + 0 白/障碍，且完成点
  `c` 本身合法（非长连/四四/三三禁手、非无气自杀）→ 加入 `c`。完成点非法的窗是
  “假四”（长连完成点等），直接剔除，既不是真威胁也不产生防御点。
* **b) 提子点**：1 气黑块的唯一气点（白下这里整块提走，可能消掉含窗内子的块）。
* **c) 吃子使能闭包**：所有“≤2 气且至少含 1 枚 a 类窗内黑子”的黑块的全部气
  （白偏离手下在这里可把 2 气组压成 1 气、下一手提掉攻击组）。
* **d) 自杀使能闭包**：对每个合法完成点 `c`，① 与 `c` 正交相邻的黑块的全部气；
  ② `c` 的 4 个正交邻点中为空者。

**健全性论证（2.2.2）**：设黑刚下出四威胁，`C` 为合法完成点集合。对白方应手
`w ∉ defense_four`：(1) `w` 不占任何合法完成点（a）⇒ 至少一个 `c` 仍为空；
(2) `w` 不是任何 1 气黑块的提子点（b）⇒ `w` 不通过提子消除任何黑块，特别是不消除
构成四窗的黑块；(3) `w` 不减少任何“≤2 气且含 a 类窗内黑子”的黑块的气（c）
⇒ `w` 无法把这种块压成 1 气组；(4) `w` 不减少“完成点 `c` 落子后所属黑块”的气、
也不占 `c` 的空正交邻点（d）⇒ 黑下 `c` 后该块仍有气。于是黑下 `c`：不自杀（4）；
白子只会给黑棋形**添加阻挡**，阻挡不可能制造长连/三三/四四（禁手成分只随己方棋子
增加而增加，白子等同墙）⇒ `c` 不构成新的长连/三三/四四；剩余唯一情形是 `c` 所在线
`run == 5` ⇒ 黑**恰五**（恰五优先于长连判定，`last_move_was_five` 用 `run == 5`）
⇒ 黑胜。逐条成立 ⇒ 集合外白应手必败，AND 只需遍历集合内应手。

### 三威胁的健全防御超集 `defense_three(b, px, py)`（a ∪ b ∪ c ∪ d，去重）

* **a)** `defense_four(b)` 全部（白可抢先破坏其它四威胁）。
* **b)** 经过 `(px,py)` 的盘内 5 窗中“0 白 0 障碍且黑子 ≥ 2”的窗的**全部空点**
  （含该三的所有“四 maker”）。
* **c) 吃子使能闭包**：≤2 气且至少含 1 枚 b 类窗内黑子的黑块的全部气（外加与四集
  同源的 1 气提子点）。
* **d) 升级合法性闭包**：b 类窗内空点中 `attack_class ∈ {OPEN_FOUR, RUSH_FOUR}`
  的每个“四 maker” `f` 的 4 个正交空邻点。

**健全性论证（2.3.2）**：设黑刚下出活三，`F` = 该三的全部四 maker。对白方应手
`w ∉ defense_three`：(1) 每个 `f ∈ F` 仍是空点（b 类闭包含 `f` 本身）且仍合法：
d 类闭包封住了“白下 `f` 的邻点把 `f` 变成自杀点”这一唯一途径，白子又不可能让 `f`
变长连/三三/四四（同 2.2.2 的阻挡论证）⇒ 黑下 `f` 必得四威胁；(2) `w` 不影响
`defense_four` 的任何封闭项（a/b/c/d 同 2.2.2 逐条）⇒ 该四威胁的防御集仍是
`defense_four` 的健全超集。因此三威胁对集合外白应手的“三→四升级”必达，随后由
`defense_four` 的健全性接管 ⇒ 集合外白应手必败，AND 只需遍历集合内应手。

### 空防御集的健全性处理（对任务书 2.3 步骤 4d 的必要加固）

`defense_four`/`defense_three` 返回空集时，任务书 2.3 步骤 4d 的处理是“白无应手可防
→ 证明成功”。但防御集的 a 项已经收录了**全盘所有合法完成点**，所以“四类候选的防御集
为空”等价于“全盘没有可立即成五的合法点”（四的完成点全是长连/三三/四四禁手或无气
自杀点，即假四）；这种情况下 2.2.2 的“黑下一手 `c` 即成五”论证不成立，直接返回成功
会给出**无证明树支撑的 W**。因此实现里把空防御集一律视为“证明不出”（黑方 OR 节点
跳过该候选、白方 AND 节点返回未证明）——只可能漏标，不可能错标。

实测：1500 个随机局面（678 个四类候选 + 7891 个三类候选）中防御集为空出现 **0 次**，
故该加固只影响不可达分支；T1/T2/T3/T6/T9 的预期标注在加固前后完全一致。

### 证明置换表（含一处健全性修正）

`ProveTT = unordered_map<uint64_t,int>`：key = 局面 Zobrist（黑先），value = **已证明
成功的最小黑攻击手数**（证明距离）。探测 `stored <= steps_left` 才命中——“预算内必胜”
对预算是单调增的（`k` 手内能赢 ⇒ 更多手也能赢），因此只有“已证明的距离不超过当前
预算”才能安全复用。

> 任务书 2.3 步骤 2 写的是 `tt[hash] >= steps_left`（注释为“已证明成功的最大预算”）。
> 那个方向不健全：它等于用“6 手内必胜”去断言“4 手内必胜”。实测反例（本次调试记录）：
> 带该方向的 TT 时 T4 局面候选 (5,8) 会拿到 `W9`（预算 4）标注，而同一调用换成空 TT
> 重跑在 2998 个节点内就被白方反驳（`win=false`）；修成 `<=` 后两张表一致，
> `candidates` 的标注与 `prove` 命令的输出也一致（tactics.py 的 A1/A2 断言即此一致性）。

### 与第 4 步（OR 式路径枚举）的差异清单

1. **W 不再是“存在一条路径即标 W”**，而是 AND-OR 证明：黑方 OR 节点存在一手攻击，
   使白方**全部**防御应手都仍失败；白方 AND 节点要求集合内每个应手后黑方仍胜。
2. **攻击候选必须合法**：`check_forbidden==false` 且非无气自杀点，展开时以
   `make_move` 实际成功为准（旧版搜索内部只按 `attack_class` 枚举，可能枚举到黑方
   实际不能走的禁手攻击手）。
3. **四窗完成点必须是“当前就合法”的点**：长连/三三/四四/自杀完成点的窗按假四剔除，
   完成点也不进防御集（旧版不做该过滤）。
4. **L 标注不再用 `U(P)` 交集过滤**：整套“路径收集 + `U(P)` 交集”机制废弃，L 改为
   对白方候选直接做证明搜索（白下 `c` 后黑方在预算 `m` 内被证明必胜 ⇒ `L=2m`）。
   旧版 `c` 恒为落盘点、交集过滤恒真的问题随之消失。
5. **步数 = 首个证明成功的预算（IDA）**，不再是启发式的“最短路径手数”。

### 命令

```
candidates <b|w> [steps=11] [max_sec=10] [winmode=0]
prove <steps> [max_sec=10]
```

* `candidates`：对 `gen_moves(color)` 的每个候选输出一行 `cand <x> <y> <tag><steps>`
  （`tag ∈ {W,L}`，无标注的候选不输出），超时/节点上限截断时追加一行 `timeout`，
  最后一行 `end`；若 `analyse` 后 `hash()` 与进入时不同则只输出 `error hash`。
* `prove`：黑方证明搜索（`allow_three=true`，即 VCT；与 `winmode` 无关）。
  `turn()!=BLACK` 输出 `error turn`；否则输出 `win` / `no` / `timeout`，不落子、
  不改棋盘（hash 不变，`assert` 复核）。节点上限 300000。

### 健全性验证与已知限制

* **tactics.py 的通用健全性断言**（对每次 `candidates` 输出的每条标注都生效）：
  A1：`W1` → `play b x y` 必须 ok 且用 Python `HybridBoard.check_black_five` 复算必须
  恰好成五；`W<k>`（k>1）→ 同局面调 `prove (k+1)/2` 必须 `win`。
  A2：`L<k>`（k 偶）→ `play w x y` 后调 `prove k/2` 必须 `win`。
  A3：`prove` 输出只能是 `win/no/timeout/error turn`。
  注：任务书原文写“`play b x y` 后发 `prove <(k+1)/2>`”，但 `play b` 之后轮到白方，
  该命令只会输出 `error turn`；因此在**落子前的同局面**（轮黑）上调 `prove`——比原文
  更强（要求黑方在同样预算内从根局面就有必胜证明）。A2 的 `play w` 之后正好轮到黑方，
  按原文执行。
* **超时/节点上限截断后无标注**：`nodes > 300000` 或超过 `max_sec` 时
  `AnalysisResult::timeout = true`，正在搜索的候选与之后所有候选都保持无标注
  （宁可漏标，不可错标），并追加一行 `timeout`。
* **证明级下标注显著变少属预期**：旧版给“存在一条黑方成五路径”的点标 W（例如 T9 局面
  会给出十几个 `W3`），新实现只给能对**白方全部应手**都证明必胜的点标 W。T9 局面
  （黑 (7,2)(7,4)(7,5)(7,6)(7,7)，长连完成点 (7,3)）现在只剩 `(7,8) W1`（立即恰五），
  若再把 (7,8) 换成障碍（唯一合法完成点消失）则**没有任何 W** —— 假四不再被错标。
* `vcf_exists` / `vct_exists` 是库内调试/测试接口（未挂 CLI 命令），现等价于
  `prove_black(b, max_steps, allow_three, 30s, 300000) == WIN`。注意 **TIMEOUT 也返回
  false**（与“证明不出”不可区分）。实测：黑活四局面 `vcf=vct=1`；T4 双三局面
  `vcf=0/vct=0`（11 手预算下 30 s / 300k 节点内证明不完，属超时截断，而非“黑方不胜”）；
  T9 假四局面 `vcf=vct=1`（(7,8) 立即成五）；单子局面 `0/0`。
* **深度证明很贵**：T4（双三局面）的候选要 6 手（11 步）才证明得出，`candidates b 11 10`
  会被 `max_sec=10` 截断（输出 `timeout`）；`prove 11` 同理。实测见下表。

| 命令（15×15，本机 `/O2`，进程含启动与 Rapfi 模式表初始化约 0.1 s） | 结果 | 用时 |
| --- | --- | --- |
| T2 局面 `candidates b 11 10` | 1 条标注（`cand 7 8 W3`）+ `end` | 0.16 s |
| T4 局面 `candidates b 11 10` | 截断：`cand 4 5 W11` / `cand 4 9 W11` + `timeout` + `end` | 10.14 s（引擎自限 `max_sec=10`） |
| T4 局面 `candidates w 11 10` | 截断：0 条标注 + `timeout` + `end` | 10.14 s |
| T4 局面 `prove 11` | `timeout` | 10.14 s |
| T8 局面（黑 (7,7) 已落）`candidates w 11 10` | 50 条 `L4` + `end` | 0.19 s |
| T9 局面 `candidates b 11 10` | 1 条标注（`cand 7 8 W1`）+ `end` | < 0.3 s |

> T4 局面（双三、要 6 手才证明得出）的 `candidates b 11 10` / `prove 11` 正好撞上
> `max_sec=10` 的自限：**命令都在 10.1 s 内返回**（= 10 s 搜索窗口 + 约 0.1 s 进程启动），
> 输出 `timeout` 表示其余候选因限流未标注——这是“宁可漏标”的预期行为。T2/T8/T9
> 这类局面秒级返回。

### 战术验收（`cpp/tests/tactics.py`）

10 个用例（即时成五、吃子反驳、真四不可吃、双三 VCT、L 标注、障碍、无副作用、
胜点交叉验证、假四/长连完成点 T9（含 T9b 障碍变体）、超时无害 T10）共 241 条断言，
`py cpp/tests/tactics.py` 输出：

```
战术用例断言=241  失败=0  用时=55.93s
PASS
```

其中 T2（吃子反驳）仍是核心回归：黑 (7,5)(7,6)(7,7) 被白贴住后只剩 (7,4)/(7,8) 两口气，
黑走 (7,4) 时该块只剩一口气 (7,8)，`defense_four` 的 b 项把 (7,8) 放进白的防御集，
白 (7,8) 提掉整块四 ⇒ 黑方无子可攻 ⇒ (7,4) 无 W 标注。T9/T9b 是新增的“假四”用例：
长连完成点 (7,3) 既不是候选也不产生标注，而旧版会给一大批点错标 `W3`。

> 第 7 步之后 `tactics.py` 的断言数从 241 变 83：`candidates w` 不再给每个空点打标注，
> T2/T5/T8 的白方断言按新语义改写（理由见 `cpp/tests/tactics.py` 文件头与本节末）。

---

## 威胁候选点与三层 VCT（第 7 步重写，`cpp/src/vcfvct.*`）

### 记号与总流程

记号沿用规格：`0` = 空格，`1` = 黑棋，`2` = 阻挡（白子 / 障碍 / 无气空点——棋型层由
`Board::build_pattern_window` 统一映射，代码里完全一致）。所有判定都走 `Board` 的
**增量棋型缓存**（`classify_point` / `cached_pattern4_black` / `probe_forbidden`），
不新写字符串匹配。

`candidates w <steps> <max_sec>` 现在的流程（`analyse()` 的白方分支）：

```
white_threat_candidates(b)            # ① 阻挡点（第一部分）
   ├─ 无“强迫威胁”线 → unconstrained：候选 = 全盘空点（legal:everywhere）
   └─ 有 → 交集框架 → 候选池（交集 / 无交集回退并集）
对候选池逐点判定                        # ② 三层 VCT（第二部分）
   ├─ 健全 AND-OR 证明搜索（第 6 步，含吃子反驳）→ L<2m>；权威步数
   ├─ 层 1 全应对 VCT（可靠但不完备）→ L<2m>
   └─ 层 2 智能应对 VCT（完备但不可靠）→ 混合判定
取“最好的一档”                          # ③ 安全 W0 优先；否则 L 步数最大（活得最久）
   └─ 仍有多个候选 → minimax（窄深 alpha-beta）收尾
```

### 第一部分：阻挡点（查表规则）

**威胁线**：线上存在空点 `e` 使 `classify_point(e,BLACK,d) ∈ {PP_FIVE, PP_FLEX4, PP_B4}`
（黑棋在该线一步能成五 / 成四）。线等级 `rank = FIVE > OPEN_FOUR > RUSH_FOUR > NONE`。

**阻挡点**：线上空点 `p`，白棋真实 `make_move(p, WHITE)`（含提子）后，该线上不存在空点
`q` 使 `classify_point(q,BLACK,d) ∈ {PP_FIVE, PP_FLEX4}`（黑棋无法再在该线成五或成活四）。

这条统一判定逐条复现规格给出的查表表：

| 线型（0 空 / 1 黑 / 2 阻挡） | 规格：阻挡点个数 | 本实现（`line_blockers`） |
| --- | --- | --- |
| `10111` | 1（那个 0 = 成五点） | {成五点}：其余空点挡不住五 |
| `011112` | 1（唯一成五点） | 同上 |
| `0011102` | 3（三个 0 都是） | {0,1,5}：一端被 2 堵死时远端 0 也有效（把活四降级为冲四） |
| `0011100` | 2（只有紧邻 111 的两个 0） | {1,5}：远端 0 挡不住另一端（黑在另一侧仍成活四） |

**双威胁必须阻挡点**：空点 `p` 在方向 `a` 落子成活四（`PP_FLEX4`）且在方向 `b != a`
落子成活三（`PP_FLEX3`）→ 黑做四三必胜，白棋必须先占该点（`double_threat_points`）。
在交集非空时，交集还会与这一集合求交再继续。

**禁手消失（多重禁手）说明**：阻挡点本身可能是黑棋禁手（白棋占之合法，不影响候选集）。
`blocking_point_forbidden_note()` 给出三类结论：0 = 非禁手；1 = 真禁手（长连 / 四四 /
三三，以 `check_forbidden` 复判为准）；2 = **假禁手**（组合表预筛 `FORBID` 但精判非禁手：
构成三的延伸点本身是禁手点，去掉后三无法延伸成活四/五）。假禁手点在白棋占住该点后
此禁手消失，黑棋其余禁手仍阻挡黑棋——只记录、不改变候选集。

**吃子点**（`capture_points_from_mask`，与威胁线相关的黑块）：

* 气 == 1 的黑块：唯一气点（白棋 1 手直接提子）；
* 气 == 2 的黑块：两个气点（落子后该块变 1 气，下一步可提）——但必须满足
  “落子后黑棋 2 步内不能连五”（`black_five_within_two`：盘上不得有一步成五或成活四的点），
  否则该吃子点无效。

**候选集（交集框架）**：`rep.lines` 里所有威胁线的阻挡点取**交集**；交集为空时按规格
回退到**并集**（`intersect_empty = true`），并并入必须阻挡点与吃子点。
“强迫威胁”只认**一手成活四 / 成五**的线（规格里的实心圆 / 三角形一档：五连、活四、四三）：
只有冲四 / 眠三一档时白棋不被强迫，候选集退化为**不受约束**（全盘空点）。

### 第二部分：三层 VCT（参数 `VctParams`）

| 层 | 步数参数 | 语义 | 可靠性 |
| --- | --- | --- | --- |
| VC | `vc = 1` | 黑落子至少形成活二 / 眠三（最浅层筛查） | — |
| VCT | `vct = 18` | 黑落子至少形成活三 / 做杀（四三；无禁手时三三、四四） | 层 2 完备但不可靠 |
| VCF | `vcf = 180` | 黑落子形成冲四 | 层 1 可靠但不完备 |

`analyse(..., const VctParams& params = VctParams())` 的缺省值就是上表；`candidates`
命令的 `steps` 参数覆盖 VCT 层预算（`main.cpp` 缺省 11）。预算落地在
`layer_attacks()`：四类手要求剩余步数 ≤ `vcf`，三类手要求 ≤ `vct`。

* **层 1 全应对 VCT**（`vct_all_response`）：黑棋只走威胁手；白棋在该手威胁线的**全部
  阻挡点 ∪ 吃子点**应对（`layer_responses`）。黑方节点是存在量词 ⇒ **胜即真胜**
  （威胁空间内应对集完备），但黑方手受限 ⇒ 不完备。
* **层 2 智能应对 VCT**（`vct_smart_response`）：白棋只在候选点内选**一个**应手
  （`smart_responses`）：① 能吃子防守且吃后原有威胁不残留眠三 → 选吃子；
  ② 否则比较各阻挡点，取“白棋落子后黑棋眠三最少、其次活二最少”的一个
  （“挡成死三优先”，`010110` 走中间 / `01110` 挡成死三都被这条比较规则覆盖）。
  完备但不可靠，只用于交叉校验。
* **混合判定**（`mixed_defense_intersection`）：全应对显示无必胜、智能应对显示有必胜时，
  枚举白棋所有应对，取“可靠 VCT 的防御点位集合”的交集作为候选点；无交集则交给
  最大步数标注。`analyse` 的白方分支里，健全 AND-OR 证明搜索的步数**优先**作为权威
  标注（它与吃子反驳一致，是“宁可漏标”的那一套），层 1 / 层 2 的步数在证明搜索
  未成功时兜底。
* **minimax 收尾**（第二部分 2.4）：取完最好一档后若仍多于一个候选点，用窄深
  alpha-beta（`alphabeta(b, 2, ...)`，每个候选 ≤ 5% 剩余时间）从黑方视角选最小者。

### 集合存储接口（供后续 Rapfi 式必胜搜索）

```cpp
struct DefenseSet {                    // 一轮的全部应对点
    std::vector<Pt> points;            // 本轮白棋应对（阻挡点 ∪ 吃子点）
    int bx, by;                        // 产生该应对集的黑棋威胁手
    int rank;                          // 该手威胁等级（AtkType）
};
struct VctRoute {                      // 一条被证明成功的路线
    std::vector<Pt> black_moves;       // 黑攻击手序列
    std::vector<DefenseSet> sets;      // 逐轮应对集（可平移、可判定无效防御）
};
struct VctOutcome {
    bool win; int steps; bool timeout;
    std::vector<DefenseSet> first_sets; // 全部成功路线的**首轮**应对集（取交集 = 候选点）
    std::vector<VctRoute> routes;       // 成功路线
};
```

本轮只做数据结构与填充（`vct_all_response` / `vct_smart_response` 都会填
`first_sets` 与 `routes`），不做查表匹配；`VctRoute` 的后续轮次按“第一条成功应手”
的代表分支记录。

### 验收结果

`cmd /c cpp\build.bat` → `[build] ok: build\engine.exe`（0 error）。

`py cpp/tests/forbid_cases.py`（导出/粘贴板.md 末尾三块，`candidates w 11 10`）：

```
[cases] 导入 3 个用例块
  [case#1] 候选点 1 个  用时 0.04s  期望=['h9']
    [inv] 不变式 OK：白落任一候选点后黑棋 2 步内不能连五
  [case#2] 候选点 221 个  (everywhere: 全盘 221 空点)  用时 0.19s
  [case#3] 候选点 1 个  用时 0.04s  期望=['g8']
    [inv] 不变式 OK：白落任一候选点后黑棋 2 步内不能连五
[timing] 禁手/摆子步骤全部 ≤ 0.20s
用例块=3  候选点块=3  等价组=0  全部通过 PASS
```

* (a) `h8 p0 h7 p0 h6 p0 i8 p0 j7` → **恰为 {h9}**（`cand 6 7 L8`）：h9 既是列 h 活三的
  阻挡点，又是 j7/i8 斜线的成三点 = 双威胁必须阻挡点；h5 同是列 h 的阻挡点，但白占
  h5 后黑 h9 成四三必胜（L6 < L8），被“取最好一档”排除。
* (b) `h8 p0 g7 p0 j10 p0 l12` → **everywhere**：盘上没有“一手成活四 / 成五”的强迫威胁
  （黑四子在同一条斜线上但引擎判成冲四档），候选集 = 全盘 221 个空点（W0）。
* (c) `g9 h9 f10 i8 g10 p0 g11 p0 e11 c13 p0` → **恰为 {g8}**（`cand 7 6 L8`）：两个活三
  （列 g、斜线 (1,1)）的阻挡点交集为空 → 回退并集 {g12, g8, d12, h8, i7}；
  白占 g8 后黑方要 4 手才证明得出（L8，白可提 (7,7) 那手），其余点 L4 ⇒ 只留 g8。

三个用例的 `candidates` 命令用时 0.04 / 0.19 / 0.04 s（≤ 5 s）。

回归（全部 PASS）：`diff_forbidden.py`、`diff_eval.py`、`engine_protocol.py`、
`search_sanity.py`、`tactics.py`。

### `candidates w` 语义升级对 `tactics.py` 的影响（3 处候选断言）

1. **T2**（吃子反驳）：旧断言“白方 (7,8) 必须没有标注”；新语义下 (7,8) 同时是阻挡点与
   提子点，**必须**出现在候选集里——改为断言“是候选点且不得为 L”（原意不变：提子点
   不能是白方必败点）。
2. **T8**（胜点验证）：旧断言“白方候选 ≥ 40 个且 (0,2)/(7,5)/(7,9)/(9,7)/(7,4) 全为 L”；
   新语义下候选集是黑方双威胁的阻挡点 {(5,7),(9,7),(7,5),(7,9)} 的“最好一档”——改为
   断言“候选数 1..8、全部落在这些阻挡点内、且全为 L”。
3. **T2/T5/T8 的通用 A2 断言**：白方 W0 现在表示“黑方在预算内证明不出必胜”（旧语义
   白方候选只可能是 L），故改为“落子合法 + 抽查前 3 个点 prove 不成 win”。

---

## 三档禁手开关（本轮补齐，`forbid` 命令）

用户规格：“不开禁手时三三、四四也是[做杀]”。原来三个复选框只作用于 Python 侧
（`rules.py` 的 `_forbid_overline/_forbid_44/_forbid_33`），C++ 引擎无论怎么设都按
renju 三禁判定（蓝色叉、`checkforbidden`、`gen_moves` 全都不受影响）。现在：

* `Board` 增加三个开关（默认全开）与 `set_forbid(o,44,33)`；改开关会立刻
  `refresh_patterns_full()` 重算全部 `p4_black_` 预筛标记，因为“四方向组合线型”本身
  就是按禁手规则合成的（`combine_pattern4_flags`：关掉的那一档不再标 `FORBID`，
  例如三三退回 `F_FLEX3_2X`）。
* `check_forbidden_impl` / `probe_forbidden` 按开关跳过对应判定；另外补上了
  “真长连 vs Rapfi 一线双四（都用 `OL` 编码）”的区分：落子前先量穿过该点的连续黑子数
  （`run_through`，纯读盘），`run >= 6` 才是长连（受长连开关管），否则按 `fours += 2`
  计——与 `rules.py` 的 `_rapfi_verdict` 完全同口径。
* `double_threat_points`（双威胁必须阻挡点）现在按“做杀”三类判定：四三恒算；
  三三只在**三三禁手关闭**时算；四四只在**四四禁手关闭**时算。
* 协议新增 `forbid <长连> <四四> <三三>`（0/1，默认全开，不改棋盘/哈希），
  `engine_client.py` 的 `reset` / `forbidden_points` 会带上 GUI 当前的三个复选框；
  诊断命令 `wcand` 直接打印 `WhiteCandidateReport`（威胁线 / 每线阻挡点 / 必须阻挡点 /
  吃子点 / 交集或并集后的候选池），用于核对用户规格里的阻挡点查表：

  | 线型 | 规格 | `wcand` 实测（row 7） |
  | --- | --- | --- |
  | `10111` | 1 | `{6}` |
  | `011112` | 1 | `{4}` |
  | `0011102` | 3 | `{4,5,9}` |
  | `0011100` | 2 | `{5,9}` |
  | `010110` | 3 | `{4,6,9}` |

验收：`py cpp/tests/forbid_switches.py` → 8 种开关组合 × 16 个局面 = 128 次比对，
引擎与 `rules.py` **0 不一致**（PASS）。其余回归（`forbid_cases` / `diff_forbidden` /
`engine_protocol` / `diff_eval` / `search_sanity` / `tactics` / `tests_torus`）全部通过。


