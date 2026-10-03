import os, sys, tkinter as tk
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gui as gui_mod
gui_mod.GameGUI._ensure_worker = lambda self: None
gui_mod.GameGUI._poll_worker = lambda self: None
gui_mod.GameGUI._maybe_refresh_engine_labels = lambda self: None
root = tk.Tk(); root.withdraw()
g = gui_mod.GameGUI(root)
print("default threat steps:", g._threat_steps())
g.open_ai_window(); root.update()
print("ai window:", g.ai_window.winfo_exists() == 1, g.ai_window.title())
g.vct_steps_var.set("7"); g.vcf_steps_var.set("x")
print("after edit:", g._threat_steps())
g.open_mode_window(); root.update()
print("mode window title:", g.mode_window.title())
print("main panel buttons:", [w.cget("text") for w in g.info.winfo_children() if isinstance(w, tk.Button)])
root.destroy()
print("UI smoke OK")
