// ==============================================================
// Vitis HLS - High-Level Synthesis from C, C++ and OpenCL v2022.2 (64-bit)
// Tool Version Limit: 2019.12
// Copyright 1986-2022 Xilinx, Inc. All Rights Reserved.
// ==============================================================
#ifndef __linux__

#include "xstatus.h"
#include "xparameters.h"
#include "xhar_net.h"

extern XHar_net_Config XHar_net_ConfigTable[];

XHar_net_Config *XHar_net_LookupConfig(u16 DeviceId) {
	XHar_net_Config *ConfigPtr = NULL;

	int Index;

	for (Index = 0; Index < XPAR_XHAR_NET_NUM_INSTANCES; Index++) {
		if (XHar_net_ConfigTable[Index].DeviceId == DeviceId) {
			ConfigPtr = &XHar_net_ConfigTable[Index];
			break;
		}
	}

	return ConfigPtr;
}

int XHar_net_Initialize(XHar_net *InstancePtr, u16 DeviceId) {
	XHar_net_Config *ConfigPtr;

	Xil_AssertNonvoid(InstancePtr != NULL);

	ConfigPtr = XHar_net_LookupConfig(DeviceId);
	if (ConfigPtr == NULL) {
		InstancePtr->IsReady = 0;
		return (XST_DEVICE_NOT_FOUND);
	}

	return XHar_net_CfgInitialize(InstancePtr, ConfigPtr);
}

#endif

