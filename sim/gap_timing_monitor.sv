`timescale 1ns/1ps
// Supplemental diagnostic only: observe the actual existing RTL state timing.
// Used alongside tb_uart with MAX_PACKETS=1; never changes stimulus or scoring.
module gap_timing_monitor;
    integer clock_number = 0;
    integer gap_start_clock = -1;
    integer checked_gaps = 0;
    reg [1:0] previous_state = 0;
    always @(posedge tb_uart.sys_clk) begin
        #1;
        clock_number = clock_number + 1;
        if (tb_uart.dut.rst) begin
            previous_state = tb_uart.dut.tx_state;
            gap_start_clock = -1;
        end else begin
            if (previous_state == 2 && tb_uart.dut.tx_state == 3)
                gap_start_clock = clock_number;
            if (previous_state == 1 && tb_uart.dut.tx_state == 2 && gap_start_clock >= 0) begin
                if (clock_number - gap_start_clock != 3)
                    $fatal(1, "Configured-zero gap was %0d clocks, expected 3", clock_number-gap_start_clock);
                checked_gaps = checked_gaps + 1;
                gap_start_clock = -1;
            end
            previous_state = tb_uart.dut.tx_state;
        end
    end
    final begin
        if (checked_gaps != 7)
            $fatal(1, "Checked %0d response gaps, expected 7", checked_gaps);
        $display("PASS configured-zero gap: 7 response gaps each occupy 3 system clocks after the stop bit");
    end
endmodule
