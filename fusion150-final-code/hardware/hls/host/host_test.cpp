/* Host equivalence gate for the fused kernel.
 *
 * Stage-1 gate: if the fused C++ does not reproduce the frozen logits
 * bit-for-bit on the host, no synthesis or board time is spent on it.
 * Checks the same three things the board validation checks:
 *   1. all 6 demo logits,
 *   2. all 1796 validation logits (10776 values),
 *   3. FNV-1a checksum and the argmax hit count (1449).
 */
#include "../src/har_net.h"
#include "../src/demo_bench.h"
#include "../src/demo_validation.h"
#include <stdio.h>
#include <string.h>
#include <stdint.h>

/* Pack 1152 int32 elements into 576 64-bit words (low half = even index). */
static void pack_in(const int32_t *in, int64_t *out) {
    for (int w = 0; w < 576; w++)
        out[w] = (int64_t)(((uint64_t)(uint32_t)in[2 * w]) |
                           ((uint64_t)(uint32_t)in[2 * w + 1] << 32));
}

static int run_case(const int32_t *in, const int32_t *expect, int idx, const char *tag) {
    int32_t out[16];
    int64_t in64[576];
    for (int i = 0; i < 16; i++) out[i] = (int32_t)0x5a5a5a5a;
    pack_in(in, in64);
    int st = har_net(in64, out);
    if (st) { printf("FAIL %s idx=%d status=%d\n", tag, idx, st); return 1; }
    for (int j = 0; j < 6; j++) {
        if (out[j] != expect[j]) {
            printf("FAIL %s idx=%d logit=%d got=%d want=%d\n", tag, idx, j, out[j], expect[j]);
            return 1;
        }
    }
    for (int j = 6; j < 16; j++) {
        if (out[j] != (int32_t)0x5a5a5a5a) {
            printf("FAIL %s idx=%d guard word %d overwritten=%d\n", tag, idx, j, out[j]);
            return 1;
        }
    }
    return 0;
}

int main(void) {
    int fails = 0;
    for (int i = 0; i < HAR_DEMO_COUNT; i++) {
        fails += run_case(har_demo_inputs + i * 1152, har_demo_logits + i * 6, i, "demo");
    }
    printf("%s demo=%d\n", fails ? "DEMO_TB_FAIL" : "DEMO_TB_PASS", HAR_DEMO_COUNT);
    if (fails) return 1;

    uint32_t hash = 2166136261u;
    unsigned correct = 0;
    for (int i = 0; i < HAR_VALIDATION_COUNT; i++) {
        int32_t out[16];
        int64_t in64[576];
        pack_in(har_validation_inputs + i * 1152, in64);
        int st = har_net(in64, out);
        if (st) { printf("FAIL validation idx=%d status=%d\n", i, st); return 1; }
        int pred = 0;
        for (int j = 0; j < 6; j++) {
            int32_t want = har_validation_logits[i * 6 + j];
            if (out[j] != want) {
                printf("FAIL validation idx=%d logit=%d got=%d want=%d\n", i, j, out[j], want);
                return 1;
            }
            hash = (hash ^ (uint32_t)out[j]) * 16777619u;
            if (out[j] > out[pred]) pred = j;
        }
        correct += (pred == har_validation_labels[i]);
    }
    printf("VALIDATION samples=%d logits=%d correct=%u checksum=%08x\n",
           HAR_VALIDATION_COUNT, HAR_VALIDATION_COUNT * 6, correct, hash);
    int ok = (correct == 1449u && hash == 0xbd0b22adu);
    printf("%s\n", ok ? "HOST_EQUIV_PASS" : "HOST_EQUIV_FAIL");
    return ok ? 0 : 1;
}
