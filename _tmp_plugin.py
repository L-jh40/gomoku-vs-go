import os, sys, re, importlib.util
import board_tools as bt
spec = importlib.util.spec_from_file_location("rapfi_grab", os.path.join("导出","rapfi_grab.py"))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

cases = {
 "case12": "h9 i9 i8 j7 i7 f11 i6 f6 h6 p0 f10 p0 f9 p0 f8 p0 f7",
 "case13user": "h9g10g9f7g8g6g7k8i8o15h7n15d10o14e7n14e6o13",
 "case7": "i10 p0 i9 p0 j9 p0 j8 p0 g8 p0 g7 p0 h7 p0 h6",
 "case4": "g8 i7 i8 g6 j8 h4 k7 p0 h7 p0 h6 p0 h5 p0",
}
for name, codes in cases.items():
    b, _ = bt.board_from_code(codes, size=15, first=bt.BLACK, gomoku=True)
    print(name, "plugin-style rapfi:", m.rapfi_forbidden(b))
