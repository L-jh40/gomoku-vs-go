# 候选点算法收尾交接（下一会话从这里继续）

## 用户冻结的语义
候选点 = 使黑棋 2 步内无法连五的点位（无禁手开关时三三也算胜）。手段：阻挡/吃子/构造无气/构造禁手；覆盖活三/冲四/做杀。
查表规则：阻挡点 = 线上"黑落成五或成四"的空点（10111/011112→1 点；0011102→3 点；0011100→紧邻 2 点）。
双威胁必须阻挡：活三∧活二并存时"成活四∧成活三"点（无禁手时含 33/44 maker）。
快速通道：白落子不影响禁手集合时跳过禁手重算。

## 已完成
- line_blockers 已改查表规则（vcfvct.cpp，已编译）：阻挡点=point_pattern_d ∈ {PP_FIVE,PP_FLEX4,PP_B4}。
- 实测：用例 a → {h9}✓；基础活三 → 仍只出一端 (8,4)✗。

## 剩余 bug 精确定位（已验证的事实）
1. vcfvct.cpp `analyse` 白方 constrained 分支（`struct Row` 起，约 1396 行）：
   每候选跑 sound_lose_steps + 三层 VCT 打 L/W 标签，然后"取最好的一档"收窄
   （sort：W 优先、L 步数降序，只保留与首行同 tag 同 steps 的行）+ minimax 收尾。
   基础活三两端证明深度不同（一端 L8 一端 L6/W0）→ 收窄丢掉另一端。
2. 修复方向（用户指令：停用候选路径的 W/L 引擎）：
   白方 constrained 分支整体替换为：`res.labels = pool 逐点 {tag=0, steps=0}`，
   直接返回（删除 Row 循环/排序/收窄/minimax）。
3. main.cpp candidates 打印处（约 231 行）有 `if (lab.tag == 0) continue;` ——
   必须改为 tag==0 时输出三列 `cand x y`（否则新标签全被吞）。
   注意：main.cpp 与 vcfvct.cpp 的上述两处改动要**同一批**做（上次只改 main.cpp
   导致 build 失败，已 git checkout 恢复）。
4. splice 技巧：vcfvct.cpp 的替换用 `s.find(marker, start)`（带 start 偏移），
   `"    res.paths_found"` 在 unconstrained 分支（51335）先出现，不带 start 会错位。

## 验收清单
- 基础活三（set 8 5/6/7 b）→ cand 恰 {(8,4),(8,8)}（两端）。
- 粘贴板 3 用例：a→{h9}、b→everywhere、c→{g8}；用户更新的 #4 → {g10,h10,h9,k6}
  （若不符：查表集与证明式语义的差 = 待与用户核对的点）。
- runner（py -3.14 cpp/tests/forbid_cases.py）：候选块精确相等 + 2 步不变式逐点复核。
- 回归：diff_forbidden、engine_protocol（vcfvct 黑方分支未动应不受影响）。
- GUI：候选方块数据源已改为引擎输出（engine_labels_done 标志机制），无需再动。
