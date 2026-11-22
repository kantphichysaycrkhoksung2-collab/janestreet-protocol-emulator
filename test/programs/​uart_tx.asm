; Bit-banged UART transmitter, 8N1, LSB first.  TX on uio[0] (pin 0).
; Timing: 50 steps per bit  ->  baud = clk / ((CLKDIV+1) * 50)
; Host: write CLKDIV, WRAP_BOT/TOP (from this file), load, push bytes to TXDATA, run.
.equ TX 0
    SETOE 0x01              ; uio[0] output
    SETP  TX, 1             ; idle high
.wrap_bot
    PULL                    ; wait for a byte -> OSR
    SETP  TX, 0             ; start bit
    DLY   47                ; 48 steps
    SETX  7                 ; 8 data bits
bit:
    OUT   TX                ; LSB first
    DLY   47
    JMP   XNZ, bit          ; OUT(1)+DLY(48)+JMP(1) = 50 steps per bit
    SETP  TX, 1             ; stop bit
    DLY   48                ; 50 steps
.wrap_top
