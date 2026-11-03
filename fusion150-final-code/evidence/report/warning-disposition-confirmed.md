# 2026-10-28 队长确认处置：原融合RC保留21条Warning

用户实际回复：**我作为队长确认按台账保留Warning**。原始待签台账保留；本确认只适用于上述精确bit，未修改原severity或设计。完整可核验记录见`warning-owner-confirmation.json`及`warning-disposition-final.json`。

---

# 融合150MHz RC1：DSP告警处置待签台账

状态：用户以队长身份确认按台账保留当前实现和原Warning级别。

精确bit：`c5e1a3bb1d4cae7698bf39458b76aa71fa918e79f4252b3c880d478ae617bde2`。

DPOP-1×9、DPOP-2×12是DSP流水线性能/功耗建议。原报告没有将这些记录定为功能错误。建议在当前交付候选中保留实现，由队长/硬件负责人确认；增加流水线会产生新设计，需重新完整验证。

依据：本精确实现普通与扩大STA setup +0.103ns、hold +0.036ns、pulse +2.203ns，所列端点零失败；已有开发集1796/10776精确一致、匹配板测、8.153分钟压力与四偏移生命周期证据。全局STA通过不等于单个DSP的功耗已实测，也不证明温压/多板可靠性。当前最差GEMM CE路径不能作为这些DSP路径的逐实例时序数值。

|编号|规则/原等级|模块|流水线建议|实际处置|
|---|---|---|---|---|
|DSP-01|DPOP-1 / Warning|Softmax|PREG=0，建议评估增加DSP输出寄存级|已由用户（队长）确认保留|
|DSP-02|DPOP-1 / Warning|Softmax|PREG=0，建议评估增加DSP输出寄存级|已由用户（队长）确认保留|
|DSP-03|DPOP-1 / Warning|Softmax|PREG=0，建议评估增加DSP输出寄存级|已由用户（队长）确认保留|
|DSP-04|DPOP-1 / Warning|Softmax|PREG=0，建议评估增加DSP输出寄存级|已由用户（队长）确认保留|
|DSP-05|DPOP-1 / Warning|Softmax|PREG=0，建议评估增加DSP输出寄存级|已由用户（队长）确认保留|
|DSP-06|DPOP-1 / Warning|Softmax|PREG=0，建议评估增加DSP输出寄存级|已由用户（队长）确认保留|
|DSP-07|DPOP-1 / Warning|Softmax|PREG=0，建议评估增加DSP输出寄存级|已由用户（队长）确认保留|
|DSP-08|DPOP-1 / Warning|Softmax|PREG=0，建议评估增加DSP输出寄存级|已由用户（队长）确认保留|
|DSP-09|DPOP-1 / Warning|Softmax|PREG=0，建议评估增加DSP输出寄存级|已由用户（队长）确认保留|
|DSP-10|DPOP-2 / Warning|LayerNorm|MREG=0，建议评估乘法器流水级及后级寄存|已由用户（队长）确认保留|
|DSP-11|DPOP-2 / Warning|LayerNorm|MREG=0，建议评估乘法器流水级及后级寄存|已由用户（队长）确认保留|
|DSP-12|DPOP-2 / Warning|LayerNorm|MREG=0，建议评估乘法器流水级及后级寄存|已由用户（队长）确认保留|
|DSP-13|DPOP-2 / Warning|LayerNorm|MREG=0，建议评估乘法器流水级及后级寄存|已由用户（队长）确认保留|
|DSP-14|DPOP-2 / Warning|LayerNorm|MREG=0，建议评估乘法器流水级及后级寄存|已由用户（队长）确认保留|
|DSP-15|DPOP-2 / Warning|LayerNorm|MREG=0，建议评估乘法器流水级及后级寄存|已由用户（队长）确认保留|
|DSP-16|DPOP-2 / Warning|LayerNorm|MREG=0，建议评估乘法器流水级及后级寄存|已由用户（队长）确认保留|
|DSP-17|DPOP-2 / Warning|LayerNorm|MREG=0，建议评估乘法器流水级及后级寄存|已由用户（队长）确认保留|
|DSP-18|DPOP-2 / Warning|Softmax|MREG=0，建议评估乘法器流水级及后级寄存|已由用户（队长）确认保留|
|DSP-19|DPOP-2 / Warning|Softmax|MREG=0，建议评估乘法器流水级及后级寄存|已由用户（队长）确认保留|
|DSP-20|DPOP-2 / Warning|Softmax|MREG=0，建议评估乘法器流水级及后级寄存|已由用户（队长）确认保留|
|DSP-21|DPOP-2 / Warning|Softmax|MREG=0，建议评估乘法器流水级及后级寄存|已由用户（队长）确认保留|

## DSP-01 — DPOP-1

实例/数据路径：`har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_696_4_fu_277/mul_35ns_32ns_64_5_1_U1208/tmp_product`。

原报告：`drc.rpt`；原等级：Warning。

PREG Output pipelining DSP har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_696_4_fu_277/mul_35ns_32ns_64_5_1_U1208/tmp_product output har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_696_4_fu_277/mul_35ns_32ns_64_5_1_U1208/tmp_product/P[47:0] is not pipelined (PREG=0). Pipelining the DSP48 output will improve performance and often saves power so it is suggested whenever possible to fully pipeline this function. If this DSP48 function was inferred, it is suggested to describe an additional register stage after this function. If the DSP48 was instantiated in the design, it is suggested to set the PREG attribute to 1.

建议：保留当前实现和原Warning；理由为上述精确实现证据。确认依据、记录时间和队长原话见本文件顶部所链确认记录。

## DSP-02 — DPOP-1

实例/数据路径：`har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_708_5_fu_377/mul_31ns_32ns_63_4_1_U1214/tmp_product`。

原报告：`drc.rpt`；原等级：Warning。

PREG Output pipelining DSP har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_708_5_fu_377/mul_31ns_32ns_63_4_1_U1214/tmp_product output har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_708_5_fu_377/mul_31ns_32ns_63_4_1_U1214/tmp_product/P[47:0] is not pipelined (PREG=0). Pipelining the DSP48 output will improve performance and often saves power so it is suggested whenever possible to fully pipeline this function. If this DSP48 function was inferred, it is suggested to describe an additional register stage after this function. If the DSP48 was instantiated in the design, it is suggested to set the PREG attribute to 1.

建议：保留当前实现和原Warning；理由为上述精确实现证据。确认依据、记录时间和队长原话见本文件顶部所链确认记录。

## DSP-03 — DPOP-1

实例/数据路径：`har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_708_5_fu_377/mul_31ns_32ns_63_4_1_U1215/tmp_product`。

原报告：`drc.rpt`；原等级：Warning。

PREG Output pipelining DSP har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_708_5_fu_377/mul_31ns_32ns_63_4_1_U1215/tmp_product output har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_708_5_fu_377/mul_31ns_32ns_63_4_1_U1215/tmp_product/P[47:0] is not pipelined (PREG=0). Pipelining the DSP48 output will improve performance and often saves power so it is suggested whenever possible to fully pipeline this function. If this DSP48 function was inferred, it is suggested to describe an additional register stage after this function. If the DSP48 was instantiated in the design, it is suggested to set the PREG attribute to 1.

建议：保留当前实现和原Warning；理由为上述精确实现证据。确认依据、记录时间和队长原话见本文件顶部所链确认记录。

## DSP-04 — DPOP-1

实例/数据路径：`har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_708_5_fu_377/mul_31ns_32ns_63_4_1_U1216/tmp_product`。

原报告：`drc.rpt`；原等级：Warning。

PREG Output pipelining DSP har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_708_5_fu_377/mul_31ns_32ns_63_4_1_U1216/tmp_product output har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_708_5_fu_377/mul_31ns_32ns_63_4_1_U1216/tmp_product/P[47:0] is not pipelined (PREG=0). Pipelining the DSP48 output will improve performance and often saves power so it is suggested whenever possible to fully pipeline this function. If this DSP48 function was inferred, it is suggested to describe an additional register stage after this function. If the DSP48 was instantiated in the design, it is suggested to set the PREG attribute to 1.

建议：保留当前实现和原Warning；理由为上述精确实现证据。确认依据、记录时间和队长原话见本文件顶部所链确认记录。

## DSP-05 — DPOP-1

实例/数据路径：`har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_708_5_fu_377/mul_31ns_32ns_63_4_1_U1217/tmp_product`。

原报告：`drc.rpt`；原等级：Warning。

PREG Output pipelining DSP har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_708_5_fu_377/mul_31ns_32ns_63_4_1_U1217/tmp_product output har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_708_5_fu_377/mul_31ns_32ns_63_4_1_U1217/tmp_product/P[47:0] is not pipelined (PREG=0). Pipelining the DSP48 output will improve performance and often saves power so it is suggested whenever possible to fully pipeline this function. If this DSP48 function was inferred, it is suggested to describe an additional register stage after this function. If the DSP48 was instantiated in the design, it is suggested to set the PREG attribute to 1.

建议：保留当前实现和原Warning；理由为上述精确实现证据。确认依据、记录时间和队长原话见本文件顶部所链确认记录。

## DSP-06 — DPOP-1

实例/数据路径：`har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_708_5_fu_377/mul_36ns_32ns_64_4_1_U1218/tmp_product`。

原报告：`drc.rpt`；原等级：Warning。

PREG Output pipelining DSP har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_708_5_fu_377/mul_36ns_32ns_64_4_1_U1218/tmp_product output har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_708_5_fu_377/mul_36ns_32ns_64_4_1_U1218/tmp_product/P[47:0] is not pipelined (PREG=0). Pipelining the DSP48 output will improve performance and often saves power so it is suggested whenever possible to fully pipeline this function. If this DSP48 function was inferred, it is suggested to describe an additional register stage after this function. If the DSP48 was instantiated in the design, it is suggested to set the PREG attribute to 1.

建议：保留当前实现和原Warning；理由为上述精确实现证据。确认依据、记录时间和队长原话见本文件顶部所链确认记录。

## DSP-07 — DPOP-1

实例/数据路径：`har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_708_5_fu_377/mul_36ns_32ns_64_4_1_U1219/tmp_product`。

原报告：`drc.rpt`；原等级：Warning。

PREG Output pipelining DSP har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_708_5_fu_377/mul_36ns_32ns_64_4_1_U1219/tmp_product output har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_708_5_fu_377/mul_36ns_32ns_64_4_1_U1219/tmp_product/P[47:0] is not pipelined (PREG=0). Pipelining the DSP48 output will improve performance and often saves power so it is suggested whenever possible to fully pipeline this function. If this DSP48 function was inferred, it is suggested to describe an additional register stage after this function. If the DSP48 was instantiated in the design, it is suggested to set the PREG attribute to 1.

建议：保留当前实现和原Warning；理由为上述精确实现证据。确认依据、记录时间和队长原话见本文件顶部所链确认记录。

## DSP-08 — DPOP-1

实例/数据路径：`har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_708_5_fu_377/mul_36ns_32ns_64_4_1_U1220/tmp_product`。

原报告：`drc.rpt`；原等级：Warning。

PREG Output pipelining DSP har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_708_5_fu_377/mul_36ns_32ns_64_4_1_U1220/tmp_product output har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_708_5_fu_377/mul_36ns_32ns_64_4_1_U1220/tmp_product/P[47:0] is not pipelined (PREG=0). Pipelining the DSP48 output will improve performance and often saves power so it is suggested whenever possible to fully pipeline this function. If this DSP48 function was inferred, it is suggested to describe an additional register stage after this function. If the DSP48 was instantiated in the design, it is suggested to set the PREG attribute to 1.

建议：保留当前实现和原Warning；理由为上述精确实现证据。确认依据、记录时间和队长原话见本文件顶部所链确认记录。

## DSP-09 — DPOP-1

实例/数据路径：`har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_708_5_fu_377/mul_36ns_32ns_64_4_1_U1221/tmp_product`。

原报告：`drc.rpt`；原等级：Warning。

PREG Output pipelining DSP har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_708_5_fu_377/mul_36ns_32ns_64_4_1_U1221/tmp_product output har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_708_5_fu_377/mul_36ns_32ns_64_4_1_U1221/tmp_product/P[47:0] is not pipelined (PREG=0). Pipelining the DSP48 output will improve performance and often saves power so it is suggested whenever possible to fully pipeline this function. If this DSP48 function was inferred, it is suggested to describe an additional register stage after this function. If the DSP48 was instantiated in the design, it is suggested to set the PREG attribute to 1.

建议：保留当前实现和原Warning；理由为上述精确实现证据。确认依据、记录时间和队长原话见本文件顶部所链确认记录。

## DSP-10 — DPOP-2

实例/数据路径：`har_net_system_i/har_net_0/inst/grp_norm_pass_fu_1147/grp_norm_pass_Pipeline_VITIS_LOOP_208_2_fu_468/mul_23s_23s_46_4_1_U658/buff0_reg`。

原报告：`drc.rpt`；原等级：Warning。

MREG Output pipelining DSP har_net_system_i/har_net_0/inst/grp_norm_pass_fu_1147/grp_norm_pass_Pipeline_VITIS_LOOP_208_2_fu_468/mul_23s_23s_46_4_1_U658/buff0_reg multiplier stage har_net_system_i/har_net_0/inst/grp_norm_pass_fu_1147/grp_norm_pass_Pipeline_VITIS_LOOP_208_2_fu_468/mul_23s_23s_46_4_1_U658/buff0_reg/P[47:0] is not pipelined (MREG=0). Pipelining the multiplier function will improve performance and will save significant power so it is suggested whenever possible to fully pipeline this function. If this multiplier was inferred, it is suggested to describe an additional register stage after this function. If there is no registered adder/accumulator following the multiply function, two pipeline stages are suggested to allow both the MREG and PREG registers to be used. If the DSP48 was instantiated in the design, it is suggested to set both the MREG and PREG attributes to 1 when performing multiply functions.

建议：保留当前实现和原Warning；理由为上述精确实现证据。确认依据、记录时间和队长原话见本文件顶部所链确认记录。

## DSP-11 — DPOP-2

实例/数据路径：`har_net_system_i/har_net_0/inst/grp_norm_pass_fu_1147/grp_norm_pass_Pipeline_VITIS_LOOP_208_2_fu_468/mul_23s_23s_46_4_1_U659/buff0_reg`。

原报告：`drc.rpt`；原等级：Warning。

MREG Output pipelining DSP har_net_system_i/har_net_0/inst/grp_norm_pass_fu_1147/grp_norm_pass_Pipeline_VITIS_LOOP_208_2_fu_468/mul_23s_23s_46_4_1_U659/buff0_reg multiplier stage har_net_system_i/har_net_0/inst/grp_norm_pass_fu_1147/grp_norm_pass_Pipeline_VITIS_LOOP_208_2_fu_468/mul_23s_23s_46_4_1_U659/buff0_reg/P[47:0] is not pipelined (MREG=0). Pipelining the multiplier function will improve performance and will save significant power so it is suggested whenever possible to fully pipeline this function. If this multiplier was inferred, it is suggested to describe an additional register stage after this function. If there is no registered adder/accumulator following the multiply function, two pipeline stages are suggested to allow both the MREG and PREG registers to be used. If the DSP48 was instantiated in the design, it is suggested to set both the MREG and PREG attributes to 1 when performing multiply functions.

建议：保留当前实现和原Warning；理由为上述精确实现证据。确认依据、记录时间和队长原话见本文件顶部所链确认记录。

## DSP-12 — DPOP-2

实例/数据路径：`har_net_system_i/har_net_0/inst/grp_norm_pass_fu_1147/grp_norm_pass_Pipeline_VITIS_LOOP_208_2_fu_468/mul_23s_23s_46_4_1_U660/buff0_reg`。

原报告：`drc.rpt`；原等级：Warning。

MREG Output pipelining DSP har_net_system_i/har_net_0/inst/grp_norm_pass_fu_1147/grp_norm_pass_Pipeline_VITIS_LOOP_208_2_fu_468/mul_23s_23s_46_4_1_U660/buff0_reg multiplier stage har_net_system_i/har_net_0/inst/grp_norm_pass_fu_1147/grp_norm_pass_Pipeline_VITIS_LOOP_208_2_fu_468/mul_23s_23s_46_4_1_U660/buff0_reg/P[47:0] is not pipelined (MREG=0). Pipelining the multiplier function will improve performance and will save significant power so it is suggested whenever possible to fully pipeline this function. If this multiplier was inferred, it is suggested to describe an additional register stage after this function. If there is no registered adder/accumulator following the multiply function, two pipeline stages are suggested to allow both the MREG and PREG registers to be used. If the DSP48 was instantiated in the design, it is suggested to set both the MREG and PREG attributes to 1 when performing multiply functions.

建议：保留当前实现和原Warning；理由为上述精确实现证据。确认依据、记录时间和队长原话见本文件顶部所链确认记录。

## DSP-13 — DPOP-2

实例/数据路径：`har_net_system_i/har_net_0/inst/grp_norm_pass_fu_1147/grp_norm_pass_Pipeline_VITIS_LOOP_208_2_fu_468/mul_23s_23s_46_4_1_U661/buff0_reg`。

原报告：`drc.rpt`；原等级：Warning。

MREG Output pipelining DSP har_net_system_i/har_net_0/inst/grp_norm_pass_fu_1147/grp_norm_pass_Pipeline_VITIS_LOOP_208_2_fu_468/mul_23s_23s_46_4_1_U661/buff0_reg multiplier stage har_net_system_i/har_net_0/inst/grp_norm_pass_fu_1147/grp_norm_pass_Pipeline_VITIS_LOOP_208_2_fu_468/mul_23s_23s_46_4_1_U661/buff0_reg/P[47:0] is not pipelined (MREG=0). Pipelining the multiplier function will improve performance and will save significant power so it is suggested whenever possible to fully pipeline this function. If this multiplier was inferred, it is suggested to describe an additional register stage after this function. If there is no registered adder/accumulator following the multiply function, two pipeline stages are suggested to allow both the MREG and PREG registers to be used. If the DSP48 was instantiated in the design, it is suggested to set both the MREG and PREG attributes to 1 when performing multiply functions.

建议：保留当前实现和原Warning；理由为上述精确实现证据。确认依据、记录时间和队长原话见本文件顶部所链确认记录。

## DSP-14 — DPOP-2

实例/数据路径：`har_net_system_i/har_net_0/inst/grp_norm_pass_fu_1147/grp_norm_pass_Pipeline_VITIS_LOOP_208_2_fu_468/mul_23s_23s_46_4_1_U662/buff0_reg`。

原报告：`drc.rpt`；原等级：Warning。

MREG Output pipelining DSP har_net_system_i/har_net_0/inst/grp_norm_pass_fu_1147/grp_norm_pass_Pipeline_VITIS_LOOP_208_2_fu_468/mul_23s_23s_46_4_1_U662/buff0_reg multiplier stage har_net_system_i/har_net_0/inst/grp_norm_pass_fu_1147/grp_norm_pass_Pipeline_VITIS_LOOP_208_2_fu_468/mul_23s_23s_46_4_1_U662/buff0_reg/P[47:0] is not pipelined (MREG=0). Pipelining the multiplier function will improve performance and will save significant power so it is suggested whenever possible to fully pipeline this function. If this multiplier was inferred, it is suggested to describe an additional register stage after this function. If there is no registered adder/accumulator following the multiply function, two pipeline stages are suggested to allow both the MREG and PREG registers to be used. If the DSP48 was instantiated in the design, it is suggested to set both the MREG and PREG attributes to 1 when performing multiply functions.

建议：保留当前实现和原Warning；理由为上述精确实现证据。确认依据、记录时间和队长原话见本文件顶部所链确认记录。

## DSP-15 — DPOP-2

实例/数据路径：`har_net_system_i/har_net_0/inst/grp_norm_pass_fu_1147/grp_norm_pass_Pipeline_VITIS_LOOP_208_2_fu_468/mul_23s_23s_46_4_1_U663/buff0_reg`。

原报告：`drc.rpt`；原等级：Warning。

MREG Output pipelining DSP har_net_system_i/har_net_0/inst/grp_norm_pass_fu_1147/grp_norm_pass_Pipeline_VITIS_LOOP_208_2_fu_468/mul_23s_23s_46_4_1_U663/buff0_reg multiplier stage har_net_system_i/har_net_0/inst/grp_norm_pass_fu_1147/grp_norm_pass_Pipeline_VITIS_LOOP_208_2_fu_468/mul_23s_23s_46_4_1_U663/buff0_reg/P[47:0] is not pipelined (MREG=0). Pipelining the multiplier function will improve performance and will save significant power so it is suggested whenever possible to fully pipeline this function. If this multiplier was inferred, it is suggested to describe an additional register stage after this function. If there is no registered adder/accumulator following the multiply function, two pipeline stages are suggested to allow both the MREG and PREG registers to be used. If the DSP48 was instantiated in the design, it is suggested to set both the MREG and PREG attributes to 1 when performing multiply functions.

建议：保留当前实现和原Warning；理由为上述精确实现证据。确认依据、记录时间和队长原话见本文件顶部所链确认记录。

## DSP-16 — DPOP-2

实例/数据路径：`har_net_system_i/har_net_0/inst/grp_norm_pass_fu_1147/grp_norm_pass_Pipeline_VITIS_LOOP_208_2_fu_468/mul_23s_23s_46_4_1_U664/buff0_reg`。

原报告：`drc.rpt`；原等级：Warning。

MREG Output pipelining DSP har_net_system_i/har_net_0/inst/grp_norm_pass_fu_1147/grp_norm_pass_Pipeline_VITIS_LOOP_208_2_fu_468/mul_23s_23s_46_4_1_U664/buff0_reg multiplier stage har_net_system_i/har_net_0/inst/grp_norm_pass_fu_1147/grp_norm_pass_Pipeline_VITIS_LOOP_208_2_fu_468/mul_23s_23s_46_4_1_U664/buff0_reg/P[47:0] is not pipelined (MREG=0). Pipelining the multiplier function will improve performance and will save significant power so it is suggested whenever possible to fully pipeline this function. If this multiplier was inferred, it is suggested to describe an additional register stage after this function. If there is no registered adder/accumulator following the multiply function, two pipeline stages are suggested to allow both the MREG and PREG registers to be used. If the DSP48 was instantiated in the design, it is suggested to set both the MREG and PREG attributes to 1 when performing multiply functions.

建议：保留当前实现和原Warning；理由为上述精确实现证据。确认依据、记录时间和队长原话见本文件顶部所链确认记录。

## DSP-17 — DPOP-2

实例/数据路径：`har_net_system_i/har_net_0/inst/grp_norm_pass_fu_1147/grp_norm_pass_Pipeline_VITIS_LOOP_208_2_fu_468/mul_23s_23s_46_4_1_U665/buff0_reg`。

原报告：`drc.rpt`；原等级：Warning。

MREG Output pipelining DSP har_net_system_i/har_net_0/inst/grp_norm_pass_fu_1147/grp_norm_pass_Pipeline_VITIS_LOOP_208_2_fu_468/mul_23s_23s_46_4_1_U665/buff0_reg multiplier stage har_net_system_i/har_net_0/inst/grp_norm_pass_fu_1147/grp_norm_pass_Pipeline_VITIS_LOOP_208_2_fu_468/mul_23s_23s_46_4_1_U665/buff0_reg/P[47:0] is not pipelined (MREG=0). Pipelining the multiplier function will improve performance and will save significant power so it is suggested whenever possible to fully pipeline this function. If this multiplier was inferred, it is suggested to describe an additional register stage after this function. If there is no registered adder/accumulator following the multiply function, two pipeline stages are suggested to allow both the MREG and PREG registers to be used. If the DSP48 was instantiated in the design, it is suggested to set both the MREG and PREG attributes to 1 when performing multiply functions.

建议：保留当前实现和原Warning；理由为上述精确实现证据。确认依据、记录时间和队长原话见本文件顶部所链确认记录。

## DSP-18 — DPOP-2

实例/数据路径：`har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_708_5_fu_377/mul_36ns_32ns_64_4_1_U1218/buff0_reg`。

原报告：`drc.rpt`；原等级：Warning。

MREG Output pipelining DSP har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_708_5_fu_377/mul_36ns_32ns_64_4_1_U1218/buff0_reg multiplier stage har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_708_5_fu_377/mul_36ns_32ns_64_4_1_U1218/buff0_reg/P[47:0] is not pipelined (MREG=0). Pipelining the multiplier function will improve performance and will save significant power so it is suggested whenever possible to fully pipeline this function. If this multiplier was inferred, it is suggested to describe an additional register stage after this function. If there is no registered adder/accumulator following the multiply function, two pipeline stages are suggested to allow both the MREG and PREG registers to be used. If the DSP48 was instantiated in the design, it is suggested to set both the MREG and PREG attributes to 1 when performing multiply functions.

建议：保留当前实现和原Warning；理由为上述精确实现证据。确认依据、记录时间和队长原话见本文件顶部所链确认记录。

## DSP-19 — DPOP-2

实例/数据路径：`har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_708_5_fu_377/mul_36ns_32ns_64_4_1_U1219/buff0_reg`。

原报告：`drc.rpt`；原等级：Warning。

MREG Output pipelining DSP har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_708_5_fu_377/mul_36ns_32ns_64_4_1_U1219/buff0_reg multiplier stage har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_708_5_fu_377/mul_36ns_32ns_64_4_1_U1219/buff0_reg/P[47:0] is not pipelined (MREG=0). Pipelining the multiplier function will improve performance and will save significant power so it is suggested whenever possible to fully pipeline this function. If this multiplier was inferred, it is suggested to describe an additional register stage after this function. If there is no registered adder/accumulator following the multiply function, two pipeline stages are suggested to allow both the MREG and PREG registers to be used. If the DSP48 was instantiated in the design, it is suggested to set both the MREG and PREG attributes to 1 when performing multiply functions.

建议：保留当前实现和原Warning；理由为上述精确实现证据。确认依据、记录时间和队长原话见本文件顶部所链确认记录。

## DSP-20 — DPOP-2

实例/数据路径：`har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_708_5_fu_377/mul_36ns_32ns_64_4_1_U1220/buff0_reg`。

原报告：`drc.rpt`；原等级：Warning。

MREG Output pipelining DSP har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_708_5_fu_377/mul_36ns_32ns_64_4_1_U1220/buff0_reg multiplier stage har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_708_5_fu_377/mul_36ns_32ns_64_4_1_U1220/buff0_reg/P[47:0] is not pipelined (MREG=0). Pipelining the multiplier function will improve performance and will save significant power so it is suggested whenever possible to fully pipeline this function. If this multiplier was inferred, it is suggested to describe an additional register stage after this function. If there is no registered adder/accumulator following the multiply function, two pipeline stages are suggested to allow both the MREG and PREG registers to be used. If the DSP48 was instantiated in the design, it is suggested to set both the MREG and PREG attributes to 1 when performing multiply functions.

建议：保留当前实现和原Warning；理由为上述精确实现证据。确认依据、记录时间和队长原话见本文件顶部所链确认记录。

## DSP-21 — DPOP-2

实例/数据路径：`har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_708_5_fu_377/mul_36ns_32ns_64_4_1_U1221/buff0_reg`。

原报告：`drc.rpt`；原等级：Warning。

MREG Output pipelining DSP har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_708_5_fu_377/mul_36ns_32ns_64_4_1_U1221/buff0_reg multiplier stage har_net_system_i/har_net_0/inst/grp_softmax_pass_fu_1858/grp_softmax_pass_Pipeline_VITIS_LOOP_708_5_fu_377/mul_36ns_32ns_64_4_1_U1221/buff0_reg/P[47:0] is not pipelined (MREG=0). Pipelining the multiplier function will improve performance and will save significant power so it is suggested whenever possible to fully pipeline this function. If this multiplier was inferred, it is suggested to describe an additional register stage after this function. If there is no registered adder/accumulator following the multiply function, two pipeline stages are suggested to allow both the MREG and PREG registers to be used. If the DSP48 was instantiated in the design, it is suggested to set both the MREG and PREG attributes to 1 when performing multiply functions.

建议：保留当前实现和原Warning；理由为上述精确实现证据。确认依据、记录时间和队长原话见本文件顶部所链确认记录。
