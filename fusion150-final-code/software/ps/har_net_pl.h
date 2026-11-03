#ifndef HAR_NET_PL_H
#define HAR_NET_PL_H
#include <stdint.h>
#define HAR_FUSED_PROFILE "fused-guard4k-v1"
#define HAR_POISON ((int32_t)0x5a5a5a5a)
typedef struct {
    int64_t in[576] __attribute__((aligned(64)));
    int32_t before[16] __attribute__((aligned(64)));
    int32_t out[1024] __attribute__((aligned(64)));
    void *device;
    uint64_t timeout_ticks;
    unsigned calls;
    int faulted;
} har_net_ctx;
enum { HAR_NP_OK=0,HAR_NP_ARG=20,HAR_NP_BUSY=21,HAR_NP_TIMEOUT=22,
       HAR_NP_STATUS=23,HAR_NP_FAULTED=24,HAR_NP_INIT=25 };
int har_net_init(har_net_ctx *s);
int har_net_run(har_net_ctx *s,const int32_t *input,int32_t *logits);
uint64_t har_net_ticks(void);
uint64_t har_net_frequency(void);
#endif
