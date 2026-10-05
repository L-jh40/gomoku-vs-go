# daoqi_katago - 道棋（环面围棋）KataGo 引擎

本目录存放 `../daoqi_gui.py`（道棋对弈观察窗口）所需的全部引擎文件。git 不
跟踪大二进制；换机器时按下面的来源重新下载放进本目录即可（目录名固定
`daoqi_katago`）。

## 文件与来源

| 文件 | 来源 |
|------|------|
| `model.bin.gz` | 道棋神经网络 `DAOQI-daoqi-s60820864-d11149172`（v10 格式，23.4M 参数），取自 <https://github.com/daoqiclub/katrain_daoqi>（`katrain/models/model.bin.gz`，道棋俱乐部官方训练） |
| `katago_opencl.exe` + `katago_eigen.exe` | KataGo 官方 v1.18.1 release <https://github.com/lightvector/KataGo/releases>（OpenCL / Eigen Windows x64 版；`daoqiclub/katrain_daoqi` 仓库里捆绑的是 Linux 版，Windows 用不了） |
| `gtp_daoqi.cfg` | GTP 模式配置（键集照抄官方 gtp_example.cfg——GTP 模式要求 `rules`/`logAllGTPCommunication` 等键；`reportAnalysisWinratesAs = BLACK` 使胜率/目差固定黑方视角，`allowResignation=false` 便于观战） |
| `analysis_daoqi.cfg` | analysis 协议配置（备用，`daoqi_gui.py` 不使用） |
| `*.dll` | VC++ / OpenCL 运行库 |

## 运行方式

`python ../daoqi_gui.py` —— UI 通过 **GTP 协议**驱动引擎：

- 规则全部由引擎执行：`play` / `kata-genmove_analyze` / `undo` /
  `play <c> pass` / `final_score`（chinese 规则 = 提子、禁自杀、全局禁同形）
- 棋盘状态以引擎 `showboard` 为唯一事实源，UI 不含任何围棋规则代码
- 对局空闲时引擎保持 `kata-analyze` 实时流：黑方胜率 / 目差 / 候选点胜率
- 道棋的环面特性来自网络权重（在平铺棋盘上训练的环面围棋），引擎按 chinese
  规则在 n×n 棋面上执行提子与禁同形

## 首次运行

OpenCL 版第一次启动会做一次 GPU 自动调优（本机 Intel UHD 约 4 分钟），结果
缓存在 `KataGoData/`，之后启动约 20 秒、AI 每手亚秒级。若无显卡或调优失败，
`daoqi_gui.py` 会自动回退 Eigen（CPU）版。

手动验证引擎（可选）：

```bat
katago_opencl.exe gtp -model model.bin.gz -config gtp_daoqi.cfg
```

出现提示符后输入 `version`，回显 `= 1.18.1+DAOQI-daoqi-...` 即正常。
