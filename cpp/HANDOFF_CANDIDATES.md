# 候选点算法完成交接（第 8 步，2026-10-06）

## 本轮已完成（用户冻结语义全部落地）

**候选点语义**：候选点 = 使黑棋 2 步内无法连五的点位（无禁手开关时三三也算胜）。
手段：直接阻挡 / 吃子 / 构造无气 / （禁手阻挡并入试落判定）；覆盖活三、冲四、做杀
（四三；无禁手时三三、四四）。实现迁移自 Rapfi：game/pattern.cpp 的 DEFENCE 防守
掩码思想（防守子试落后攻击方线型 < F3）+ game/movegen.cpp 的 findFourDefence /
findB4F3Defence / findFlex4LineDefence。

**新算法**（vcfvct.cpp 第 3 节，全部重写）：
1. `scan_black_threats`：全盘 O(n²)×4 查表扫描黑棋"强迫威胁点"，按方向线型分类：
   - kind 0 成五点（某方向 F5，盘上有四）：防御 = 成五点 ∪ 吃子（10111→1 点）；
   - kind 1 杀点（活四/双四成分参与的立即胜：F4∧三/四、双活四、双冲四、三三[关]）：
     防御 = 杀点本身 ∪ 吃子 ∪ 无气构造（活四不可挡，占位/降级探针无效 → 用例 a={h9}）；
   - kind 2 四三杀点（B4∧F3）：防御 = 杀点 ∪ 活三线"线型降级"探针（<F3）∪ 冲四线
     成五点 ∪ 吃子/无气构造（用例 #4={h9,h10,g10,k6}）；
   - kind 3 纯活四点（单方向 F4，活三端点）：防御 = 该线试落阻挡点 ∪ 吃子/无气构造
     （用例 #5={h9,h5}；用例 c 三威胁交集={g8}）。
   - 纯冲四点（单方向 B4）/ 纯活三点**不是**强迫威胁 → 不产生候选（用例 b=everywhere）。
   - p4==FORBID 且 check_forbidden 为真的真禁手点跳过；假禁手点照常分类。
2. `line_defense_points`（试落阻挡）：白棋真实 make_move（含提子/无气翻转）后线上
   不再有"黑棋可落的 F5/F4 制造点"（制造点本身禁手/自杀的算假威胁）。只探测线上
   黑子 ±5 窗口内的空点。用户规格查表逐条复现：10111/011112→1；0011102→3；
   0011100→紧邻 2。
3. `self_capture_defense`（无气构造）：黑棋落威胁点后其块气恰 1/2 时的气点
   （1 气：q 自填即被提；2 气：白占一气后下一手提）——用例 c 的 g8 即此机制。
4. `threat_captures`：威胁相关黑块（威胁方向线 ±5 内黑子）的 1 气提子点 + 2 气点
   （带 black_five_within_two 守卫）。
5. `white_threat_candidates`：候选 = 所有威胁防御集的**交集**；交集为空回退**并集**
   （黑棋多重杀，白棋已不可挡）；无威胁 → unconstrained（全盘空点）。

**停用封存**（vcfvct.cpp 内 `#if 0` 块，源码保留不编译）：第 7 步的威胁线查表阻挡点
（line_threat_rank/line_still_winning/line_blockers/collect_threat_lines/
threat_lines_through）、双威胁必须阻挡点（double_threat_points）、阻挡点禁手说明、
三层 VCT（layer_* / vct_all_response / vct_smart_response / mixed_defense_intersection）、
禁手消失判定（collect_real_33/creates_new_black_33）、白方逐点 W/L 标注路径
（sound_lose_steps + analyse 白分支旧体 → analyse_white_legacy）。
vcfvct.h 中三者的声明保留（无定义，调用即链接失败），已加注释。

**协议变化**：`candidates w` 输出三列 `cand x y`（无 W/L 标注，tag=0）；黑方
`candidates b` 输出不变（仍只输出有标注的行，tag==0 跳过）。GUI：engine_client.py
接受 3/4 列（tag=None），gui.py 角标文字跳过 tag=None。

## 验收结果（全部通过）
- 粘贴板 5 用例（forbid_cases.py）：a→{h9}、b→everywhere(221)、c→{g8}、
  #4→{g10,h10,h9,k6}、#5→{h5,h9}；逐点 prove-2 不变式 OK；单块用时 ≤0.05s。
- 回归：tactics.py（66 断言）、engine_protocol.py（43）、forbid_switches.py（136 组合）、
  diff_forbidden.py、diff_eval.py、search_sanity.py、tests_torus.py 全部 PASS。

## 下一会话从这里继续：rapfi 式逐节点搜索（用户主线任务）
1. 读 rapfi search/（searchengine.cpp / searchthread.cpp / movepick.cpp）与
   game/wincheck.h（quickWinCheck 静态杀）+ game/board.h 的 p4Count/StateInfo，
   规划迁移：PVS/alpha-beta 逐节点 + 置换表 + quickWinCheck + movegen 分层
   （WINNING/VCF/VCT/VC2/DEFEND_*），替换本项目的证明级 AND-OR 搜索与 gen_moves。
2. 本项目的混合规则差异点（迁移时必须保留）：白棋吃子/黑棋无气自杀（make_move）、
   无气空点=阻挡（棋型层已统一）、白棋不能连五只能封堵（winmode line_block）、
   禁手三开关（forbid 命令）、环面模式（board 支持，rapfi 没有）。
3. 候选点算法（本轮产出）作为白方防御集生成器/着法排序的底层件直接复用。
4. 工具脚本：cpp/tests/_run_paste_cases.py（5 用例快速复核 cand/wcand）、
   cpp/tests/_pat_probe.py（pat 棋型探针）。
