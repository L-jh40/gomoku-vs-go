"""traditional_gui.py - 传统围棋（9~19 路）KataGo 对弈/复盘窗口。

界面与引擎代码全部复用同目录的 daoqi_gui.py（GTP 客户端、实时胜率/目差、
候选点、AI 自动对弈、悔棋/停一手/手数），本文件只做三件事：

  1. 引擎目录 -> ../tools/katago-traditional-15
     （kata1-b18c384nbt-s9996604416-d4316597426.bin.gz + gtp_traditional.cfg）
  2. 普通棋盘（关掉环面镜面提示），默认 15 路、贴目 7.5（中国规则），
     右侧「棋盘尺寸」可在 9 / 11 / 13 / 15 / 16 / 17 / 19 路之间切换
     （切换后点「新对局」生效）
  3. 复盘导航：← / → 在已下的手数里前后翻看（只翻显示，不动引擎），
     点一下棋盘或按 → 到最新一手即回到实时局面；每手访问数默认 300

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
# 2) 9~19 路都可选
base.BOARD_SIZES = (9, 11, 13, 15, 16, 17, 19)

DEFAULT_SIZE = 15
DEFAULT_KOMI = "7.5"
DEFAULT_VISITS = "300"

_NOTE = ("说明：规则全部由 KataGo 执行（chinese 规则：\n"
         "提子、禁自杀、全局禁同形）；胜率/目差为黑方\n"
         "视角。引擎：katago-traditional-15（b18c384nbt）。\n"
         "← / → 可在已下手数里前后翻看（不动引擎），\n"
         "点棋盘回到最新局面；右侧「棋盘尺寸」支持\n"
         "9/11/13/15/16/17/19 路，选好点「新对局」生效。")


class TraditionalApp(base.DaoqiApp):
    """和道棋界面同一套代码，只换成传统围棋引擎 + 普通棋盘。"""

    def __init__(self, root: tk.Tk):
        self._first_boot = True
        self._view_pos = None          # None = 实时局面；否则是 _snapshots 下标
        self._live_state = None        # 进入翻看前保存的实时局面
        super().__init__(root)
        try:
            self.root.bind("<Left>", lambda _e: self._browse(-1))
            self.root.bind("<Right>", lambda _e: self._browse(1))
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _start_engine(self):
        if self._first_boot:
            self._first_boot = False
            self.size.set(DEFAULT_SIZE)
            self.komi_var.set(DEFAULT_KOMI)
            self.visits_var.set(DEFAULT_VISITS)
            self.hint_on.set(0)          # 0 = 不画环面镜面区
            self.root.title("传统围棋 - KataGo 对弈/复盘 (katago-traditional-15)")
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

    # ------------------------------------------------------------------
    # 复盘导航（纯显示层，不动引擎）
    # ------------------------------------------------------------------
    def _snapshot_state(self):
        return (dict(self.stones), dict(self.numbers),
                dict(self.captures), self.last_move)

    def _restore_state(self, state):
        st, num, cap, lm = state
        self.stones, self.numbers = dict(st), dict(num)
        self.captures, self.last_move = dict(cap), lm

    def _browse(self, delta: int):
        snaps = getattr(self, "_snapshots", None)
        if not snaps:
            return
        if self._view_pos is None:                      # 从实时进入翻看
            self._live_state = self._snapshot_state()
            pos = len(snaps) - 1 + delta
        else:
            pos = self._view_pos + delta
        if pos >= len(snaps) - 1:                       # 到最新一手 -> 实时局面
            if self._live_state is not None:
                self._restore_state(self._live_state)
            self._view_pos = None
            self._live_state = None
            self._set_status("已回到最新局面")
        else:
            pos = max(0, pos)
            self._view_pos = pos
            self._restore_state(snaps[pos])
            self.candidates = []
            self._set_status("浏览第 %d 手（← / → 前后，点击棋盘回到最新）"
                             % (pos + 1))
        self.draw_board()

    def _sync_board(self, stones):
        self._view_pos = None
        self._live_state = None
        super()._sync_board(stones)

    def _new_game(self):
        self._view_pos = None
        self._live_state = None
        super()._new_game()

    def _on_click(self, event):
        if self._view_pos is not None:                  # 翻看时点棋盘 = 回到最新
            if self._live_state is not None:
                self._restore_state(self._live_state)
            self._view_pos = None
            self._live_state = None
            self._set_status("已回到最新局面")
            self.draw_board()
            return
        super()._on_click(event)


def main():
    root = tk.Tk()
    TraditionalApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
