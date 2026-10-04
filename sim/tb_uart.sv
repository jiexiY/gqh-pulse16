`timescale 1ns/1ps
module tb_uart #(parameter integer GAP_CYCLES=0);
    reg sys_clk=0, reset_btn=0, uart_rx_i=1;
    wire uart_tx_o, led0_n, led1_n;
    reg [63:0] request, expected, received=0;
    reg [7:0] byte_received;
    integer fd, count=0, replies=0, rx_bytes=0, status, i;
    integer max_packets=0;
    reg [1023:0] vectors;
    real host_bit_ns=8680.555556;
    localparam real TX_BIT_NS=234.0*37.038;
    always #18.519 sys_clk=~sys_clk;
`ifdef POST_PNR
    // The generated netlist has fixed parameters from the production build.
    trade_top dut (.*);
`else
    trade_top #(.TX_GAP_CYCLES(GAP_CYCLES)) dut (.*);
`endif

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
            @(negedge uart_tx_o);
            #(TX_BIT_NS/2.0);
            if (uart_tx_o !== 0) $fatal(1,"TX start-bit error");
            for(b=0;b<8;b=b+1) begin #(TX_BIT_NS); value[b]=uart_tx_o; end
            #(TX_BIT_NS);
            if (uart_tx_o !== 1) $fatal(1,"TX stop-bit error");
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
        status=$value$plusargs("MAX_PACKETS=%d",max_packets);
        fd=$fopen(vectors,"r"); if(!fd) $fatal(1,"Cannot open vectors");
        #30000;
        // Reject a short false start, then verify no unsolicited output.
        uart_rx_i=0; #(host_bit_ns/5); uart_rx_i=1; #(host_bit_ns*12);
        if(rx_bytes != 0) $fatal(1,"Unsolicited output after glitch");
        // A malformed stop bit must discard the partial packet.
        send_byte(8'hff);
        uart_rx_i=0; #(host_bit_ns*10); uart_rx_i=1; #(host_bit_ns*12);
        if(rx_bytes != 0) $fatal(1,"Unsolicited output after framing error");
        while(!$feof(fd) && (max_packets == 0 || count < max_packets)) begin
            status=$fscanf(fd,"%h %h\n",request,expected);
            if(status == 2) begin
                for(i=7;i>=0;i=i-1) begin
                    if(i==0 && rx_bytes != count*8) $fatal(1,"Premature response");
                    send_byte(request[i*8+:8]);
                    // Exercise host scheduling delays inside a request.
                    if(i==3 && count % 17 == 0) #(host_bit_ns*4);
                end
                fork
                    begin wait(replies == count+1); end
                    begin #20000000; $fatal(1,"UART timeout at packet %0d",count); end
                join_any
                disable fork;
                if(received !== expected)
                    $fatal(1,"UART packet %0d req=%h expected=%h got=%h",count,request,expected,received);
                count=count+1;
                // Leave idle time on a few transactions, immediately start others.
                if(count % 19 == 0) #(host_bit_ns*20);
            end
        end
        #(host_bit_ns*30);
        if(rx_bytes != count*8) $fatal(1,"Extra response bytes");
        $fclose(fd);
        $display("PASS UART: %0d packets, bit period %0.3f ns, gap %0d clocks",count,host_bit_ns,GAP_CYCLES);
        $finish;
    end
endmodule

