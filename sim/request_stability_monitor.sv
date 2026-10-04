`timescale 1ns/1ps
// Non-driving assertion monitor for the engine's documented stable-request
// contract. Compile alongside the existing tb_uart; do not change its stimulus.
module request_stability_monitor;
    reg active = 0;
    reg [63:0] accepted_request;
    integer checked_cycles = 0;
    integer accepted_packets = 0;
    integer completed_packets = 0;
    always @(posedge tb_uart.sys_clk) begin
        if (tb_uart.dut.rst) begin
            active <= 0;
        end else begin
            if (active) begin
                if (tb_uart.dut.packet !== accepted_request)
                    $fatal(1, "Engine request changed while response was pending");
                checked_cycles = checked_cycles + 1;
            end
            if (tb_uart.dut.request_valid && tb_uart.dut.engine_ready) begin
                if (active)
                    $fatal(1, "Second engine request accepted before response");
                accepted_request <= tb_uart.dut.packet;
                active <= 1;
                accepted_packets = accepted_packets + 1;
            end
            if (tb_uart.dut.response_valid) begin
                if (!active)
                    $fatal(1, "Engine response without an accepted request");
                active <= 0;
                completed_packets = completed_packets + 1;
            end
        end
    end
    final begin
        if (active || accepted_packets == 0 || accepted_packets != completed_packets)
            $fatal(1, "Incomplete stable-request verification");
        $display("PASS stable request: %0d accepted/completed packets, %0d protected cycles",
                 completed_packets, checked_cycles);
    end
endmodule
