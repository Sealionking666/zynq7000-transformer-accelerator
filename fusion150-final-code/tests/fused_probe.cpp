#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "har_net.h"
#include "har_fixed.h"

static uint32_t rng=0x6d2b79f5u;
static uint32_t next(){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
static int32_t in[1152];
static int64_t packed[576],before[576];
static har_workspace ws;
static const int32_t sentinel=(int32_t)0x5a5a5a5a;
static void pack(){for(int i=0;i<576;i++)packed[i]=(int64_t)((uint64_t)(uint32_t)in[2*i]|((uint64_t)(uint32_t)in[2*i+1]<<32));}
static int check(int invalid){
    int32_t expected[6],out[32];for(int i=0;i<32;i++)out[i]=sentinel;
    pack();memcpy(before,packed,sizeof packed);
    int a=har_predict_q16(in,expected,&ws,har_gemm_cpu,0);
    int b=har_net(packed,out);
    if(a!=b || (invalid && a!=1)){printf("STATUS_FAIL %d %d\n",a,b);return 1;}
    if(!a && memcmp(expected,out,sizeof expected)){puts("LOGITS_FAIL");return 1;}
    for(int i=a?0:6;i<32;i++)if(out[i]!=sentinel){puts("OUTPUT_TAIL_FAIL");return 1;}
    if(memcmp(before,packed,sizeof packed)){puts("INPUT_WRITE_FAIL");return 1;}
    return 0;
}
int main(){
    int valid=0,invalid=0;
    for(int t=0;t<640;t++){
        for(int i=0;i<1152;i++){
            switch(t%8){
                case 0:in[i]=0;break;
                case 1:in[i]=8388607;break;
                case 2:in[i]=-8388607;break;
                case 3:in[i]=(i&1)?8388607:-8388607;break;
                case 4:in[i]=(int32_t)(next()%8193u)-4096;break;
                case 5:in[i]=(next()%32u)?0:8388607;break;
                default:in[i]=(int32_t)(next()%16777215u)-8388607;break;
            }
        }
        if(check(0))return 1;valid++;
    }
    const int32_t bad[]={8388608,-8388608,INT32_MAX,INT32_MIN};
    memset(in,0,sizeof in);
    for(int pos=0;pos<1152;pos++)for(int j=0;j<4;j++){
        in[pos]=bad[j];if(check(1))return 1;invalid++;in[pos]=0;
    }
    // Recheck valid output after all rejected inputs and prior mixed valid calls.
    for(int i=0;i<1152;i++)in[i]=0;
    if(check(0))return 1;valid++;
    printf("FUSED_PROBE_PASS valid=%d invalid=%d output_tail=32 input_immutable=1\n",valid,invalid);
}
