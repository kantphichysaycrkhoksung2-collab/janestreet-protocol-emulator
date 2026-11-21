// SPDX-License-Identifier: Apache-2.0
// Mini microcode engine (tiny PIO-style).
//
// 32 x 16-bit instruction memory, written by the host. One instruction per
// "step"; a step happens every (clkdiv+1) clk cycles while `run` is high.
//
// Instruction word: [15:12] op   [11:8] A (pin idx / condition)   [7:0] imm
//
//  op  mnemonic  effect
//   0  DLY  n     idle n extra steps (instruction takes n+1 steps)
//   1  SETP p,v   pin p <= imm[0]
//   2  SETOE m    uio output-enable mask <= imm[7:0]
//   3  WAITP p,v  stall until pin p == imm[0]
//   4  JMP c,t    if cond(c) pc <= imm[4:0]   c: 0 always, 1 X!=0 (X--),
//                                              2 Y!=0 (Y--), 3 TX FIFO empty
//   5  PULL       stall until TX FIFO has data, OSR <= byte (pops FIFO)
//   6  PUSH       stall until RX FIFO has room, push ISR
//   7  OUT p      pin p <= OSR[0]; OSR >>= 1              (LSB first)
//   8  IN p       ISR <= {pin p, ISR[7:1]}                (LSB first)
//   9  SETX n     X <= imm       10 SETY n   Y <= imm      11 SETO n  OSR <= imm
//  12  SETF n     FLAGS <= imm (host visible)
//  13  HALT       clears CTRL.run
//  14,15 NOP
//
// Zero-overhead loop: after executing the instruction at wrap_top the PC
// goes to wrap_bot (instead of wrap_top+1). A taken JMP overrides this.
//
// Pin index p: input  0-7 uio_in[7:0], 8-12 ui_in[3..7]
//              output 0-7 uio_out[7:0], 8-14 uo_out[1..7]

`default_nettype none

module mini_engine (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        run,
    input  wire        clr,          // 1-cycle pulse: reset PC/X/Y/OSR/ISR/delay
    input  wire [7:0]  clkdiv,
    input  wire [4:0]  wrap_bot,
    input  wire [4:0]  wrap_top,
    // instruction memory write port
    input  wire        imem_we,
    input  wire [4:0]  imem_waddr,
    input  wire [15:0] imem_wdata,
    // pins
    input  wire [15:0] pin_in,
    // FIFO side
    input  wire        fifo_en,      // 0 = FIFOs owned by the hardwired UART
    input  wire        tx_empty,
    input  wire [7:0]  tx_data,
    input  wire        rx_full,
    output wire        pull,
    output wire        push,
    output wire [7:0]  push_data,
    // register-file requests
    output wire        pin_we,
    output wire [3:0]  pin_idx,
    output wire        pin_val,
    output wire        oe_we,
    output wire [7:0]  oe_val,
    output wire        flags_we,
    output wire [7:0]  flags_val,
    output wire        halt,
    output wire [4:0]  pc_o
);
  localparam [3:0] OP_DLY = 4'd0,  OP_SETP = 4'd1, OP_SETOE = 4'd2, OP_WAITP = 4'd3,
                   OP_JMP = 4'd4,  OP_PULL = 4'd5, OP_PUSH  = 4'd6, OP_OUT   = 4'd7,
                   OP_IN  = 4'd8,  OP_SETX = 4'd9, OP_SETY  = 4'd10, OP_SETO = 4'd11,
                   OP_SETF = 4'd12, OP_HALT = 4'd13;

  reg [15:0] imem [0:31];
  always @(posedge clk) if (imem_we) imem[imem_waddr] <= imem_wdata;

  reg [4:0] pc;
  reg [7:0] x, y, osr, isr, dly, divcnt;

  wire step = run & (divcnt >= clkdiv);

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n)            divcnt <= 8'd0;
    else if (!run || step) divcnt <= 8'd0;
    else                   divcnt <= divcnt + 8'd1;
  end

  wire [15:0] instr = imem[pc];
  wire [3:0]  op    = instr[15:12];
  wire [3:0]  a     = instr[11:8];
  wire [7:0]  imm   = instr[7:0];
  wire        pin_v = pin_in[a];

  wire jmp_taken = (a == 4'd0) | ((a == 4'd1) & (x != 8'd0)) |
                   ((a == 4'd2) & (y != 8'd0)) | ((a == 4'd3) & tx_empty);

  reg stall;
  always @* begin
    case (op)
      OP_WAITP: stall = (pin_v != imm[0]);
      OP_PULL:  stall = tx_empty | ~fifo_en;
      OP_PUSH:  stall = rx_full  | ~fifo_en;
      default:  stall = 1'b0;
    endcase
  end

  wire fire = step & (dly == 8'd0) & ~stall;

  assign pull      = fire & (op == OP_PULL);
  assign push      = fire & (op == OP_PUSH);
  assign push_data = isr;
  assign pin_we    = fire & ((op == OP_SETP) | (op == OP_OUT));
  assign pin_idx   = a;
  assign pin_val   = (op == OP_SETP) ? imm[0] : osr[0];
  assign oe_we     = fire & (op == OP_SETOE);
  assign oe_val    = imm;
  assign flags_we  = fire & (op == OP_SETF);
  assign flags_val = imm;
  assign halt      = fire & (op == OP_HALT);
  assign pc_o      = pc;

  wire [4:0] pc_inc = (pc == wrap_top) ? wrap_bot : pc + 5'd1;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      pc <= 5'd0; x <= 8'd0; y <= 8'd0; osr <= 8'd0; isr <= 8'd0; dly <= 8'd0;
    end else if (clr) begin
      pc <= 5'd0; x <= 8'd0; y <= 8'd0; osr <= 8'd0; isr <= 8'd0; dly <= 8'd0;
    end else if (step) begin
      if (dly != 8'd0) begin
        dly <= dly - 8'd1;
      end else if (!stall) begin
        pc <= (op == OP_JMP && jmp_taken) ? imm[4:0] : pc_inc;
        case (op)
          OP_DLY:  dly <= imm;
          OP_JMP:  begin
                     if (a == 4'd1) x <= x - 8'd1;
                     if (a == 4'd2) y <= y - 8'd1;
                   end
          OP_PULL: osr <= tx_data;
          OP_OUT:  osr <= {1'b0, osr[7:1]};
          OP_IN:   isr <= {pin_v, isr[7:1]};
          OP_SETX: x   <= imm;
          OP_SETY: y   <= imm;
          OP_SETO: osr <= imm;
          default: ;
        endcase
      end
    end
  end
endmodule
