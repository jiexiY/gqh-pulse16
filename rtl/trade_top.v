`timescale 1ns/1ps
module trade_top #(
    parameter integer CLKS_PER_BIT = 234,
    // Initial conservative bridge setting: 0.5 ms idle between response bytes.
    // Tune only after measuring the physical BL616 bridge with official tests.
    parameter integer TX_GAP_CYCLES = 13500
) (
    input wire sys_clk, input wire reset_btn, input wire uart_rx_i,
    output wire uart_tx_o, output wire led0_n, output wire led1_n
);
    reg [7:0] power_on = 0;
    reg [1:0] reset_sync = 0;
    always @(posedge sys_clk) begin
        reset_sync <= {reset_sync[0], reset_btn};
        if (!(&power_on)) power_on <= power_on + 1'b1;
    end
    wire rst = !(&power_on) || reset_sync[1];
    wire [7:0] rx_data;
    wire rx_valid, rx_error;
    uart_rx #(.CLKS_PER_BIT(CLKS_PER_BIT)) receiver (
        .clk(sys_clk), .rst(rst), .rx(uart_rx_i),
        .data(rx_data), .valid(rx_valid), .framing_error(rx_error));

    reg [63:0] packet;
    reg [2:0] rx_count;
    reg request_valid;
    wire engine_ready, response_valid;
    wire [63:0] response;
    signal_engine engine (.clk(sys_clk), .rst(rst), .request_valid(request_valid),
        .request(packet), .ready(engine_ready),
        .response_valid(response_valid), .response(response));

    localparam TX_IDLE=0, TX_START=1, TX_WAIT=2, TX_GAP=3;
    localparam integer GW = TX_GAP_CYCLES < 2 ? 1 : $clog2(TX_GAP_CYCLES);
    reg [1:0] tx_state;
    reg [63:0] tx_packet;
    reg [2:0] tx_count;
    reg [GW-1:0] gap_count;
    wire tx_busy, tx_done;
    uart_tx #(.CLKS_PER_BIT(CLKS_PER_BIT)) transmitter (
        .clk(sys_clk), .rst(rst), .data(tx_packet[63:56]),
        .start(tx_state == TX_START), .tx(uart_tx_o), .busy(tx_busy), .done(tx_done));
    assign led0_n = (tx_state == TX_IDLE) && engine_ready;
    assign led1_n = 1'b1;

    always @(posedge sys_clk) begin
        if (rst) begin
            packet <= 0; rx_count <= 0; request_valid <= 0;
            tx_state <= TX_IDLE; tx_packet <= 0; tx_count <= 0; gap_count <= 0;
        end else begin
            request_valid <= 0;
            if (rx_error) rx_count <= 0;
            else if (rx_valid && engine_ready && tx_state == TX_IDLE) begin
                packet <= {packet[55:0], rx_data};
                rx_count <= rx_count + 1'b1;
                if (rx_count == 7) request_valid <= 1;
            end
            case (tx_state)
                TX_IDLE: if (response_valid) begin
                    tx_packet <= response; tx_count <= 0; tx_state <= TX_START;
                end
                TX_START: tx_state <= TX_WAIT;
                TX_WAIT: if (tx_done) begin
                    if (tx_count == 7) tx_state <= TX_IDLE;
                    else begin
                        tx_count <= tx_count + 1'b1;
                        tx_packet <= {tx_packet[55:0], 8'd0};
                        gap_count <= TX_GAP_CYCLES > 0 ? TX_GAP_CYCLES - 1 : 0;
                        tx_state <= TX_GAP;
                    end
                end
                TX_GAP: if (gap_count == 0) tx_state <= TX_START;
                    else gap_count <= gap_count - 1'b1;
                default: tx_state <= TX_IDLE;
            endcase
        end
    end
endmodule
