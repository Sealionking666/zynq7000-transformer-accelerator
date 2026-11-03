# SoC for the one-shot fused har_net accelerator.
#
#   ps7 (M_AXI_GP0) -> axi_interconnect_0 -> har_net_0/s_axi_control   (AXI-Lite)
#   gmem_in/out -> two slaves of ACP interconnect -> ps7/S_AXI_ACP
#
# Two m_axi bundles instead of the legacy three: the fused kernel never streams
# A/B matrices from DDR, only the Q16 input in and the six logits out.
#
# Usage: vivado -mode batch -source build_net_soc.tcl

set project_dir "__PROJECT_DIR__"
set part "xc7z020clg400-2"
set bd_name "har_net_system"
set ip_repo "__IP_REPO__"

file mkdir $project_dir
create_project har_net_soc $project_dir -part $part -force
set_property target_language Verilog [current_project]

if {![file exists $ip_repo]} { error "Exported HLS IP not found at $ip_repo" }
set_property ip_repo_paths $ip_repo [current_project]
update_ip_catalog -rebuild

create_bd_design $bd_name

# ---------------- PS ----------------
create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps7
set ps [get_bd_cells ps7]
set_property -dict [list \
  CONFIG.PCW_CRYSTAL_PERIPHERAL_FREQMHZ {33.333333} \
  CONFIG.PCW_UIPARAM_DDR_ENABLE {1} \
  CONFIG.PCW_UIPARAM_DDR_MEMORY_TYPE {DDR 3} \
  CONFIG.PCW_UIPARAM_DDR_PARTNO {MT41K256M16TW-107} \
  CONFIG.PCW_UIPARAM_DDR_DEVICE_CAPACITY {4096 MBits} \
  CONFIG.PCW_UIPARAM_DDR_DRAM_WIDTH {16 Bits} \
  CONFIG.PCW_UIPARAM_DDR_BUS_WIDTH {32 Bit} \
  CONFIG.PCW_UIPARAM_DDR_FREQ_MHZ {533.333333} \
  CONFIG.PCW_UIPARAM_DDR_SPEED_BIN {DDR3_1066F} \
  CONFIG.PCW_UIPARAM_DDR_CL {7} \
  CONFIG.PCW_UIPARAM_DDR_CWL {6} \
  CONFIG.PCW_UIPARAM_DDR_ROW_ADDR_COUNT {15} \
  CONFIG.PCW_UIPARAM_DDR_COL_ADDR_COUNT {10} \
  CONFIG.PCW_UIPARAM_DDR_BANK_ADDR_COUNT {3} \
  CONFIG.PCW_UIPARAM_DDR_ECC {Disabled} \
  CONFIG.PCW_USE_M_AXI_GP0 {1} \
  CONFIG.PCW_USE_S_AXI_HP0 {1} \
  CONFIG.PCW_USE_S_AXI_ACP {1} \
  CONFIG.PCW_USE_DEFAULT_ACP_USER_VAL {1} \
  CONFIG.PCW_S_AXI_ACP_ARUSER_VAL {31} \
  CONFIG.PCW_S_AXI_ACP_AWUSER_VAL {31} \
  CONFIG.PCW_EN_CLK0_PORT {1} \
  CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {150} \
  CONFIG.PCW_UART1_PERIPHERAL_ENABLE {1} \
  CONFIG.PCW_UART1_UART1_IO {MIO 48 .. 49} \
  CONFIG.PCW_UART1_BAUD_RATE {115200} \
  CONFIG.PCW_PRESET_BANK0_VOLTAGE {LVCMOS 3.3V} \
  CONFIG.PCW_PRESET_BANK1_VOLTAGE {LVCMOS 3.3V} \
] $ps

apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 \
  -config {make_external "FIXED_IO, DDR" apply_board_preset "0"} $ps

# ---------------- Accelerator ----------------
create_bd_cell -type ip -vlnv xilinx.com:hls:har_net:1.0 har_net_0
set accel [get_bd_cells har_net_0]

create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 axi_interconnect_0
set ic0 [get_bd_cells axi_interconnect_0]
set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {1}] $ic0

create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 axi_interconnect_acp
set acp_ic [get_bd_cells axi_interconnect_acp]
set_property -dict [list CONFIG.NUM_SI {2} CONFIG.NUM_MI {1} CONFIG.NUM_CLKS {1} CONFIG.HAS_ARESETN {1}] $acp_ic


create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst_ps7_0_100M
set rst [get_bd_cells rst_ps7_0_100M]

connect_bd_net [get_bd_pins ps7/FCLK_CLK0] \
  [get_bd_pins ps7/M_AXI_GP0_ACLK] \
  [get_bd_pins ps7/S_AXI_HP0_ACLK] \
  [get_bd_pins ps7/S_AXI_ACP_ACLK] \
  [get_bd_pins axi_interconnect_acp/aclk] \
  [get_bd_pins axi_interconnect_0/ACLK] \
  [get_bd_pins axi_interconnect_0/S00_ACLK] \
  [get_bd_pins axi_interconnect_0/M00_ACLK] \
  [get_bd_pins har_net_0/ap_clk] \
  [get_bd_pins rst_ps7_0_100M/slowest_sync_clk]

connect_bd_net [get_bd_pins ps7/FCLK_RESET0_N] [get_bd_pins rst_ps7_0_100M/ext_reset_in]

connect_bd_net [get_bd_pins rst_ps7_0_100M/peripheral_aresetn] \
  [get_bd_pins axi_interconnect_0/ARESETN] \
  [get_bd_pins axi_interconnect_0/S00_ARESETN] \
  [get_bd_pins axi_interconnect_0/M00_ARESETN] \
  [get_bd_pins axi_interconnect_acp/aresetn] \
  [get_bd_pins har_net_0/ap_rst_n]

connect_bd_intf_net [get_bd_intf_pins ps7/M_AXI_GP0] [get_bd_intf_pins axi_interconnect_0/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_interconnect_0/M00_AXI] [get_bd_intf_pins har_net_0/s_axi_control]

connect_bd_intf_net [get_bd_intf_pins har_net_0/m_axi_gmem_in] [get_bd_intf_pins axi_interconnect_acp/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_interconnect_acp/M00_AXI] [get_bd_intf_pins ps7/S_AXI_ACP]
connect_bd_intf_net [get_bd_intf_pins har_net_0/m_axi_gmem_out] [get_bd_intf_pins axi_interconnect_acp/S01_AXI]

assign_bd_address
validate_bd_design

# Actual elaborated properties/connectivity, retained as control evidence.
set af [open "$project_dir/acp_topology.txt" w]
foreach {prop expected} {PCW_USE_S_AXI_ACP 1 PCW_USE_DEFAULT_ACP_USER_VAL 1 PCW_S_AXI_ACP_ARUSER_VAL 31 PCW_S_AXI_ACP_AWUSER_VAL 31} {
 set actual [get_property CONFIG.$prop $ps]
 puts $af "$prop=$actual"
 if {$actual != $expected} {error "ACP property mismatch $prop=$actual"}
}
foreach pin {har_net_0/m_axi_gmem_in axi_interconnect_acp/S00_AXI axi_interconnect_acp/M00_AXI ps7/S_AXI_ACP har_net_0/m_axi_gmem_out axi_interconnect_acp/S01_AXI} {
 set net [get_bd_intf_nets -of_objects [get_bd_intf_pins $pin]]
 if {[llength $net] != 1} {error "Missing/ambiguous ACP control connection $pin"}
 puts $af "$pin=$net peers=[get_bd_intf_pins -of_objects $net]"
}
puts $af "ACP_VLNV=[get_property VLNV $acp_ic]"
foreach p {NUM_SI NUM_MI NUM_CLKS HAS_ARESETN} {
 puts $af "ACP_$p=[get_property CONFIG.$p $acp_ic]"
}
foreach name {har_net_0/m_axi_gmem_in har_net_0/m_axi_gmem_out ps7/S_AXI_ACP} {
 set pin [get_bd_intf_pins $name]
 foreach prop [lsort [list_property $pin]] {
  if {[string match CONFIG.* $prop]} {puts $af "$name.$prop=[get_property $prop $pin]"}
 }
}
close $af
write_bd_tcl -force "$project_dir/acp_elaborated_bd.tcl"

save_bd_design

set report [open "$project_dir/ps_config_report.txt" w]
puts $report "Vivado 2022.2 / AX7Z020B fused-net SoC PS configuration"
foreach p [lsort [list_property $ps]] {
    if {[string match "CONFIG.*" $p]} { puts $report "$p=[get_property $p $ps]" }
}
close $report

set amap [open "$project_dir/address_map.txt" w]
puts $amap "Address map for $bd_name"
foreach seg [get_bd_addr_segs -of_objects [get_bd_addr_spaces ps7/Data]] {
    set off [get_property offset $seg]
    set rng [get_property range $seg]
    set nm  [get_property name $seg]
    puts $amap [format "%-60s offset=%s range=%s" $nm $off $rng]
    puts "ADDRMAP $nm offset=$off range=$rng"
}
close $amap

set bd_file [get_files "*/$bd_name.bd"]
make_wrapper -files $bd_file -top
set wrapper_file "$project_dir/har_net_soc.gen/sources_1/bd/${bd_name}/hdl/${bd_name}_wrapper.v"
if {![file exists $wrapper_file]} { error "Generated wrapper not found: $wrapper_file" }
add_files -norecurse $wrapper_file

set_property source_mgmt_mode None [current_project]
set_property top ${bd_name}_wrapper [current_fileset]
update_compile_order -fileset sources_1

puts "NET_SOC_BD_CREATED=$project_dir/har_net_soc.xpr"
close_project
puts "NET_SOC_TCL_DONE"
exit
