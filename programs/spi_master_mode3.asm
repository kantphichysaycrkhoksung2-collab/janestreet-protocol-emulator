.wrap_bot 0
.wrap_top 12
    PULL
    SETX 8
loop:
    SETP 1, 1
    OUT 2, MSB
    IN 3
    SETP 1, 0
    JMP XNZ, loop
    PUSH
    HALT
