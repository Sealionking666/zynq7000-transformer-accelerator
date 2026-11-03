#include "har_net.h"
#include "demo_bench.h"
#include <stdio.h>

/* Pack 1152 int32 elements into 576 64-bit words (low half = even index). */
static void pack_in(const int32_t *in, int64_t *out) {
    for (int w = 0; w < 576; w++)
        out[w] = (int64_t)(((uint64_t)(uint32_t)in[2 * w]) |
                           ((uint64_t)(uint32_t)in[2 * w + 1] << 32));
}

int main(void) {
    int fails = 0;
    for (int i = 0; i < HAR_DEMO_COUNT; i++) {
        int32_t out[16];
        int64_t in64[576];
        for (int j = 0; j < 16; j++) out[j] = (int32_t)0x5a5a5a5a;
        pack_in(har_demo_inputs + i * 1152, in64);
        int st = har_net(in64, out);
        if (st) { printf("HAR_NET_TB status=%d case=%d\n", st, i); fails++; continue; }
        for (int j = 0; j < 6; j++) {
            if (out[j] != har_demo_logits[i * 6 + j]) {
                printf("HAR_NET_TB case=%d logit=%d got=%d want=%d\n",
                       i, j, out[j], har_demo_logits[i * 6 + j]);
                fails++;
            }
        }
        for (int j = 6; j < 16; j++) {
            if (out[j] != (int32_t)0x5a5a5a5a) { printf("HAR_NET_TB guard case=%d\n", i); fails++; }
        }
    }
    printf("%s cases=%d failures=%d\n", fails ? "HAR_NET_TB_FAIL" : "HAR_NET_TB_PASS",
           HAR_DEMO_COUNT, fails);
    return fails ? 1 : 0;
}
