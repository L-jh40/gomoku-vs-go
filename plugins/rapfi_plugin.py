# -*- coding: utf-8 -*-
"""外置插件：Rapfi / Yixin 局面 → 粘贴板.md

独立小工具，不修改 gui.py，也不改动 Yixin / Rapfi 目录里的任何文件：
它只读取剪贴板（在 Rapfi/Yixin 里用它自带的复制功能复制局面即可）。

点一次按钮完成：
    剪贴板 → 自动分块坐标（有无空格都行）→ 计算禁手位置
    → 追加两行到 粘贴板.md（代码一行，禁手位置一行）

运行：
    py -3.14 plugins/rapfi_plugin.py            （或双击 rapfi_plugin.bat）

命令行（不开窗口，直接打印结果）：
    py -3.14 plugins/rapfi_plugin.py --text "h8i9j10"
    py -3.14 plugins/rapfi_plugin.py --clipboard
"""
from __future__ import annotations

import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import board_tools

FOUL_NAMES = {"three_three": "三三禁手", "four_four": "四四禁手",
              "overline": "长连禁手", "self_capture": "自吃（无气）",
              "occupied": "位置已占"}
DEFAULT_NAME = "粘贴板.md"


def default_save_dir() -> str:
    return os.path.join(APP_DIR, "导出")


def default_path() -> str:
    return os.path.join(default_save_dir(), DEFAULT_NAME)


def build_block(text: str, size: int = 15, first_black: bool = True,
                gomoku: bool = True, forbidden_label: bool = True):
    """(block, board, info, fouls) for one clipboard/typed position."""
    return board_tools.position_block(
        text, size=size,
        first=board_tools.BLACK if first_black else board_tools.WHITE,
        gomoku=gomoku, forbidden_label=forbidden_label)


def describe(board, info, fouls) -> str:
    names = ", ".join("%s %s" % (code, FOUL_NAMES.get(ftype, ftype))
                      for code, ftype in fouls[:20])
    if len(fouls) > 20:
        names += " …共 %d 个" % len(fouls)
    lines = [
        "解析：%dx%d，先行 %s，%s，%d 手"
        % (board.size, board.size,
           "黑" if info.get("first", board_tools.BLACK) == board_tools.BLACK
           else "白",
           "外部局面（无吃子判定）" if info.get("gomoku") else "本程序局面",
           len(board.history)),
        "禁手点：%s" % (names if names else "无"),
    ]
    errors = list(info.get("errors") or [])
    if errors:
        lines.append("被跳过：" + " ".join(
            "%s(%s)" % (t, FOUL_NAMES.get(f, f)) for t, f in errors[:20]))
    lines.append("")
    lines.append(board_tools.render(board))
    return chr(10).join(lines)


class RapfiPlugin:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Rapfi/Yixin 局面 → 粘贴板.md")
        pad = {"padx": 6, "pady": 3}

        tk.Label(root, text="局面代码（可含空格，也可无空格；Rapfi 复制的即可）",
                 font=("Microsoft YaHei UI", 9)).pack(anchor=tk.W, **pad)
        self.text = tk.Text(root, width=58, height=5, font=("Consolas", 10))
        self.text.pack(fill=tk.BOTH, expand=False, **pad)

        row = tk.Frame(root)
        row.pack(fill=tk.X, **pad)
        tk.Button(row, text="读取剪贴板", command=self.read_clipboard).pack(
            side=tk.LEFT)
        tk.Button(row, text="解析预览", command=self.preview).pack(
            side=tk.LEFT, padx=4)
        tk.Button(row, text="一键：剪贴板 → 追加到文件",
                  command=self.one_click).pack(side=tk.LEFT, padx=4)

        opts = tk.Frame(root)
        opts.pack(fill=tk.X, **pad)
        tk.Label(opts, text="棋盘尺寸:").pack(side=tk.LEFT)
        self.size_var = tk.StringVar(value="15")
        tk.Spinbox(opts, from_=5, to=25, width=4,
                   textvariable=self.size_var).pack(side=tk.LEFT)
        self.first_var = tk.StringVar(value="black")
        tk.Label(opts, text="  先行:").pack(side=tk.LEFT)
        tk.Radiobutton(opts, text="黑", value="black",
                       variable=self.first_var).pack(side=tk.LEFT)
        tk.Radiobutton(opts, text="白", value="white",
                       variable=self.first_var).pack(side=tk.LEFT)
        self.gomoku_var = tk.IntVar(value=1)
        tk.Checkbutton(opts, text="外部局面（无吃子/自吃判定）",
                       variable=self.gomoku_var).pack(side=tk.LEFT, padx=6)
        self.label_var = tk.IntVar(value=1)
        tk.Checkbutton(opts, text="禁手行写成 forbid:（None 表示无禁手）",
                       variable=self.label_var).pack(side=tk.LEFT)

        file_row = tk.Frame(root)
        file_row.pack(fill=tk.X, **pad)
        tk.Label(file_row, text="追加到:").pack(side=tk.LEFT)
        self.path_var = tk.StringVar(value=default_path())
        tk.Entry(file_row, textvariable=self.path_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(file_row, text="浏览", command=self.browse).pack(
            side=tk.LEFT)
        tk.Button(file_row, text="打开", command=self.open_file).pack(
            side=tk.LEFT)

        tk.Label(root, text="预览", font=("Microsoft YaHei UI", 9)).pack(
            anchor=tk.W, **pad)
        self.preview_text = tk.Text(root, width=58, height=16,
                                    font=("Consolas", 9), background="#f7f7f7")
        self.preview_text.pack(fill=tk.BOTH, expand=True, **pad)

        self.status = tk.Label(root, text="就绪", anchor=tk.W,
                               font=("Microsoft YaHei UI", 9), fg="#333333")
        self.status.pack(fill=tk.X, **pad)

        self.read_clipboard(quiet=True)

    # ------------------------------------------------------------------
    def read_clipboard(self, quiet: bool = False):
        try:
            content = self.root.clipboard_get()
        except Exception:
            if not quiet:
                self.status.config(text="剪贴板为空或不是文本")
            return ""
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", content.strip())
        if not quiet:
            self.status.config(text="已从剪贴板读取 %d 个字符"
                                    % len(content.strip()))
        return content

    def browse(self):
        path = filedialog.asksaveasfilename(
            initialdir=os.path.dirname(self.path_var.get() or default_path()),
            initialfile=os.path.basename(self.path_var.get() or DEFAULT_NAME),
            defaultextension=".md",
            filetypes=[("Markdown", "*.md"), ("文本", "*.txt"),
                       ("所有文件", "*.*")])
        if path:
            self.path_var.set(path)

    def open_file(self):
        path = self.path_var.get().strip() or default_path()
        if not os.path.exists(path):
            messagebox.showinfo("打开", "文件还不存在:\n" + path)
            return
        try:
            os.startfile(path)
        except Exception as exc:
            messagebox.showinfo("打开", path + "\n" + str(exc))

    def _options(self):
        try:
            size = int(self.size_var.get())
        except ValueError:
            size = 15
        return (size, self.first_var.get() == "black",
                bool(self.gomoku_var.get()), bool(self.label_var.get()))

    def _parse(self):
        content = self.text.get("1.0", tk.END).strip()
        if not content:
            self.set_preview("请先复制 Rapfi/Yixin 的局面代码，"
                             "或点【读取剪贴板】。")
            return None
        size, first_black, gomoku, label = self._options()
        try:
            block, board, info, fouls = build_block(
                content, size=size, first_black=first_black, gomoku=gomoku,
                forbidden_label=label)
        except Exception as exc:
            self.set_preview("解析失败：%s" % exc)
            self.status.config(text="解析失败")
            return None
        moves_line, forbidden_line, _f = board_tools.position_lines(
            board, info.get("moves"), forbidden_label=label)
        shown = ["代码行:      " + moves_line,
                 "禁手行:      " + forbidden_line,
                 ""]
        shown.append(describe(board, info, fouls))
        self.set_preview(chr(10).join(shown))
        self.status.config(text="解析成功：%d 手，%d 个禁手点"
                                % (len(board.history), len(fouls)))
        return block, board, info, fouls

    def preview(self):
        self._parse()

    def one_click(self):
        if not self.read_clipboard(quiet=True):
            if not self.text.get("1.0", tk.END).strip():
                messagebox.showinfo("Rapfi 插件",
                                    "剪贴板为空；请先在 Rapfi/Yixin 里复制局面，"
                                    "或把代码粘贴到上面的输入框。")
                return
        self.append()

    def append(self):
        parsed = self._parse()
        if parsed is None:
            return
        block, board, info, fouls = parsed
        path = self.path_var.get().strip() or default_path()
        directory = os.path.dirname(path)
        try:
            if directory:
                os.makedirs(directory, exist_ok=True)
            board_tools.append_position(path, block)
        except Exception as exc:
            messagebox.showerror("Rapfi 插件", "写入失败：\n%s" % exc)
            self.status.config(text="写入失败")
            return
        self.status.config(text="已追加到 %s（%d 手，%d 个禁手点）"
                                % (path, len(board.history), len(fouls)))

    def set_preview(self, text: str):
        self.preview_text.delete("1.0", tk.END)
        self.preview_text.insert("1.0", text)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv:
        text = ""
        if argv[0] == "--clipboard":
            import tkinter as _tk
            r = _tk.Tk()
            r.withdraw()
            text = r.clipboard_get()
            r.destroy()
        elif argv[0] == "--text":
            text = argv[1] if len(argv) > 1 else ""
        if text:
            block, board, info, fouls = build_block(text)
            print(block)
            print()
            print(describe(board, info, fouls))
            return 0
    root = tk.Tk()
    RapfiPlugin(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
