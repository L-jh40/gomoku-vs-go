import board_tools as bt
codes = "h9g10g9f7g8g6g7k8i8o15h7n15d10o14e7n14e6o13"
block, b, info, fouls = bt.position_block(codes, size=15, gomoku=True)
print(block)
print("fouls:", fouls)
print("history:", len(b.history))
