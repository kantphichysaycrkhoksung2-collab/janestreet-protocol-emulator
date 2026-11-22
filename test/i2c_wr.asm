.wrap_bot 0
.wrap_top 17
    PULL
    SETX 8
bit_loop:
    OUT 0, MSB
    SETP 1, 1
    SETP 1, 0
    JMP XNZ, bit_loop
    SETP 0, 1
    SETP 1, 1
    IN 0
    SETP 1, 0
    JMP OSR7, nack_err
    SETI 0x00
    PUSH
    HALT
nack_err:
    SETI 0x80
    PUSH
    HALT
