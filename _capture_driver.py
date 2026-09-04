"""Temporary visual-check driver: builds the real GUI in a given state and
captures its windows to PNG via the Win32 PrintWindow API (works while the
window is occluded).  Usage: py _capture_driver.py <state>"""
import ctypes
import ctypes.wintypes as wt
import os
import sys
import time

import tkinter as tk

import gui
from board import HybridBoard

STATE = sys.argv[1] if len(sys.argv) > 1 else "default"
OUT = "_shots"
os.makedirs(OUT, exist_ok=True)

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32
PW_RENDERFULLCONTENT = 0x2


class BMIHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG),
                ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG),
                ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


def grab(hwnd, path):
    rect = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w <= 0 or h <= 0:
        return False
    hdc = user32.GetWindowDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    user32.PrintWindow(hwnd, mem, PW_RENDERFULLCONTENT)
    bmi = BMIHEADER()
    bmi.biSize = ctypes.sizeof(BMIHEADER)
    bmi.biWidth, bmi.biHeight = w, -h
    bmi.biPlanes, bmi.biBitCount = 1, 32
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bmi), 0)
    from PIL import Image
    Image.frombuffer("RGB", (w, h), buf.raw, "raw", "BGRX", 0, 1).save(path)
    for d in (mem, bmp, hdc):
        gdi32.DeleteObject(d)
    user32.ReleaseDC(hwnd, hdc)
    return True


ENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def windows_of_this_process():
    out = []
    pid = kernel32.GetCurrentProcessId()

    def cb(hwnd, _l):
        p = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value == pid and user32.IsWindowVisible(hwnd):
            out.append(hwnd)
        return True

    user32.EnumWindows(ENUMPROC(cb), 0)
    return out


root = tk.Tk()
app = gui.GameGUI(root, board_size=15, black_is_ai=False, white_is_ai=False)
root.update()

if STATE == "mode":
    app.open_mode_window()
    root.update()
elif STATE == "cell":
    app.style_cell_var.set(1)
    app._on_style_cell()
elif STATE == "stones":
    app.style_cell_var.set(1)
    app._on_style_cell()
    app.hint_var.set(1)
    b = app.board
    for i, (x, y) in enumerate([(7, 7), (8, 7), (7, 8), (6, 8), (7, 9)]):
        (b.play_black if i % 2 == 0 else b.play_white)(x, y)
    app.last_move = (7, 9)
    app.draw_board()
elif STATE == "stones_point":
    app.style_point_var.set(1)
    app._on_style_point()
    app.hint_var.set(1)
    b = app.board
    for i, (x, y) in enumerate([(7, 7), (8, 7), (7, 8), (6, 8), (7, 9)]):
        (b.play_black if i % 2 == 0 else b.play_white)(x, y)
    app.last_move = (7, 9)
    app.draw_board()
elif STATE == "cell9":
    app.style_cell_var.set(1)
    app._on_style_cell()
    app.board_size_vars[9].set(1)
    app._on_size_check(9)
    app.new_game()
elif STATE == "point19":
    app.board_size_vars[19].set(1)
    app._on_size_check(19)
    app.new_game()
elif STATE == "mode_cell9":
    app.style_cell_var.set(1)
    app._on_style_cell()
    app.board_size_vars[9].set(1)
    app._on_size_check(9)
    app.new_game()
    app.open_mode_window()
    root.update()

end = time.time() + 5
while time.time() < end:
    root.update()
    time.sleep(0.02)

i = 0
for hwnd in windows_of_this_process():
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buf, 256)
    title = buf.value.strip().replace(" ", "_").replace("/", "-") or "win"
    i += 1
    path = os.path.join(OUT, f"{STATE}_{i}_{title}.png")
    ok = grab(hwnd, path)
    print(("OK " if ok else "FAIL ") + path)
root.destroy()
