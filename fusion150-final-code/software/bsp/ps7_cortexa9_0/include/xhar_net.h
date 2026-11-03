// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2022.2 (64-bit)
// Tool Version Limit: 2019.12
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// ==============================================================
#ifndef XHAR_NET_H
#define XHAR_NET_H

#ifdef __cplusplus
extern "C" {
#endif

/***************************** Include Files *********************************/
#ifndef __linux__
#include "xil_types.h"
#include "xil_assert.h"
#include "xstatus.h"
#include "xil_io.h"
#else
#include <stdint.h>
#include <assert.h>
#include <dirent.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include <stddef.h>
#endif
#include "xhar_net_hw.h"

/**************************** Type Definitions ******************************/
#ifdef __linux__
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
#else
typedef struct {
    u16 DeviceId;
    u64 Control_BaseAddress;
} XHar_net_Config;
#endif

typedef struct {
    u64 Control_BaseAddress;
    u32 IsReady;
} XHar_net;

typedef u32 word_type;

/***************** Macros (Inline Functions) Definitions *********************/
#ifndef __linux__
#define XHar_net_WriteReg(BaseAddress, RegOffset, Data) \
    Xil_Out32((BaseAddress) + (RegOffset), (u32)(Data))
#define XHar_net_ReadReg(BaseAddress, RegOffset) \
    Xil_In32((BaseAddress) + (RegOffset))
#else
#define XHar_net_WriteReg(BaseAddress, RegOffset, Data) \
    *(volatile u32*)((BaseAddress) + (RegOffset)) = (u32)(Data)
#define XHar_net_ReadReg(BaseAddress, RegOffset) \
    *(volatile u32*)((BaseAddress) + (RegOffset))

#define Xil_AssertVoid(expr)    assert(expr)
#define Xil_AssertNonvoid(expr) assert(expr)

#define XST_SUCCESS             0
#define XST_DEVICE_NOT_FOUND    2
#define XST_OPEN_DEVICE_FAILED  3
#define XIL_COMPONENT_IS_READY  1
#endif

/************************** Function Prototypes *****************************/
#ifndef __linux__
int XHar_net_Initialize(XHar_net *InstancePtr, u16 DeviceId);
XHar_net_Config* XHar_net_LookupConfig(u16 DeviceId);
int XHar_net_CfgInitialize(XHar_net *InstancePtr, XHar_net_Config *ConfigPtr);
#else
int XHar_net_Initialize(XHar_net *InstancePtr, const char* InstanceName);
int XHar_net_Release(XHar_net *InstancePtr);
#endif

void XHar_net_Start(XHar_net *InstancePtr);
u32 XHar_net_IsDone(XHar_net *InstancePtr);
u32 XHar_net_IsIdle(XHar_net *InstancePtr);
u32 XHar_net_IsReady(XHar_net *InstancePtr);
void XHar_net_EnableAutoRestart(XHar_net *InstancePtr);
void XHar_net_DisableAutoRestart(XHar_net *InstancePtr);
u32 XHar_net_Get_return(XHar_net *InstancePtr);

void XHar_net_Set_input_r(XHar_net *InstancePtr, u64 Data);
u64 XHar_net_Get_input_r(XHar_net *InstancePtr);
void XHar_net_Set_logits(XHar_net *InstancePtr, u64 Data);
u64 XHar_net_Get_logits(XHar_net *InstancePtr);

void XHar_net_InterruptGlobalEnable(XHar_net *InstancePtr);
void XHar_net_InterruptGlobalDisable(XHar_net *InstancePtr);
void XHar_net_InterruptEnable(XHar_net *InstancePtr, u32 Mask);
void XHar_net_InterruptDisable(XHar_net *InstancePtr, u32 Mask);
void XHar_net_InterruptClear(XHar_net *InstancePtr, u32 Mask);
u32 XHar_net_InterruptGetEnabled(XHar_net *InstancePtr);
u32 XHar_net_InterruptGetStatus(XHar_net *InstancePtr);

#ifdef __cplusplus
}
#endif

#endif
