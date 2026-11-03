set_param general.maxThreads 4
lassign $argv checkpoint out template
if {[file exists $out]} {error "Fresh async report output required"}
file mkdir $out
if {[catch {
open_checkpoint $checkpoint
set har_async_report_dir $out
source $template
report_timing -delay_type max -max_paths 30 -path_type full_clock_expanded -input_pins -nets -file $out/setup30.rpt
report_timing -delay_type min -max_paths 10 -path_type full_clock_expanded -input_pins -nets -file $out/hold10.rpt
check_timing -verbose -file $out/check_timing.rpt
close_design
} message options]} {puts stderr $message;puts stderr [dict get $options -errorinfo];exit 1}
puts V41_PRESET_CLEAR_REVIEW_PASS
exit 0
