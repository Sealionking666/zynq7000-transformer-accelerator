#include "build_identity.h"
#include "official_identity.h"
#include "har_net_pl.h"
#include "xil_cache.h"
#include "xil_printf.h"
#include <stdint.h>
extern const int32_t official_inputs[];
extern const int32_t official_expected[];
extern const int32_t official_labels[];
static har_net_ctx net __attribute__((aligned(64)));
static int32_t input[1152] __attribute__((aligned(64)));
static int32_t output[6] __attribute__((aligned(64)));
int main(void) {
 Xil_ICacheEnable();Xil_DCacheEnable();
 xil_printf("HAR_PROFILE name=%s token=%s guard_bytes=4160\r\n",HAR_FUSED_PROFILE,HAR_BUILD_TOKEN);
 xil_printf("HAR_OFFICIAL_BEGIN samples=2947 logits=17682 input_sha256=%s oracle_sha256=%s\r\n",OFFICIAL_INPUT_SHA256,OFFICIAL_ORACLE_SHA256);
 int status=har_net_init(&net);
 if(status){xil_printf("HAR_OFFICIAL_FAIL init=%d\r\n",status);return 1;}
 unsigned correct=0,before=net.calls;uint32_t ih=2166136261u,h=2166136261u;
 uint64_t begin=har_net_ticks();
 for(int i=0;i<2947;i++){
  for(int k=0;k<1152;k++){input[k]=official_inputs[i*1152+k];ih=(ih^(uint32_t)input[k])*16777619u;}
  status=har_net_run(&net,input,output);
  if(status||net.faulted){xil_printf("HAR_OFFICIAL_FAIL sample=%d status=%d faulted=%d\r\n",i,status,net.faulted);return 1;}
  for(int k=0;k<1152;k++)if(input[k]!=official_inputs[i*1152+k]){xil_printf("HAR_OFFICIAL_FAIL input_mutation sample=%d element=%d\r\n",i,k);return 1;}
  int pred=0;
  for(int j=0;j<6;j++){
   if(output[j]!=official_expected[i*6+j]){xil_printf("HAR_OFFICIAL_FAIL sample=%d logit=%d got=%08x want=%08x\r\n",i,j,(unsigned)output[j],(unsigned)official_expected[i*6+j]);return 1;}
   h=(h^(uint32_t)output[j])*16777619u;
   if(output[j]>output[pred])pred=j;
  }
  correct+=(pred==official_labels[i]);
  xil_printf("HAR_OFFICIAL_SAMPLE sample=%d label=%d prediction=%d calls=%u input_checksum=%08x logits=%08x,%08x,%08x,%08x,%08x,%08x\r\n",i,official_labels[i],pred,net.calls-before,ih,(unsigned)output[0],(unsigned)output[1],(unsigned)output[2],(unsigned)output[3],(unsigned)output[4],(unsigned)output[5]);
 }
 uint64_t end=har_net_ticks(),ticks=end-begin;
 xil_printf("HAR_OFFICIAL_TIME begin=%08x%08x end=%08x%08x ticks=%08x%08x timer_hz=%u\r\n",(unsigned)(begin>>32),(unsigned)begin,(unsigned)(end>>32),(unsigned)end,(unsigned)(ticks>>32),(unsigned)ticks,(unsigned)har_net_frequency());
 xil_printf("HAR_OFFICIAL_PASS samples=2947 logits=17682 calls=%u correct=%u input_checksum=%08x checksum=%08x\r\n",net.calls-before,correct,ih,h);
 return 0;
}
