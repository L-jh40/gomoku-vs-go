# cpp/engine — 五子棋(黑) vs 围棋(白) 混合规则 C++ 引擎

五子棋(黑) vs 围棋(白)混合规则 C++ 引擎 —— make/undo 增量引擎 + Rapfi 禁手移植 +
字典序元组评估 + alpha-beta 搜索 + VCF/VCT 威胁搜索 + W/L 标注。

完整技术细节见 [`IMPLEMENTATION.md`](IMPLEMENTATION.md)。

## 构建与运行

```bat
cmd /c cpp\build.bat          :: 编译 cpp\src\*.cpp -> cpp\build\engine.exe
cpp\build\engine.exe          :: 启动引擎（stdin 读命令、stdout 逐行输出并 flush）
```

`build.bat` 调用本机 MSVC 的 `vcvars64.bat`，以
`cl /nologo /utf-8 /EHsc /O2 /std:c++17 /MT` 编译 `src\*.cpp`。

## 命令速查

| 命令 | 参数 | 功能 | 输出 |
| --- | --- | --- | --- |
| `size` | `<n>`（9..19 奇数） | 重置 n×n 空盘并清空置换表 | 无 |
| `set` | `<x> <y> <b\|w\|o>` | 直接摆子（`o`=障碍），不提子、不换回合 | 无 |
| `clear` | 无 | 清空棋盘 | 无 |
| `checkforbidden` | 无 | 所有黑棋非法点（禁手 ∪ 无气自杀） | 每行 `x y`，末尾 `end` |
| `play` | `<b\|w> <x> <y>` | 正式落子（白提黑、黑自杀拒绝） | `ok` / `illegal` |
| `undo` | 无 | 悔一步 | `ok` / `err`（空历史 `err`） |
| `hash` | 无 | 当前局面 Zobrist | 16 位十六进制 |
| `eval` | 无 | 打包评估（只评估不搜索） | `eval <packed> F1=.. F5=.. risk=.. terr=..` |
| `counters` | 无 | 六类线型计数 / 风险 / 领地 | `cnt b=.. w=.. risk=<n> terr=<n>` |
| `winmode` | `<0\|1>` | 胜负模式（0=line_block，1=occupy） | 无 |
| `genmove` | `<b\|w> [max_depth] [min_sec] [max_sec] [winmode]` | 迭代加深搜索，不落子 | `info depth <d> move <x> <y> score <packed>` 若干行 + `move <x> <y>` / `pass` / `resign` |
| `candidates` | `<b\|w> [steps=11] [max_sec=10] [winmode=0]` | 候选点 VCF/VCT W/L 标注 | `cand <x> <y> <W\|L><steps>` 若干行 + 可选 `timeout` + `end` |
| `quit` | 无 | 退出 | 无 |

其余命令（`move` / `dump` / `pat` / `bencheval` / `searchstat`）见
[`IMPLEMENTATION.md`](IMPLEMENTATION.md) 的命令表。

## 测试

在仓库根目录运行：

```bat
py cpp\tests\engine_protocol.py    :: 命令行协议回归（43 条断言）
py cpp\tests\diff_forbidden.py     :: 黑棋禁手差分 + make/undo 压力
py cpp\tests\diff_eval.py          :: 增量评估 counters/eval 差分
py cpp\tests\search_sanity.py      :: alpha-beta 搜索健全性
py cpp\tests\tactics.py            :: VCF/VCT + W/L 战术用例
```

## 交互示例（真实会话原文）

启动 `cpp\build\engine.exe`，依次输入以下 6 行：

```text
size 15
play b 7 7
play w 8 8
genmove b 2 0 5
candidates b 11 5
quit
```

引擎 stdout 原文（`size`/`quit` 无输出，故首两行是两次 `play` 的回执）：

```text
ok
ok
info depth 0 move 7 8 score -8589932545
info depth 2 move 7 8 score -8589930497
move 7 8
cand 7 8 W7
cand 7 9 W7
cand 8 7 W7
cand 9 7 W7
cand 5 7 W7
cand 5 9 W7
cand 6 7 W7
cand 6 8 W7
cand 7 5 W7
cand 7 6 W7
cand 8 6 W7
cand 9 5 W7
end
```

含义：黑 (7,7)、白 (8,8) 各落一子后，`genmove b 2 0 5` 迭代加深到 depth 2 给出
`move 7 8`；`candidates b 11 5` 对候选点做 VCF/VCT 标注，列出了 12 个 7 手内
黑方必胜（`W7`）的点，以 `end` 结束。

## 已知限制

1. **线式必胜判定偏乐观**：路径枚举只要收到一条路径就标注，不要求白方每个应手都输。
2. **攻击候选不查禁手**：搜索内部攻击手只按 `attack_class` 枚举，不查 `check_forbidden`。
3. **超时截断漏标注**：`nodes > 300000` 或超过 `max_sec` 时后续候选保持无标注（宁可漏标）。
4. **GUI 未接入**：只有 stdin/stdout 命令行协议。

细节与更多说明见 [`IMPLEMENTATION.md`](IMPLEMENTATION.md)。
