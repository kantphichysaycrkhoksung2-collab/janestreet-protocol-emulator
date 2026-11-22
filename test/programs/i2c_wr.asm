; I2C master: (repeated) START + send bytes.  SDA = uio[0] (pin 0), SCL = uio[1] (pin 1),
; both open-drain: the engine only ever drives them low or releases them (SETD / OUT od),
; clock stretching is honoured by WAITP SCL.
;
; TX FIFO: first byte = (7-bit address << 1) | R/W, then data bytes. Natural bit order.
; For every byte sent one status byte is pushed to RXDATA: 0x00 = ACK, 0x80 = NACK.
; On NACK the transaction is aborted and the rest of the TX FIFO is flushed.
; Ends with HALT; the bus stays claimed (SCL low) so that another program can continue
; (i2c_rd.asm, i2c_stop.asm, or i2c_wr.asm again for a repeated START).
; 5 steps per SCL period: SCL = clk / ((CLKDIV+1) * 5).
.equ SDA 0
.equ SCL 1
    PULL                    ; address byte -> OSR
    SETD SDA, 1             ; make sure both lines are released (repeated START prep)
    SETD SCL, 1
    WAITP SCL, 1
    DLY  1
    SETD SDA, 0             ; START: SDA falls while SCL is high
    DLY  1
    SETD SCL, 0
byte:
    SETX 7
bit:
    OUT  SDA, MSB, OD       ; SDA = OSR[7] (drive low or release)
    SETD SCL, 1
    WAITP SCL, 1            ; clock stretching
    SETD SCL, 0
    JMP  XNZ, bit
    SETD SDA, 1             ; release SDA for the ACK slot
    SETD SCL, 1
    WAITP SCL, 1
    SETI 0
    IN   SDA                ; ISR[7] = ACK bit (0 = ACK)
    PUSH                    ; report 0x00 / 0x80
    JMPH SDA, nack          ; SDA still high -> NACK
    SETD SCL, 0
    JMP  TXE, done
    PULL
    JMP  ALWAYS, byte
nack:
    SETD SCL, 0
flush:
    JMP  TXE, done
    PULL
    JMP  ALWAYS, flush
done:
    HALT
