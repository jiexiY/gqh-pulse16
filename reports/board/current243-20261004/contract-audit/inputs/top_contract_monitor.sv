`timescale 1ns/1ps
// Independent monitor plus simulation-only adversarial RX-pin stimulus.
module top_contract_monitor;
    reg pending = 0, transmitting = 0;
    reg [63:0] accepted_packet, transmit_packet, transmit_response;
    integer accepted = 0, completed = 0, aborted = 0;
    integer engine_cycles = 0, tx_cycles = 0;
    integer ignored_valid = 0, ignored_error = 0, injections = 0;
    integer b;
    reg [7:0] noise = 8'ha5;

    always @(posedge tb_uart.sys_clk) begin
        if (tb_uart.dut.rst) begin
            if (pending) aborted = aborted + 1;
            pending <= 0;
            transmitting <= 0;
        end else begin
            if (pending) begin
                if (tb_uart.dut.packet !== accepted_packet)
                    $fatal(1, "Request changed before engine response");
                engine_cycles = engine_cycles + 1;
            end
            if (transmitting) begin
                if (tb_uart.dut.packet !== transmit_packet)
                    $fatal(1, "Request fields changed during UART response");
                if (tb_uart.dut.response !== transmit_response)
                    $fatal(1, "Engine response changed during UART response");
                tx_cycles = tx_cycles + 1;
                if (tb_uart.dut.tx_state == 0 && !tb_uart.dut.response_valid)
                    transmitting <= 0;
            end
            if (tb_uart.dut.tx_state != 0) begin
                if (tb_uart.dut.rx_valid) ignored_valid = ignored_valid + 1;
                if (tb_uart.dut.rx_error) ignored_error = ignored_error + 1;
            end
            if (tb_uart.dut.request_valid && tb_uart.dut.engine_ready) begin
                if (pending || transmitting)
                    $fatal(1, "New request accepted before old transaction ended");
                accepted_packet <= tb_uart.dut.packet;
                pending <= 1;
                accepted = accepted + 1;
            end
            if (tb_uart.dut.response_valid) begin
                if (!pending) $fatal(1, "Response without outstanding request");
                pending <= 0;
                completed = completed + 1;
                transmit_packet <= tb_uart.dut.packet;
                transmit_response <= tb_uart.dut.response;
                transmitting <= 1;
            end
        end
    end

    // Exercise both valid unexpected bytes and malformed stop bits during TX.
    // All overrides end within 13 bit periods of TX start, before the normal
    // sender can begin its next stop-and-wait request (an 80-bit response).
    initial forever begin
        wait(tb_uart.dut.tx_state != 0 && !tb_uart.dut.rst);
        injections = injections + 1;
        if (injections % 2 == 0) begin
            force tb_uart.uart_rx_i = 1'b0;
            #(tb_uart.host_bit_ns * 10.5);
            force tb_uart.uart_rx_i = 1'b1;
            #(tb_uart.host_bit_ns * 2.0);
        end else begin
            force tb_uart.uart_rx_i = 1'b0;
            #(tb_uart.host_bit_ns);
            for (b=0; b<8; b=b+1) begin
                if (noise[b]) force tb_uart.uart_rx_i = 1'b1;
                else force tb_uart.uart_rx_i = 1'b0;
                #(tb_uart.host_bit_ns);
            end
            force tb_uart.uart_rx_i = 1'b1;
            #(tb_uart.host_bit_ns * 2.0);
        end
        release tb_uart.uart_rx_i;
        wait(tb_uart.dut.tx_state == 0);
        @(posedge tb_uart.sys_clk);
    end

    final begin
        if (pending || transmitting || accepted != completed + aborted ||
            aborted != 1 || completed != tb_uart.count || completed == 0 ||
            ignored_valid == 0 || ignored_error == 0)
            $fatal(1, "Incomplete contract/reset/error coverage");
        $display("PASS contract: %0d completed, %0d aborted, %0d protected engine cycles, %0d protected TX cycles, %0d ignored valid RX, %0d ignored RX errors",
                 completed, aborted, engine_cycles, tx_cycles, ignored_valid, ignored_error);
    end
endmodule
