; Bit-banged UART receiver, 8N1, LSB first.  RX on pin 8 (ui_in[3]).
; Samples each bit in the middle (50 steps per bit), pushes received bytes to RXDATA.
.equ RX 8
.wrap_bot
    WAITP RX, 0             ; wait for start bit
    DLY   71                ; skip to the centre of bit 0
    SETX  7
bit:
    IN    RX                ; sample (LSB first)
    DLY   47
    JMP   XNZ, bit          ; 1+48+1 = 50 steps per bit
    PUSH                    ; ~middle of the stop bit
    WAITP RX, 1             ; wait for the line to go idle
.wrap_top
