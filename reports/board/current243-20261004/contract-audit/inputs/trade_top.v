`timescale 1ns/1ps
module trade_top #(
    parameter integer CLKS_PER_BIT = 234,
    // Isolated minimum-gap experiment; physical bridge reliability is unverified.
    // Configured zero still gives three idle clocks through the existing FSM.
    parameter integer TX_GAP_CYCLES = 0
) (
    input wire sys_clk, input wire reset_btn, input wire uart_rx_i,
    output wire uart_tx_o, output wire led0_n, output wire led1_n
);
    reg [7:0] power_on = 0;
    reg [1:0] reset_sync = 0;
    // Zero escape followed by a maximal 8-bit LFSR reaches 0x80 after
    // exactly 255 clocks, matching the original saturating-counter reset.
    wire startup_done = power_on == 8'h80;
    always @(posedge sys_clk) begin
        reset_sync <= {reset_sync[0], reset_btn};
        if (!startup_done)
            power_on <= {power_on[6:0], power_on[7] ^ power_on[5] ^
                         power_on[4] ^ power_on[3] ^ (power_on == 0)};
    end
    wire rst = !startup_done || reset_sync[1];
    wire [7:0] rx_data;
    wire rx_valid, rx_error;
    uart_rx #(.CLKS_PER_BIT(CLKS_PER_BIT)) receiver (
        .clk(sys_clk), .rst(rst), .rx(uart_rx_i),
        .data(rx_data), .valid(rx_valid), .framing_error(rx_error));

    reg [15:0] request_index;
    // Only price bytes advance this bank; each complete request replaces all
    // four bytes before request_valid can reach the engine.
    reg [31:0] prices;
    wire [15:0] price1 = prices[31:16];
    wire [15:0] price2 = prices[15:0];
    reg item1_b, item2_b;
    // Valid protocol items are 0x11 and 0x22: preserve their slot order with
    // one selector bit each rather than storing redundant identifier bits.
    wire [63:0] packet = {request_index, item1_b ? 8'h22 : 8'h11, price1,
                         item2_b ? 8'h22 : 8'h11, price2};
    reg [2:0] rx_count;
    reg request_valid;
    wire engine_ready, response_valid;
    wire [63:0] response;
    signal_engine engine (.clk(sys_clk), .rst(rst), .request_valid(request_valid),
        .request(packet), .ready(engine_ready),
        .response_valid(response_valid), .response(response));

    localparam TX_IDLE=0, TX_START=1, TX_BITS=2, TX_GAP=3;
    localparam integer TIMER_MAX = TX_GAP_CYCLES > CLKS_PER_BIT ? TX_GAP_CYCLES : CLKS_PER_BIT;
    localparam integer TW = TIMER_MAX < 2 ? 1 : $clog2(TIMER_MAX + 1);
    reg [1:0] tx_state;
    // Engine response remains stable until the next accepted request, which
    // stop-and-wait reception prevents until this response finishes sending.
    wire [3:0] tx_actions = {response[33:32], response[17:16]};
    reg [7:0] tx_data;
    // Baud timing and inter-byte idle never overlap, so share one timer.
    reg [TW-1:0] tx_timer;
    reg [9:0] tx_frame;
    // The leading stop bit is a shift sentinel: reaching 1 means the stop
    // bit has just occupied the output for one full baud period.
    assign uart_tx_o = tx_frame[0];
    // The request remains unchanged until the response finishes. Reuse its
    // index/item fields instead of copying and shifting an entire response.
    // The action fields can likewise reuse the stable engine response.
    always @* begin
        case (rx_count)
            0: tx_data = packet[63:56];
            1: tx_data = packet[55:48];
            2: tx_data = packet[47:40];
            3: tx_data = {6'd0, tx_actions[3:2]};
            4: tx_data = packet[23:16];
            5: tx_data = {6'd0, tx_actions[1:0]};
            default: tx_data = 0;
        endcase
    end
    assign led0_n = (tx_state == TX_IDLE) && engine_ready;
    assign led1_n = 1'b1;

    always @(posedge sys_clk) begin
        if (rst) begin
            request_index <= 0; prices <= 0;
            item1_b <= 0; item2_b <= 0; rx_count <= 0; request_valid <= 0;
            tx_state <= TX_IDLE; tx_timer <= 0;
            tx_frame <= 10'h3ff;
        end else begin
            request_valid <= 0;
            if (rx_error && tx_state == TX_IDLE) rx_count <= 0;
            else if (rx_valid && engine_ready && tx_state == TX_IDLE && !response_valid) begin
                case (rx_count)
                    0,1: request_index <= {request_index[7:0], rx_data};
                    2: item1_b <= rx_data[5];
                    3,4,6,7: prices <= {prices[23:0], rx_data};
                    5: item2_b <= rx_data[5];
                endcase
                rx_count <= rx_count + 1'b1;
                if (rx_count == 7) request_valid <= 1;
            end
            case (tx_state)
                TX_IDLE: if (response_valid) begin
                    rx_count <= 0; tx_state <= TX_START;
                end
                TX_START: begin
                    tx_frame <= {1'b1, tx_data, 1'b0};
                    tx_timer <= CLKS_PER_BIT - 1;
                    tx_state <= TX_BITS;
                end
                TX_BITS: if (tx_timer != 0) tx_timer <= tx_timer - 1'b1;
                    else if (tx_frame == 10'd1) begin
                        if (rx_count == 7) begin
                            rx_count <= 0;
                            tx_state <= TX_IDLE;
                        end
                        else begin
                            rx_count <= rx_count + 1'b1;
                            // Match the previous UART-done + gap-state latency.
                            tx_timer <= TX_GAP_CYCLES > 0 ? TX_GAP_CYCLES : 1;
                            tx_state <= TX_GAP;
                        end
                    end else begin
                        tx_frame <= {1'b0, tx_frame[9:1]};
                        tx_timer <= CLKS_PER_BIT - 1;
                    end
                TX_GAP: if (tx_timer == 0) tx_state <= TX_START;
                    else tx_timer <= tx_timer - 1'b1;
                default: tx_state <= TX_IDLE;
            endcase
        end
    end
endmodule
