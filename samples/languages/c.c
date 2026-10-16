#include <stdio.h>
int main(void) {
    int a = 10;
    int b = 20;
    int result = 0;
    if (a < b) {
        result = a + b * 2;
    } else {
        result = a - b;
    }
    return 0;
}

