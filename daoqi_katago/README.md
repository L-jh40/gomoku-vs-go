# daoqi_katago - 道棋（环面围棋）KataGo 引擎

本目录存放"道棋AI（环面·KataGo）"所需的全部引擎文件。git 不跟踪大二进制；
换机器时按下面的来源重新下载放进本目录即可（目录名固定 `daoqi_katago`）。

## 文件与来源

| 文件 | 来源 |
|------|------|
| `model.bin.gz` | 道棋神经网络 `DAOQI-daoqi-s60820864-d11149172`（v10 格式，23.4M 参数），取自 <https://github.com/daoqiclub/katrain_daoqi>（`katrain/models/model.bin.gz`，道棋俱乐部官方训练） |
| `katago_opencl.exe` + `katago_eigen.exe` | KataGo 官方 v1.18.1 release <https://github.com/lightvector/KataGo/releases>（OpenCL / Eigen Windows x64 版；`daoqiclub/katrain_daoqi` 仓库里捆绑的是 Linux 版，Windows 用不了） |
| `analysis_daoqi.cfg` | 本项目改写的 analysis 服务配置（基于 KataGo v1.18 的 analysis_example.cfg + 道棋版 KaTrain 的设置：`reportAnalysisWinratesAs = BLACK`、`nnRandomize`、`conservativePass`） |
| `*.dll` | VC++ / OpenCL 运行库（官方 zip 与 katrain_daoqi 仓库各一份，取并集） |

引擎通过 KataGo 的 **analysis 协议**（stdin/stdout JSON）驱动，由上级目录的
`katago_client.py` 封装；GUI 的「道棋AI」勾选框只在**环面模式**下对**白棋**
（围棋方）生效，胜率/目差显示与候选点都来自同一个查询。

## 首次运行

OpenCL 版第一次启动会做一次 GPU 自动调优（本机 Intel UHD 约 4 分钟），结果
缓存在 `KataGoData/`，之后启动约 25 秒、每手查询亚秒级。若无显卡或调优失败，
`katago_client.py` 会自动回退 Eigen（CPU）版，启动约 2 秒、速度慢。

手动预跑一次调优（可选，避免第一手 AI 等待）：

```bat
katago_opencl.exe analysis -model model.bin.gz -config analysis_daoqi.cfg
```

等到 stderr 出现 `Started, ready to begin handling requests` 后 Ctrl+C 退出。

## 道棋与环面

道棋模型是在"平铺 16 路棋盘"上训练的环面围棋网络（上下左右回绕）。本项目
环面模式下，board.py 已经按回绕规则完成了提子，所以客户端直接把**当前局面
石子**作为 `initialStones` 发给引擎（`initialPlayer` = 行棋方，`moves` 为空），
不做走子历史重放——环面提子、黑棋"平盘禁着但环面合法"的着法、无劫规则等都
不会让重放出错。A/B 验证：同一局面同一行棋方，initialStones 与重放两种传法
的评估一致。
