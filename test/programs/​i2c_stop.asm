; I2C master: STOP condition (bus must be claimed: SCL low).
.equ SDA 0
.equ SCL 1
    SETD SDA, 0             ; SDA low while SCL is low
    SETD SCL, 1
    WAITP SCL, 1
    DLY  1
    SETD SDA, 1             ; SDA rises while SCL is high = STOP
    DLY  3                  ; bus free time
    HALT
