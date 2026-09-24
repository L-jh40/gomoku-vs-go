// main.cpp - 最小命令行交互循环。
//
// 从 stdin 逐行读取、stdout 输出、每条命令后 flush（行缓冲，不等待 EOF）。
// 支持协议：
//   size <n>            9..19 奇数，重置空盘
//   set <x> <y> <b|w|o> 直接摆子(o=障碍)，不提子、不换回合（摆局面用）
//   clear               清空棋盘
//   checkforbidden      输出当前局面所有黑棋非法点(禁手 + 无气自杀)，每行 "x y"，末尾 end
//   quit                退出
// 另为差分/一致性测试补充：
//   move <x> <y> <b|w>  正式落子(含白提黑、黑自杀拒绝)，输出 ok / err
//   undo                悔一步，输出 ok / err
//   hash                输出 16 位十六进制 Zobrist
//   dump                输出 size 行、每行 size 个格子值(0..3)
#include "board.h"
#include "forbidden.h"

#include <cstdio>
#include <iostream>
#include <sstream>
#include <string>

int main() {
    std::ios::sync_with_stdio(false);

    gvg::Board board(15);
    std::string line;

    while (std::getline(std::cin, line)) {
        std::istringstream in(line);
        std::string cmd;
        if (!(in >> cmd)) { std::cout.flush(); continue; }

        if (cmd == "size") {
            int n = 15;
            if (in >> n) board.reset(n);
        } else if (cmd == "set") {
            int x, y;
            std::string c;
            if (in >> x >> y >> c) {
                uint8_t v = gvg::EMPTY;
                if (c == "b") v = gvg::BLACK;
                else if (c == "w") v = gvg::WHITE;
                else if (c == "o") v = gvg::OBSTACLE;
                board.set_cell(x, y, v);
            }
        } else if (cmd == "clear") {
            board.clear();
        } else if (cmd == "checkforbidden") {
            for (int x = 0; x < board.size(); ++x) {
                for (int y = 0; y < board.size(); ++y) {
                    if (!board.is_empty(x, y)) continue;
                    // 输出“黑棋不能落”的全部点：无气自杀 或 Rapfi 禁手。
                    if (board.is_dead_empty(x, y) || gvg::check_forbidden(board, x, y))
                        std::cout << x << ' ' << y << '\n';
                }
            }
            std::cout << "end\n";
        } else if (cmd == "move") {
            int x, y;
            std::string c;
            bool ok = false;
            if (in >> x >> y >> c) {
                const int color = (c == "b") ? gvg::BLACK : gvg::WHITE;
                ok = board.make_move(x, y, color);
            }
            std::cout << (ok ? "ok" : "err") << '\n';
        } else if (cmd == "undo") {
            std::cout << (board.undo_move() ? "ok" : "err") << '\n';
        } else if (cmd == "hash") {
            char buf[32];
            std::snprintf(buf, sizeof(buf), "%016llx",
                          static_cast<unsigned long long>(board.hash()));
            std::cout << buf << '\n';
        } else if (cmd == "dump") {
            for (int x = 0; x < board.size(); ++x) {
                for (int y = 0; y < board.size(); ++y)
                    std::cout << static_cast<int>(board.at(x, y));
                std::cout << '\n';
            }
        } else if (cmd == "quit") {
            break;
        }

        std::cout.flush();
    }
    return 0;
}
