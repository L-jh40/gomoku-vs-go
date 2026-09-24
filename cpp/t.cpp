#include <stdio.h>
#include <vector>
#include <algorithm>

int main() {
    std::vector<int> v{3, 1, 2};
    std::sort(v.begin(), v.end());
    printf("hi %d\n", v[0]);
    return 0;
}
