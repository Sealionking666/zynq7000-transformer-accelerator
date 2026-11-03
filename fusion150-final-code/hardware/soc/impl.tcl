# Full implementation flow for the matrix SoC, with the IP-lock problem fixed.
#
# ROOT CAUSE of the earlier synthesis failures
# --------------------------------------------
# The exported HLS IP is newer than the revision Vivado recorded when the block
# design was built, so Vivado locked it:
#
#   | matrix_system_matmul_int8_0_0 | IP revision change | Upgrade IP | ... |
#   WARNING: [BD 41-1661] One or more IPs have been locked in the design
#
# A locked IP means generate_target produces no checkpoints, which makes every
# out-of-context synthesis sub-run fail with:
#   ERROR: [Designutils 20-414] HRTInvokeSpec : No Verilog or VHDL sources specified
#
# So the order matters: UPGRADE the IP, regenerate targets, verify the
# checkpoints actually appeared, and only then launch synthesis.
#
# Usage: vivado -mode batch -source build_matrix_impl.tcl

set project_dir "__PROJECT_DIR__"
set bd_name "har_net_system"
set artifacts "$project_dir/artifacts"
set reports "$project_dir/impl_reports"

open_project "$project_dir/har_net_soc.xpr"
file mkdir $artifacts
file mkdir $reports

set bd [lindex [get_files -filter {FILE_TYPE == "Block Designs"}] 0]
if {$bd eq ""} { error "Block design not found in project" }
puts "BD = $bd"

# ---- 1. unlock: upgrade any IP whose revision changed ----
puts "=== upgrading locked IPs ==="
set upgraded 0
foreach ip [get_ips -quiet] {
    if {[get_property IS_LOCKED $ip]} {
        if {[catch {upgrade_ip $ip} e]} {
            puts "upgrade FAILED for $ip: $e"
        } else {
            puts "upgraded $ip"
            incr upgraded
        }
    }
}
puts "UPGRADED_COUNT=$upgraded"

set still 0
foreach ip [get_ips -quiet] {
    if {[get_property IS_LOCKED $ip]} { incr still; puts "STILL LOCKED: $ip" }
}
if {$still > 0} { error "$still IP(s) remain locked; generate_target would fail" }
puts "NO_LOCKED_IPS"

# ---- 2. generate outputs and verify they exist ----
puts "=== generating targets ==="
generate_target all $bd -force
puts "GENERATE_TARGET_DONE"

set gen_ip_dir "$project_dir/har_net_soc.gen/sources_1/bd/${bd_name}/ip"
set ip_v_count [llength [glob -nocomplain "$gen_ip_dir/*/synth/*.v"]]
set ip_src_count [llength [glob -nocomplain "$gen_ip_dir/*/src/*"]]
puts "GENERATED ip_synth_v=$ip_v_count ip_src=$ip_src_count"

# NOTE: do NOT require *.dcp here. The per-IP out-of-context synthesis runs are
# what CREATE the checkpoints; before they run there is legitimately no .dcp.
# Requiring one at this point would abort a perfectly healthy flow. What must
# exist is the generated HDL, because its ABSENCE is the actual cause of
# "HRTInvokeSpec : No Verilog or VHDL sources specified".
if {$ip_v_count == 0} {
    error "No IP synthesis HDL was generated under $gen_ip_dir - OOC runs would fail"
}

update_compile_order -fileset sources_1
puts "COMPILE_ORDER_UPDATED"

# ---- 3. synthesis ----
puts "=== synthesis ==="
reset_run synth_1
launch_runs synth_1 -jobs 4
wait_on_run synth_1
set synth_status [get_property STATUS [get_runs synth_1]]
puts "SYNTH_DONE status=$synth_status"
if {[get_property PROGRESS [get_runs synth_1]] != "100%"} {
    error "Synthesis failed: $synth_status"
}

# ---- 4. implementation and bitstream ----
puts "=== implementation ==="
set_property strategy Performance_ExplorePostRoutePhysOpt [get_runs impl_1]
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
set impl_status [get_property STATUS [get_runs impl_1]]
puts "IMPL_DONE status=$impl_status"
if {[get_property PROGRESS [get_runs impl_1]] != "100%"} {
    error "Implementation failed: $impl_status"
}

open_run impl_1

# ---- 5. real timing numbers. Do not assume a frequency. ----
set wns [get_property SLACK [get_timing_paths -delay_type max]]
set whs [get_property SLACK [get_timing_paths -delay_type min]]
puts "TIMING WNS=$wns WHS=$whs"
report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose -file "$reports/timing_summary.rpt"
report_utilization -file "$reports/utilization.rpt"
report_drc -file "$reports/drc.rpt"
report_clocks -file "$reports/clocks.rpt"
write_checkpoint "$reports/final-routed.dcp"

if {$wns eq "" || $wns < 0} { error "Setup timing failed: $wns" }
if {$whs eq "" || $whs < 0} { error "Hold timing failed: $whs" }

# ---- 6. bitstream ----
set run_dir [get_property DIRECTORY [get_runs impl_1]]
set bitfile "$run_dir/${bd_name}_wrapper.bit"
if {![file exists $bitfile]} { error "Bitstream not found at $bitfile" }
file copy -force $bitfile "$artifacts/har_net_system.bit"
puts "BITSTREAM=$artifacts/matrix_system.bit"

# ---- 7. XSA WITH the bitstream, so software can have the PL configured ----
write_hw_platform -fixed -include_bit -force "$artifacts/har_net_system.xsa"
if {![file exists "$artifacts/har_net_system.xsa"]} { error "XSA not produced" }
puts "XSA=$artifacts/matrix_system.xsa"

close_project
puts "NET_IMPL_DONE"
exit
