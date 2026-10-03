`timescale 1ns/1ps
module tb_engine;
    reg clk=0, rst=1, request_valid=0;
    reg [63:0] request=0;
    wire ready, response_valid;
    wire [63:0] response;
    reg [63:0] expected;
    integer fd, count=0, cycles, status;
    reg [1023:0] vectors;
    always #5 clk=~clk;
    signal_engine dut (.*);
    initial begin
        if (!$value$plusargs("VECTORS=%s", vectors)) $fatal(1, "Missing VECTORS");
        fd=$fopen(vectors,"r"); if (!fd) $fatal(1,"Cannot open vectors");
        repeat(3) @(negedge clk); rst=0;
        while (!$feof(fd)) begin
            @(negedge clk);
            status=$fscanf(fd,"%h %h\n",request,expected);
            if (status == 2) begin
                if (!ready) $fatal(1,"Engine not ready");
                request_valid=1;
                @(negedge clk); request_valid=0; cycles=0;
                while (!response_valid && cycles < 32) begin
                    @(negedge clk); cycles=cycles+1;
                end
                if (!response_valid) $fatal(1,"Engine timeout at vector %0d",count);
                if (response !== expected)
                    $fatal(1,"Vector %0d request=%h expected=%h got=%h",count,request,expected,response);
                count=count+1;
                @(negedge clk);
                if (response_valid) $fatal(1,"Duplicate response-valid pulse");
            end
        end
        $fclose(fd);
        $display("PASS engine: %0d complete packet responses",count);
        $finish;
    end
endmodule

