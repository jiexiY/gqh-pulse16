`timescale 1ns/1ps
// 8N1 receiver. Synchronize the external pin before sampling at bit centres.
module uart_rx #(parameter integer CLKS_PER_BIT = 234) (
    input wire clk, input wire rst, input wire rx,
    output wire [7:0] data, output reg valid,
    output reg framing_error
);
    localparam integer CW = $clog2(CLKS_PER_BIT);
    localparam IDLE=0, START=1, DATA=2, STOP=3, WAIT_HIGH=4;
    reg [1:0] sync_rx = 2'b11;
    reg [2:0] state;
    reg [CW-1:0] count;
    reg [2:0] bit_index;
    reg [7:0] shift;
    // Consumers sample only on valid. The complete shift value already stays
    // stable through STOP and IDLE, so a second eight-bit output latch is not
    // required for the packet receiver's valid-qualified interface.
    assign data = shift;
    always @(posedge clk) begin
        if (rst) sync_rx <= 2'b11;
        else sync_rx <= {sync_rx[0], rx};
    end
    always @(posedge clk) begin
        if (rst) begin
            state <= IDLE; count <= 0; bit_index <= 0;
            shift <= 0; valid <= 0; framing_error <= 0;
        end else begin
            valid <= 0;
            framing_error <= 0;
            case (state)
                IDLE: if (!sync_rx[1]) begin
                    count <= (CLKS_PER_BIT / 2) - 1; state <= START;
                end
                START: if (count != 0) count <= count - 1'b1;
                    else if (!sync_rx[1]) begin
                        count <= CLKS_PER_BIT - 1; bit_index <= 0; state <= DATA;
                    end else state <= IDLE;
                DATA: if (count != 0) count <= count - 1'b1;
                    else begin
                        shift <= {sync_rx[1], shift[7:1]}; count <= CLKS_PER_BIT - 1;
                        if (bit_index == 7) state <= STOP;
                        else bit_index <= bit_index + 1'b1;
                    end
                STOP: if (count != 0) count <= count - 1'b1;
                    else begin
                        state <= IDLE;
                        if (sync_rx[1]) begin valid <= 1; end
                        else begin framing_error <= 1; state <= WAIT_HIGH; end
                    end
                WAIT_HIGH: if (sync_rx[1]) state <= IDLE;
                default: state <= IDLE;
            endcase
        end
    end
endmodule

