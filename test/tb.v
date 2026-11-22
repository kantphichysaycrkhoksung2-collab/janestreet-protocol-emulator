`default_nettype none
`timescale 1ns / 1ps

module tb ();
  initial begin
    $dumpfile("tb.fst");
    $dumpvars(0, tb);
    #1;
  end

  reg        clk, rst_n, ena;
  reg        cs_n, sck, mosi;      // host SPI port (ui_in[0..2])
  reg  [4:0] pins_in;              // ui_in[7:3]
  reg  [7:0] uio_ext;              // external drive on the bidir pins
  wire [7:0] ui_in = {pins_in, mosi, sck, cs_n};
  wire [7:0] uo_out, uio_out, uio_oe;
  // pad = chip drive where output-enabled, external drive/pull-up elsewhere
  wire [7:0] uio_in = (uio_out & uio_oe) | (uio_ext & ~uio_oe);

  tt_um_janestreet_emulator user_project (
      .ui_in  (ui_in),
      .uo_out (uo_out),
      .uio_in (uio_in),
      .uio_out(uio_out),
      .uio_oe (uio_oe),
      .ena    (ena),
      .clk    (clk),
      .rst_n  (rst_n)
  );
endmodule
