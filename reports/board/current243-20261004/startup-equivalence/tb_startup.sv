`timescale 1ns/1ps
module tb_startup;
    reg sys_clk=0, reset_btn=0, uart_rx_i=1;
    wire btx, bled0, bled1, ctx, cled0, cled1;
    reg [7:0] counter_model=0, lfsr_model=0;
    reg [1:0] sync_model=0;
    integer cycle;
    baseline_trade_top baseline(.sys_clk(sys_clk),.reset_btn(reset_btn),.uart_rx_i(uart_rx_i),
        .uart_tx_o(btx),.led0_n(bled0),.led1_n(bled1));
    candidate_trade_top candidate(.sys_clk(sys_clk),.reset_btn(reset_btn),.uart_rx_i(uart_rx_i),
        .uart_tx_o(ctx),.led0_n(cled0),.led1_n(cled1));
    always #18.519 sys_clk=~sys_clk;
    initial begin
        #1;
        if (baseline.rst !== 1 || candidate.rst !== 1) $fatal(1,"Initial reset not asserted");
        for(cycle=1;cycle<=1024;cycle=cycle+1) begin
            @(posedge sys_clk);
            if(counter_model != 255) counter_model=counter_model+1'b1;
            if(lfsr_model != 128)
                lfsr_model={lfsr_model[6:0],lfsr_model[7]^lfsr_model[5]^lfsr_model[4]^lfsr_model[3]^(lfsr_model==0)};
            sync_model={sync_model[0],reset_btn};
            #1;
            if(baseline.power_on !== counter_model || candidate.power_on !== lfsr_model)
                $fatal(1,"Actual startup state differs from exhaustive model at clock%0d",cycle);
            if(baseline.reset_sync !== sync_model || candidate.reset_sync !== sync_model)
                $fatal(1,"Button synchronization differs at clock%0d",cycle);
            if(baseline.rst !== candidate.rst || candidate.rst !== ((counter_model!=255)||sync_model[1]))
                $fatal(1,"Reset timeline differs at clock%0d",cycle);
            if(btx !== ctx || bled0 !== cled0 || bled1 !== cled1)
                $fatal(1,"Idle outputs differ across reset at clock%0d",cycle);
            @(negedge sys_clk);
            reset_btn=((cycle>=247 && cycle<263) || ((cycle%17)<5));
        end
        $display("PASS startup RTL: 1024 clocks, exact255-clock completion, overlapping and repeated button resets");
        $finish;
    end
endmodule
