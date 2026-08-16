"""
main.py - 入口点

支持:
  - GUI 对弈 (默认): python main.py
  - 命令行模式 (机机对弈): python main.py --cli
  - 自定义棋盘大小: --size 19
  - 白棋获胜条件: --white-win capture / line
"""

import argparse
import sys

from board import BLACK, WHITE, EMPTY, HybridBoard


def run_cli(size: int = 15, max_moves: int = 300,
            white_win: str = "line", max_depth: int = 2):
    """命令行模式: 黑白 AI 对弈, 打印棋盘."""
    import ai_black
    import ai_white
    import rules
    import time

    board = HybridBoard(size)
    current = BLACK
    print(f"=== 混合规则对弈 (CLI) 棋盘 {size}x{size} ===")
    print(f"黑棋算法: minimax  白棋获胜条件: {white_win}")

    for move_no in range(1, max_moves + 1):
        print(f"\n--- 第 {move_no} 手: {'黑' if current == BLACK else '白'} ---")
        t0 = time.time()
        if current == BLACK:
            legal = rules.all_legal_black_moves(board)
            if not legal:
                print("黑棋投子认负 (全为禁手/死位), 白棋胜")
                break
            move = ai_black.best_black_move(
                board, time_limit=1.0, max_depth=max_depth
            )
            if move is None:
                print("黑棋投子认负, 白棋胜")
                break
            x, y = move
            ok, ftype = rules.is_black_legal_move(board, x, y)
            if not ok:
                print(f"黑棋 AI 选了禁手 ({ftype})! 改用任意合法着法")
                x, y = legal[0]
            ok2, _ = board.play_black(x, y)
            if not ok2:
                print(f"黑棋下 ({x},{y}) 失败 (自吃或非法)")
                break
            print(f"黑下 ({x},{y})  用时 {time.time()-t0:.2f}s")
            if board.check_black_five(x, y):
                print_board(board)
                print("黑棋连五, 黑胜!")
                return
            current = WHITE
        else:
            move = ai_white.best_white_move(
                board, time_limit=1.0, max_depth=max_depth
            )
            if move is None:
                print("白棋投子认负, 黑棋胜")
                break
            x, y = move
            ok, captured = board.play_white(x, y)
            if not ok:
                print(f"白棋下 ({x},{y}) 失败!")
                break
            print(f"白下 ({x},{y})  吃 {len(captured)} 黑  用时 {time.time()-t0:.2f}s")
            # 白棋获胜检查
            won = False
            if white_win == "capture":
                won = board.white_wins_by_capture()
            else:
                won = board.white_wins_by_line_block()
            if won:
                print_board(board)
                print("白棋获胜!")
                return
            current = BLACK
        print_board(board)
        print(f"黑: {board.black_stone_count()}  白: {board.white_stone_count()}  黑被吃: {board.captured_count[WHITE]}")

    print("\n达到最大手数, 平局或未决. 当前黑子:", board.black_stone_count())


def print_board(board: HybridBoard):
    """简单打印棋盘."""
    size = board.size
    print("   " + " ".join(f"{j:2d}" for j in range(size)))
    for i in range(size):
        row = []
        for j in range(size):
            v = board.grid[i, j]
            if v == BLACK:
                row.append(" X")
            elif v == WHITE:
                row.append(" O")
            else:
                row.append(" .")
        print(f"{i:2d} " + "".join(row))


def run_gui(size: int = 15):
    """GUI 模式."""
    import gui
    gui.BOARD_SIZE = size
    gui.main()


def main():
    parser = argparse.ArgumentParser(description="混合规则对弈 (黑五子+禁手 / 白围棋吃子)")
    parser.add_argument("--cli", action="store_true", help="命令行模式 (机机对弈)")
    parser.add_argument("--size", type=int, default=15, help="棋盘大小 (默认 15)")
    parser.add_argument("--max-moves", type=int, default=300, help="CLI 模式最大手数")
    parser.add_argument("--white-win", choices=["capture", "line"], default="line",
                        help="白棋获胜条件: capture=吃光黑棋, line=全线封堵 (默认 line)")
    parser.add_argument("--depth", type=int, choices=[0, 2, 4, 6, 8], default=2,
                        help="minimax 搜索层数 (默认 2)")
    args = parser.parse_args()

    if args.cli:
        run_cli(size=args.size, max_moves=args.max_moves,
                white_win=args.white_win,
                max_depth=args.depth)
    else:
        run_gui(size=args.size)


if __name__ == "__main__":
    main()
