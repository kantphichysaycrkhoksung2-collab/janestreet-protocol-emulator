// SPI mode-0 slave, MSB first, 16-bit frames: {rw, addr[6:0], data[7:0]}
//   rw = 1 : read  (data returned on MISO during the last 8 bits)
//   rw = 0 : write (data taken from MOSI)
// Several 16-bit frames may follow within one CS_N low period.
// Everything is sampled in the clk domain, so clk must be >= 4x SCK
// (8x or more recommended).

`default_nettype none

module host_spi (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       cs_n,
    input  wire       sck,
    input  wire       mosi,
    output wire       miso,
    output reg        wr_pulse,   // 1 clk after a complete write frame
    output reg  [6:0] wr_addr,
    output reg  [7:0] wr_data,
    output reg        rd_pulse,   // 1 clk after a complete read frame (pop side effects)
    output reg  [6:0] cmd_addr,   // address of the frame in progress / last frame
    input  wire [7:0] rd_val      // combinational register read for cmd_addr
);
  reg cs_m, cs_s, sck_m, sck_s, sck_q, mosi_m, mosi_s;
  reg [3:0] cnt;
  reg [7:0] shin, msh;
  reg       cmd_rd, miso_o;

  wire rise =  sck_s & ~sck_q;
  wire fall = ~sck_s &  sck_q;

  assign miso = miso_o;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      cs_m <= 1'b1; cs_s <= 1'b1;
      sck_m <= 1'b0; sck_s <= 1'b0; sck_q <= 1'b0;
      mosi_m <= 1'b0; mosi_s <= 1'b0;
      cnt <= 4'd0; shin <= 8'd0; msh <= 8'd0;
      cmd_rd <= 1'b0; cmd_addr <= 7'd0; miso_o <= 1'b0;
      wr_pulse <= 1'b0; rd_pulse <= 1'b0; wr_addr <= 7'd0; wr_data <= 8'd0;
    end else begin
      cs_m <= cs_n;  cs_s <= cs_m;
      sck_m <= sck;  sck_s <= sck_m;  sck_q <= sck_s;
      mosi_m <= mosi; mosi_s <= mosi_m;

      wr_pulse <= 1'b0;
      rd_pulse <= 1'b0;

      if (cs_s) begin
        cnt <= 4'd0;
        miso_o <= 1'b0;
      end else begin
        if (rise) begin
          shin <= {shin[6:0], mosi_s};
          cnt  <= cnt + 4'd1;
          if (cnt == 4'd7) begin
            cmd_rd   <= shin[6];
            cmd_addr <= {shin[5:0], mosi_s};
          end
          if (cnt == 4'd15) begin
            if (cmd_rd) rd_pulse <= 1'b1;
            else begin
              wr_pulse <= 1'b1;
              wr_addr  <= cmd_addr;
              wr_data  <= {shin[6:0], mosi_s};
            end
          end
        end
        if (fall) begin
          if (cnt == 4'd8) begin
            miso_o <= rd_val[7];
            msh    <= {rd_val[6:0], 1'b0};
          end else if (cnt > 4'd8) begin
            miso_o <= msh[7];
            msh    <= {msh[6:0], 1'b0};
          end
        end
      end
    end
  end
endmodule
