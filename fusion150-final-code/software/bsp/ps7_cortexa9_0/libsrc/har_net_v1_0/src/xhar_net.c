// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2022.2 (64-bit)
// Tool Version Limit: 2019.12
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// ==============================================================
/***************************** Include Files *********************************/
#include "xhar_net.h"

/************************** Function Implementation *************************/
#ifndef __linux__
int XHar_net_CfgInitialize(XHar_net *InstancePtr, XHar_net_Config *ConfigPtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(ConfigPtr != NULL);

    InstancePtr->Control_BaseAddress = ConfigPtr->Control_BaseAddress;
    InstancePtr->IsReady = XIL_COMPONENT_IS_READY;

    return XST_SUCCESS;
}
#endif

void XHar_net_Start(XHar_net *InstancePtr) {
    u32 Data;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XHar_net_ReadReg(InstancePtr->Control_BaseAddress, XHAR_NET_CONTROL_ADDR_AP_CTRL) & 0x80;
    XHar_net_WriteReg(InstancePtr->Control_BaseAddress, XHAR_NET_CONTROL_ADDR_AP_CTRL, Data | 0x01);
}

u32 XHar_net_IsDone(XHar_net *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XHar_net_ReadReg(InstancePtr->Control_BaseAddress, XHAR_NET_CONTROL_ADDR_AP_CTRL);
    return (Data >> 1) & 0x1;
}

u32 XHar_net_IsIdle(XHar_net *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XHar_net_ReadReg(InstancePtr->Control_BaseAddress, XHAR_NET_CONTROL_ADDR_AP_CTRL);
    return (Data >> 2) & 0x1;
}

u32 XHar_net_IsReady(XHar_net *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XHar_net_ReadReg(InstancePtr->Control_BaseAddress, XHAR_NET_CONTROL_ADDR_AP_CTRL);
    // check ap_start to see if the pcore is ready for next input
    return !(Data & 0x1);
}

void XHar_net_EnableAutoRestart(XHar_net *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XHar_net_WriteReg(InstancePtr->Control_BaseAddress, XHAR_NET_CONTROL_ADDR_AP_CTRL, 0x80);
}

void XHar_net_DisableAutoRestart(XHar_net *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XHar_net_WriteReg(InstancePtr->Control_BaseAddress, XHAR_NET_CONTROL_ADDR_AP_CTRL, 0);
}

u32 XHar_net_Get_return(XHar_net *InstancePtr) {
    u32 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XHar_net_ReadReg(InstancePtr->Control_BaseAddress, XHAR_NET_CONTROL_ADDR_AP_RETURN);
    return Data;
}
void XHar_net_Set_input_r(XHar_net *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XHar_net_WriteReg(InstancePtr->Control_BaseAddress, XHAR_NET_CONTROL_ADDR_INPUT_R_DATA, (u32)(Data));
    XHar_net_WriteReg(InstancePtr->Control_BaseAddress, XHAR_NET_CONTROL_ADDR_INPUT_R_DATA + 4, (u32)(Data >> 32));
}

u64 XHar_net_Get_input_r(XHar_net *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XHar_net_ReadReg(InstancePtr->Control_BaseAddress, XHAR_NET_CONTROL_ADDR_INPUT_R_DATA);
    Data += (u64)XHar_net_ReadReg(InstancePtr->Control_BaseAddress, XHAR_NET_CONTROL_ADDR_INPUT_R_DATA + 4) << 32;
    return Data;
}

void XHar_net_Set_logits(XHar_net *InstancePtr, u64 Data) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XHar_net_WriteReg(InstancePtr->Control_BaseAddress, XHAR_NET_CONTROL_ADDR_LOGITS_DATA, (u32)(Data));
    XHar_net_WriteReg(InstancePtr->Control_BaseAddress, XHAR_NET_CONTROL_ADDR_LOGITS_DATA + 4, (u32)(Data >> 32));
}

u64 XHar_net_Get_logits(XHar_net *InstancePtr) {
    u64 Data;

    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Data = XHar_net_ReadReg(InstancePtr->Control_BaseAddress, XHAR_NET_CONTROL_ADDR_LOGITS_DATA);
    Data += (u64)XHar_net_ReadReg(InstancePtr->Control_BaseAddress, XHAR_NET_CONTROL_ADDR_LOGITS_DATA + 4) << 32;
    return Data;
}

void XHar_net_InterruptGlobalEnable(XHar_net *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XHar_net_WriteReg(InstancePtr->Control_BaseAddress, XHAR_NET_CONTROL_ADDR_GIE, 1);
}

void XHar_net_InterruptGlobalDisable(XHar_net *InstancePtr) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XHar_net_WriteReg(InstancePtr->Control_BaseAddress, XHAR_NET_CONTROL_ADDR_GIE, 0);
}

void XHar_net_InterruptEnable(XHar_net *InstancePtr, u32 Mask) {
    u32 Register;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Register =  XHar_net_ReadReg(InstancePtr->Control_BaseAddress, XHAR_NET_CONTROL_ADDR_IER);
    XHar_net_WriteReg(InstancePtr->Control_BaseAddress, XHAR_NET_CONTROL_ADDR_IER, Register | Mask);
}

void XHar_net_InterruptDisable(XHar_net *InstancePtr, u32 Mask) {
    u32 Register;

    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    Register =  XHar_net_ReadReg(InstancePtr->Control_BaseAddress, XHAR_NET_CONTROL_ADDR_IER);
    XHar_net_WriteReg(InstancePtr->Control_BaseAddress, XHAR_NET_CONTROL_ADDR_IER, Register & (~Mask));
}

void XHar_net_InterruptClear(XHar_net *InstancePtr, u32 Mask) {
    Xil_AssertVoid(InstancePtr != NULL);
    Xil_AssertVoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    XHar_net_WriteReg(InstancePtr->Control_BaseAddress, XHAR_NET_CONTROL_ADDR_ISR, Mask);
}

u32 XHar_net_InterruptGetEnabled(XHar_net *InstancePtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    return XHar_net_ReadReg(InstancePtr->Control_BaseAddress, XHAR_NET_CONTROL_ADDR_IER);
}

u32 XHar_net_InterruptGetStatus(XHar_net *InstancePtr) {
    Xil_AssertNonvoid(InstancePtr != NULL);
    Xil_AssertNonvoid(InstancePtr->IsReady == XIL_COMPONENT_IS_READY);

    return XHar_net_ReadReg(InstancePtr->Control_BaseAddress, XHAR_NET_CONTROL_ADDR_ISR);
}

