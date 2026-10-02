import sys, os
sys.path.insert(0, os.path.join(os.getcwd(), "导出"))
import board_tools as bt
import importlib.util
spec = importlib.util.spec_from_file_location("rapfi_grab", os.path.join("导出", "rapfi_grab.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
print("engine:", m.RAPFI_ENGINE, os.path.exists(m.RAPFI_ENGINE))

codes = "h9g10g9f7g8g6g7k8i8o15h7n15d10o14e7n14e6o13"
b, _ = bt.board_from_code(codes, size=15, first=bt.BLACK, gomoku=True)
live = m.rapfi_forbidden(b)
print("rapfi forbid:", live)
print("ours:", [c for c,_ in bt.forbidden_codes(b)])
