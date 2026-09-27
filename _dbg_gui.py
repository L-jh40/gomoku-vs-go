import time
import tkinter as tk
from tkinter import messagebox

import gui

captured = []
messagebox.showerror = lambda *a, **k: captured.append(("error",) + a)
messagebox.showinfo = lambda *a, **k: captured.append(("info",) + a)
messagebox.showwarning = lambda *a, **k: captured.append(("warn",) + a)

def main():
    global root, app, captured
    root = tk.Tk()
    app = gui.GameGUI(root, board_size=15, black_is_ai=True, white_is_ai=True)
    app.engine_var.set(1)
    app.depth_var.set("2")
    root.update()
    print("engine_var:", app.engine_var.get(), "| mode:", app.mode_label.cget("text"), flush=True)
    print("worker alive:", app.ai_worker_proc.is_alive() if app.ai_worker_proc else None, flush=True)

    app.maybe_play_ai()
    print("after maybe_play_ai: ai_thinking =", app.ai_thinking, flush=True)
    t0 = time.time()
    while time.time() - t0 < 15:
        root.update()
        time.sleep(0.02)
        if not app.ai_thinking and app.board.black_stone_count() > 0:
            break
    print(f"t={time.time()-t0:.1f}s ai_thinking={app.ai_thinking} black={app.board.black_stone_count()}", flush=True)
    print("thinking_label:", repr(app.thinking_label.cget("text")), flush=True)
    print("dialogs:", captured, flush=True)
    ec = app.engine_client
    if ec is not None:
        print("client proc alive:", ec.proc is not None and ec.proc.poll() is None, flush=True)
    root.destroy()
    print("DBG_DONE")


if __name__ == "__main__":
    main()
