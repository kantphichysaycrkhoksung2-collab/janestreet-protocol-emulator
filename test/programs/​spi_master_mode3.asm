; SPI master, mode 3 (CPOL=1 CPHA=1), MSB first.  Same pins and host protocol as mode 0.
.equ SCLK 8
.equ MOSI 9
.equ CS   10
.equ MISO 8
    SETP CS, 1
    SETP SCLK, 1            ; idle high
.wrap_bot
    PULL
    SETP CS, 0
    DLY  3
byte:
    SETX 7
bit:
    SETP SCLK, 0            ; falling edge: slave shifts out the next MISO bit
    OUT  MOSI, MSB          ; MOSI changes after the falling edge
    DLY  6
    SETP SCLK, 1            ; rising edge: both sides sample
    IN   MISO, MSB
    DLY  4
    JMP  XNZ, bit
    PUSH
    JMP  TXE, done
    PULL
    JMP  ALWAYS, byte
done:
    DLY  3
    SETP CS, 1
.wrap_top
