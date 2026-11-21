/*
 * Copyright (c) 2024 Your Name
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module  tt_um_janestreet_emulator  (
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: Input path
    output wire [7:0] uio_out,  // IOs: Output path
    output wire [7:0] uio_oe,   // IOs: Enable path (active high: 0=input, 1=output)
    input  wire       ena,      // always 1 when the design is powered, so you can ignore it
    input  wire       clk,      // clock
    input  wire       rst_n     // reset_n - low to reset
);

  // All output pins must be assigned. If not used, assign to 0.
// SPDX-License-Identifier: Apache-2.0
// tt_um_janestreet_emulator - protocol emulator: host SPI + register file +
//                             PIO-style microcode engine + hardwired UART
//                             (UART and engine share the TX/RX FIFOs)
//
// ---------------------------------------------------------------- pin map
//  ui_in[0]  CS_N  \
//  ui_in[1]  SCK    > host SPI slave, mode 0, 16-bit frames {rw, addr[6:0], data[7:0]}
//  ui_in[2]  MOSI  /
//  ui_in[3..7]      engine/UART input pins 8..12   (UART RX default: pin 8 = ui_in[3])
//  uo_out[0] MISO   (driven 0 while CS_N is high)
//  uo_out[1..7]     engine/UART output pins 8..14  (UART TX default: pin 8 = uo_out[1])
//  uio[7:0]         engine/UART pins 0..7, in and out; direction = OEMASK
//                   (UART TX forces the output enable of its pin when it is uio)
//  Every output bit is driven; anything not used by the host or firmware idles at 0.
//  clk >= 4x SCK (8x recommended).  Default CLK_HZ = 25 MHz.
//
// ----------------------------------------------------------- pin index space
//     inputs : idx 0-7  = uio_in[7:0]     idx 8-12 = ui_in[3..7]
//     outputs: idx 0-7  = uio_out[7:0]    idx 8-14 = uo_out[1..7]
//
// ------------------------------------------------------------ register map
//   00 ID        R   0xE1
//   01 CTRL      RW  [0] run engine  [1] uart_mode (FIFOs belong to UART)
//                    [2] write 1 = soft-clear engine (PC/X/Y/OSR/ISR); reads 0
//                    run self-clears on HALT
//   02 STATUS    R   [0] tx_full [1] tx_empty [2] rx_full [3] rx_empty
//                    [4] uart_tx_busy [5] frame_err [6] overrun(sticky) [7] run
//   03 TXDATA    W   push byte to TX FIFO (UART TX or engine PULL)
//   04 RXDATA    R   head of RX FIFO; the read pops it (0 if empty)
//   05 CLKDIV    RW  engine step = (CLKDIV+1) clk cycles
//   06 BAUD      RW  [1:0] 0=115200 1=57600 2=19200 3=9600 (hardwired UART)
//   07 PINMAP    RW  [3:0] UART TX output pin idx, [7:4] UART RX input pin idx
//                    (reset 0x88: TX on uo_out[1], RX on ui_in[3];
//                     TX idx 15 = disabled, RX idx > 12 = held idle-high)
//   08 OEMASK    RW  uio output enables
//   09 GPIO_LO   RW  output values, pins 0-7
//   0A GPIO_HI   RW  output values, pins 8-14 in [6:0]
//   0B PIN_LO    R   input pins 0-7
//   0C PIN_HI    R   input pins 8-12 in [4:0]
//   0D WRAP_BOT  RW  [4:0]            0E WRAP_TOP  RW  [4:0] (reset 31)
//   0F FLAGS     RW  8 flag bits (engine SETF / host)
//   10 PC        R   engine program counter
//   11 IMEM_ADDR RW  [4:0] instruction write pointer
//   12 IMEM_LO   W   low byte staging
//   13 IMEM_HI   W   writes {HI,LO} to imem[IMEM_ADDR], then IMEM_ADDR++

`default_nettype none

module tt_um_janestreet_emulator #(
    parameter CLK_HZ = 25_000_000   // 12-bit baud divider: fine up to ~39 MHz at 9600
) (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);
  localparam [6:0] A_ID = 7'h00, A_CTRL = 7'h01, A_STATUS = 7'h02, A_TXDATA = 7'h03,
                   A_RXDATA = 7'h04, A_CLKDIV = 7'h05, A_BAUD = 7'h06, A_PINMAP = 7'h07,
                   A_OEMASK = 7'h08, A_GPIO_LO = 7'h09, A_GPIO_HI = 7'h0A, A_PIN_LO = 7'h0B,
                   A_PIN_HI = 7'h0C, A_WRAP_BOT = 7'h0D, A_WRAP_TOP = 7'h0E, A_FLAGS = 7'h0F,
                   A_PC = 7'h10, A_IMEM_ADDR = 7'h11, A_IMEM_LO = 7'h12, A_IMEM_HI = 7'h13;

  // ---------------- reset ----------------
  wire rstn;
  reset_sync u_rst (.clk(clk), .arst_n(rst_n), .srst_n(rstn));

  // ---------------- host SPI ----------------
  wire       h_wr, h_rd, miso;
  wire [6:0] h_waddr, h_cmd_addr;
  wire [7:0] h_wdata;
  reg  [7:0] h_rdval;

  host_spi u_host (
      .clk(clk), .rst_n(rstn),
      .cs_n(ui_in[0]), .sck(ui_in[1]), .mosi(ui_in[2]), .miso(miso),
      .wr_pulse(h_wr), .wr_addr(h_waddr), .wr_data(h_wdata),
      .rd_pulse(h_rd), .cmd_addr(h_cmd_addr), .rd_val(h_rdval)
  );

  // ---------------- registers ----------------
  reg        run, uart_mode, clr_r;
  reg [7:0]  clkdiv, pinmap, oe_mask, flags, imem_lo;
  reg [1:0]  baud_sel;
  reg [14:0] gpio_out;
  reg [4:0]  wrap_bot, wrap_top, imem_addr;

  // engine -> register-file requests
  wire       e_pull, e_push, e_pin_we, e_oe_we, e_flags_we, e_halt, e_pin_val;
  wire [7:0] e_push_data, e_oe_val, e_flags_val;
  wire [3:0] e_pin_idx;
  wire [4:0] pc;

  always @(posedge clk or negedge rstn) begin
    if (!rstn) begin
      run <= 1'b0; uart_mode <= 1'b0; clr_r <= 1'b0;
      clkdiv <= 8'd0; baud_sel <= 2'd0; pinmap <= 8'h88; oe_mask <= 8'd0;
      gpio_out <= 15'd0; wrap_bot <= 5'd0; wrap_top <= 5'd31;
      flags <= 8'd0; imem_addr <= 5'd0; imem_lo <= 8'd0;
    end else begin
      clr_r <= 1'b0;
      if (h_wr) begin
        case (h_waddr)
          A_CTRL:      begin run <= h_wdata[0]; uart_mode <= h_wdata[1]; clr_r <= h_wdata[2]; end
          A_CLKDIV:    clkdiv   <= h_wdata;
          A_BAUD:      baud_sel <= h_wdata[1:0];
          A_PINMAP:    pinmap   <= h_wdata;
          A_OEMASK:    oe_mask  <= h_wdata;
          A_GPIO_LO:   gpio_out[7:0]  <= h_wdata;
          A_GPIO_HI:   gpio_out[14:8] <= h_wdata[6:0];
          A_WRAP_BOT:  wrap_bot <= h_wdata[4:0];
          A_WRAP_TOP:  wrap_top <= h_wdata[4:0];
          A_FLAGS:     flags    <= h_wdata;
          A_IMEM_ADDR: imem_addr <= h_wdata[4:0];
          A_IMEM_LO:   imem_lo  <= h_wdata;
          A_IMEM_HI:   imem_addr <= imem_addr + 5'd1;
          default: ;
        endcase
      end
      // engine requests take priority over host writes in the same cycle
      if (e_pin_we && e_pin_idx != 4'd15) gpio_out[e_pin_idx] <= e_pin_val;
      if (e_oe_we)    oe_mask <= e_oe_val;
      if (e_flags_we) flags   <= e_flags_val;
      if (e_halt)     run     <= 1'b0;
    end
  end

  wire imem_we = h_wr && (h_waddr == A_IMEM_HI);

  // ---------------- baud divider ----------------
  localparam [11:0] D0 = (CLK_HZ + 57600) / 115200;
  localparam [11:0] D1 = (CLK_HZ + 28800) / 57600;
  localparam [11:0] D2 = (CLK_HZ + 9600)  / 19200;
  localparam [11:0] D3 = (CLK_HZ + 4800)  / 9600;

  reg [11:0] div;
  always @* begin
    case (baud_sel)
      2'd0:    div = D0;
      2'd1:    div = D1;
      2'd2:    div = D2;
      default: div = D3;
    endcase
  end

  // ---------------- pins ----------------
  wire [15:0] pin_in = {3'b000, ui_in[7:3], uio_in};

  // ---------------- FIFOs (both sides on clk) + UART ----------------
  wire       tx_wfull, tx_rempty, rx_wfull, rx_rempty;
  wire [7:0] tx_rdata, rx_rdata;
  wire       u_pop, u_push, txd, tx_busy, frame_err, overrun;
  wire [7:0] u_rxdata;

  wire tx_winc = h_wr && (h_waddr == A_TXDATA);
  wire rx_rinc = h_rd && (h_cmd_addr == A_RXDATA);
  wire tx_rinc = uart_mode ? u_pop  : e_pull;
  wire rx_winc = uart_mode ? u_push : e_push;
  wire [7:0] rx_wdata = uart_mode ? u_rxdata : e_push_data;

  async_fifo #(.DSIZE(8), .ASIZE(3)) u_tx_fifo (
      .wclk(clk), .wrst_n(rstn), .winc(tx_winc), .wdata(h_wdata), .wfull(tx_wfull),
      .rclk(clk), .rrst_n(rstn), .rinc(tx_rinc), .rdata(tx_rdata), .rempty(tx_rempty)
  );

  async_fifo #(.DSIZE(8), .ASIZE(3)) u_rx_fifo (
      .wclk(clk), .wrst_n(rstn), .winc(rx_winc), .wdata(rx_wdata), .wfull(rx_wfull),
      .rclk(clk), .rrst_n(rstn), .rinc(rx_rinc), .rdata(rx_rdata), .rempty(rx_rempty)
  );

  // RX pin index > 12 has no pin behind it: hold the line idle-high instead of
  // reading constant 0 (which would look like a permanent start bit).
  wire uart_rxd = uart_mode ? ((pinmap[7:4] > 4'd12) ? 1'b1 : pin_in[pinmap[7:4]]) : 1'b1;

  uart_tx u_tx (
      .clk(clk), .rst_n(rstn), .div(div),
      .fifo_empty(tx_rempty | ~uart_mode), .fifo_data(tx_rdata), .fifo_pop(u_pop),
      .txd(txd), .busy(tx_busy)
  );

  uart_rx u_rx (
      .clk(clk), .rst_n(rstn), .div(div), .rxd(uart_rxd),
      .fifo_full(rx_wfull), .fifo_push(u_push), .fifo_data(u_rxdata),
      .frame_err(frame_err), .overrun(overrun)
  );

  // ---------------- engine ----------------
  mini_engine u_eng (
      .clk(clk), .rst_n(rstn), .run(run), .clr(clr_r),
      .clkdiv(clkdiv), .wrap_bot(wrap_bot), .wrap_top(wrap_top),
      .imem_we(imem_we), .imem_waddr(imem_addr), .imem_wdata({h_wdata, imem_lo}),
      .pin_in(pin_in),
      .fifo_en(~uart_mode), .tx_empty(tx_rempty), .tx_data(tx_rdata), .rx_full(rx_wfull),
      .pull(e_pull), .push(e_push), .push_data(e_push_data),
      .pin_we(e_pin_we), .pin_idx(e_pin_idx), .pin_val(e_pin_val),
      .oe_we(e_oe_we), .oe_val(e_oe_val),
      .flags_we(e_flags_we), .flags_val(e_flags_val),
      .halt(e_halt), .pc_o(pc)
  );

  // ---------------- output pin mux ----------------
  wire [3:0] tx_idx = pinmap[3:0];
  reg [14:0] pout;
  reg [7:0]  oe_eff;
  always @* begin
    pout   = gpio_out;
    oe_eff = oe_mask;
    if (uart_mode && tx_idx != 4'd15) begin
      pout[tx_idx] = txd;
      if (tx_idx < 4'd8) oe_eff[tx_idx] = 1'b1;
    end
  end

  assign uo_out  = {pout[14:8], miso};   // every output bit is driven; unused pins stay 0
  assign uio_out = pout[7:0];
  assign uio_oe  = oe_eff;

  // ---------------- register read mux ----------------
  always @* begin
    case (h_cmd_addr)
      A_ID:        h_rdval = 8'hE1;
      A_CTRL:      h_rdval = {6'b0, uart_mode, run};
      A_STATUS:    h_rdval = {run, overrun, frame_err, tx_busy, rx_rempty, rx_wfull, tx_rempty, tx_wfull};
      A_RXDATA:    h_rdval = rx_rempty ? 8'h00 : rx_rdata;
      A_CLKDIV:    h_rdval = clkdiv;
      A_BAUD:      h_rdval = {6'b0, baud_sel};
      A_PINMAP:    h_rdval = pinmap;
      A_OEMASK:    h_rdval = oe_mask;
      A_GPIO_LO:   h_rdval = gpio_out[7:0];
      A_GPIO_HI:   h_rdval = {1'b0, gpio_out[14:8]};
      A_PIN_LO:    h_rdval = pin_in[7:0];
      A_PIN_HI:    h_rdval = pin_in[15:8];
      A_WRAP_BOT:  h_rdval = {3'b0, wrap_bot};
      A_WRAP_TOP:  h_rdval = {3'b0, wrap_top};
      A_FLAGS:     h_rdval = flags;
      A_PC:        h_rdval = {3'b0, pc};
      A_IMEM_ADDR: h_rdval = {3'b0, imem_addr};
      default:     h_rdval = 8'h00;
    endcase
  end

  wire _unused = &{ena, 1'b0};
endmodule

`default_nettype wire
  