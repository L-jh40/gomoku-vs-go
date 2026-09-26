# C++ 混合规则引擎（棋盘 + 黑棋禁手 + 增量评估 + alpha-beta 搜索）

## 总览与快速上手

**一句话定位**：五子棋(黑) vs 围棋(白)混合规则 C++ 引擎 —— make/undo 增量引擎 +
Rapfi 禁手移植 + 字典序元组评估 + alpha-beta 搜索 + VCF/VCT 威胁搜索 + W/L 标注。

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
| `play` | `<b\|w> <x> <y>` | 正式落子（白提黑、黑自杀拒绝），不自动换回合语义由 `make_move` 决定 | `ok` / `illegal` |
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
| `tests/tactics.py` | VCF/VCT 威胁搜索 + W/L 标注的战术用例（T1..T8，33 条断言）。 | `py cpp\tests\tactics.py` |

### 四条已知限制

1. **线式必胜判定偏乐观**：VCF/VCT 的路径枚举是“线式”的 —— 收到一条路径只说明
   “存在某个白应手序列让黑方成五”，并不要求白方每个应手都输；三的防御集取超集
   只保证不遗漏真实防守，判定“必胜”时不做全分支 AND。实测反例：任务书 T5 局面
   `candidates w 11` 会把白 (7,7) 标成 `L6`。
2. **攻击候选不查禁手**：根候选来自 `gen_moves`（黑方已过滤禁手与自杀点），但搜索
   内部的攻击手只按 `attack_class` 枚举，不查 `check_forbidden`，极小概率枚举到
   黑方实际不能走的禁手攻击手，分析结果偏乐观。
3. **超时截断漏标注**：`nodes > 300000` 或超过 `max_sec` 时 `AnalysisResult::timeout = true`，
   正在搜索的候选与之后所有候选都保持无标注（宁可漏标，不可错标），并追加一行 `timeout`。
4. **GUI 未接入**：引擎只提供 stdin/stdout 命令行协议，尚未接入任何图形界面。

> 本节是总览与快速上手；技术细节若与下文“分步实现记录”冲突，**以下文为准**。

本目录用 C++17 从零实现「五子棋(黑) vs 围棋(白)」混合规则引擎：可 make/undo 的
棋盘、移植自 Rapfi 的黑棋禁手判定、随 make/undo 增量维护的评估计数器，以及在
此之上的 alpha-beta 搜索（negamax + 置换表 + 着法排序 + 迭代加深）。不含
VCF/VCT、不做 W/L 标注、不含 GUI。

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


## VCF/VCT 与 W/L 标注（第 4 步，`cpp/src/vcfvct.*`、`candidates` 命令）

黑方（攻击方）的威胁空间搜索：枚举“四/活三/成五”攻击手，白方按防御集合应手，
走到黑方成五即为一条必胜路径。全程 `make_move`/`undo_move`，不拷贝棋盘；
所有排序都用 `(威胁等级, order_score, x, y)` 全序，输出确定（同局面同参数两次
运行逐字节一致，测试里有断言）。

### 威胁级别与防御集合

* `attack_class(b,x,y)`：把空点当黑子，用与禁手判定/`order_score` 相同的
  `classify_point` 四方向线型求最强级别：
  `FIVE > OPEN_FOUR(F4) > RUSH_FOUR(B4/B4S) > OPEN_THREE(F3/F3S) > NONE`。
  合法黑棋不可能同时有两个方向的四（四四禁手），故“任一方向”语义安全。
* `scan_four_windows`：全盘 4 方向 × 所有盘内 5 连窗，取“4 黑 + 1 空 + 0 白/障碍”
  的窗的唯一空点 = 完成点。
* `scan_capture_points`：局部 flood fill 求每个黑块的气，气数 == 1 的黑块，其唯一
  气点就是白方的提子点（白下这里整块提走）。
* **四的防御集是精确集合**：`white_defense_for_fours = 完成点 ∪ 提子点`。
  证明：白下集合外的点既没有占住任何四窗的完成点，也没有减少任何“仅剩一口气”
  黑块的气，于是黑方仍可把某个四窗补成恰五（恰五优先于长连判定，黑方此手合法）
  —— 即“白下集合外黑下一步即成五”。所以黑方若能在该集合的**每个**元素之后
  仍成五，就是真必胜。
* **三的防御集是超集**：`white_defense_for_threes = 四防御集 ∪ {经过落点的 5 窗中
  “无白无障碍且黑子数 ≥ 2”的窗的全部空点} ∪ 提子点`。三没有“一步不挡就输”的
  精确集（白可以脱先），因此必须取超集：集合越大越保守，只要黑方对集合内每个
  应手都能成五，真实防守（⊆ 超集）自然也挡不住 —— “宁可多试白应手，不可漏真实
  防御”。

### 搜索与判定

* `black_attacks`（VCF/VCT 共用内核）：候选 = 已有黑子切比雪夫距离 ≤ 4 的空点里
  `attack_class` 达标的点；排序 `OPEN_FOUR > RUSH_FOUR > OPEN_THREE`，同类按
  `order_score(b,x,BLACK)` 降序。必做剪枝：四（该手不成五）且剩余手数 < 2 剪掉，
  活三且剩余手数 < 3 剪掉。每个候选落子后按“是否含四成分”选防御集（2.8.2），
  把 `(黑手, 白方全部应手集合)` 记进 `WinPath`，逐个白应手递归，成五/白方无应手
  时收一条路径。
* `analyse`：对 `gen_moves(color)` 的每个候选 c，先落 c；黑方恰五 → `W1`；
  白方已达成胜利条件 → 无标注；否则从 c 之后的局面枚举黑方必胜路径
  （黑候选时 c 记入 `black_moves[0]`）。
* **步数公式**：`m` = 路径里黑方攻击手数。黑候选 c 是第 1 手，黑第 m 手成五落在
  总第 `2m-1` 手 → `W = 2m-1`；白候选是第 1 手，黑第 m 手成五落在总第 `2m` 手
  → `L = 2m`（白应手不消耗 m）。
* **U(P) 与交集**：`U(P) = ∪_i (black_moves[i] ∪ defense_sets[i])`，即一条路径上
  黑方落点 ∪ 各步白方防御集合的并。白候选 c 只有在存在某条路径 P 使 `c ∉ U(P)`
  时才标 L（否则 c 出现在所有路径的 U 里，可能真的防住了）。实现中 c 已落在盘上，
  而 U(P) 的元素都是空点，故该过滤对白候选恒为真（保留了规格语义与代码结构）。
* **迭代加深**：每个候选从 `budget = 1` 起递增调用枚举（黑候选用 `budget-1`，
  白候选用 `budget`），取第一个能收成路径的预算下的最短路径手数。小预算树小，
  不会被 `PathCollector` 的 200 条上限截断，避免步数系统性偏大；同时比直接跑
  最大预算更快（实测 T4 局面 `candidates b 11` 从 1.3s 降到 0.31s）。

### `candidates` 命令

```
candidates <b|w> [steps=11] [max_sec=10] [winmode=0]
```
对 `gen_moves(color)` 的每个候选输出一行 `cand <x> <y> <tag><steps>`
（`tag` 为 `W`/`L`，`steps` 见上式；无标注的候选不输出），超时/节点上限截断时
追加一行 `timeout`，最后一行 `end`；若 `analyse` 后 `hash()` 与进入时不同则只输出
`error hash`（正常情况不会发生）。

### 健全性与已知限制

1. **超时/节点上限截断后无标注**：`nodes > 300000` 或超过 `max_sec` 时
   `AnalysisResult::timeout = true`，正在搜索的候选与之后所有候选都保持无标注
   （宁可漏标，不可错标）。
2. **路径枚举是“线式”的**：收到一条路径只说明“存在某个白应手序列让黑方成五”，
   不保证白方**每个**应手都输。产生超集防御集的做法只保证不遗漏真实防守，但判定
   “该候选必胜”时并不要求遍历集合内每个分支都成立。实测反例：任务书 T5 局面
   `candidates w 11` 会把白 (7,7) 标成 `L6`（白方真正的防守点 (7,5)/(4,5) 等
   在防御集合内，黑方对集合内其它点仍能成五，于是枚举到路径就出了标注）。
   若要严格“必胜”语义，需要把判定改成对每个白应手的 AND（minimax 手数）——
   代码里 2.9 的注释与本次交付报告都记了这条后续工作；当前实现按任务书
   2.10 的“paths 非空即标注”公式。
3. **三三/四四禁手只作用于根候选**：根候选来自 `gen_moves`（黑方已过滤禁手与
   自杀点），但搜索内部的攻击手只按 `attack_class` 枚举，不查 `check_forbidden`
   —— 与任务书 2.7/2.8 的候选定义一致；代价是极小概率枚举到“黑方实际不能走”
   的禁手攻击手（例如三三形态），分析结果偏乐观。
4. **黑方长连**：攻击枚举只把 `F5`（恰五）当胜利；`OL`（长连）不产生 `F5`
   也不进攻击集合，符合“长连是禁手、不是胜利”。
5. `vcf_exists` / `vct_exists` 是库内调试/测试接口（纯 VCF / VCT 是否存在必胜），
   当前未挂 CLI 命令；实测：黑活四局面 `vcf=vct=1`，T4 双三局面 `vcf=0/vct=1`，
   单子局面 `0/0`。

### 战术验收（`cpp/tests/tactics.py`）

8 个用例（即时成五、吃子反驳、真四不可吃、双三 VCT、L 标注、障碍、无副作用、
胜点交叉验证）共 33 条断言，`py cpp/tests/tactics.py` 输出：

```
战术用例断言=33  失败=0  用时=2.38s
PASS
```

其中 T2（吃子反驳）是核心回归：黑 (7,5)(7,6)(7,7) 被白 (6,5)(8,5)(6,6)(8,6)
(6,7)(8,7)(6,4)(8,4)(7,3) 贴住后只剩 (7,4)/(7,8) 两口气。黑走 (7,4) 时该块只剩
一口气 (7,8)，`scan_capture_points` 把 (7,8) 放进白的防御集，白 (7,8) 提掉整块四，
黑方后续没有任何黑子，枚举不到路径 → (7,4) 无 W 标注。如果防御集漏掉提子点，
(7,4) 会被错标成 W1。
