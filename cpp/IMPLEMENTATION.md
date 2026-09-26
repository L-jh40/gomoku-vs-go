# C++ 混合规则引擎（第一步：棋盘 + 黑棋禁手）

本目录用 C++17 从零实现「五子棋(黑) vs 围棋(白)」混合规则引擎的第一部分：
可 make/undo 的棋盘，以及移植自 Rapfi 的黑棋禁手判定。不含搜索 / 评估 / GUI。

## 目录与职责

| 文件 | 职责 |
| --- | --- |
| `src/board.h` / `src/board.cpp` | `Board` 类：19×19 上限的 `uint8` 棋盘、历史栈、白提黑、黑自杀拒绝、Zobrist 哈希、障碍摆放。 |
| `src/forbidden.h` / `src/forbidden.cpp` | `check_forbidden(board,x,y)`：黑棋长连 / 四四 / 三三禁手判定；线型分类查表；`probe_forbidden` 诊断接口。 |
| `src/main.cpp` | 命令行循环（逐行读、逐行 flush），协议见下。 |
| `build.bat` | 调用指定路径的 `vcvars64.bat`，用 `cl /std:c++17 /O2 /MT` 编译 `src\*.cpp` 到 `build\engine.exe`。 |
| `tests/diff_forbidden.py` | 与 Python `board.HybridBoard` + `rules.is_black_legal_move` 的差分测试，以及 make/undo 压力测试。 |
| `tests/verify_rapfi.py` | 交叉验证：用独立重实现的 Rapfi 判定与引擎 `checkforbidden` 逐点比较。 |

## 构建与运行

```bat
cmd /c cpp\build.bat
py cpp\tests\diff_forbidden.py
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
size <n>             9..19 奇数，重置空盘
set <x> <y> <b|w|o>  摆子（o=障碍），不提子、不换回合
clear                清空棋盘
checkforbidden       输出所有黑棋非法点(禁手+自杀)，每行 "x y"，末尾 end
quit                 退出
move <x> <y> <b|w>   正式落子(白提黑、黑自杀拒绝)，输出 ok / err
undo                 悔一步，输出 ok / err
hash                 输出 16 位十六进制 Zobrist
dump                 输出 size 行、每行 size 个格子值(0..3)
pat <x> <y>          诊断：输出四方向线型、组合线型、四数、真三数、是否禁手
```

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
