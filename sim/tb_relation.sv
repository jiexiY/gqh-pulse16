`timescale 1ns/1ps
module tb_relation;
    reg clk=0, rst=1, request_valid=0;
    reg [63:0] request=0;
    wire ready, response_valid;
    wire [63:0] response;
    reg [63:0] expected;
    reg [27:0] expected_a, expected_b;
    reg [27:0] prior_a=0, prior_b=0;
    reg [27:0] expected_commit, expected_prior;
    reg checked_item;
    integer fd, count=0, cycles, status, commits=0, reads=0;
    reg [1023:0] vectors;
    always #5 clk=~clk;
    signal_engine dut (.*);

    // Check metadata against the independent reference after each item commit,
    // including every warm-up packet, while avoiding nonblocking-assignment races.
    always @(posedge clk) begin
        if (!rst && dut.state == dut.COMMIT) begin
            checked_item = dut.selected_b;
            expected_commit = checked_item ? expected_b : expected_a;
            #1;
            if (dut.metadata[checked_item] !== expected_commit)
                $fatal(1,"Metadata invariant failed packet=%0d item=%0d expected=%h got=%h",
                       count, checked_item, expected_commit, dut.metadata[checked_item]);
            commits=commits+1;
        end
        else if (!rst && dut.state == dut.READ && request[63:48] != 0) begin
            checked_item = dut.selected_b;
            expected_prior = checked_item ? prior_b : prior_a;
            #1;
            if ({dut.previous_le,dut.previous_ge} !== expected_prior[7:6])
                $fatal(1,"Loaded relation failed packet=%0d item=%0d expected=%b got=%b",
                       count, checked_item, expected_prior[7:6],
                       {dut.previous_le,dut.previous_ge});
            reads=reads+1;
        end
    end

    initial begin
        if (!$value$plusargs("VECTORS=%s", vectors)) $fatal(1,"Missing VECTORS");
        fd=$fopen(vectors,"r"); if (!fd) $fatal(1,"Cannot open vectors");
        repeat(3) @(negedge clk); rst=0;
        while (!$feof(fd)) begin
            @(negedge clk);
            status=$fscanf(fd,"%h %h %h %h\n",request,expected,expected_a,expected_b);
            if (status == 4) begin
                if (!ready) $fatal(1,"Engine not ready");
                request_valid=1;
                @(negedge clk); request_valid=0; cycles=0;
                while (!response_valid && cycles < 32) begin
                    @(negedge clk); cycles=cycles+1;
                end
                if (!response_valid) $fatal(1,"Engine timeout at vector %0d",count);
                if (response !== expected)
                    $fatal(1,"Response failed packet=%0d request=%h expected=%h got=%h",
                           count,request,expected,response);
                prior_a=expected_a; prior_b=expected_b; count=count+1;
                @(negedge clk);
                if (response_valid) $fatal(1,"Duplicate response-valid pulse");
            end else if (status != -1) $fatal(1,"Malformed vector");
        end
        $fclose(fd);
        if (commits != count*2) $fatal(1,"Missing metadata checks");
        $display("PASS relation: %0d packets, %0d metadata invariants, %0d loaded relations",count,commits,reads);
        $finish;
    end
endmodule
