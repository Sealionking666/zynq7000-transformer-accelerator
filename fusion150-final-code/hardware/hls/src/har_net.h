#ifndef HAR_NET_H
#define HAR_NET_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* One-shot fused HAR accelerator.
 *
 * The whole frozen network (10 integer GEMMs, RMSNorm, softmax, requantisation,
 * residual adds, ReLU, mean pooling) runs inside a single accelerator call.
 * Weights and the exp LUT are on-chip constants; the only DDR traffic is the
 * 1152-word Q16 input and the 6 logits.
 *
 * Transport note: the input port is 64 bit (the PS HP0 slave is 64 bit), so
 * the 1152 int32 elements travel as 576 packed words, low half = even element
 * index, high half = odd element index.
 *
 * Bit-exactness: every integer operation reproduces the frozen
 * har_predict_q16() reference sequence, including the modular shifts and the
 * reciprocal-plus-repair divisions. This is verified against all 1796 frozen
 * validation samples before any synthesis is attempted.
 */
enum { HAR_NET_OK = 0, HAR_NET_BAD_INPUT = 1, HAR_NET_OVERFLOW = 3 };
int har_net(const int64_t *input, int32_t *logits);
#ifdef __cplusplus
}
#endif
#endif
