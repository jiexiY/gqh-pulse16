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
    localparam IDLE=0, LOAD=1, META=2, READ=3, SUM=4, ADD=5, COMMIT=6;
    reg [2:0] state;
    reg [15:0] second_price;
    reg second_b;
    reg warmup;
    reg restart;
    reg slot;
    reg selected_b;
    reg [15:0] price;
    // Per-item metadata also lives in unscored synchronous BSRAM.
    // Index zero masks stale contents until both item records are replaced.
    // Store the last price's inclusive relation to its own completed average.
    // Equality sets both flags. This is exactly the relation needed next time,
    // so retaining the entire previous price and recomparing it is unnecessary.
    reg [27:0] metadata [0:1] /* synthesis syn_ramstyle = "block_ram" */;
    reg [27:0] item_meta;
    // Gowin SUG550 section 5.15: map the history to unscored BSRAM.
    reg [15:0] history [0:31] /* synthesis syn_ramstyle = "block_ram" */;
    reg [15:0] oldest;
    reg [19:0] new_sum;
    reg previous_le, previous_ge;
    reg [1:0] last_action;
    wire [19:0] selected_sum = item_meta[27:8];
    wire [3:0] pointer = restart ? 4'd0 : item_meta[3:0];
    wire [4:0] address = {selected_b, pointer};
    wire [16:0] difference = {1'b0, price} - {1'b0, new_sum[19:4]};
    wire compare_equal = difference[15:0] == 0;
    wire current_le = difference[16] || compare_equal;
    wire current_ge = !difference[16];
    wire subtract_oldest = state == SUM;
    wire [19:0] operand = {4'd0, subtract_oldest ? oldest : price};
    wire [19:0] sum_result = new_sum + (operand ^ {20{subtract_oldest}}) + subtract_oldest;
    wire [1:0] next_action = warmup ? 2'd0 :
        (previous_le && !difference[16] && !compare_equal) ? 2'd2 :
        (previous_ge && difference[16]) ? 2'd1 :
        last_action;
    assign ready = state == IDLE;

    // Synchronous RAM read and write; never consume uninitialized data in warm-up.
    always @(posedge clk) begin
        if (state == META) item_meta <= metadata[selected_b];
        if (state == READ) oldest <= history[address];
        if (state == COMMIT) begin
            history[address] <= price;
            // Update during warm-up too: index 15 establishes the relation
            // used by the first scored packet (index 16).
            metadata[selected_b] <= {new_sum, current_le, current_ge,
                                    next_action, (pointer + 4'd1)};
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            state <= IDLE; second_price <= 0; second_b <= 0; warmup <= 0; restart <= 0;
            slot <= 0; selected_b <= 0; price <= 0;
            new_sum <= 0; previous_le <= 0; previous_ge <= 0; last_action <= 0;
            response <= 0; response_valid <= 0;
        end else begin
            response_valid <= 0;
            case (state)
                IDLE: if (request_valid) begin
                    second_price <= request[15:0]; second_b <= request[23:16] == 8'h22;
                    price <= request[39:24]; selected_b <= request[47:40] == 8'h22;
                    warmup <= request[63:48] < 16; restart <= request[63:48] == 0;
                    slot <= 0; state <= META;
                    response <= {request[63:48], request[47:40], 8'd0,
                                 request[23:16], 8'd0, 16'd0};
                end
                LOAD: begin
                    selected_b <= second_b;
                    price <= second_price;
                    state <= META;
                end
                META: state <= READ;
                READ: begin
                    new_sum <= restart ? 20'd0 : selected_sum;
                    previous_le <= item_meta[7];
                    previous_ge <= item_meta[6];
                    last_action <= item_meta[5:4];
                    state <= warmup ? ADD : SUM;
                end
                SUM: begin
                    new_sum <= sum_result;
                    state <= ADD;
                end
                ADD: begin
                    new_sum <= sum_result;
                    state <= COMMIT;
                end
                COMMIT: begin
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

