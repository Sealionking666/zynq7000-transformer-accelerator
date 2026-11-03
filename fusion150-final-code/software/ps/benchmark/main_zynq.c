#include "build_identity.h"
/* Bare-metal benchmark / validation for the one-shot fused accelerator.
 *
 * The ARM path (har_predict_q16 + har_gemm_cpu) is kept as an independent
 * reference so every board run cross-checks PL logits against ARM logits and
 * against the frozen expected logits, exactly as the legacy harness did.
 */
#include "har_fixed.h"
#include "har_net_pl.h"
#include "har_demo.h"
#include "xil_printf.h"
#include "xil_cache.h"

static har_net_ctx net;
#ifdef HAR_VALIDATION
static int32_t validation_input_storage[1152] __attribute__((aligned(64)));
#endif
static int32_t hardware[6];
#ifndef HAR_VALIDATION
static har_workspace workspace;
static int32_t cpu[6];
static void print_ticks(const char *name, uint64_t t) {
    xil_printf("%s=0x%08x%08x ", name, (unsigned)(t >> 32), (unsigned)t);
}
#endif

int main(void) {
    Xil_ICacheEnable();
    Xil_DCacheEnable();
    xil_printf("HAR_PROFILE name=%s token=%s guard_bytes=4160\r\n", HAR_FUSED_PROFILE, HAR_BUILD_TOKEN);
#ifdef HAR_VALIDATION
    xil_printf("\r\nHAR_VALIDATION_BEGIN samples=%d\r\n", HAR_VALIDATION_COUNT);
#else
    xil_printf("\r\nHAR_BOARD_BEGIN contract=int8-nearest-q16-v1 samples=%d repeats=10 fused=1\r\n",
               HAR_DEMO_COUNT);
#endif
#ifndef HAR_VALIDATION
    print_ticks("timer_hz", har_net_frequency());
    xil_printf("\r\n");
#endif
    int status = har_net_init(&net);
    if (status) { xil_printf("HAR_BOARD_FAIL init=%d\r\n", status); return 1; }

#ifdef HAR_VALIDATION
    {
        unsigned correct = 0;
        uint32_t hash = 2166136261u;
        unsigned before = net.calls;
        for (int i = 0; i < HAR_VALIDATION_COUNT; i++) {
            const int32_t *original_input=har_validation_inputs+i*1152;
            for(int k=0;k<1152;k++)validation_input_storage[k]=original_input[k];
            const int32_t *input=validation_input_storage;
            if (har_net_run(&net, input, hardware)) {
                xil_printf("HAR_VALIDATION_FAIL sample=%d status=%d\r\n", i, net.faulted);
                return 1;
            }
            int pred = 0;
            for (int j = 0; j < 6; j++) {
                int32_t want = har_validation_logits[i * 6 + j];
                if (hardware[j] != want) {
                    xil_printf("HAR_VALIDATION_FAIL sample=%d logit=%d got=%d want=%d\r\n",
                               i, j, hardware[j], want);
                    return 1;
                }
                hash = (hash ^ (uint32_t)hardware[j]) * 16777619u;
                if (hardware[j] > hardware[pred]) pred = j;
            }
            correct += (pred == har_validation_labels[i]);
            if ((i + 1) % 256 == 0 || i + 1 == HAR_VALIDATION_COUNT)
                xil_printf("HAR_VALIDATION_PROGRESS samples=%d checksum=%08x\r\n", i + 1, hash);
        }
        xil_printf("HAR_VALIDATION_PASS samples=%d logits=%d raw32_calls=%u correct=%u checksum=%08x\r\n",
                   HAR_VALIDATION_COUNT, HAR_VALIDATION_COUNT * 6, net.calls - before,
                   correct, hash);
    }
#else
    {
        unsigned passed = 0;
        unsigned before = net.calls;
        for (int repeat = 0; repeat < 11; repeat++) {
            for (int sample = 0; sample < HAR_DEMO_COUNT; sample++) {
                const int32_t *input = har_demo_inputs + sample * 1152;
                uint64_t t0 = har_net_ticks();
                status = har_predict_q16(input, cpu, &workspace, har_gemm_cpu, 0);
                uint64_t cpu_ticks = har_net_ticks() - t0;
                if (status) { xil_printf("HAR_BOARD_FAIL cpu=%d\r\n", status); return 1; }

                t0 = har_net_ticks();
                status = har_net_run(&net, input, hardware);
                uint64_t pl_ticks = har_net_ticks() - t0;
                if (status || net.faulted) {
                    xil_printf("HAR_BOARD_FAIL inference=%d calls=%u faulted=%d\r\n",
                               status, net.calls, net.faulted);
                    return 1;
                }
                for (int j = 0; j < 6; j++) {
                    if (cpu[j] != hardware[j] || hardware[j] != har_demo_logits[sample * 6 + j]) {
                        xil_printf("HAR_BOARD_FAIL repeat=%d sample=%d logit=%d expected=%d pl=%d arm=%d\r\n",
                                   repeat, sample, j, har_demo_logits[sample * 6 + j],
                                   hardware[j], cpu[j]);
                        return 1;
                    }
                }
                xil_printf("HAR_SAMPLE_PASS repeat=%d sample=%d warmup=%d ", repeat, sample, repeat == 0);
                print_ticks("cpu_ticks", cpu_ticks);
                print_ticks("pspl_ticks", pl_ticks);
                xil_printf("\r\n");
                if (repeat) passed++;
            }
        }
        xil_printf("HAR_BOARD_PASS measured_inferences=%u logits=%u raw32_calls=%u\r\n",
                   passed, passed * 6, net.calls - before);
    }
#endif
    return 0;
}
