// dbg.cpp - 临时诊断：逐步复现 prove_black 的关键子步骤。
#include "board.h"
#include "forbidden.h"
#include "vcfvct.h"
#include <stdio.h>
using namespace gvg;

int main() {
    Board b(15);
    b.make_move(6, 7, BLACK);
    b.make_move(7, 7, BLACK);
    b.make_move(8, 7, BLACK);
    printf("turn=%d\n", b.turn());

    const int idx57 = Board::index(5, 7);
    printf("p4(5,7)=%d pat_dir0=%d dir_index=%d\n",
           b.cached_pattern4_black(idx57), b.cached_pattern(0, idx57, 0),
           Board::dir_index(1, 0));
    printf("check_forbidden(5,7)=%d\n", (int)check_forbidden(b, 5, 7));

    ProveResult r = prove_black(b, 3, true, 5.0, 300000);
    printf("prove_black(3)=%d (WIN=0 UNKNOWN=1 TIMEOUT=2)\n", (int)r);

    // 逐步走一遍应发生的证明链
    bool ok = b.make_move(5, 7, BLACK);
    printf("make(5,7)=%d five=%d\n", ok, (int)b.last_move_was_five());
    ok = b.make_move(4, 7, WHITE);
    printf("make(4,7)=%d\n", ok);
    ok = b.make_move(9, 7, BLACK);
    printf("make(9,7)=%d five=%d\n", ok, (int)b.last_move_was_five());
    b.undo_move();
    b.undo_move();
    b.undo_move();
    printf("hash_restored_done\n");
    return 0;
}
