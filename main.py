"""
main.py - application entry point.

    python main.py                 # windowed AI-vs-AI GUI (15x15)
    python main.py --size 19       # 19x19 GUI
    python main.py --cli           # command-line AI-vs-AI match
"""

from __future__ import annotations

import argparse
import time

from board import EMPTY, BLACK, WHITE, HybridBoard
import rules
import ai_black
import ai_white
import ai_search


def print_board(board: HybridBoard):
    size = board.size
    print("   " + " ".join(f"{j:2d}" for j in range(size)))
    for x in range(size):
        chars = []
        for y in range(size):
            v = int(board.grid[x, y])
            if v == BLACK:
                chars.append(" X")
            elif v == WHITE:
                chars.append(" O")
            else:
                chars.append(" .")
        print(f"{x:2d} " + "".join(chars))


def run_cli(size: int = 15, max_moves: int = 300, max_depth: int = 2):
    board = HybridBoard(size)
    current = BLACK
    print(f"=== Gomoku(黑) vs Go(白)  {size}x{size}  depth={max_depth} ===")

    for move_no in range(1, max_moves + 1):
        t0 = time.time()
        if current == BLACK:
            move = ai_black.best_black_move(board, time_limit=None,
                                            max_depth=max_depth)
            if move is None:
                print("黑棋投子认负，白胜")
                return
            x, y = move
            ok, _ = board.play_black(x, y)
            if not ok:
                print(f"黑棋非法着法 {(x, y)}，白胜")
                return
            print(f"黑 {move}  用时 {time.time() - t0:.2f}s")
            if board.check_black_five(x, y):
                print_board(board)
                print("黑棋连五，黑胜!")
                return
            current = WHITE
        else:
            move = ai_white.best_white_move(board, time_limit=None,
                                            max_depth=max_depth)
            if move is None:
                if ai_search.white_should_pass(board):
                    print("白棋 pass")
                else:
                    print("白棋投子认负，黑胜")
                    return
            else:
                x, y = move
                ok, _ = board.play_white(x, y)
                if not ok:
                    print("白棋落子失败")
                    return
                print(f"白 {move}  用时 {time.time() - t0:.2f}s")
                if board.white_wins_by_capture():
                    print_board(board)
                    print("白棋吃光黑棋，白胜!")
                    return
                if board.white_wins_by_line_block():
                    print_board(board)
                    print("白棋封堵全部五连线路，白胜!")
                    return
            current = BLACK

        print_board(board)
        print(f"黑: {board.black_stone_count()}  白: {board.white_stone_count()}  "
              f"黑被吃: {board.captured_count[WHITE]}")

    print("达到最大手数，对局结束")


def main():
    parser = argparse.ArgumentParser(description="Gomoku vs Go hybrid game")
    parser.add_argument("--cli", action="store_true", help="命令行模式")
    parser.add_argument("--size", type=int, default=15, help="棋盘大小，默认 15")
    parser.add_argument("--max-moves", type=int, default=300,
                        help="CLI 模式最大手数")
    parser.add_argument("--depth", type=int, default=2, choices=[0, 2, 4, 6, 8],
                        help="minimax 层数")
    args = parser.parse_args()

    if args.cli:
        run_cli(size=args.size, max_moves=args.max_moves, max_depth=args.depth)
    else:
        import gui
        gui.main(args.size)


if __name__ == "__main__":
    main()
