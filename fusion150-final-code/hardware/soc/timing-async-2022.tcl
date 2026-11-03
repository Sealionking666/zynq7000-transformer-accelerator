# Source in a fresh Vivado 2022.2 research project with the routed design open.
# Uses the documented command, not a Tcl variable or speculative get_param name.
# The caller must set an existing fresh report directory; never edit a sealed run.
if {![info exists har_async_report_dir] || ![file isdirectory $har_async_report_dir]} {
    error "Set har_async_report_dir to the fresh attempt's report directory"
}
set har_async_config [file join $har_async_report_dir timing_config.rpt]
set har_async_summary [file join $har_async_report_dir timing_summary_async.rpt]
if {[file exists $har_async_config] || [file exists $har_async_summary]} {
    error "Async timing output exists; use a new attempt"
}
config_timing_analysis -enable_preset_clear_arcs true
report_config_timing -all -file $har_async_config
report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose -file $har_async_summary
# These reports alone do not sign off LUTAR or prove all recovery/removal paths.
