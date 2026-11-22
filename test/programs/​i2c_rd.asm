; I2C master: read bytes.  Continues after i2c_wr.asm sent an address byte with R/W=1
; (bus claimed, SCL low).  TX FIFO: one dummy byte per byte to read.
; Every received byte is pushed to RXDATA (MSB first, natural order).
; All bytes are ACKed except the last one (NACK), then HALT; use i2c_stop.asm next.
.equ SDA 0
.equ SCL 1
rbyte:
    PULL                    ; consume one token
    SETX 7
rbit:
    SETD SCL, 1
    WAITP SCL, 1            ; clock stretching
    IN   SDA, MSB
    SETD SCL, 0
    JMP  XNZ, rbit
    PUSH
    JMP  TXE, nackbyte      ; no more tokens: this was the last byte
    SETD SDA, 0             ; ACK
    JMP  ALWAYS, ackclk
nackbyte:
    SETD SDA, 1             ; NACK (released)
ackclk:
    SETD SCL, 1
    WAITP SCL, 1
    SETD SCL, 0
    SETD SDA, 1             ; release SDA
    JMP  TXE, done
    JMP  ALWAYS, rbyte
done:
    HALT
