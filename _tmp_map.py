import board_tools as bt
import inspect
print([n for n in dir(bt) if 'coord' in n or 'code' in n])
codes = "h9g10g9f7g8g6g7k8i8o15h7n15d10o14e7n14e6o13"
b, _ = bt.board_from_code(codes, size=15, first=bt.BLACK, gomoku=True)
# print the board with coordinate labels
for x in range(15):
    row = []
    for y in range(15):
        v = int(b.grid[x, y])
        ch = {0:'.',1:'X',2:'O',3:'#'}[v]
        row.append(ch)
    print("x=%2d " % x + "".join(row))
print()
print("stone positions:")
for (x, y) in b.history:
    print("  ", (x, y), bt.coord_to_code(x, y, 15), int(b.grid[x,y]))
