#include "har_fixed.h"
#include "har_parameters.h"
#include <limits.h>

/* No float/libm calls at inference time. All hidden activations are Q16.
 * Model constants are generated offline from the frozen source weights. */
int64_t har_floor_shift(int64_t x, unsigned sh) {
    if (!sh) return x;
    int64_t d = (int64_t)1 << sh;
    int64_t q = x / d;
    return q - (x < 0 && x % d != 0);
}
int64_t har_round_div(int64_t x, int64_t d) {
    return x >= 0 ? (x + d/2)/d : -((-x+d/2)/d);
}
uint64_t har_isqrt(uint64_t x) {
    uint64_t result=0, bit=(uint64_t)1 << 62;
    while (bit>x) bit>>=2;
    while (bit) {
        if (x>=result+bit) { x-=result+bit; result=(result>>1)+bit; }
        else result>>=1;
        bit>>=2;
    }
    return result;
}
static int8_t quant(int32_t x, int exp) {
    int sh=16+exp;
    int64_t q=sh>0 ? har_round_div(x,(int64_t)1<<sh) : (int64_t)x*((int64_t)1<<(-sh));
    return (int8_t)(q < -128 ? -128 : q>127 ? 127 : q);
}
static int store_q16(int64_t x,int32_t *out) {
    if (x<INT32_MIN || x>INT32_MAX) return HAR_OVERFLOW;
    *out=(int32_t)x; return HAR_OK;
}
static int rescale_acc(int32_t x,int exp,int32_t *out) {
    return store_q16(exp>=0 ? (int64_t)x*((int64_t)1<<exp) : har_floor_shift(x,(unsigned)-exp),out);
}
int har_gemm_cpu(const int8_t *a,const int8_t *b,int32_t *c,int m,int k,int n,void *ctx) {
    (void)ctx;
    if(m<1||m>32||k<1||k>36||n<1||n>32) return 1;
    for(int i=0;i<m;i++) for(int j=0;j<n;j++) {
        int32_t sum=0;
        for(int r=0;r<k;r++) sum+=(int32_t)a[i*k+r]*(int32_t)b[r*n+j];
        c[i*n+j]=sum;
    }
    return 0;
}
static int linear(const int32_t *x,int m,int k,int n,const int8_t *w,const int32_t *bias,
                  int ie,int we,int32_t *out,har_workspace *s,har_gemm_fn gemm,void *ctx) {
    for(int i=0;i<m*k;i++) s->a8[i]=quant(x[i],ie);
    if(gemm(s->a8,w,s->c32,m,k,n,ctx)) return HAR_GEMM_ERROR;
    s->gemm_calls++;
    for(int i=0;i<m*n;i++) {
        int32_t z;
        if(rescale_acc(s->c32[i],16+ie+we,&z)) return HAR_OVERFLOW;
        if(store_q16((int64_t)z+bias[i%n],out+i)) return HAR_OVERFLOW;
    }
    return HAR_OK;
}
static int norm(const int32_t *x,const int32_t *gamma,int32_t *out) {
    for(int i=0;i<32;i++) {
        uint64_t sq=0;
        for(int j=0;j<16;j++) {
            int64_t v=x[i*16+j];
            /* Guard before squaring/summing, with room for all 16 terms. */
            if(v <= -((int64_t)1<<28) || v >= ((int64_t)1<<28)) return HAR_OVERFLOW;
            sq+=(uint64_t)(v*v);
        }
        uint64_t denominator=har_isqrt(sq/16+HAR_EPSILON_Q32);
        if(!denominator) denominator=1;
        for(int j=0;j<16;j++) {
            int64_t numerator=(int64_t)x[i*16+j]*gamma[j]*4;
            if(store_q16(har_round_div(numerator,(int64_t)denominator),out+i*16+j)) return HAR_OVERFLOW;
        }
    }
    return HAR_OK;
}
static void softmax_rows(const int32_t *x,int32_t *out) {
    for(int row=0;row<32;row++) {
        int32_t maximum=x[row*32];
        for(int j=1;j<32;j++) if(x[row*32+j]>maximum) maximum=x[row*32+j];
        int64_t total=0;
        for(int j=0;j<32;j++) {
            int64_t idx=((int64_t)maximum-x[row*32+j]+128)/256;
            if(idx>4096) idx=4096;
            out[row*32+j]=har_exp_lut[idx]; total+=out[row*32+j];
        }
        for(int j=0;j<32;j++) out[row*32+j]=(int32_t)(((int64_t)out[row*32+j]*65536+total/2)/total);
    }
}
#define TRY(call) do { int status=(call); if(status) return status; } while(0)
#define LINEAR(name,x,m,k,n,out) TRY(linear(x,m,k,n,har_##name##_weight,har_##name##_bias,HAR_##name##_INPUT_EXP,HAR_##name##_WEIGHT_EXP,out,s,gemm,ctx))

int har_predict_q16(const int32_t input[1152],int32_t logits[6],har_workspace *s,har_gemm_fn gemm,void *ctx) {
    if(!input||!logits||!s||!gemm) return HAR_BAD_INPUT;
    s->gemm_calls=0;
    for(int i=0;i<1152;i++) if(input[i]<=-8388608||input[i]>=8388608) return HAR_BAD_INPUT;
    LINEAR(embed,input,32,36,16,s->h);
    for(int i=0;i<512;i++) TRY(store_q16((int64_t)s->h[i]+har_position[i],s->h+i));
    TRY(norm(s->h,har_norm1_gamma,s->n));
    LINEAR(q,s->n,32,16,16,s->q);
    LINEAR(k,s->n,32,16,16,s->k);
    LINEAR(v,s->n,32,16,16,s->v);
    for(int i=0;i<32;i++) for(int j=0;j<16;j++) {
        s->a8[i*16+j]=quant(s->q[i*16+j],HAR_Q_EXP);
        s->b8[j*32+i]=quant(s->k[i*16+j],HAR_K_EXP);
    }
    if(gemm(s->a8,s->b8,s->c32,32,16,32,ctx)) return HAR_GEMM_ERROR;
    s->gemm_calls++;
    for(int i=0;i<1024;i++) {
        int32_t z; TRY(rescale_acc(s->c32[i],16+HAR_Q_EXP+HAR_K_EXP,&z));
        s->scores[i]=(int32_t)har_floor_shift(z,2);
    }
    softmax_rows(s->scores,s->prob);
    for(int i=0;i<1024;i++) s->a8[i]=quant(s->prob[i],HAR_PROB_EXP);
    for(int i=0;i<512;i++) s->b8[i]=quant(s->v[i],HAR_V_EXP);
    if(gemm(s->a8,s->b8,s->c32,32,32,16,ctx)) return HAR_GEMM_ERROR;
    s->gemm_calls++;
    for(int i=0;i<512;i++) TRY(rescale_acc(s->c32[i],16+HAR_PROB_EXP+HAR_V_EXP,s->av+i));
    LINEAR(out,s->av,32,16,16,s->temp);
    for(int i=0;i<512;i++) TRY(store_q16((int64_t)s->h[i]+s->temp[i],s->h+i));
    TRY(norm(s->h,har_norm2_gamma,s->n));
    LINEAR(ff1,s->n,32,16,32,s->ff);
    for(int i=0;i<1024;i++) if(s->ff[i]<0) s->ff[i]=0;
    LINEAR(ff2,s->ff,32,32,16,s->temp);
    for(int i=0;i<512;i++) TRY(store_q16((int64_t)s->h[i]+s->temp[i],s->h+i));
    for(int j=0;j<16;j++) {
        int64_t sum=0;for(int i=0;i<32;i++) sum+=s->h[i*16+j];
        s->n[j]=(int32_t)har_floor_shift(sum,5);
    }
    LINEAR(classifier,s->n,1,16,6,logits);
    return HAR_OK;
}
