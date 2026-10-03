`timescale 1ns/1ps
module uart_tx #(parameter integer CLKS_PER_BIT = 234) (
    input wire clk, input wire rst,
    input wire [7:0] data, input wire start,
    output reg tx, output reg busy, output reg done
);
    localparam integer CW = $clog2(CLKS_PER_BIT);
    reg [CW-1:0] count;
    reg [3:0] bit_index;
    reg [9:0] frame;
    always @(posedge clk) begin
        if (rst) begin
            tx <= 1; busy <= 0; done <= 0; count <= 0;
            bit_index <= 0; frame <= 10'h3ff;
        end else begin
            done <= 0;
            if (!busy) begin
                tx <= 1;
                if (start) begin
                    frame <= {1'b1, data, 1'b0}; tx <= 0;
                    count <= CLKS_PER_BIT - 1; bit_index <= 0; busy <= 1;
                end
            end else if (count != 0) count <= count - 1'b1;
            else if (bit_index == 9) begin
                tx <= 1; busy <= 0; done <= 1;
            end else begin
                frame <= {1'b1, frame[9:1]}; tx <= frame[1];
                bit_index <= bit_index + 1'b1; count <= CLKS_PER_BIT - 1;
            end
        end
    end
endmodule

