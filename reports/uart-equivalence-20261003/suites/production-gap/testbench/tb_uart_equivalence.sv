`timescale 1ns/1ps
module tb_uart_equivalence #(parameter integer GAP_CYCLES=13500);
    reg sys_clk=0, reset_btn=0, uart_rx_i=1;
    wire baseline_tx, candidate_tx, baseline_led0, baseline_led1;
    wire candidate_led0, candidate_led1;
    reg [63:0] request, expected, received=0;
    reg [7:0] byte_received;
    integer fd, count=0, replies=0, rx_bytes=0, status, i;
    integer compared_clocks=0, injected_errors=0;
    reg [1023:0] vectors;
    real host_bit_ns=8680.555556;
    localparam real TX_BIT_NS=234.0*37.038;
    always #18.519 sys_clk=~sys_clk;
    baseline_trade_top #(.TX_GAP_CYCLES(GAP_CYCLES)) baseline (
        .sys_clk(sys_clk), .reset_btn(reset_btn), .uart_rx_i(uart_rx_i),
        .uart_tx_o(baseline_tx), .led0_n(baseline_led0), .led1_n(baseline_led1));
    candidate_trade_top #(.TX_GAP_CYCLES(GAP_CYCLES)) candidate (
        .sys_clk(sys_clk), .reset_btn(reset_btn), .uart_rx_i(uart_rx_i),
        .uart_tx_o(candidate_tx), .led0_n(candidate_led0), .led1_n(candidate_led1));

    // Check every stable clock phase, including start, data, stop and byte gaps.
    always @(negedge sys_clk) begin
        if (baseline_tx !== candidate_tx)
            $fatal(1,"TX waveform mismatch packet=%0d time=%0t baseline=%b candidate=%b",
                   count,$time,baseline_tx,candidate_tx);
        compared_clocks=compared_clocks+1;
    end

    task send_byte(input [7:0] value);
        integer b;
        begin
            uart_rx_i=0; #(host_bit_ns);
            for(b=0;b<8;b=b+1) begin uart_rx_i=value[b]; #(host_bit_ns); end
            uart_rx_i=1; #(host_bit_ns);
        end
    endtask

    task read_byte(output [7:0] value);
        integer b;
        begin
            @(negedge baseline_tx);
            #(TX_BIT_NS/2.0);
            if (baseline_tx !== 0) $fatal(1,"TX start-bit error");
            for(b=0;b<8;b=b+1) begin #(TX_BIT_NS); value[b]=baseline_tx; end
            #(TX_BIT_NS);
            if (baseline_tx !== 1) $fatal(1,"TX stop-bit error");
            #(TX_BIT_NS/2.0);
        end
    endtask

    initial forever begin
        read_byte(byte_received);
        received={received[55:0],byte_received};
        rx_bytes=rx_bytes+1;
        if(rx_bytes % 8 == 0) replies=replies+1;
    end

    initial begin
        if (!$value$plusargs("VECTORS=%s",vectors)) $fatal(1,"Missing VECTORS");
        status=$value$plusargs("BIT_NS=%f",host_bit_ns);
        fd=$fopen(vectors,"r"); if(!fd) $fatal(1,"Cannot open vectors");
        #30000;
        uart_rx_i=0; #(host_bit_ns/5); uart_rx_i=1; #(host_bit_ns*12);
        if(rx_bytes != 0) $fatal(1,"Unsolicited output after glitch");
        send_byte(8'hff);
        uart_rx_i=0; #(host_bit_ns*10); uart_rx_i=1; #(host_bit_ns*12);
        if(rx_bytes != 0) $fatal(1,"Unsolicited output after framing error");
        while(!$feof(fd)) begin
            status=$fscanf(fd,"%h %h\n",request,expected);
            if(status == 2) begin
                for(i=7;i>=0;i=i-1) begin
                    if(i==0 && rx_bytes != count*8) $fatal(1,"Premature response");
                    send_byte(request[i*8+:8]);
                    if(i==3 && count % 17 == 0) #(host_bit_ns*4);
                end
                // Malformed host traffic during an outgoing response must not
                // corrupt the candidate's shared receive/transmit byte counter.
                if (count % 19 == 0) begin
                    uart_rx_i=0; #(host_bit_ns*10);
                    uart_rx_i=1; #(host_bit_ns*12);
                    injected_errors=injected_errors+1;
                end
                fork
                    begin wait(replies == count+1); end
                    begin #20000000; $fatal(1,"UART timeout at packet %0d",count); end
                join_any
                disable fork;
                if(received !== expected)
                    $fatal(1,"UART packet %0d req=%h expected=%h got=%h",count,request,expected,received);
                count=count+1;
                if(count % 19 == 0) #(host_bit_ns*20);
            end else if (status != -1) $fatal(1,"Malformed vector");
        end
        #(host_bit_ns*30);
        if(rx_bytes != count*8) $fatal(1,"Extra response bytes");
        $fclose(fd);
        $display("PASS UART equivalence: %0d packets, %0d clocks, %0d active-TX errors, gap %0d clocks",count,compared_clocks,injected_errors,GAP_CYCLES);
        $finish;
    end
endmodule
