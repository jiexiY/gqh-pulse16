# Run with Gowin Education's IDE/bin/gw_sh.exe from any working directory.
# Keep the checked-in GUI project and this CLI build on the same source list.
set project_root [file normalize [file join [file dirname [info script]] ..]]
if {[info exists env(PULSE16_PROJECT_ROOT)]} {
    set project_root $env(PULSE16_PROJECT_ROOT)
}
cd $project_root
open_project [file join $project_root trade_top.gprj]
set_option -top_module trade_top
set_option -output_base_name trade_top
set_option -synthesis_tool gowinsynthesis
set_option -verilog_std v2001
set_option -global_freq 27.000
set_option -frequency 27.000
set_option -gen_text_timing_rpt 1
set_option -gen_verilog_sim_netlist 1
set_option -show_init_in_vo 1
run all
