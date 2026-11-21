`default_nettype none

// Async-assert, sync-release reset
module reset_sync (
    input  wire clk,
    input  wire arst_n,
    output wire srst_n
);
  reg [1:0] q;
  always @(posedge clk or negedge arst_n)
    if (!arst_n) q <= 2'b00;
    else         q <= {q[0], 1'b1};
  assign srst_n = q[1];
endmodule

// 2-flop synchronizer
module sync2 #(parameter W = 1) (
    input  wire         clk,
    input  wire         rst_n,
    input  wire [W-1:0] d,
    output reg  [W-1:0] q
);
  reg [W-1:0] m;
  always @(posedge clk or negedge rst_n)
    if (!rst_n) {q, m} <= {(2*W){1'b0}};
    else        {q, m} <= {m, d};
endmodule

// Gray-pointer async FIFO (first-word-fall-through read), depth = 2**ASIZE
module async_fifo #(
    parameter DSIZE = 8,
    parameter ASIZE = 3   // must be >= 2
) (
    input  wire             wclk,
    input  wire             wrst_n,
    input  wire             winc,
    input  wire [DSIZE-1:0] wdata,
    output reg              wfull,
    input  wire             rclk,
    input  wire             rrst_n,
    input  wire             rinc,
    output wire [DSIZE-1:0] rdata,
    output reg              rempty
);
  localparam DEPTH = 1 << ASIZE;

  reg [DSIZE-1:0] mem [0:DEPTH-1];
  reg [ASIZE:0]   wbin, wptr, rbin, rptr;   // extra MSB for full/empty
  wire [ASIZE:0]  wq2_rptr, rq2_wptr;

  sync2 #(ASIZE+1) u_sync_r2w (.clk(wclk), .rst_n(wrst_n), .d(rptr), .q(wq2_rptr));
  sync2 #(ASIZE+1) u_sync_w2r (.clk(rclk), .rst_n(rrst_n), .d(wptr), .q(rq2_wptr));

  // ---- write domain ----
  wire [ASIZE:0] wbin_next  = wbin + {{ASIZE{1'b0}}, (winc & ~wfull)};
  wire [ASIZE:0] wgray_next = (wbin_next >> 1) ^ wbin_next;
  wire wfull_val = (wgray_next == {~wq2_rptr[ASIZE:ASIZE-1], wq2_rptr[ASIZE-2:0]});

  always @(posedge wclk or negedge wrst_n)
    if (!wrst_n) begin
      wbin <= 0; wptr <= 0; wfull <= 1'b0;
    end else begin
      wbin <= wbin_next; wptr <= wgray_next; wfull <= wfull_val;
    end

  always @(posedge wclk)
    if (winc && !wfull) mem[wbin[ASIZE-1:0]] <= wdata;

  // ---- read domain ----
  wire [ASIZE:0] rbin_next  = rbin + {{ASIZE{1'b0}}, (rinc & ~rempty)};
  wire [ASIZE:0] rgray_next = (rbin_next >> 1) ^ rbin_next;
  wire rempty_val = (rgray_next == rq2_wptr);

  always @(posedge rclk or negedge rrst_n)
    if (!rrst_n) begin
      rbin <= 0; rptr <= 0; rempty <= 1'b1;
    end else begin
      rbin <= rbin_next; rptr <= rgray_next; rempty <= rempty_val;
    end

  assign rdata = mem[rbin[ASIZE-1:0]];
endmodule

// UART transmitter: IDLE -> START -> DATA(8, LSB first) -> STOP, 8N1
module uart_tx (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [11:0] div,        // clk cycles per bit
    input  wire        fifo_empty,
    input  wire [7:0]  fifo_data,
    output wire        fifo_pop,
    output reg         txd,
    output wire        busy
);
  localparam [1:0] S_IDLE = 2'd0, S_START = 2'd1, S_DATA = 2'd2, S_STOP = 2'd3;

  reg [1:0]  state;
  reg [11:0] cnt;
  reg [2:0]  idx;
  reg [7:0]  shreg;

  wire tick = (cnt >= div - 12'd1);

  assign fifo_pop = (state == S_IDLE) && !fifo_empty;
  assign busy     = (state != S_IDLE);

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      state <= S_IDLE; cnt <= 12'd0; idx <= 3'd0; shreg <= 8'd0; txd <= 1'b1;
    end else begin
      case (state)
        S_IDLE: begin
          txd <= 1'b1; cnt <= 12'd0; idx <= 3'd0;
          if (!fifo_empty) begin
            shreg <= fifo_data;
            txd   <= 1'b0;            // start bit
            state <= S_START;
          end
        end
        S_START: begin
          if (tick) begin
            cnt <= 12'd0; txd <= shreg[0]; state <= S_DATA;
          end else cnt <= cnt + 12'd1;
        end
        S_DATA: begin
          if (tick) begin
            cnt <= 12'd0;
            if (idx == 3'd7) begin
              txd <= 1'b1; state <= S_STOP;
            end else begin
              idx <= idx + 3'd1; shreg <= {1'b0, shreg[7:1]}; txd <= shreg[1];
            end
          end else cnt <= cnt + 12'd1;
        end
        S_STOP: begin
          if (tick) begin
            cnt <= 12'd0; state <= S_IDLE;
          end else cnt <= cnt + 12'd1;
        end
      endcase
    end
  end
endmodule

// UART receiver: 1x sampling at bit centre, falling-edge start detect
module uart_rx (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [11:0] div,
    input  wire        rxd,
    input  wire        fifo_full,
    output wire        fifo_push,
    output wire [7:0]  fifo_data,
    output reg         frame_err,
    output reg         overrun
);
  localparam [1:0] S_IDLE = 2'd0, S_START = 2'd1, S_DATA = 2'd2, S_STOP = 2'd3;

  reg rxd_m, rxd_s, rxd_q;
  always @(posedge clk or negedge rst_n)
    if (!rst_n) {rxd_q, rxd_s, rxd_m} <= 3'b111;
    else        {rxd_q, rxd_s, rxd_m} <= {rxd_s, rxd_m, rxd};

  wire start_edge = rxd_q & ~rxd_s;

  reg [1:0]  state;
  reg [11:0] cnt;
  reg [2:0]  idx;
  reg [7:0]  shreg;

  wire tick      = (cnt >= div - 12'd1);
  wire half_tick = (cnt >= {1'b0, div[11:1]} - 12'd1);

  assign fifo_data = shreg;
  assign fifo_push = (state == S_STOP) && tick && rxd_s && !fifo_full;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      state <= S_IDLE; cnt <= 12'd0; idx <= 3'd0; shreg <= 8'd0;
      frame_err <= 1'b0; overrun <= 1'b0;
    end else begin
      case (state)
        S_IDLE: begin
          cnt <= 12'd0; idx <= 3'd0;
          if (start_edge) state <= S_START;
        end
        S_START: begin
          if (half_tick) begin
            cnt <= 12'd0;
            state <= rxd_s ? S_IDLE : S_DATA;   // glitch -> abort
          end else cnt <= cnt + 12'd1;
        end
        S_DATA: begin
          if (tick) begin
            cnt <= 12'd0;
            shreg <= {rxd_s, shreg[7:1]};
            if (idx == 3'd7) state <= S_STOP;
            else idx <= idx + 3'd1;
          end else cnt <= cnt + 12'd1;
        end
        S_STOP: begin
          if (tick) begin
            cnt <= 12'd0; state <= S_IDLE;
            if (rxd_s) begin
              frame_err <= 1'b0;
              if (fifo_full) overrun <= 1'b1;
            end else frame_err <= 1'b1;
          end else cnt <= cnt + 12'd1;
        end
      endcase
    end
  end
endmodule
