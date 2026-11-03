#include "build_identity.h"
#include "har_net_lifecycle.h"
#include "har_demo.h"
#include "xil_cache.h"
#include "xil_printf.h"

/* Deliberately short software timeout. Hardware is allowed to finish normally.
   The input and context stay alive, intact and exclusively owned throughout.
   This does not inject stuck AXI, bad BRESP, a reset, or electrical faults. */
static har_net_ctx net,other;
static int32_t storage[1168] __attribute__((aligned(64)));
static int32_t logits[6] __attribute__((aligned(64)));
#define NEED(c,n) do {if(!(c)){xil_printf("HAR_LIFECYCLE_FAIL check=%d offset=%d\r\n",n,offset);return 1;}}while(0)
int main(void) {
    Xil_ICacheEnable();Xil_DCacheEnable();
    xil_printf("HAR_PROFILE name=%s token=%s guard_bytes=4160\r\n",HAR_FUSED_PROFILE,HAR_BUILD_TOKEN);
    xil_printf("HAR_LIFECYCLE_BEGIN contract=bounded-timeout-drain-v1\r\n");
    int offset=0;
    NEED(har_net_init(&net)==HAR_NP_OK,1);
    const uint64_t normal_timeout=net.timeout_ticks;
    unsigned total_rejections=0;
    for(offset=0;offset<4;offset++) {
        int32_t *input=storage+offset;
        for(int i=0;i<1152;i++)input[i]=har_validation_inputs[i];
        net.timeout_ticks=normal_timeout;
        NEED(har_net_run(&net,input,logits)==HAR_NP_OK,2);
        for(int j=0;j<6;j++)NEED(logits[j]==har_validation_logits[j],3);
        const unsigned before=net.calls;
        for(int j=0;j<6;j++)logits[j]=-12345;
        net.timeout_ticks=1;
        NEED(har_net_run(&net,input,logits)==HAR_NP_TIMEOUT,4);
        NEED(net.faulted&&har_net_device_state()==HAR_DEV_FAULTED&&net.calls==before,5);
        /* Exercise the first drain immediately, before printing or extra work. */
        int result=har_net_recover(&net);
        unsigned rejected=result==HAR_NP_FAULTED;
        NEED(result==HAR_NP_OK||result==HAR_NP_FAULTED,6);
        if(result!=HAR_NP_OK) {
            NEED(har_net_init(&other)==HAR_NP_FAULTED,7);
            NEED(har_net_init(&net)==HAR_NP_FAULTED,8);
            NEED(har_net_run(&net,input,logits)==HAR_NP_FAULTED,9);
            const uint64_t start=har_net_ticks();
            do {
                result=har_net_recover(&net);
                if(result==HAR_NP_FAULTED)rejected++;
                NEED(har_net_ticks()-start<har_net_frequency()/10u,10);
                NEED(result==HAR_NP_OK||result==HAR_NP_FAULTED,11);
            }while(result!=HAR_NP_OK);
        }
        NEED(net.calls==before&&!net.faulted&&har_net_device_state()==HAR_DEV_READY,12);
        for(int j=0;j<6;j++)NEED(logits[j]==-12345,13);
        NEED(har_net_init(&other)==HAR_NP_BUSY,14);
        total_rejections+=rejected;
        net.timeout_ticks=normal_timeout;
        NEED(har_net_run(&net,input,logits)==HAR_NP_OK&&net.calls==before+1,15);
        for(int j=0;j<6;j++)NEED(logits[j]==har_validation_logits[j],16);
        xil_printf("HAR_LIFECYCLE_CASE offset=%d timeout_ticks=1 early_rejections=%u late_published=0 calls=%u\r\n",offset*4,rejected,net.calls);
    }
    NEED(total_rejections>0,17);
    xil_printf("HAR_LIFECYCLE_PASS cases=4 timeouts=4 drains=4 normal_calls=%u early_rejections=%u late_published=0\r\n",net.calls,total_rejections);
    return 0;
}
