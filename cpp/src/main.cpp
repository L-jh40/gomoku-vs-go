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
//   pat <x> <y>         诊断：输出四方向线型等
// 评估相关（只评估，不搜索）：
//   eval                输出打包后的 int64 评估值与各字段
//   counters            输出黑白六类线型计数 / 风险 / 领地
//   bencheval <n>       随机走 n 步 make_move+pack_score，输出毫秒与 evals/sec
#include "board.h"
#include "eval.h"
#include "forbidden.h"

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <iostream>
#include <sstream>
#include <string>

namespace {

uint64_t g_rng = 0x243F6A8885A308D3ULL;

inline uint64_t rnd() {
    uint64_t z = (g_rng += 0x9E3779B97F4A7C15ULL);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
    return z ^ (z >> 31);
}

void print_counters(const gvg::Board& board) {
    const int32_t* b = board.black_counts();
    const int32_t* w = board.white_counts();
    std::cout << "cnt b=";
    for (int i = 0; i < gvg::NUM_EVAL_CLASSES; ++i) {
        if (i) std::cout << ',';
        std::cout << b[i];
    }
    std::cout << " w=";
    for (int i = 0; i < gvg::NUM_EVAL_CLASSES; ++i) {
        if (i) std::cout << ',';
        std::cout << w[i];
    }
    std::cout << " risk=" << board.risk() << " terr=" << board.territory() << '\n';
}

void print_eval(const gvg::Board& board) {
    const int32_t* bc = board.black_counts();
    const int F1 = std::min<int>(bc[0], 255);
    const int F2 = std::min<int>(bc[1], 255);
    const int F3 = std::min<int>(bc[2], 255);
    const int F4 = std::min<int>(bc[3] + bc[4], 255);
    const int F5 = std::min<int>(bc[5], 255);
    std::cout << "eval " << gvg::pack_score(board) << " F1=" << F1 << " F2=" << F2
              << " F3=" << F3 << " F4=" << F4 << " F5=" << F5
              << " risk=" << board.risk() << " terr=" << board.territory() << '\n';
}

}  // namespace

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
        } else if (cmd == "pat") {
            int x, y;
            if (in >> x >> y) {
                gvg::ForbiddenProbe r = gvg::probe_forbidden(board, x, y);
                std::cout << r.dir[0] << ' ' << r.dir[1] << ' ' << r.dir[2] << ' '
                          << r.dir[3] << ' ' << r.p4 << ' ' << r.fours << ' '
                          << r.threes << ' ' << (r.forbidden ? 1 : 0) << '\n';
            }
        } else if (cmd == "eval") {
            print_eval(board);
        } else if (cmd == "counters") {
            print_counters(board);
        } else if (cmd == "bencheval") {
            long long n = 0;
            if (in >> n && n > 0) {
                using clock = std::chrono::steady_clock;
                const auto t0 = clock::now();
                long long evals = 0;
                volatile long long sink = 0;
                const int sz = board.size();
                for (long long i = 0; i < n; ++i) {
                    const int color = board.turn();
                    bool placed = false;
                    for (int attempt = 0; attempt < 64 && !placed; ++attempt) {
                        const int x = static_cast<int>(rnd() % sz);
                        const int y = static_cast<int>(rnd() % sz);
                        if (board.is_empty(x, y) && board.make_move(x, y, color))
                            placed = true;
                    }
                    if (!placed) {
                        for (int x = 0; x < sz && !placed; ++x)
                            for (int y = 0; y < sz && !placed; ++y)
                                if (board.is_empty(x, y) && board.make_move(x, y, color))
                                    placed = true;
                    }
                    if (!placed) {
                        // 盘面已满（黑自杀/无气等原因无合法点）：清盘继续，
                        // 保证 bench 实际完成 n 次 make_move + pack_score。
                        board.clear();
                        continue;
                    }
                    sink += gvg::pack_score(board);
                    ++evals;
                    if ((i + 1) % 200 == 0) board.undo_move();
                }
                const auto t1 = clock::now();
                const double ms =
                    std::chrono::duration<double, std::milli>(t1 - t0).count();
                const double eps = (ms > 0.0) ? (evals * 1000.0 / ms) : 0.0;
                std::cout << "bencheval " << n << ' '
                          << static_cast<long long>(ms) << ' '
                          << static_cast<long long>(eps) << '\n';
                (void)sink;
            }
        } else if (cmd == "quit") {
            break;
        }

        std::cout.flush();
    }
    return 0;
}
