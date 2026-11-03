
proc ensure_stopped {} {
 if {[catch {stop} reason] && ![string equal -nocase [string trim $reason] "Already stopped"]} {error $reason}
 set st [state];puts "VERIFIED_CORE_STATE=$st"
 if {![string match -nocase "*stopped*" $st]} {error "Core not stopped: $st"}
}
proc go {} {
 connect -url tcp:127.0.0.1:3121
 puts [jtag targets]
 if {[llength [targets -target-properties -filter {name =~ "xc7z020"}]] != 1} {error "Require exactly one XC7Z020"}
 targets -set -filter {name =~ "ARM*#0"}
 set raw [mrd -value 0xF800025C];scan $raw %x mode;puts "BOOT_MODE_RAW=$raw"
 if {($mode & 7) != 0} {error "Requires JTAG boot; no programming attempted"}
 targets -set -filter {name =~ "ARM*#1"};ensure_stopped
 targets -set -filter {name =~ "ARM*#0"};ensure_stopped
 rst -system;after 1000
 targets -set -filter {name =~ "ARM*#1"};ensure_stopped
 targets -set -filter {name =~ "ARM*#0"};ensure_stopped
 targets -set -filter {name =~ "xc7z020"};fpga hardware.bit
 puts HAR_FPGA_PROGRAMMED
 targets -set -filter {name =~ "ARM*#0"}
 uplevel #0 {source ps7_init.tcl};ps7_init;ps7_post_config;ensure_stopped
 puts HAR_PS_INIT_DONE
 dow application.elf;puts HAR_ELF_DOWNLOADED
 con;puts HAR_APPLICATION_STARTED;disconnect
}
if {[catch {go} reason]} {puts "HAR_DOWNLOAD_FAILED=$reason";catch {disconnect};exit 1}
exit 0
