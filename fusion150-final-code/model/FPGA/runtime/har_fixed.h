#ifndef HAR_FIXED_H
#define HAR_FIXED_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Raw32 GEMM: packed row-major INT8 A[M,K], B[K,N], INT32 C[M,N]. */
typedef int (*har_gemm_fn)(const int8_t*,const int8_t*,int32_t*,int,int,int,void*);
enum { HAR_OK=0, HAR_BAD_INPUT=1, HAR_GEMM_ERROR=2, HAR_OVERFLOW=3 };
typedef struct {
    int32_t h[512], q[512], k[512], v[512], n[512];
    int32_t scores[1024], prob[1024], av[512], ff[1024], temp[512];
    int8_t a8[1152], b8[1152];
    int32_t c32[1024];
    unsigned gemm_calls;
} har_workspace;
int har_predict_q16(const int32_t input[1152], int32_t logits[6],
                    har_workspace *ws, har_gemm_fn gemm, void *context);
int har_gemm_cpu(const int8_t*,const int8_t*,int32_t*,int,int,int,void*);
int64_t har_floor_shift(int64_t value, unsigned shift);
int64_t har_round_div(int64_t value, int64_t divisor);
uint64_t har_isqrt(uint64_t value);
#ifdef __cplusplus
}
#endif
#endif
