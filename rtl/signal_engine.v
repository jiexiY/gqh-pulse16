`timescale 1ns/1ps
// One shared arithmetic datapath services two independent item histories.
// Window RAM has no reset: index 0 invalidates it, and warm-up overwrites every
// entry before any old entry is used. This permits synthesis to infer memory.
module signal_engine (
    input wire clk, input wire rst,
    input wire request_valid, input wire [63:0] request,
    output wire ready,
    output reg response_valid, output reg [63:0] response
);
    localparam IDLE=0, LOAD=1, READ=2, SUM=3, COMMIT=4;
    reg [2:0] state;
    reg [63:0] packet;
    reg slot;
    reg selected_b;
    reg [15:0] price;
    reg [19:0] sum_a, sum_b;
    reg [15:0] previous_a, previous_b;
    reg [1:0] action_a, action_b;
    reg [3:0] pointer_a, pointer_b;
    // Gowin SUG550 section 5.15: map the history to unscored BSRAM.
    reg [15:0] history [0:31] /* synthesis syn_ramstyle = "block_ram" */;
    reg [15:0] oldest;
    reg [19:0] old_sum, new_sum;
    reg [15:0] previous;
    reg [1:0] last_action;
    wire warmup = packet[63:48] < 16;
    wire [4:0] address = {selected_b, selected_b ? pointer_b : pointer_a};
    wire [1:0] next_action = warmup ? 2'd0 :
        ((previous <= old_sum[19:4]) && (price > new_sum[19:4])) ? 2'd2 :
        ((previous >= old_sum[19:4]) && (price < new_sum[19:4])) ? 2'd1 :
        last_action;
    assign ready = state == IDLE;

    // Synchronous RAM read and write; never consume uninitialized data in warm-up.
    always @(posedge clk) begin
        if (state == READ) oldest <= history[address];
        if (state == COMMIT) history[address] <= price;
    end

    always @(posedge clk) begin
        if (rst) begin
            state <= IDLE; packet <= 0; slot <= 0; selected_b <= 0; price <= 0;
            sum_a <= 0; sum_b <= 0; previous_a <= 0; previous_b <= 0;
            action_a <= 0; action_b <= 0; pointer_a <= 0; pointer_b <= 0;
            old_sum <= 0; new_sum <= 0; previous <= 0; last_action <= 0;
            response <= 0; response_valid <= 0;
        end else begin
            response_valid <= 0;
            case (state)
                IDLE: if (request_valid) begin
                    packet <= request; slot <= 0; state <= LOAD;
                    response <= {request[63:48], request[47:40], 8'd0,
                                 request[23:16], 8'd0, 16'd0};
                    if (request[63:48] == 0) begin
                        sum_a <= 0; sum_b <= 0; previous_a <= 0; previous_b <= 0;
                        action_a <= 0; action_b <= 0; pointer_a <= 0; pointer_b <= 0;
                    end
                end
                LOAD: begin
                    selected_b <= (slot ? packet[23:16] : packet[47:40]) == 8'h22;
                    price <= slot ? packet[15:0] : packet[39:24];
                    state <= READ;
                end
                READ: begin
                    old_sum <= selected_b ? sum_b : sum_a;
                    previous <= selected_b ? previous_b : previous_a;
                    last_action <= selected_b ? action_b : action_a;
                    state <= SUM;
                end
                SUM: begin
                    new_sum <= old_sum - (warmup ? 20'd0 : {4'd0, oldest})
                               + {4'd0, price};
                    state <= COMMIT;
                end
                COMMIT: begin
                    if (selected_b) begin
                        sum_b <= new_sum; previous_b <= price; action_b <= next_action;
                        pointer_b <= pointer_b + 1'b1;
                    end else begin
                        sum_a <= new_sum; previous_a <= price; action_a <= next_action;
                        pointer_a <= pointer_a + 1'b1;
                    end
                    if (!slot) begin
                        response[33:32] <= next_action; slot <= 1; state <= LOAD;
                    end else begin
                        response[17:16] <= next_action;
                        response_valid <= 1; state <= IDLE;
                    end
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule

