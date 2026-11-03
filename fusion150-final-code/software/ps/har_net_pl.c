/* Research adapter v1: one whole-network transaction, full 4-KiB output
 * allocation plus a private prefix guard. No changes to the standard adapter.
 * Timed profile includes all packing, poison, cache, control and guard work.
 *
 * v4 keeps the exact same profile, guards, packing, control and timer
 * boundary. Only the implementation of the range cache maintenance changes:
 * the stock BSP range helper stores to the PL310 Cache Sync register once per
 * 32-byte line, so every line waits for its own completion; v4 issues the same
 * line-by-line L1 clean and L2 clean/invalidate-by-PA operations and performs
 * one completion sync per range, which is the documented PL310 usage. */
#include "har_net_pl.h"
#include <stddef.h>
#include <string.h>
#ifdef HAR_DRIVER_TEST
#include "test_hal.h"
#else
#include "xparameters.h"
#include "xhar_net.h"
#include "xil_cache.h"
#include "xtime_l.h"
#include "xl2cc.h"
#ifndef XPAR_HAR_NET_0_DEVICE_ID
#error Matching fused SoC BSP required
#endif
#endif
#ifndef HAR_TRANSPORT_VECTOR
#define HAR_TRANSPORT_VECTOR 0
#endif
#if HAR_TRANSPORT_VECTOR != 0 && HAR_TRANSPORT_VECTOR != 1
#error Unsupported transport implementation
#endif
#if HAR_TRANSPORT_VECTOR
/* Byte intrinsics preserve legal four-byte public alignment and access the
   int64 private packing buffer through character bytes, without aliasing casts. */
#if defined(__ARM_NEON) || defined(__ARM_NEON__)
#include <arm_neon.h>
typedef uint32x4_t har_vec4;
static inline har_vec4 load4(const void *p) {
    return vreinterpretq_u32_u8(vld1q_u8((const uint8_t *)p));
}
static inline void store4(void *p,har_vec4 value) {
    vst1q_u8((uint8_t *)p,vreinterpretq_u8_u32(value));
}
#else
/* Native control tests execute the same vector word semantics. Production
   Cortex-A9 instructions are verified separately from the linked ARM ELF. */
typedef uint32_t har_vec4 __attribute__((vector_size(16)));
static inline har_vec4 load4(const void *p) {
    har_vec4 value;memcpy(&value,p,sizeof(value));return value;
}
static inline void store4(void *p,har_vec4 value) {
    memcpy(p,&value,sizeof(value));
}
#endif
#endif
/* Exact pinned ACP inputs/outputs use coherent transactions.
   Poison, whole4160B guards and all four completion/control barriers remain. */
static XHar_net engine;
/* Single-owner device state: ownership and the fault latch belong to the one physical device, so
 * memset(ctx) must never resurrect a faulted device. */
enum { HAR_DEV_UNINIT=0, HAR_DEV_READY=1, HAR_DEV_RUNNING=2, HAR_DEV_FAULTED=3 };
static struct {
    int state;
    const har_net_ctx *owner;
    unsigned recoveries;
    int reason;
    unsigned completion_seen;
} g_dev = {HAR_DEV_UNINIT, 0, 0, 0, 0};
int har_net_device_state(void) { return g_dev.state; }
uint64_t har_net_ticks(void) { XTime t; XTime_GetTime(&t);return (uint64_t)t; }
uint64_t har_net_frequency(void) {return (uint64_t)COUNTS_PER_SECOND;}
static void barrier(void) {
#ifdef HAR_DRIVER_TEST
    har_test_barrier();
#else
    __asm__ volatile("dsb sy" ::: "memory");
#endif
}
static int span(const void *a,size_t an,const void *b,size_t bn) {
    uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;
    if (x>UINTPTR_MAX-an || y>UINTPTR_MAX-bn) return 1;
    return x<y+bn && y<x+an;
}
int har_net_init(har_net_ctx *s) {
    if (!s || ((uintptr_t)s&63u)) return HAR_NP_ARG;
    if (g_dev.state==HAR_DEV_FAULTED) { s->faulted=1; return HAR_NP_FAULTED; }
    if (g_dev.state==HAR_DEV_RUNNING || (g_dev.state==HAR_DEV_READY && g_dev.owner!=s)) {
        s->faulted=1; return HAR_NP_BUSY;
    }
    memset(s,0,sizeof(*s));
    if (XHar_net_Initialize(&engine,XPAR_HAR_NET_0_DEVICE_ID)) {
        s->faulted=1; g_dev.state=HAR_DEV_FAULTED; g_dev.reason=HAR_NP_INIT; g_dev.owner=s; return HAR_NP_INIT;
    }
    XHar_net_DisableAutoRestart(&engine);
    s->device=&engine;s->timeout_ticks=har_net_frequency()*5u;
    g_dev.state=HAR_DEV_READY; g_dev.owner=s; g_dev.reason=0; g_dev.completion_seen=0;
    return HAR_NP_OK;
}

/* Recovery is an explicit drain of a timed-out transaction, never a reset.
 * DONE is clear-on-read: retain its witness while waiting for subsequent IDLE.
 * Caller keeps ctx and direct input alive/unmodified until drain or PL+CPU reset.
 * Hardware return/guard errors and unsolicited busy state require reload.
 */
int har_net_recover(har_net_ctx *s) {
    if (!s || ((uintptr_t)s&63u)) return HAR_NP_ARG;
    if (g_dev.owner!=s || s->device!=&engine) return HAR_NP_ARG;
    if (g_dev.state!=HAR_DEV_FAULTED) return
        g_dev.state==HAR_DEV_READY ? HAR_NP_OK : HAR_NP_BUSY;
    if (g_dev.reason!=HAR_NP_TIMEOUT) return HAR_NP_FAULTED;
    uint32_t state=XHar_net_ReadReg(engine.Control_BaseAddress,XHAR_NET_CONTROL_ADDR_AP_CTRL);
    if (state&0x80u) {g_dev.reason=HAR_NP_STATUS; return HAR_NP_STATUS;}
    if (state&2u) g_dev.completion_seen=1u;
    if (!g_dev.completion_seen || !(state&4u)) return HAR_NP_FAULTED;
    if (state&1u) {g_dev.reason=HAR_NP_STATUS; return HAR_NP_STATUS;}
    barrier();
    if ((int)XHar_net_Get_return(&engine)) {
        g_dev.reason=HAR_NP_STATUS; return HAR_NP_STATUS;
    }
    barrier();
    uint32_t bad=0;
    for (int i=0;i<16;i++) bad|=(uint32_t)(s->before[i]!=HAR_POISON);
    for (int i=6;i<1024;i++) bad|=(uint32_t)(s->out[i]!=HAR_POISON);
    if (bad) {g_dev.reason=HAR_NP_STATUS; return HAR_NP_STATUS;}
    /* Do not publish the late result or reinitialise/restart the HLS block. */
    s->faulted=0; g_dev.reason=0; g_dev.completion_seen=0;
    g_dev.state=HAR_DEV_READY; g_dev.recoveries++;
    return HAR_NP_OK;
}
int har_net_run(har_net_ctx *s,const int32_t *input,int32_t *logits) {
    if (!s || !input || !logits || ((uintptr_t)s&63u) ||
        ((uintptr_t)input&3u) || ((uintptr_t)logits&3u)) return HAR_NP_ARG;
    if (s->faulted) return HAR_NP_FAULTED;
    if (g_dev.state==HAR_DEV_FAULTED) { s->faulted=1; return HAR_NP_FAULTED; }
    if (g_dev.state!=HAR_DEV_READY || g_dev.owner!=s) return HAR_NP_BUSY;
    if (s->device!=&engine || !s->timeout_ticks ||
        span(input,4608,s,sizeof(*s)) || span(logits,24,s,sizeof(*s))) return HAR_NP_ARG;
    /* One initial read consumes a stale clear-on-read DONE. Require IDLE,
       disable implicit retries and reject START/AUTO_RESTART already set. */
    uint32_t state=XHar_net_ReadReg(engine.Control_BaseAddress,XHAR_NET_CONTROL_ADDR_AP_CTRL);
    if (!(state&4u) || (state&0x81u)) {s->faulted=1;g_dev.state=HAR_DEV_FAULTED;g_dev.reason=HAR_NP_BUSY;return HAR_NP_BUSY;}
    /* No CPU typed aliasing: only pass the byte address to the PL master.
       Its64-bit input port requires8-byte alignment; retain the old private
       packing path for every legal4-byte-only aligned public input. */
#if !defined(__BYTE_ORDER__) || __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error Direct input requires the registered little-endian target
#endif
    const int direct_input=(((uintptr_t)input&7u)==0u);
    const uintptr_t packed_address=direct_input?(uintptr_t)input:(uintptr_t)s->in;
#if HAR_TRANSPORT_VECTOR
    /* This ARM/host profile is little endian. Contiguous Q16 words have the
       same exact bytes as the scalar low-word/high-word packing. */
#if !defined(__BYTE_ORDER__) || __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error Vector packing requires the registered little-endian target
#endif
    const har_vec4 poison={HAR_POISON,HAR_POISON,HAR_POISON,HAR_POISON};
    if (!direct_input) {
    for (int i=0;i<1152;i+=4)
        store4((unsigned char *)s->in+4*i,load4(input+i));
    }
    for (int i=0;i<16;i+=4) store4(s->before+i,poison);
    for (int i=0;i<1024;i+=4) store4(s->out+i,poison);
#else
    if (!direct_input) for (int w=0;w<576;w++)
        s->in[w]=(int64_t)((uint64_t)(uint32_t)input[2*w] |
                          ((uint64_t)(uint32_t)input[2*w+1]<<32));
    for (int i=0;i<16;i++) s->before[i]=HAR_POISON;
    for (int i=0;i<1024;i++) s->out[i]=HAR_POISON;
#endif
    /* Qualified ACP coherent reads and writes observe dirty shareable buffers.
       Both direct/fallback inputs and all output lines use the pinned route.
       This DSB publishes the newly written poison before accelerator start. */
    barrier();
    XHar_net_Set_input_r(&engine,(u64)packed_address);
    XHar_net_Set_logits(&engine,(u64)(uintptr_t)s->out);
    g_dev.state=HAR_DEV_RUNNING;
    barrier();XHar_net_Start(&engine);
    uint64_t start=har_net_ticks();
    while (!(XHar_net_ReadReg(engine.Control_BaseAddress,XHAR_NET_CONTROL_ADDR_AP_CTRL)&2u)) {
        if (har_net_ticks()-start>=s->timeout_ticks) {s->faulted=1;g_dev.state=HAR_DEV_FAULTED;g_dev.reason=HAR_NP_TIMEOUT;return HAR_NP_TIMEOUT;}
    }
    barrier();
    if ((int)XHar_net_Get_return(&engine)) {s->faulted=1;g_dev.state=HAR_DEV_FAULTED;g_dev.reason=HAR_NP_STATUS;return HAR_NP_STATUS;}
    /* Completed ACP coherent writes are visible before the full guard scan. */
    barrier();
    uint32_t bad=0;
#if HAR_TRANSPORT_VECTOR
    har_vec4 diff={0,0,0,0};
    for (int i=0;i<16;i+=4) diff|=load4(s->before+i)^poison;
    bad=(uint32_t)s->out[6]^(uint32_t)HAR_POISON;
    bad|=(uint32_t)s->out[7]^(uint32_t)HAR_POISON;
    for (int i=8;i<1024;i+=4) diff|=load4(s->out+i)^poison;
    bad|=diff[0]|diff[1]|diff[2]|diff[3];
#else
    for (int i=0;i<16;i++) bad|=(uint32_t)(s->before[i]!=HAR_POISON);
    for (int i=6;i<1024;i++) bad|=(uint32_t)(s->out[i]!=HAR_POISON);
#endif
    if (bad) {s->faulted=1;g_dev.state=HAR_DEV_FAULTED;g_dev.reason=HAR_NP_STATUS;return HAR_NP_STATUS;}
    memcpy(logits,s->out,24);s->calls++;g_dev.state=HAR_DEV_READY;
    return HAR_NP_OK;
}
