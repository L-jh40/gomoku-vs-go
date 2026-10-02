p = "导出/粘贴板.md"
lines = open(p, encoding="utf-8").read().split(chr(10))
for i, l in enumerate(lines[32:43], start=33):
    print(i, repr(l))
