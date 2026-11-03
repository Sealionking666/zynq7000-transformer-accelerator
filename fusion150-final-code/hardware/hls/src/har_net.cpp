/* One-shot fused HAR accelerator (architecture N1, tuning round v3).
 *
 * WHY THIS EXISTS
 * ---------------
 * The carried_best architecture calls the PL ten times per inference and every
 * call pays: three cache-flush calls, an AXI-Lite configure+start, a DONE poll,
 * a full 4 KiB invalidate, a 4 KiB poison-tail read-back and an output copy.
 * Measured split of its 0.697 ms total: 60.4% "gemm" bucket (of which only
 * 165.6 us is PL RTL) and 39.5% PS epilogues.
 *
 * v2 (N1 baseline, 285.5 us on board, 26,355 cosim cycles) kept the whole
 * network on the die: one call, one flush, one invalidate. This v3 round
 * removes the four remaining structural cycle sinks, every one of them
 * bit-exact against the same frozen reference:
 *
 *   1. The 96 64-bit divider calls (2 per norm row x 64 rows, 1 per softmax
 *      row x 32) are hoisted into their own flat row loops that pipeline at
 *      II=1 (the v2 row serialised isqrt -> divide -> elementwise, so every
 *      divider call sat on the critical path). The division itself is still
 *      the exact integer '/' of the reference -- no approximation, nothing
 *      to prove.
 *   2. norm and softmax are restructured into row-parallel passes
 *      (sum -> isqrt x4 -> divide -> elementwise) so the per-row long
 *      operations pipeline across rows instead of serialising behind the
 *      variable-trip isqrt while-loop of v2.
 *   3. gemm keeps v2's single 8x16 accumulator bank (4-way interleaving was
 *      measured to cost ~30k extra LUT in bank muxing) but registers the
 *      products one stage before the accumulate, taking the DSP multiply
 *      out of the loop-carried path that held the inner loop at II=4.
 *      Accumulation order per output element is unchanged, so the result is
 *      bit-identical.
 *   4. The input port is widened to 64 bit (the PS HP0 slave is 64 bit), so
 *      the 1152-word load streams as 576 words. The element order inside the
 *      packed word is low half = even index, high half = odd index.
 *   5. softmax max/sum use four interleaved partial chains and the mean pool
 *      reads eight consecutive elements per cycle (bank-conflict free).
 *
 * PIPELINE (identical order to har_predict_q16)
 *   load+quant input -> embed -> (+pos) -> norm1 -> {K,V,Q} -> scores
 *   -> softmax -> quant -> av -> out -> (+res) -> norm2 -> ff1 -> relu
 *   -> ff2 -> (+res) -> meanpool -> classifier -> logits
 */
#include <stdint.h>
#include <string.h>
#include "har_net.h"
#include "har_parameters.h"
#include "har_exp_local.h"
#include "har_wflat_defs.h"

#define LANES 16  /* parallel output lanes = one 16-lane activation group */
#define ASTR 36
#define BSTR 32

/* Divide/quant shifts and rescale exponents, all derived from the frozen
 * parameter macros so they cannot drift away from the reference. */
#define SH_INPUT   (16 + HAR_embed_INPUT_EXP)      /* 11 */
#define SH_N_QKV   (16 + HAR_q_INPUT_EXP)          /* 11 */
#define SH_Q_OUT   (16 + HAR_Q_EXP)                /* 12 */
#define SH_K_OUT   (16 + HAR_K_EXP)                /* 12 */
#define SH_V_OUT   (16 + HAR_V_EXP)                /* 11 */
#define SH_PROB    (16 + HAR_PROB_EXP)             /* 9  */
#define SH_AV      (16 + HAR_out_INPUT_EXP)        /* 11 */
#define SH_FF1_IN  (16 + HAR_ff1_INPUT_EXP)        /* 12 */
#define SH_FF2_IN  (16 + HAR_ff2_INPUT_EXP)        /* 12 */
#define SH_CLS_IN  (16 + HAR_classifier_INPUT_EXP) /* 13 */

#define RS_EMBED (16 + HAR_embed_INPUT_EXP + HAR_embed_WEIGHT_EXP)  /* 4 */
#define RS_Q     (16 + HAR_q_INPUT_EXP + HAR_q_WEIGHT_EXP)          /* 4 */
#define RS_K     (16 + HAR_k_INPUT_EXP + HAR_k_WEIGHT_EXP)          /* 4 */
#define RS_V     (16 + HAR_v_INPUT_EXP + HAR_v_WEIGHT_EXP)          /* 4 */
#define RS_OUT   (16 + HAR_out_INPUT_EXP + HAR_out_WEIGHT_EXP)      /* 3 */
#define RS_FF1   (16 + HAR_ff1_INPUT_EXP + HAR_ff1_WEIGHT_EXP)      /* 5 */
#define RS_FF2   (16 + HAR_ff2_INPUT_EXP + HAR_ff2_WEIGHT_EXP)      /* 5 */
#define RS_CLS   (16 + HAR_classifier_INPUT_EXP + HAR_classifier_WEIGHT_EXP) /* 6 */

#define SH_SCORE (16 + HAR_Q_EXP + HAR_K_EXP)      /* 8, then >>2 */
#define SH_AVQ   (16 + HAR_PROB_EXP + HAR_V_EXP)   /* 4  */

#define NF_NORM  (((uint64_t)1 << 45) - 1)
#define NF_SMX   (((uint64_t)1 << 47) - 1)

/* Every rescale exponent must stay inside the reference's exact 32-bit fast
 * path, otherwise the reference would take its widened branch. */
#if RS_EMBED < 0 || RS_EMBED > 16 || RS_Q < 0 || RS_OUT > 16 || RS_CLS > 16
#error rescale exponent outside the reference fast path
#endif
#if ((585216LL << RS_CLS) + 22892) > 2147483647LL
#error rescale guard bound no longer holds
#endif

/* The 64-bit integer division of the reference is used verbatim, but hoisted
 * into flat row loops that pipeline at II=1: the HLS pipelined divider has a
 * long latency yet accepts one new operand pair per cycle, so 32 row-level
 * divisions cost ~latency+32 cycles instead of sitting serially inside each
 * row's isqrt->divide->elementwise chain as they did in v2. Integer division
 * is exact by definition, so there is nothing to prove here. */

/* Eight independent exact bit-pair square roots. Frozen-all-input interval
 * proof bounds x<=7969210477391<2^43. Original leading bits2^56..2^44
 * are seven no-ops (res=0, x unchanged); run identical remaining22steps.
 * Preserve the schedule request; actual HLS II/cycles remain to observe. */
/* Every value here stays below 2^43 (the frozen interval proof bounds the row sum),
 * so 44 bits are enough. The narrower synthesized type shortens the restoring step's
 * carry chain -- the worst setup path in the routed design -- while keeping the same
 * arithmetic on the same values. The host build keeps the plain 64-bit type. */
#ifdef __SYNTHESIS__
#include <ap_int.h>
typedef ap_uint<44> sqrt_word_t;
typedef ap_uint<45> sqrt_diff_t;
#else
typedef uint64_t sqrt_word_t;
typedef uint64_t sqrt_diff_t;
#endif

/* Before each restoring step, r is a multiple of four times bit.
 * Both additions are therefore exact ORs. Widen the subtraction to45bits:
 * operands fit44, so bit44 is precisely its borrow and the accepted low44
 * bits equal the original nonnegative subtraction. Arithmetic unchanged. */
static inline void sqrt_step(sqrt_word_t &x, sqrt_word_t &r, sqrt_word_t bit) {
#pragma HLS INLINE
    sqrt_diff_t trial = (sqrt_diff_t)x - (sqrt_diff_t)(r | bit);
    if (((trial >> 44) & 1) == 0) {
        x = (sqrt_word_t)trial;
        r = (r >> 1) | bit;
    } else r >>= 1;
}

static void isqrt8(const uint64_t x[8], uint32_t y[8]) {
    sqrt_word_t xa = x[0], xb = x[1], xc = x[2], xd = x[3];
    sqrt_word_t xe = x[4], xf = x[5], xg = x[6], xh = x[7];
    sqrt_word_t ra = 0, rb = 0, rc = 0, rd = 0;
    sqrt_word_t re = 0, rf = 0, rg = 0, rh = 0;
    sqrt_word_t bit = (sqrt_word_t)1 << 42;
    for (int i = 0; i < 22; i++) {
#pragma HLS PIPELINE II=1
        sqrt_step(xa, ra, bit);
        sqrt_step(xb, rb, bit);
        sqrt_step(xc, rc, bit);
        sqrt_step(xd, rd, bit);
        sqrt_step(xe, re, bit);
        sqrt_step(xf, rf, bit);
        sqrt_step(xg, rg, bit);
        sqrt_step(xh, rh, bit);
        bit >>= 2;
    }
    y[0] = (uint32_t)ra; y[1] = (uint32_t)rb;
    y[2] = (uint32_t)rc; y[3] = (uint32_t)rd;
    y[4] = (uint32_t)re; y[5] = (uint32_t)rf;
    y[6] = (uint32_t)rg; y[7] = (uint32_t)rh;
}

/* Round the magnitude half-up, then restore the sign: exactly the reference
 * 32-bit quant() path used at every call site (all shifts are 9..13). */
/* Exact floor/remainder form: ties round away from zero. Clipping on
 * base confines the selected rounded result to[-128,127], so only the low8
 * carry is needed; no full32-bit magnitude or sign-restoration chain. */
#define QUANT_INTO(dst, val, SH)                                             \
    do {                                                                    \
        static_assert((SH) >= 1 && (SH) <= 30, "quant shift range");          \
        static_assert((-1 >> 1) == -1, "quant requires arithmetic shift");   \
        int32_t _x = (val);                                                  \
        int32_t _base = _x >> (SH);                                          \
        uint32_t _rem = (uint32_t)_x & (((uint32_t)1 << (SH)) - 1);           \
        uint32_t _half = (uint32_t)1 << ((SH) - 1);                           \
        uint32_t _bump = (_rem > _half) || (_rem == _half && _x >= 0);        \
        uint8_t _bits = (uint8_t)((uint32_t)_base + _bump);                   \
        int32_t _small = (int32_t)(_bits & 127u) - (int32_t)(_bits & 128u);    \
        (dst) = (int8_t)(_base < -128 ? -128 : (_base >= 127 ? 127 : _small)); \
    } while (0)

/* RMSNorm of all 32 rows, same frozen sequence as v2's NORM_ROW:
 *   A: sq = sum(v^2) over the row, with the range gate
 *   B: den = isqrt(sq/16 + eps)          (four rows per 29-step sweep)
 *   C: rc  = floor((2^45-1)/den)         (one pipelined divider, II=1)
 *   D: elementwise requantise            (row at a time, per-row scalars)
 *
 * v5 note: v3/v4 kept DEN[]/RC[] completely partitioned and indexed them with
 * i>>4 inside one flat 512-element pipeline. That turns every pipeline stage
 * into a 32:1 64-bit mux, which is what pushed csynth to 90.3k LUT and made
 * scheduling stall for tens of minutes at "Synthesizing". v5 keeps the same
 * arithmetic and pass structure but runs pass D row by row, so den/rc/half
 * are loop-invariant scalars and the 32-entry arrays stay ordinary RAMs. The
 * row sum is regrouped over four parallel chains; integer add/multiply are
 * exact, so no bit of the result changes. */
/* Explicit row/column banks:32rows x16columns, exactly512words.
   Physical bank=(row%4,col%8); local address=(row/4)*2+col/8. */
typedef int32_t har_act[4][8][16];
#define ACT(a,r,c) ((a)[(r)&3][(c)&7][((r)>>2)*2+((c)>>3)])
#define ACT_FLAT(a,i) ACT(a,(i)>>4,(i)&15)
/* Frozen-all-input interval proof bounds both RMSNorm inputs in signed23.
 * Keep original32-bit range checks; narrow only the exact square operand. */
struct norm23_t { signed int value:23; };
static int norm_pass(har_act &SRC, const int32_t *GAM, har_act &DST) {
#pragma HLS INLINE off
    static uint64_t DEN[32];
    static uint64_t RC[32];
    uint32_t bad = 0;

    for (int r = 0; r < 32; r += 8) {
        uint64_t xs[8];
#pragma HLS ARRAY_PARTITION variable=xs complete
        uint32_t ds[8];
#pragma HLS ARRAY_PARTITION variable=ds complete
        uint64_t sq0=0,sq1=0,sq2=0,sq3=0;
        uint64_t sq4=0,sq5=0,sq6=0,sq7=0;
        /* Eight rows share a cyclic8 bank at each j, and a bank has two read
           ports, so the row sum needs four cycles per j with eight rows. */
        for (int j = 0; j < 16; j++) {
#pragma HLS PIPELINE II=1
            int32_t v0=ACT_FLAT(SRC,(r*16+j)),v1=ACT_FLAT(SRC,((r+1)*16+j));
            int32_t v2=ACT_FLAT(SRC,((r+2)*16+j)),v3=ACT_FLAT(SRC,((r+3)*16+j));
            int32_t v4=ACT_FLAT(SRC,((r+4)*16+j)),v5=ACT_FLAT(SRC,((r+5)*16+j));
            int32_t v6=ACT_FLAT(SRC,((r+6)*16+j)),v7=ACT_FLAT(SRC,((r+7)*16+j));
            bad|=(uint32_t)(v0<=-268435456 || v0>=268435456);
            bad|=(uint32_t)(v1<=-268435456 || v1>=268435456);
            bad|=(uint32_t)(v2<=-268435456 || v2>=268435456);
            bad|=(uint32_t)(v3<=-268435456 || v3>=268435456);
            bad|=(uint32_t)(v4<=-268435456 || v4>=268435456);
            bad|=(uint32_t)(v5<=-268435456 || v5>=268435456);
            bad|=(uint32_t)(v6<=-268435456 || v6>=268435456);
            bad|=(uint32_t)(v7<=-268435456 || v7>=268435456);
            norm23_t narrow0;narrow0.value=v0;
            uint64_t norm_square0=(uint64_t)((int64_t)narrow0.value*(int64_t)narrow0.value);
#pragma HLS BIND_OP variable=norm_square0 op=mul impl=dsp latency=3
            sq0+=norm_square0;
            norm23_t narrow1;narrow1.value=v1;
            uint64_t norm_square1=(uint64_t)((int64_t)narrow1.value*(int64_t)narrow1.value);
#pragma HLS BIND_OP variable=norm_square1 op=mul impl=dsp latency=3
            sq1+=norm_square1;
            norm23_t narrow2;narrow2.value=v2;
            uint64_t norm_square2=(uint64_t)((int64_t)narrow2.value*(int64_t)narrow2.value);
#pragma HLS BIND_OP variable=norm_square2 op=mul impl=dsp latency=3
            sq2+=norm_square2;
            norm23_t narrow3;narrow3.value=v3;
            uint64_t norm_square3=(uint64_t)((int64_t)narrow3.value*(int64_t)narrow3.value);
#pragma HLS BIND_OP variable=norm_square3 op=mul impl=dsp latency=3
            sq3+=norm_square3;
            norm23_t narrow4;narrow4.value=v4;
            uint64_t norm_square4=(uint64_t)((int64_t)narrow4.value*(int64_t)narrow4.value);
#pragma HLS BIND_OP variable=norm_square4 op=mul impl=dsp latency=3
            sq4+=norm_square4;
            norm23_t narrow5;narrow5.value=v5;
            uint64_t norm_square5=(uint64_t)((int64_t)narrow5.value*(int64_t)narrow5.value);
#pragma HLS BIND_OP variable=norm_square5 op=mul impl=dsp latency=3
            sq5+=norm_square5;
            norm23_t narrow6;narrow6.value=v6;
            uint64_t norm_square6=(uint64_t)((int64_t)narrow6.value*(int64_t)narrow6.value);
#pragma HLS BIND_OP variable=norm_square6 op=mul impl=dsp latency=3
            sq6+=norm_square6;
            norm23_t narrow7;narrow7.value=v7;
            uint64_t norm_square7=(uint64_t)((int64_t)narrow7.value*(int64_t)narrow7.value);
#pragma HLS BIND_OP variable=norm_square7 op=mul impl=dsp latency=3
            sq7+=norm_square7;
        }
        xs[0]=sq0/16+HAR_EPSILON_Q32;xs[1]=sq1/16+HAR_EPSILON_Q32;
        xs[2]=sq2/16+HAR_EPSILON_Q32;xs[3]=sq3/16+HAR_EPSILON_Q32;
        xs[4]=sq4/16+HAR_EPSILON_Q32;xs[5]=sq5/16+HAR_EPSILON_Q32;
        xs[6]=sq6/16+HAR_EPSILON_Q32;xs[7]=sq7/16+HAR_EPSILON_Q32;
        isqrt8(xs, ds);
        for (int q = 0; q < 8; q++) {
#pragma HLS UNROLL
            DEN[r + q] = ds[q] ? (uint64_t)ds[q] : 1;
        }
    }
    if (bad) return HAR_NET_OVERFLOW;

    for (int r = 0; r < 32; r++) {
#pragma HLS PIPELINE II=1
        RC[r] = NF_NORM / DEN[r];
    }

    for (int r = 0; r < 32; r++) {
        uint64_t den = DEN[r], rc = RC[r], half = den >> 1;
        for (int j = 0; j < 16; j++) {
#pragma HLS PIPELINE II=1
#pragma HLS UNROLL factor=4
            /* Observed routed passD product failed100MHz. Preserve exact
               arithmetic, but explicitly pipeline this named DSP product. */
            int64_t norm_product = (int64_t)ACT_FLAT(SRC,(r * 16 + j)) * (int64_t)GAM[j];
#pragma HLS BIND_OP variable=norm_product op=mul impl=dsp latency=3
            int64_t num = norm_product * 4;
            uint64_t mag = (num < 0) ? (uint64_t)(-num) : (uint64_t)num;
            uint64_t nv = mag + half;
            uint64_t norm_recip_product = nv * rc;
#pragma HLS BIND_OP variable=norm_recip_product op=mul impl=dsp latency=4
            uint64_t q0 = norm_recip_product >> 45;
            int64_t q = (int64_t)(q0 + (nv - q0 * den >= den));
            ACT_FLAT(DST,(r * 16 + j)) = (int32_t)((num < 0) ? -q : q);
        }
    }
    return 0;
}

/* Shared 8-row x 16-lane INT8 GEMM datapath. One instance only (INLINE off),
 * so the ten layer calls time-share the same 128 multipliers.
 *
 * v4 note: the v3 inner loop took two t steps per iteration to buy II=2, but
 * that doubled the live product/accumulator datapath and measured 38.2k LUT
 * for this function alone (csynth: whole design 90.3k LUT, 57,531 slice LUTs
 * after synthesis vs 53,200 available -> place_design DRC UTLZ-1). v4 keeps
 * the v3 row-parallel norm/softmax passes and the 64-bit input port, and
 * reverts only this loop to the v1 shape (16.6k LUT, II~4), which fits the
 * 7z020 again. Accumulation order per output element is unchanged either way,
 * so the logits stay bit-identical. */
/* Exact packed-pair arithmetic was exhaustively checked with ap_int and
 * mapped to one DSP in isolated Vivado synthesis. Network scheduling and
 * routing are new experiments. The host executes the same packed identity. */
#ifdef __SYNTHESIS__
static void packed_pair_values(ap_int<8> a, ap_int<8> b0, ap_int<8> b1, ap_int<16>& y0, ap_int<16>& y1) {
#pragma HLS INLINE
 ap_int<25> packed_b=((ap_int<25>)b1<<17)+(ap_uint<8>)b0;
 ap_int<33> packed_product=(ap_int<33>)(a*packed_b);
#pragma HLS BIND_OP variable=packed_product op=mul impl=dsp latency=3
 ap_int<17> low17=packed_product.range(16,0);
 ap_int<17> sign_fix=b0<0 ? ((ap_int<17>)a<<8) : (ap_int<17>)0;
 y0=(ap_int<16>)(low17-sign_fix);
 y1=(ap_int<16>)((packed_product>>17)+(low17<0));
}
#endif
static inline void gemm_pair8(int8_t a, int8_t b0, int8_t b1,
                              int16_t &y0, int16_t &y1) {
#pragma HLS INLINE
#ifdef __SYNTHESIS__
    ap_int<16> p0, p1;
    packed_pair_values((ap_int<8>)a, (ap_int<8>)b0, (ap_int<8>)b1, p0, p1);
    y0 = (int16_t)p0; y1 = (int16_t)p1;
#else
    int64_t packed_b = (int64_t)b1 * 131072 + (uint8_t)b0;
    int64_t product = (int64_t)a * packed_b;
    int32_t low17 = (int32_t)((uint64_t)product & 131071u);
    if (low17 & 65536) low17 -= 131072;
    int32_t sign_fix = b0 < 0 ? (int32_t)a * 256 : 0;
    y0 = (int16_t)(low17 - sign_fix);
    y1 = (int16_t)((product - low17) / 131072);
#endif
}

static void gemm(int8_t (&A)[32][ASTR], int8_t (&B)[32][BSTR], int32_t (&C)[64][16],
                 int m, int k, int n, int cbase, int weight_base) {
#pragma HLS INLINE off
    static const int8_t WROM[180][16] = {
        {-1,-13,27,3,0,-25,-23,-7,-21,-18,30,18,-15,-34,-14,-15},
        {22,-22,-11,1,-34,13,11,7,-35,13,-24,9,12,-8,22,1},
        {20,-17,1,7,-1,-10,-12,16,-24,20,-30,-23,-17,-9,-22,-34},
        {5,-41,16,32,17,-31,-1,55,-53,34,15,33,-26,-56,32,46},
        {12,9,2,-22,-21,49,41,11,-18,0,-13,10,54,56,10,-23},
        {3,3,-13,-25,-20,32,5,9,-29,38,-4,2,3,50,5,-38},
        {34,3,32,-19,11,-17,20,15,0,20,-4,-28,-47,44,0,-24},
        {-31,14,29,9,-8,1,-42,-37,32,-40,1,5,15,-31,-20,-11},
        {-33,5,-46,-23,-40,38,-22,6,-9,-14,-28,-11,56,1,-12,-16},
        {-24,5,18,33,17,-22,-2,-10,-3,2,8,-8,-17,-19,-23,-23},
        {19,-27,25,1,-26,17,-21,36,-16,30,-29,7,47,25,31,18},
        {-7,-4,-15,-2,15,14,2,16,6,12,10,5,0,-20,3,-18},
        {20,-44,33,36,33,-60,-7,20,-50,51,40,35,-28,-33,27,51},
        {4,26,-2,-10,9,44,42,18,12,14,-6,-26,51,50,-11,-9},
        {-39,-2,-16,-47,-21,42,-6,13,-11,-12,-38,-25,32,5,-19,-29},
        {32,1,9,-2,4,-25,26,-2,-4,14,-25,-26,-41,50,-15,-35},
        {-10,26,-1,4,13,3,13,-13,-8,-1,-4,7,-14,12,13,-19},
        {-11,-4,-34,-32,8,16,-40,-7,20,-18,-40,-1,32,-18,5,25},
        {1,26,33,3,-12,-29,-7,2,4,8,3,13,21,-26,-32,-20},
        {9,-34,1,11,2,18,-22,33,-37,32,-24,24,37,18,30,-9},
        {8,-19,13,9,-19,-26,-4,-16,-5,10,-5,-6,19,-15,10,3},
        {26,-36,58,28,34,-34,4,29,-41,34,30,41,-65,-46,29,43},
        {15,8,-4,-35,-14,38,62,1,11,18,19,-20,35,48,19,-41},
        {-39,27,26,-13,-5,34,-29,-13,15,-23,-25,-3,45,-18,-38,-27},
        {19,2,39,-10,-4,-17,14,22,-9,14,-25,-26,-19,23,-23,-1},
        {-7,15,0,-2,1,21,35,-28,14,-1,32,-1,-15,32,21,-19},
        {-27,30,6,-38,-6,-2,-16,-25,18,5,-18,-20,4,-47,-29,20},
        {-13,2,4,19,28,-38,15,-4,-11,-21,36,20,-18,-21,-15,-13},
        {7,1,28,-2,-5,10,-28,33,-47,14,-3,8,44,11,-6,15},
        {-1,-14,-10,11,10,1,11,-3,-3,-21,5,-18,19,1,-28,-26},
        {19,-6,61,64,25,-66,-2,10,-41,16,80,48,-67,-33,40,41},
        {4,27,33,-29,-5,37,51,10,-10,0,3,2,14,31,2,-51},
        {-56,39,10,-7,11,-2,-45,-51,32,-38,22,-15,-5,-41,-68,-5},
        {31,4,25,12,-24,-39,7,20,5,12,10,5,-29,9,-1,-10},
        {10,15,-10,2,31,25,15,-3,12,6,-12,-2,-27,34,29,-36},
        {-53,23,20,-12,29,22,-48,-20,-8,-28,6,-10,-32,-13,-27,-23},
        {-22,42,36,53,-14,-34,36,7,-28,6,-6,-15,-7,13,-3,-53},
        {11,-37,-14,-23,19,53,-54,-7,-29,1,-6,-22,-15,17,30,-11},
        {13,-38,-13,-19,-18,42,23,6,5,-20,1,21,7,-11,29,27},
        {56,-6,7,32,-16,4,16,36,-34,-50,13,10,-50,13,-37,4},
        {16,-16,2,16,1,25,17,-23,-16,-31,17,30,-29,-24,-11,18},
        {-28,2,38,-6,-24,-50,11,-3,12,-21,33,5,35,-36,32,-13},
        {-2,4,-22,-21,-25,35,16,9,-4,17,-5,-22,8,6,-8,-23},
        {-35,6,-24,-5,1,17,-21,-7,29,26,-5,17,19,15,-29,-31},
        {-6,-44,-87,17,-44,9,-14,-33,32,-16,4,-11,-50,-33,35,3},
        {-9,-22,21,12,-21,3,-23,3,0,26,-6,17,11,10,9,-25},
        {5,-63,-40,14,-15,69,4,1,-8,-23,-55,-30,-49,2,14,41},
        {-2,-12,-20,-15,-18,49,-4,-18,38,20,4,-10,-33,-32,-22,35},
        {-48,-5,-6,-21,21,-10,-10,-6,36,43,42,49,13,1,-20,-8},
        {-1,-25,-14,-23,-26,-5,-22,-1,34,40,-3,0,-1,-41,33,11},
        {-29,13,-5,9,-26,-24,9,1,26,3,7,7,27,7,3,17},
        {-15,-19,-5,-11,-9,29,-12,-20,29,-29,14,39,-43,-23,21,11},
        {-39,12,21,10,5,-24,-33,-15,35,0,46,26,-5,-6,-6,-5},
        {34,-19,10,35,24,-4,-15,12,-25,-46,-44,-29,-40,11,3,-4},
        {-15,7,37,8,-5,16,42,-4,-30,-13,-11,-7,-19,30,2,6},
        {16,7,-14,-38,-17,37,-14,-18,6,11,15,11,29,32,-34,7},
        {23,0,-8,34,29,8,-17,11,-6,4,-2,-27,-8,31,-28,-14},
        {21,-20,5,29,-28,-20,-33,-12,11,-5,5,22,-32,-13,5,3},
        {43,6,-9,-8,-21,27,-36,-8,-17,-33,-44,5,13,-12,-9,20},
        {-35,27,8,7,22,-15,-17,4,-19,35,21,5,13,-11,30,-38},
        {7,-55,-40,1,-40,50,-35,-38,22,8,22,18,-54,-19,19,13},
        {-5,16,17,-16,22,-27,-17,-28,-8,35,-10,-12,-7,-12,34,3},
        {16,53,52,13,21,-53,39,30,-20,13,6,-4,2,55,-75,-10},
        {-9,36,39,10,35,-19,-6,45,-38,-9,44,-4,15,-4,-12,-23},
        {3,-36,-35,-23,-11,36,-12,0,-7,22,11,11,-35,-38,7,15},
        {24,-16,-22,-51,4,31,-55,-21,26,-23,3,-26,-48,-25,44,21},
        {21,-2,26,26,27,-28,-13,-6,-5,20,-11,-18,-14,33,-45,6},
        {-39,14,32,-26,18,-15,-5,16,10,16,3,1,48,19,1,-14},
        {14,32,21,17,6,7,26,-6,42,-23,-1,32,-24,22,-30,-2},
        {-2,-26,-12,14,13,-33,-11,-5,-12,-7,13,18,-13,-25,7,5},
        {-27,-11,-18,-38,-1,7,22,-22,10,17,17,-10,30,30,9,37},
        {3,29,-6,-10,-31,-8,3,6,-26,-13,-32,7,13,8,-28,36},
        {2,16,21,37,21,-15,34,-31,2,33,10,24,35,-33,-22,3},
        {20,-22,28,14,1,-47,30,-3,23,-42,26,-6,9,27,7,-39},
        {-30,-22,-1,-18,-22,-29,43,23,2,26,7,-30,-31,16,-34,-37},
        {-45,50,14,-21,-15,25,0,-12,-10,-3,-5,25,-49,-1,4,-18},
        {11,-28,-23,49,32,-29,-10,-29,-30,-21,-19,-28,32,-13,33,-38},
        {-27,-14,-23,-29,-9,13,13,16,-5,-31,-8,17,-34,36,-33,14},
        {-9,-13,-9,-8,17,40,-17,-9,9,2,20,14,42,15,-38,68},
        {4,4,1,-30,-21,39,-46,3,-37,-30,1,12,7,19,-6,29},
        {-14,36,41,-23,-49,-45,-40,-5,-26,-12,64,-41,-13,-6,43,-11},
        {-4,5,-19,5,28,-32,28,5,-42,6,-28,-14,-39,11,-34,-48},
        {-30,32,19,13,-39,13,37,55,3,6,18,10,-17,45,12,-35},
        {-6,10,44,-26,-37,19,-25,-9,4,3,-8,41,-36,32,48,20},
        {65,79,13,3,-45,58,70,56,98,-32,24,-40,-28,-45,17,-39},
        {-11,-23,68,-47,-32,40,-46,-35,-54,18,-23,-14,87,-12,4,-17},
        {-44,-16,71,-85,-36,12,4,73,-11,-34,-31,-43,-18,69,-54,47},
        {-34,13,9,43,-66,7,72,37,33,-29,-7,37,-39,12,91,17},
        {0,43,16,77,46,-12,95,6,33,-34,60,-38,-66,-59,64,63},
        {-25,67,64,57,-49,1,-7,34,-68,21,-49,-8,-32,-44,34,-75},
        {1,-66,-96,69,22,-2,25,-47,-35,2,-17,10,-19,-71,90,63},
        {-19,-48,-13,27,-5,-41,-65,2,-15,44,-34,6,62,-46,55,12},
        {21,-15,55,45,23,-71,-64,-52,11,29,24,45,-37,-71,17,13},
        {48,-18,-71,-1,58,-45,17,-68,-13,33,-22,-54,-29,28,-17,-35},
        {-55,-39,30,-72,-60,-49,38,6,18,12,-6,16,-14,38,-85,-7},
        {4,37,16,20,-44,-37,-76,-71,-83,-37,-100,-72,43,-37,-2,-8},
        {103,106,73,92,49,-31,48,-56,65,-96,52,43,-66,-29,18,-19},
        {-80,-11,0,-31,45,-2,-66,13,25,52,10,-76,77,12,67,-30},
        {8,-27,51,-84,-71,-19,24,87,1,-37,-42,-29,-59,78,-32,3},
        {70,17,96,-25,37,-104,18,-81,-3,-27,-32,51,33,69,-16,-120},
        {-14,-21,-24,-7,25,3,-19,27,9,10,-3,5,5,-49,-17,15},
        {-73,-29,-37,11,1,-33,-57,-10,48,-43,11,30,9,-10,-34,30},
        {9,44,-5,-18,38,32,-3,25,12,21,-50,9,-15,-3,25,-36},
        {39,36,-6,-28,-26,-1,-16,-24,32,-37,-14,1,-7,-20,0,-16},
        {-40,6,-41,19,-21,59,-84,11,21,30,-5,8,-14,-26,12,-29},
        {-47,-27,-36,4,-11,21,-69,-21,23,-52,20,43,21,-17,-19,54},
        {-34,21,-26,-31,-6,21,-68,18,-8,-14,-21,28,-25,35,-4,-45},
        {-31,22,31,-1,8,17,-52,21,27,-14,9,10,-17,-40,24,28},
        {7,-9,-17,3,38,29,-30,-6,8,-10,2,24,-1,18,19,6},
        {-5,18,34,-7,13,5,32,35,4,-51,21,33,37,-10,28,31},
        {13,-19,58,0,-7,-39,34,-5,-26,-4,14,-39,44,11,-53,-2},
        {62,18,-33,-5,2,-2,81,-25,-36,62,-30,-7,2,0,21,-56},
        {-31,27,-7,10,40,-8,8,65,37,29,-11,-23,-31,55,-17,-18},
        {29,13,44,-25,-51,-2,22,10,-16,-13,28,-44,34,2,-37,-27},
        {7,-30,26,30,28,31,42,55,-9,29,50,-40,34,-11,-41,24},
        {-16,10,32,6,2,27,-17,7,14,-10,12,-34,-7,48,45,-20},
        {26,-13,-24,-42,33,-28,-39,57,19,54,-42,-19,-37,58,10,-9},
        {53,-6,47,-4,-11,-52,42,-44,-15,-33,-45,-5,-9,-24,-21,-2},
        {8,-14,9,28,-11,-14,28,21,17,-8,2,39,31,-24,32,14},
        {-31,19,-39,20,29,18,4,23,-4,-7,17,18,-5,-2,35,23},
        {-15,31,-28,-4,37,-27,-51,62,-13,64,-36,-16,-23,65,8,-27},
        {6,25,74,-49,-22,-22,-26,6,-35,7,13,1,-13,-45,7,-10},
        {23,-6,-53,35,-18,1,-18,-3,19,-5,15,-3,6,50,-16,30},
        {47,-28,34,16,-12,29,0,-10,7,-47,21,33,35,5,-22,11},
        {-1,-39,5,2,-35,1,13,-40,-38,-76,27,-10,11,-31,29,36},
        {72,-20,-30,50,47,54,52,-26,2,12,15,13,-44,54,43,16},
        {36,-8,-2,57,17,23,32,42,19,51,26,12,44,4,-1,30},
        {31,16,-7,34,32,13,2,-55,28,-8,7,2,28,32,25,-14},
        {36,-16,60,-16,-26,-39,-34,-49,-14,-22,-4,10,-20,-5,-22,2},
        {1,30,5,42,30,-27,-54,-34,-64,48,-22,15,-8,-28,10,-9},
        {24,1,48,-5,-22,-37,22,-11,-30,16,33,-60,-2,34,-66,27},
        {-1,-6,52,11,24,13,8,69,-53,47,-16,-61,-9,27,9,-22},
        {-20,-27,12,20,8,-7,7,8,3,12,10,-30,-2,-21,29,14},
        {27,34,-15,10,18,-15,37,-20,22,-10,-12,8,-19,-9,-4,2},
        {-39,-13,-6,-31,-35,46,-54,43,28,29,-22,-40,-21,-48,58,10},
        {-25,9,41,-47,-28,-22,-17,6,-18,31,15,-25,27,3,-37,-28},
        {37,14,-16,4,-16,15,22,8,36,-8,18,31,-24,3,7,28},
        {19,23,20,-11,-21,-33,25,-8,-29,-13,0,23,20,41,-44,-38},
        {-52,-50,14,-8,-14,28,-62,-1,-39,33,43,-9,25,-21,32,16},
        {10,0,-10,-4,-16,26,9,39,37,16,-15,38,-43,13,-29,23},
        {18,-1,-3,14,-7,-10,30,9,-6,-22,13,33,8,3,-33,2},
        {32,3,-9,-32,-13,29,6,42,71,10,-7,66,-38,5,8,33},
        {-38,-38,32,-36,-12,24,-32,-1,-22,32,-12,-6,21,-15,-18,19},
        {14,9,7,26,-3,-32,10,-39,-28,0,27,-9,28,-5,-28,-37},
        {-23,-26,24,-20,1,8,-14,16,-28,22,15,-34,35,17,16,-24},
        {7,-16,-33,-15,-6,28,12,1,35,-5,-8,36,-40,-16,19,46},
        {-8,9,3,12,9,-28,39,-7,-34,-31,23,18,34,36,-41,-15},
        {-49,-33,11,-15,-24,5,-29,13,-11,10,18,-16,27,2,2,-18},
        {-30,-18,-47,4,37,61,2,2,8,45,50,46,8,-40,8,61},
        {3,-22,-21,20,-7,-17,-19,-23,7,-14,0,1,-10,-5,5,-3},
        {6,-20,-37,8,-15,45,31,-6,39,-22,-16,53,-41,-29,-3,29},
        {-31,-6,34,-25,-12,21,-14,21,-10,10,-47,-38,33,-21,22,-41},
        {-4,-17,28,-13,-16,13,-18,-7,-35,18,-33,3,-9,-12,-17,-18},
        {-37,13,32,10,-4,-22,4,-15,-28,32,27,1,19,-9,7,-22},
        {-43,-37,-19,8,12,40,-33,-19,-7,48,36,39,5,-30,-14,50},
        {-38,-51,-26,6,26,49,-39,12,47,11,33,69,-5,-28,-9,71},
        {28,20,21,11,-1,-35,11,-1,-1,-23,33,8,17,37,-46,-20},
        {-13,-49,-9,-56,-48,30,-56,5,33,69,-5,-46,9,-49,35,9},
        {-14,21,-13,6,-1,-27,-17,20,-15,1,29,23,-12,-8,-40,-7},
        {6,46,17,-1,29,-40,39,-13,-5,3,-1,-6,30,16,-23,-33},
        {29,-5,-12,-21,-16,-7,-11,-16,1,-18,22,27,-28,8,-23,-20},
        {-52,-39,47,-29,-18,26,-15,-3,-21,35,6,-14,52,-6,-16,-1},
        {-19,-20,24,-13,15,24,10,22,-42,39,1,-35,9,22,-7,-1},
        {-4,5,-11,-6,-6,-9,26,-31,-26,-40,3,33,14,-15,-18,-25},
        {51,38,-66,-31,42,-21,0,0,0,0,0,0,0,0,0,0},
        {15,6,-42,19,34,-41,0,0,0,0,0,0,0,0,0,0},
        {23,-73,-29,44,0,-1,0,0,0,0,0,0,0,0,0,0},
        {-40,51,6,-12,46,-25,0,0,0,0,0,0,0,0,0,0},
        {-39,32,30,10,12,-19,0,0,0,0,0,0,0,0,0,0},
        {-13,7,4,-19,-38,13,0,0,0,0,0,0,0,0,0,0},
        {7,18,-28,3,0,-51,0,0,0,0,0,0,0,0,0,0},
        {38,-12,-25,-8,-44,16,0,0,0,0,0,0,0,0,0,0},
        {39,52,9,-39,-25,1,0,0,0,0,0,0,0,0,0,0},
        {0,-16,20,23,-17,41,0,0,0,0,0,0,0,0,0,0},
        {-13,-8,48,-25,-5,-45,0,0,0,0,0,0,0,0,0,0},
        {30,28,30,-19,10,-49,0,0,0,0,0,0,0,0,0,0},
        {-39,-46,14,21,1,-5,0,0,0,0,0,0,0,0,0,0},
        {37,-39,-33,11,3,-27,0,0,0,0,0,0,0,0,0,0},
        {-35,40,-4,-16,0,67,0,0,0,0,0,0,0,0,0,0},
        {-8,30,24,-47,-44,0,0,0,0,0,0,0,0,0,0,0},
    };
#pragma HLS ARRAY_PARTITION variable=WROM complete dim=2
    for (int i = 0; i < m; i += 16) {
        int32_t acc[16][LANES];
#pragma HLS ARRAY_PARTITION variable=acc complete dim=0
        for (int r = 0; r < 16; r++) {
#pragma HLS UNROLL
            for (int l = 0; l < LANES; l++) {
#pragma HLS UNROLL
                acc[r][l] = 0;
            }
        }
        for (int t = 0; t < k; t++) {
#pragma HLS PIPELINE II=1
            int8_t av[16];
#pragma HLS ARRAY_PARTITION variable=av complete
            for (int r = 0; r < 16; r++) {
#pragma HLS UNROLL
                av[r] = (i + r < m) ? A[i + r][t] : (int8_t)0;
            }
            int8_t bv[LANES];
#pragma HLS ARRAY_PARTITION variable=bv complete
            for (int l = 0; l < LANES; l++) {
#pragma HLS UNROLL
                bv[l] = weight_base >= 0
                    ? WROM[weight_base + t * ((n + 15) >> 4) + (cbase >> 4)][l]
                    : B[t][l];
            }
            /* Two independent products share one selected weight operand. */
            for (int r = 0; r < 16; r += 2) {
#pragma HLS UNROLL
                for (int l = 0; l < LANES; l++) {
#pragma HLS UNROLL
                    int16_t p0, p1;
                    gemm_pair8(bv[l], av[r], av[r + 1], p0, p1);
                    acc[r][l] += (int32_t)p0;
                    acc[r + 1][l] += (int32_t)p1;
                }
            }
        }
        for (int r = 0; r < 16; r++) {
#pragma HLS UNROLL
            for (int l = 0; l < LANES; l++) {
#pragma HLS UNROLL
                if (i + r < m && cbase + l < n)
                    C[(i + r) * ((n + 15) >> 4) + (cbase >> 4)][l] = acc[r][l];
            }
        }
    }
}

/* Copy one 16-column group of a frozen matrix into the B operand buffer.
 * OFF, K, NFULL and CBASE are compile-time constants, so the sixteen lane
 * reads of one row differ only in the low address bits and stay in distinct
 * banks of the cyclic-16 WFLAT partition. */
#define LOAD_B(OFF, K, NFULL, CBASE)                                        \
    do {                                                                    \
        for (int _t = 0; _t < (K); _t++) {                                   \
            for (int _l = 0; _l < LANES; _l++) {                             \
                if ((CBASE) + _l < (NFULL))                                  \
                    B8[_t][_l] = WFLAT[(OFF) + _t * (NFULL) + (CBASE) + _l];  \
            }                                                               \
        }                                                                   \
    } while (0)

/* Softmax over 32 rows of SC into PR: row maximum, LUT + row total,
 * reciprocal + rounding bias, then the exact per-element patch loop (the
 * v2 arithmetic verbatim). Stage 1/2 keep four interleaved chains inside a
 * row; stage 3/4 are per row, so den/rc/rb are scalars and TOT[]/RCS[]/RBS[]
 * stay ordinary RAMs instead of completely partitioned mux banks (v3/v4). */
static void softmax_pass(int32_t *SC, int32_t *PR) {
#pragma HLS INLINE off
    static uint64_t TOT[32];
    static uint32_t RCS[32];
    static uint64_t RBS[32];

    /* Two rows per iteration: eight independent max chains and eight
     * exp-LUT chains. The two rows are 32 words apart, so they share the
     * same cyclic8 bank at each column and a bank has two read ports; that
     * fixes the loop at II=2, but the cycle count per row halves. The frozen
     * LUT, row maximum, reciprocal/bias stages and patch arithmetic are
     * untouched. */
    for (int r = 0; r < 32; r += 2) {
        int32_t a0 = SC[r * 32], a1 = SC[r * 32 + 1];
        int32_t a2 = SC[r * 32 + 2], a3 = SC[r * 32 + 3];
        int32_t b0 = SC[(r + 1) * 32], b1 = SC[(r + 1) * 32 + 1];
        int32_t b2 = SC[(r + 1) * 32 + 2], b3 = SC[(r + 1) * 32 + 3];
        for (int jj = 1; jj < 8; jj++) {
#pragma HLS PIPELINE II=1
            int32_t p0 = SC[r * 32 + 4 * jj], p1 = SC[r * 32 + 4 * jj + 1];
            int32_t p2 = SC[r * 32 + 4 * jj + 2], p3 = SC[r * 32 + 4 * jj + 3];
            int32_t q0 = SC[(r + 1) * 32 + 4 * jj], q1 = SC[(r + 1) * 32 + 4 * jj + 1];
            int32_t q2 = SC[(r + 1) * 32 + 4 * jj + 2], q3 = SC[(r + 1) * 32 + 4 * jj + 3];
            if (p0 > a0) a0 = p0;
            if (p1 > a1) a1 = p1;
            if (p2 > a2) a2 = p2;
            if (p3 > a3) a3 = p3;
            if (q0 > b0) b0 = q0;
            if (q1 > b1) b1 = q1;
            if (q2 > b2) b2 = q2;
            if (q3 > b3) b3 = q3;
        }
        int32_t mx = (a0 > a1) ? a0 : a1;
        mx = (mx > a2) ? mx : a2;
        mx = (mx > a3) ? mx : a3;
        int32_t nx = (b0 > b1) ? b0 : b1;
        nx = (nx > b2) ? nx : b2;
        nx = (nx > b3) ? nx : b3;

        uint64_t t0 = 0, t1 = 0, t2 = 0, t3 = 0;
        uint64_t u0 = 0, u1 = 0, u2 = 0, u3 = 0;
        for (int jj = 0; jj < 8; jj++) {
#pragma HLS PIPELINE II=1
            uint32_t et0 = ((uint32_t)mx - (uint32_t)SC[r * 32 + 4 * jj + 0]) + 128u;
            uint32_t it0 = (et0 < 128u) ? 4096u : (et0 >> 8);
            if (it0 > 4096u) it0 = 4096u;
            int32_t vt0 = har_exp_lookup_local(it0);
            PR[r * 32 + 4 * jj + 0] = vt0;
            t0 += (uint64_t)vt0;

            uint32_t et1 = ((uint32_t)mx - (uint32_t)SC[r * 32 + 4 * jj + 1]) + 128u;
            uint32_t it1 = (et1 < 128u) ? 4096u : (et1 >> 8);
            if (it1 > 4096u) it1 = 4096u;
            int32_t vt1 = har_exp_lookup_local(it1);
            PR[r * 32 + 4 * jj + 1] = vt1;
            t1 += (uint64_t)vt1;

            uint32_t et2 = ((uint32_t)mx - (uint32_t)SC[r * 32 + 4 * jj + 2]) + 128u;
            uint32_t it2 = (et2 < 128u) ? 4096u : (et2 >> 8);
            if (it2 > 4096u) it2 = 4096u;
            int32_t vt2 = har_exp_lookup_local(it2);
            PR[r * 32 + 4 * jj + 2] = vt2;
            t2 += (uint64_t)vt2;

            uint32_t et3 = ((uint32_t)mx - (uint32_t)SC[r * 32 + 4 * jj + 3]) + 128u;
            uint32_t it3 = (et3 < 128u) ? 4096u : (et3 >> 8);
            if (it3 > 4096u) it3 = 4096u;
            int32_t vt3 = har_exp_lookup_local(it3);
            PR[r * 32 + 4 * jj + 3] = vt3;
            t3 += (uint64_t)vt3;

            uint32_t eu0 = ((uint32_t)nx - (uint32_t)SC[(r + 1) * 32 + 4 * jj + 0]) + 128u;
            uint32_t iu0 = (eu0 < 128u) ? 4096u : (eu0 >> 8);
            if (iu0 > 4096u) iu0 = 4096u;
            int32_t vu0 = har_exp_lookup_local(iu0);
            PR[(r + 1) * 32 + 4 * jj + 0] = vu0;
            u0 += (uint64_t)vu0;

            uint32_t eu1 = ((uint32_t)nx - (uint32_t)SC[(r + 1) * 32 + 4 * jj + 1]) + 128u;
            uint32_t iu1 = (eu1 < 128u) ? 4096u : (eu1 >> 8);
            if (iu1 > 4096u) iu1 = 4096u;
            int32_t vu1 = har_exp_lookup_local(iu1);
            PR[(r + 1) * 32 + 4 * jj + 1] = vu1;
            u1 += (uint64_t)vu1;

            uint32_t eu2 = ((uint32_t)nx - (uint32_t)SC[(r + 1) * 32 + 4 * jj + 2]) + 128u;
            uint32_t iu2 = (eu2 < 128u) ? 4096u : (eu2 >> 8);
            if (iu2 > 4096u) iu2 = 4096u;
            int32_t vu2 = har_exp_lookup_local(iu2);
            PR[(r + 1) * 32 + 4 * jj + 2] = vu2;
            u2 += (uint64_t)vu2;

            uint32_t eu3 = ((uint32_t)nx - (uint32_t)SC[(r + 1) * 32 + 4 * jj + 3]) + 128u;
            uint32_t iu3 = (eu3 < 128u) ? 4096u : (eu3 >> 8);
            if (iu3 > 4096u) iu3 = 4096u;
            int32_t vu3 = har_exp_lookup_local(iu3);
            PR[(r + 1) * 32 + 4 * jj + 3] = vu3;
            u3 += (uint64_t)vu3;

        }
        TOT[r] = (t0 + t1) + (t2 + t3);
        TOT[r + 1] = (u0 + u1) + (u2 + u3);
    }

    for (int r = 0; r < 32; r++) {
#pragma HLS PIPELINE II=1
        uint64_t den = TOT[r];
        uint64_t half = den >> 1;
        uint32_t rc = (uint32_t)(NF_SMX / den);
        RCS[r] = rc;
        RBS[r] = (half * (uint64_t)rc) >> 16;
    }

    /* Scores in SC are dead after all exponentials and reciprocals.
     * Read exponentials from PR and normalize into SC, avoiding an
     * in-place memory dependency with no extra buffer or copy. */
    for (int i = 0; i < 1024; i++) {
#pragma HLS PIPELINE II=1
#pragma HLS UNROLL factor=4
        int r = i >> 5;
        uint64_t den = TOT[r];
        uint64_t half = den >> 1;
        uint32_t rc = RCS[r];
        uint64_t rb = RBS[r];
        uint64_t e = (uint64_t)PR[i];
        uint64_t soft_product = e * (uint64_t)rc;
#pragma HLS BIND_OP variable=soft_product op=mul impl=dsp latency=3
        uint32_t q = (uint32_t)((soft_product + rb) >> 31);
        uint64_t correction_product = (uint64_t)q * den;
#pragma HLS BIND_OP variable=correction_product op=mul impl=dsp latency=3
        uint64_t rem = (e << 16) + half - correction_product;
        SC[i] = (int32_t)(q + (rem >= den));
    }
}

int har_net(const int64_t *input, int32_t *logits) {
#pragma HLS INTERFACE m_axi port=input offset=slave bundle=gmem_in depth=576 max_read_burst_length=256
#pragma HLS INTERFACE m_axi port=logits offset=slave bundle=gmem_out depth=16 max_write_burst_length=16
#pragma HLS INTERFACE s_axilite port=input bundle=control
#pragma HLS INTERFACE s_axilite port=logits bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control

    /* All weights live on chip for the whole call. */
#include "har_wflat_body.inc"
#pragma HLS ARRAY_PARTITION variable=WFLAT cyclic factor=16

    static int8_t A8[32][ASTR];
#pragma HLS ARRAY_PARTITION variable=A8 cyclic factor=8 dim=1
#pragma HLS ARRAY_PARTITION variable=A8 cyclic factor=4 dim=2
    static int8_t B8[32][BSTR];
#pragma HLS ARRAY_PARTITION variable=B8 cyclic factor=LANES dim=2
    /* Two-dimensional so the bank is the compile-time lane index: with a
     * flat cyclic-16 partition the bank is index%16 and the row stride n is a
     * runtime value, so the sixteen lane stores of one row could not be shown
     * to hit different banks and were serialised to one word per clock. */
    static int32_t C32[64][16];
#pragma HLS ARRAY_PARTITION variable=C32 complete dim=2
    static har_act H;
#pragma HLS ARRAY_PARTITION variable=H complete dim=1
#pragma HLS ARRAY_PARTITION variable=H complete dim=2
    static har_act NR;
#pragma HLS ARRAY_PARTITION variable=NR complete dim=1
#pragma HLS ARRAY_PARTITION variable=NR complete dim=2
    static int32_t AVB[512];
#pragma HLS ARRAY_PARTITION variable=AVB cyclic factor=8
    static int8_t V8[512];
#pragma HLS ARRAY_PARTITION variable=V8 cyclic factor=8
    static int8_t K8[512];
#pragma HLS ARRAY_PARTITION variable=K8 cyclic factor=16
    static int32_t SC[1024];
#pragma HLS ARRAY_PARTITION variable=SC cyclic factor=8
    static int32_t PR[1024];
#pragma HLS ARRAY_PARTITION variable=PR cyclic factor=8
    static int32_t GAM1[16];
#pragma HLS ARRAY_PARTITION variable=GAM1 complete
    static int32_t GAM2[16];
#pragma HLS ARRAY_PARTITION variable=GAM2 complete
    static int64_t PSUM[16];
#pragma HLS ARRAY_PARTITION variable=PSUM complete

    for (int i = 0; i < 16; i++) GAM1[i] = har_norm1_gamma[i];
    for (int i = 0; i < 16; i++) GAM2[i] = har_norm2_gamma[i];

    /* ---- stage 1: stream in 64-bit words, range-check and quantise ------ */
    /* HP0 is a 64-bit slave, so the 1152 Q16 words arrive as 576 packed
     * words (low half = even element index). Branch-free range collection
     * keeps the load loop at II=1. */
    uint32_t bad = 0;
    for (int i = 0; i < 32; i++) {
        for (int w = 0; w < 18; w++) {
#pragma HLS PIPELINE II=1
            uint64_t wd = (uint64_t)input[i * 18 + w];
            int32_t x0 = (int32_t)(uint32_t)(wd & 0xffffffffu);
            int32_t x1 = (int32_t)(uint32_t)(wd >> 32);
            bad |= (uint32_t)(x0 <= -8388608 || x0 >= 8388608);
            bad |= (uint32_t)(x1 <= -8388608 || x1 >= 8388608);
            QUANT_INTO(A8[i][2 * w], x0, SH_INPUT);
            QUANT_INTO(A8[i][2 * w + 1], x1, SH_INPUT);
        }
    }
    if (bad) return HAR_NET_BAD_INPUT;

    /* ---- stage 2: embed GEMM + bias rescale --------------------------- */
    gemm(A8, B8, C32, 32, 36, 16, 0, 0);
    /* Stages 2 and 3 in one pass: the embed rescale and the positional add are both
     * elementwise over the same 512 values and the two 32-bit additions associate, so
     * the fused form is bit-identical while one 8-wide pass disappears. */
    for (int i = 0; i < 512; i++) {
#pragma HLS PIPELINE II=1
#pragma HLS UNROLL factor=8
#pragma HLS DEPENDENCE variable=H inter false
        int32_t e = (int32_t)((uint32_t)C32[i >> 4][i & 15] << RS_EMBED) +
                    har_embed_bias[i & 15];
        ACT_FLAT(H,(i)) = (int32_t)((uint32_t)e + (uint32_t)har_position[i]);
    }

    /* ---- stage 4: norm1 ----------------------------------------------- */
    if (norm_pass(H, GAM1, NR)) return HAR_NET_OVERFLOW;

    /* ---- stage 5: quantise the norm output once for q/k/v -------------- */
    /* Norm1 quantization only: spatial NR banks, unchanged QUANT_INTO.
     * row=4*(q/2)+rb, col=8*(q%2)+l -> NR[rb][l][q].
     * Each A8 row/column bank receives at most two writes per q. */
    for (int q = 0; q < 16; q++) {
#pragma HLS PIPELINE II=1
        for (int rb = 0; rb < 4; rb++) {
#pragma HLS UNROLL
            for (int l = 0; l < 8; l++) {
#pragma HLS UNROLL
                int r = 4 * (q >> 1) + rb;
                int c = 8 * (q & 1) + l;
                QUANT_INTO(A8[r][c], NR[rb][l][q], SH_N_QKV);
            }
        }
    }

    /* ---- stage 6: K GEMM -> transposed INT8 K^T buffer ----------------- */
    gemm(A8, B8, C32, 32, 16, 16, 0, 52);
    /* 2x2 tile: at most two reads/writes per existing physical bank. */
    for (int rb = 0; rb < 16; rb++) {
        for (int cb = 0; cb < 8; cb++) {
#pragma HLS PIPELINE II=1
#pragma HLS DEPENDENCE variable=K8 inter false
            for (int rr = 0; rr < 2; rr++) {
#pragma HLS UNROLL
                for (int cc = 0; cc < 2; cc++) {
#pragma HLS UNROLL
                    int r=2*rb+rr,c=2*cb+cc;
                    int32_t z=(int32_t)((uint32_t)C32[r][c] << RS_K)+har_k_bias[c];
                    int8_t q8;
                    QUANT_INTO(q8,z,SH_K_OUT);
                    K8[c*32+r]=q8;
                }
            }
        }
    }

    /* ---- stage 7: V GEMM, held in INT8 until after the scores GEMM ----- */
    gemm(A8, B8, C32, 32, 16, 16, 0, 68);
    for (int i = 0; i < 512; i++) {
#pragma HLS PIPELINE II=1
#pragma HLS UNROLL factor=8
        int32_t z = (int32_t)((uint32_t)C32[i >> 4][i & 15] << RS_V) + har_v_bias[i & 15];
        QUANT_INTO(V8[i], z, SH_V_OUT);
    }

    /* ---- stage 8: Q GEMM, overwrites the shared activation buffer ------ */
    gemm(A8, B8, C32, 32, 16, 16, 0, 36);
    for (int r = 0; r < 32; r++) {
        for (int c = 0; c < 16; c++) {
#pragma HLS PIPELINE II=1
#pragma HLS UNROLL factor=8
            int32_t z = (int32_t)((uint32_t)C32[r][c] << RS_Q) + har_q_bias[c];
            QUANT_INTO(A8[r][c], z, SH_Q_OUT);
        }
    }

    /* ---- stage 9: scores = Q x K^T (two 16-lane passes) ---------------- */
    for (int cb = 0; cb < 32; cb += LANES) {
        for (int t = 0; t < 16; t++) {
            for (int l = 0; l < LANES; l++) {
                B8[t][l] = K8[t * 32 + cb + l];
            }
        }
        gemm(A8, B8, C32, 32, 16, 32, cb, -1);
    }
    for (int i = 0; i < 1024; i++) {
#pragma HLS PIPELINE II=1
#pragma HLS UNROLL factor=8
        int32_t z = (int32_t)((uint32_t)C32[i >> 4][i & 15] << SH_SCORE);
        SC[i] = z >> 2;
    }

    /* ---- stage 10: softmax with the frozen Q30 exp LUT ----------------- */
    softmax_pass(SC, PR);

    /* ---- stage 11: quantise probabilities ----------------------------- */
    for (int i = 0; i < 32; i++) {
        for (int c = 0; c < 32; c++) {
#pragma HLS PIPELINE II=1
#pragma HLS UNROLL factor=8
            QUANT_INTO(A8[i][c], SC[i * 32 + c], SH_PROB);
        }
    }

    /* ---- stage 12: restore V into the B operand, then av = P x V ------- */
    for (int i = 0; i < 32; i++) {
        for (int c = 0; c < 16; c++) {
#pragma HLS PIPELINE II=1
#pragma HLS UNROLL factor=8
            B8[i][c] = V8[i * 16 + c];
        }
    }
    gemm(A8, B8, C32, 32, 32, 16, 0, -1);
    for (int i = 0; i < 512; i++) {
#pragma HLS PIPELINE II=1
#pragma HLS UNROLL factor=8
        AVB[i] = (int32_t)((uint32_t)C32[i >> 4][i & 15] << SH_AVQ);
    }

    /* ---- stage 13: out projection + residual -------------------------- */
    for (int r = 0; r < 32; r++) {
        for (int c = 0; c < 16; c++) {
#pragma HLS PIPELINE II=1
#pragma HLS UNROLL factor=8
            QUANT_INTO(A8[r][c], AVB[r * 16 + c], SH_AV);
        }
    }
    gemm(A8, B8, C32, 32, 16, 16, 0, 84);
    for (int i = 0; i < 512; i++) {
#pragma HLS PIPELINE II=1
#pragma HLS UNROLL factor=8
#pragma HLS DEPENDENCE variable=H inter false
        int32_t projected = (int32_t)((uint32_t)C32[i >> 4][i & 15] << RS_OUT) + har_out_bias[i & 15];
        ACT_FLAT(H,(i)) = (int32_t)((uint32_t)ACT_FLAT(H,(i)) + (uint32_t)projected);
    }

    /* ---- stage 14: norm2 ---------------------------------------------- */
    if (norm_pass(H, GAM2, NR)) return HAR_NET_OVERFLOW;

    /* ---- stage 15: ff1 + ReLU ----------------------------------------- */
    /* Norm2 quantization: same fixed NR bank mapping as norm1.
     * Only traversal and unrolling change; preserve SH_FF1_IN exactly. */
    for (int q = 0; q < 16; q++) {
#pragma HLS PIPELINE II=1
        for (int rb = 0; rb < 4; rb++) {
#pragma HLS UNROLL
            for (int l = 0; l < 8; l++) {
#pragma HLS UNROLL
                int r = 4 * (q >> 1) + rb;
                int c = 8 * (q & 1) + l;
                QUANT_INTO(A8[r][c], NR[rb][l][q], SH_FF1_IN);
            }
        }
    }
    for (int cb = 0; cb < 32; cb += LANES) {
        gemm(A8, B8, C32, 32, 16, 32, cb, 100);
    }
    for (int r = 0; r < 32; r++) {
        for (int c = 0; c < 32; c++) {
#pragma HLS PIPELINE II=1
#pragma HLS UNROLL factor=8
            int32_t z = (int32_t)((uint32_t)C32[2 * r + (c >> 4)][c & 15] << RS_FF1) +
                        har_ff1_bias[c];
            /* Both FF1 GEMMs finished before this loop. Their A8 input is
             * dead; write the exact next-stage quantization in its place. */
            int32_t relu = (z < 0) ? 0 : z;
            QUANT_INTO(A8[r][c], relu, SH_FF2_IN);
        }
    }

    /* ---- stage 16: ff2 + residual ------------------------------------- */
    gemm(A8, B8, C32, 32, 32, 16, 0, 132);
    /* FF2 residual only: rb/l are spatial constants, q is bank depth.
     * row=4*(q/2)+rb, col=8*(q%2)+l gives ACT(H,row,col)=H[rb][l][q].
     * Each of the original 512 elements is updated exactly once; unsigned
     * shift and add expressions retain the frozen wrap semantics. */
    for (int q = 0; q < 16; q++) {
#pragma HLS PIPELINE II=1
#pragma HLS DEPENDENCE variable=H inter false
        for (int rb = 0; rb < 4; rb++) {
#pragma HLS UNROLL
            for (int l = 0; l < 8; l++) {
#pragma HLS UNROLL
                int r = 4 * (q >> 1) + rb;
                int c = 8 * (q & 1) + l;
                int32_t projected = (int32_t)((uint32_t)C32[r][c] << RS_FF2) + har_ff2_bias[c];
                H[rb][l][q] = (int32_t)((uint32_t)H[rb][l][q] + (uint32_t)projected);
            }
        }
    }

    /* ---- stage 17: temporal mean pool --------------------------------- */
    /* Sixteen i-ordered accumulators, eight bank-conflict-free H reads per
     * cycle; each column still sums its 32 rows in the same ascending order
     * as v2 (and 64-bit addition is exact under reordering anyway). */
    for (int j = 0; j < 16; j++) {
#pragma HLS UNROLL
        PSUM[j] = 0;
    }
    for (int i = 0; i < 32; i++) {
        for (int b = 0; b < 2; b++) {
#pragma HLS PIPELINE II=1
            for (int jj = 0; jj < 8; jj++) {
#pragma HLS UNROLL
                PSUM[b * 8 + jj] += (int64_t)ACT_FLAT(H,(i * 16 + b * 8 + jj));
            }
        }
    }
    for (int j = 0; j < 16; j++) {
#pragma HLS PIPELINE II=1
        ACT_FLAT(NR,(j)) = (int32_t)(PSUM[j] >> 5);
    }

    /* ---- stage 18: classifier ----------------------------------------- */
    for (int c = 0; c < 16; c++) {
#pragma HLS PIPELINE II=1
#pragma HLS UNROLL factor=8
        QUANT_INTO(A8[0][c], ACT_FLAT(NR,(c)), SH_CLS_IN);
    }
    gemm(A8, B8, C32, 1, 16, 6, 0, 164);
    for (int c = 0; c < 6; c++) {
        logits[c] = (int32_t)((uint32_t)C32[0][c] << RS_CLS) + har_classifier_bias[c];
    }
    return HAR_NET_OK;
}
