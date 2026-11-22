; SPI master, mode 0 (CPOL=0 CPHA=0), MSB first, 8-bit transfers.
; Pins: SCLK = out 8 (uo_out[1]), MOSI = out 9 (uo_out[2]), CS_N = out 10 (uo_out[3]),
;       MISO = in 8 (ui_in[3]).
; Host: queue bytes in TXDATA, run.  Each received byte is pushed to RXDATA.
; CS_N stays low while more bytes are waiting in the TX FIFO, so queue a whole
; transaction before starting the engine.   SCLK = clk / ((CLKDIV+1) * 17 steps).
.equ SCLK 8
.equ MOSI 9
.equ CS   10
.equ MISO 8
    SETP CS, 1
    SETP SCLK, 0
.wrap_bot
    PULL                    ; first byte of a transaction
    SETP CS, 0
    DLY  3                  ; CS setup
byte:
    SETX 7
bit:
    OUT  MOSI, MSB          ; data changes while SCLK is low
    DLY  6                  ; setup
    SETP SCLK, 1            ; rising edge: slave samples MOSI
    IN   MISO, MSB          ; master samples MISO
    DLY  4
    SETP SCLK, 0            ; falling edge
    JMP  XNZ, bit
    PUSH                    ; received byte
    JMP  TXE, done          ; nothing more queued -> end transaction
    PULL
    JMP  ALWAYS, byte
done:
    DLY  3                  ; CS hold
    SETP CS, 1
.wrap_top
