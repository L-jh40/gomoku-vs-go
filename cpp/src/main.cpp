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
//   forbid <o> <44> <33> 设置三档禁手开关（1=开，默认全开；不改棋盘/哈希）
//   pat <x> <y>         诊断：输出四方向线型等
//   wcand               诊断：白棋威胁候选点的原始报告（威胁线 + 每线阻挡点 +
//                       双威胁必须阻挡点 + 吃子点 + 交集/并集回退后的候选池）
// 评估相关（只评估，不搜索）：
//   eval                输出打包后的 int64 评估值与各字段
//   counters            输出黑白六类线型计数 / 风险 / 领地
//   bencheval <n>       随机走 n 步 make_move+pack_score，输出毫秒与 evals/sec
// 搜索相关（只搜索，不落子；落子由调用方用 play 执行）：
//   play <b|w> <x> <y>          正式落子(白提黑、黑自杀拒绝)，输出 ok / illegal
//   winmode <0|1>               设置胜负模式（0=line_block 默认，1=occupy）
//   genmove <b|w> [max_depth] [min_sec] [max_sec] [winmode]
//                               迭代加深搜索；每完成一个偶深度输出一行
//                               info depth <d> move <x> <y> score <packed>，
//                               最后输出 move <x> <y>（白无着 pass / 黑无着 resign）
//   searchstat                  输出上一次 genmove 的 nodes / depth / 毫秒
// 战术搜索（VCF/VCT + W/L 标注）：
//   candidates <b|w> [steps=11] [max_sec=10] [winmode=0] [vc=1] [vct=18] [vcf=180]
//                               给 gen_moves(color) 的每个候选打标注；每行输出
//                               cand <x> <y> <tag><steps>（tag=W/L），超时截断时
//                               额外输出一行 timeout，末尾 end。棋盘被改动时
//                               只输出 error hash。
//   prove <steps> [max_sec=10]  黑方证明搜索（含三的 VCT）：轮到黑方时，在 steps
//                               个黑攻击手数内对白方全部防御都被证明则输出 win；
//                               证明不出输出 no；触限流输出 timeout；非黑方回合
//                               输出 error turn。不落子、不改棋盘。
#include "board.h"
#include "eval.h"
#include "forbidden.h"
#include "search.h"
#include "vcfvct.h"

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

namespace {

uint64_t g_rng = 0x243F6A8885A308D3ULL;

int  g_winmode = 0;               // 0=line_block, 1=occupy
gvg::SearchResult g_last_search;  // 供 searchstat 报告

struct TurnRestore {
    gvg::Board& board;
    int orig;
    bool active;
    ~TurnRestore() {
        if (active) board.set_turn(orig);
    }
};

int to_int(const std::string& s, int def) {
    try {
        return std::stoi(s);
    } catch (...) {
        return def;
    }
}

double to_double(const std::string& s, double def) {
    try {
        return std::stod(s);
    } catch (...) {
        return def;
    }
}

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
            if (in >> n) {
                board.reset(n);
                gvg::tt_clear();   // 尺寸变化后置换表作废
            }
        } else if (cmd == "play") {
            std::string c;
            int x, y;
            bool ok = false;
            if (in >> c >> x >> y) {
                const int color = (c == "b") ? gvg::BLACK : gvg::WHITE;
                ok = board.make_move(x, y, color);
            }
            std::cout << (ok ? "ok" : "illegal") << '\n';
        } else if (cmd == "winmode") {
            int m = 0;
            if (in >> m) g_winmode = m;
        } else if (cmd == "forbid") {
            // forbid <长连> <四四> <三三>：1=禁手开（默认），0=该档禁手关闭。
            // 只改 Board 的三个开关（重算 p4_black_ 预筛），不改棋盘/哈希。
            int o = 1, f4 = 1, f3 = 1;
            if (in >> o >> f4 >> f3) board.set_forbid(o != 0, f4 != 0, f3 != 0);
        } else if (cmd == "genmove") {
            std::string c;
            if (in >> c) {
                std::vector<std::string> rest;
                std::string tok;
                while (in >> tok) rest.push_back(tok);
                int    max_depth = 4;
                double min_sec   = 0.0;
                double max_sec   = 10.0;
                int    wm        = g_winmode;
                if (rest.size() >= 1) max_depth = to_int(rest[0], max_depth);
                if (rest.size() >= 2) min_sec   = to_double(rest[1], min_sec);
                if (rest.size() >= 3) max_sec   = to_double(rest[2], max_sec);
                if (rest.size() >= 4) wm        = to_int(rest[3], wm);

                const int want = (c == "b") ? gvg::BLACK : gvg::WHITE;
                TurnRestore guard{board, board.turn(), false};
                if (board.turn() != want) {
                    board.set_turn(want);
                    guard.active = true;
                }
                g_last_search = gvg::search_root(board, max_depth, min_sec,
                                                 max_sec, wm);

                for (size_t i = 0; i < g_last_search.depth_scores.size(); ++i) {
                    std::cout << "info depth " << (static_cast<int>(i) * 2)
                              << " move " << g_last_search.depth_move_x[i]
                              << ' ' << g_last_search.depth_move_y[i]
                              << " score " << g_last_search.depth_scores[i]
                              << '\n';
                }
                if (g_last_search.move_x < 0)
                    std::cout << (want == gvg::WHITE ? "pass" : "resign")
                              << '\n';
                else
                    std::cout << "move " << g_last_search.move_x << ' '
                              << g_last_search.move_y << '\n';
            }
        } else if (cmd == "searchstat") {
            std::cout << "searchstat nodes " << g_last_search.nodes
                      << " depth " << g_last_search.completed_depth << " ms "
                      << static_cast<long long>(g_last_search.elapsed_sec *
                                                1000.0)
                      << '\n';
        } else if (cmd == "candidates") {
            std::string c;
            if (in >> c) {
                std::vector<std::string> rest;
                std::string tok;
                while (in >> tok) rest.push_back(tok);
                int    steps   = 11;
                double max_sec = 10.0;
                int    wm      = g_winmode;
                if (rest.size() >= 1) steps   = to_int(rest[0], steps);
                if (rest.size() >= 2) max_sec = to_double(rest[1], max_sec);
                if (rest.size() >= 3) wm      = to_int(rest[2], wm);
                // 三档威胁搜索步数（VC2 / VCT / VCF），缺省 1 / 18 / 180。
                gvg::VctParams params;
                if (rest.size() >= 4) params.vc  = to_int(rest[3], params.vc);
                if (rest.size() >= 5) params.vct = to_int(rest[4], params.vct);
                if (rest.size() >= 6) params.vcf = to_int(rest[5], params.vcf);

                const int color = (c == "b") ? gvg::BLACK : gvg::WHITE;
                const uint64_t h0 = board.hash();
                gvg::AnalysisResult r =
                    gvg::analyse(board, color, steps, wm, max_sec, 300000,
                                 params);
                if (board.hash() != h0) {
                    std::cout << "error hash\n";
                } else {
                    for (size_t i = 0; i < r.labels.size(); ++i) {
                        const gvg::CandidateLabel& lab = r.labels[i];
                        if (lab.tag == 0) {
                            // 白棋威胁候选点（第 8 步）：无 W/L 标注，输出三列
                            // cand x y（威胁防御集交集，逐点证明搜索已停用封存）。
                            std::cout << "cand " << lab.x << ' ' << lab.y
                                      << '\n';
                            continue;
                        }
                        // 步数只是下界时加 '+'（W8+ = 至少 8 步；层 2 智能应对兜底）
                        std::cout << "cand " << lab.x << ' ' << lab.y << ' '
                                  << lab.tag << lab.steps
                                  << (lab.at_least ? "+" : "") << '\n';
                    }
                    if (r.timeout) std::cout << "timeout\n";
                    std::cout << "end\n";
                }
            }
        } else if (cmd == "wcand") {
            // 诊断：白棋威胁候选点的原始报告（不进“取最好一档”的收窄）。
            const uint64_t h0 = board.hash();
            const gvg::WhiteCandidateReport rep =
                gvg::white_threat_candidates(board);
            if (board.hash() != h0) {
                std::cout << "error hash\n";
            } else {
                std::cout << "unconstrained " << (rep.unconstrained ? 1 : 0)
                          << "\n";
                std::cout << "threatlines " << rep.threat_lines << "\n";
                for (size_t i = 0; i < rep.lines.size(); ++i) {
                    const gvg::ThreatLine& tl = rep.lines[i];
                    std::cout << "line " << tl.dx << ' ' << tl.dy << " rank "
                              << tl.rank << " blockers";
                    for (size_t k = 0; k < tl.blockers.size(); ++k)
                        std::cout << ' ' << tl.blockers[k].first << ','
                                  << tl.blockers[k].second;
                    std::cout << "\n";
                }
                std::cout << "mustblock";
                for (size_t k = 0; k < rep.must_block.size(); ++k)
                    std::cout << ' ' << rep.must_block[k].first << ','
                              << rep.must_block[k].second;
                std::cout << "\ncaptures";
                for (size_t k = 0; k < rep.captures.size(); ++k)
                    std::cout << ' ' << rep.captures[k].first << ','
                              << rep.captures[k].second;
                std::cout << "\nintersect " << rep.intersect_size << ' '
                          << (rep.intersect_empty ? 1 : 0) << "\npool";
                for (size_t k = 0; k < rep.candidates.size(); ++k)
                    std::cout << ' ' << rep.candidates[k].first << ','
                              << rep.candidates[k].second;
                std::cout << "\nend\n";
            }
        } else if (cmd == "prove") {
            // 黑方证明搜索（VCT，含三）：不落子、不改棋盘，与 g_winmode 无关。
            int    steps   = 11;
            double max_sec = 10.0;
            std::vector<std::string> rest;
            std::string tok;
            while (in >> tok) rest.push_back(tok);
            if (rest.size() >= 1) steps   = to_int(rest[0], steps);
            if (rest.size() >= 2) max_sec = to_double(rest[1], max_sec);

            if (board.turn() != gvg::BLACK) {
                std::cout << "error turn\n";
            } else {
                const uint64_t h0 = board.hash();
                const gvg::ProveResult r = gvg::prove_black(
                    board, steps, /*allow_three=*/true, max_sec, 300000);
                if (board.hash() != h0) {
                    std::cout << "error hash\n";
                } else if (r == gvg::ProveResult::WIN) {
                    std::cout << "win\n";
                } else if (r == gvg::ProveResult::TIMEOUT) {
                    std::cout << "timeout\n";
                } else {
                    std::cout << "no\n";
                }
            }
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
