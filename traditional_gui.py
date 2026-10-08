"""traditional_gui.py - 传统围棋（15 路为主）KataGo 对弈观察窗口。

界面与引擎代码全部复用同目录的 daoqi_gui.py（GTP 客户端、实时胜率/目差、
候选点、AI 自动对弈、悔棋/停一手/手数），本文件只改三处默认值：

  1. 引擎目录 -> ../tools/katago-traditional-15
     （kata1-b18c384nbt-s9996604416-d4316597426.bin.gz + gtp_traditional.cfg）
  2. 普通棋盘（关掉环面镜面提示），默认 15 路、贴目 7.5（中国规则）
  3. 每手访问数默认 300

访问数(v)参考——本机实测 OpenCL + b18c384nbt ≈ 42 访/秒：
  100 访 ≈ 2.4 秒/手   300 访 ≈ 7 秒/手   800 访 ≈ 19 秒/手
界面里“每手访问数”随时可改；后台另有一条 kata-analyze 100 的分析流。

运行：python traditional_gui.py
"""
from __future__ import annotations

import os
import sys
import tkinter as tk

_HERE = os.path.dirname(os.path.abspath(__file__))
_TRAD_DIR = os.path.join(os.path.dirname(_HERE), "tools", "katago-traditional-15")
_MODEL = "kata1-b18c384nbt-s9996604416-d4316597426.bin.gz"

if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
import daoqi_gui as base          # noqa: E402

# 1) 让共用的引擎客户端指向传统围棋引擎
base.DAOQI_DIR = _TRAD_DIR
base.MODEL_PATH = os.path.join(_TRAD_DIR, _MODEL)
base.CONFIG_PATH = os.path.join(_TRAD_DIR, "gtp_traditional.cfg")
base.BOARD_SIZES = (9, 13, 15, 19)

DEFAULT_SIZE = 15
DEFAULT_KOMI = "7.5"
DEFAULT_VISITS = "300"

_NOTE = ("说明：规则全部由 KataGo 执行（chinese 规则：\n"
         "提子、禁自杀、全局禁同形）；胜率/目差为黑方\n"
         "视角。引擎：katago-traditional-15（b18c384nbt）。")


class TraditionalApp(base.DaoqiApp):
    """和道棋界面同一套代码，只换成传统围棋引擎 + 普通棋盘。"""

    def __init__(self, root: tk.Tk):
        self._first_boot = True
        super().__init__(root)

    def _start_engine(self):
        if self._first_boot:
            self._first_boot = False
            self.size.set(DEFAULT_SIZE)
            self.komi_var.set(DEFAULT_KOMI)
            self.visits_var.set(DEFAULT_VISITS)
            self.hint_on.set(0)          # 0 = 不画环面镜面区
            self.root.title("传统围棋 - KataGo 对弈观察 (katago-traditional-15)")
            self._relabel_note()
        super()._start_engine()

    def _relabel_note(self):
        stack = [self.root]
        while stack:
            w = stack.pop()
            try:
                if isinstance(w, tk.Label) and "道棋" in str(w.cget("text")):
                    w.config(text=_NOTE)
            except Exception:
                pass
            try:
                stack.extend(w.winfo_children())
            except Exception:
                pass


def main():
    root = tk.Tk()
    TraditionalApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
