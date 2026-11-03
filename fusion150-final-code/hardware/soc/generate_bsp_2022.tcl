# Headless HSI flow; avoids the Eclipse project service.
if {[llength $argv] != 3} {error "Expected XSA, output BSP directory, driver repository"}
lassign $argv xsa dest repo
if {[catch {
    hsi::set_repo_path $repo
    hsi::open_hw_design $xsa
    hsi::create_sw_design har_bsp -proc ps7_cortexa9_0 -os standalone
    hsi::set_property CONFIG.stdin ps7_uart_1 [hsi::get_os]
    hsi::set_property CONFIG.stdout ps7_uart_1 [hsi::get_os]
    hsi::generate_bsp -dir $dest
    puts HAR_HSI_BSP_PASS
} err]} {puts stderr "HAR_HSI_BSP_FAIL: $err";exit 1}
exit 0
